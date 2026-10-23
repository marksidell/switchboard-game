"""The trunk 8 ATA's registration, for the page's health column (mqtt.md §6.3).

The Grandstream HT80x V2 that feeds trunk 8 (trunk_circuit.md §4.5) is the
public trunk: outside callers reach the switchboard through its FXS port 1
only while that port is registered with the SIP provider. Its web interface
has a JSON API, the one its own pages use:

  POST /cgi-bin/dologin         username=…&P2=<password, base64>
       → {"response": "success", "body": {"session_token": "…", …}}
  POST /cgi-bin/api.values.get  request=P4921&session_token=…
       → {"response": "success", "body": {"P4921": "Registered"}}

It logs in as the ATA's read-only `viewer` account: the ATA keeps one session
per account, so logging in as `admin` would log the admin out of the web page
on every look.

P4921 is FXS 1's registration, "Registered" or "Not Registered". Read from
the firmware's Status page script, 2026-10-23, not from a manual.

The ATA's certificate is issued by Grandstream's CA to its MAC address, not to
its name, so it is pinned: the certificate itself, saved in host/etc/sbgame/,
is the only one trusted.

`sbgame-netcheck` runs this every 10s and publishes, retained:

  host/public_trunk          "registered", "disconnected", "offline" or "error"
  host/public_trunk/checked  host Unix time of the last look
"""

from __future__ import annotations

import base64
import http.cookiejar
import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("ata")

HOST = "switchboard.sidell.org"
CRED_FILE = "/etc/sbgame/ata.cred"
CERT_FILE = "/etc/sbgame/ata-cert.pem"
REG = "P4921"                   # FXS 1 registration
TIMEOUT = 5.0
LOGIN_BACKOFF = 300.0           # after a refused login: the ATA locks out on repeats

REGISTERED = "registered"
DISCONNECTED = "disconnected"
OFFLINE = "offline"
ERROR = "error"


class Refused(Exception):
    """The ATA answered, but not with what was asked for."""


def read_cred(path: str) -> tuple[str, str]:
    """Username on the first line, password on the second."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if len(lines) < 2 or not lines[0].strip():
        raise Refused(f"{path}: want the username, then the password, one per line")
    return lines[0].strip(), lines[1]


def pinned(cert_file: str) -> ssl.SSLContext:
    """A context that trusts the one certificate in cert_file and nothing else."""
    ctx = ssl.create_default_context(cafile=cert_file)
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    ctx.check_hostname = False          # named for its MAC; the pin is the check
    return ctx


class Ata:
    """One login kept between looks, renewed when the ATA stops taking it."""

    def __init__(self, host: str = HOST, cred_file: str = CRED_FILE,
                 cert_file: str = CERT_FILE) -> None:
        self.base = f"https://{host}"
        self.cred_file = cred_file
        self.cert_file = cert_file
        self.token = ""
        self.refused_at = 0.0           # monotonic time of the last refused login
        self.opener = None
        self.last = ""                  # the last state, logged when it changes

    def post(self, path: str, data: dict[str, str]) -> dict:
        if self.opener is None:
            self.opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=pinned(self.cert_file)),
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        req = urllib.request.Request(
            self.base + path, data=urllib.parse.urlencode(data).encode(),
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.base + "/"})
        with self.opener.open(req, timeout=TIMEOUT) as r:
            try:
                return json.loads(r.read(65536))
            except ValueError:
                raise Refused(f"{path}: not JSON") from None

    def login(self) -> None:
        if self.refused_at and time.monotonic() - self.refused_at < LOGIN_BACKOFF:
            raise Refused("login refused; waiting before trying again")
        user, password = read_cred(self.cred_file)
        # The login page sends the password base64-encoded (js-base64's encode).
        p2 = base64.b64encode(password.encode("utf-8")).decode("ascii")
        r = self.post("/cgi-bin/dologin", {"username": user, "P2": p2})
        body = r.get("body")
        token = body.get("session_token") if isinstance(body, dict) else None
        if r.get("response") != "success" or not token:
            self.refused_at = time.monotonic()
            raise Refused(f"login refused: {body!r}")
        self.refused_at = 0.0
        self.token = token

    def registration(self) -> str:
        """P4921 as the ATA reports it. Raises OSError or Refused."""
        r: dict = {}
        for _ in (0, 1):
            if not self.token:
                self.login()
            r = self.post("/cgi-bin/api.values.get",
                          {"request": REG, "session_token": self.token})
            body = r.get("body")
            if r.get("response") == "success" and isinstance(body, dict) and REG in body:
                return str(body[REG])
            self.token = ""             # expired, most likely: log in once more
        raise Refused(f"values.get: {r!r}")

    def state(self) -> str:
        """One of REGISTERED, DISCONNECTED, OFFLINE, ERROR."""
        why = ""
        try:
            reg = self.registration()
            s = REGISTERED if reg == "Registered" else DISCONNECTED
            why = reg
        except (Refused, OSError) as e:
            s = OFFLINE if unreachable(e) else ERROR
            why = str(e)
        if s != self.last:
            log.info("public trunk %s (%s)", s, why)
            self.last = s
        return s


def unreachable(e: Exception) -> bool:
    """The ATA not answering at all — no name, no route, refused, no answer in
    time — as against a fault once it has: a bad certificate, an HTTP error,
    a refused login, a missing credentials file."""
    if isinstance(e, urllib.error.HTTPError):
        return False
    if isinstance(e, urllib.error.URLError):
        e = e.reason if isinstance(e.reason, Exception) else OSError(str(e.reason))
    if isinstance(e, (ssl.SSLError, ssl.CertificateError, FileNotFoundError,
                      PermissionError, Refused)):
        return False
    return isinstance(e, OSError)

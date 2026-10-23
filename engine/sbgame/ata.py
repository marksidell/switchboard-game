"""The trunk 8 ATA's registration, for the page's health column (mqtt.md §6.3).

The Grandstream HT80x V2 that feeds trunk 8 (trunk_circuit.md §4.5) is the
public trunk: outside callers reach the switchboard through its FXS port 1
only while that port is registered with the SIP provider.

It is asked over SSH, not through its web interface (mqtt.md Rev 42). The web
interface keeps one session for the whole device, whatever the account, so a
look every 10s logged anyone out of its pages; an SSH session does not. Its
command shell takes no remote command, so `status` and `exit` go in on stdin,
and the answer has a line

    Port 1: On Hook<TAB>Registered          ("Not Registered" when not)

SSH there takes the admin account only. The password comes from the
credentials file through SSH_ASKPASS, which is this same program's console
script run with ASKPASS_ENV set (`askpass()`), so it is never on a command
line or in the environment. The ATA's host key is pinned in a known-hosts file.

`sbgame-netcheck` runs this every 10s and publishes, retained:

  host/public_trunk          "registered", "disconnected", "offline" or "error"
  host/public_trunk/checked  host Unix time of the last look
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("ata")

HOST = "switchboard.sidell.org"
CRED_FILE = "/etc/sbgame/ata.cred"
KNOWN_HOSTS = "/etc/sbgame/ata-known_hosts"
CONNECT_TIMEOUT = 5             # seconds, to reach the ATA
TIMEOUT = 15.0                  # seconds, for the whole session
LOGIN_BACKOFF = 300.0           # after a refused login: the ATA locks out on repeats
ASKPASS_ENV = "SBGAME_ATA_ASKPASS"  # set: print the password from this file

REGISTERED = "registered"
DISCONNECTED = "disconnected"
OFFLINE = "offline"
ERROR = "error"

PORT1 = re.compile(r"^\s*Port 1:\s*(.*?)\s*$", re.M)
# ssh's own words when the ATA does not answer at all.
UNREACHABLE = ("Could not resolve hostname", "Connection timed out", "Connection refused",
               "No route to host", "Network is unreachable", "Host is down")
REFUSED = ("Permission denied", "Too many authentication failures")


class Refused(Exception):
    """The ATA answered, but not with what was asked for."""


def read_cred(path: str) -> tuple[str, str]:
    """Username on the first line, password on the second."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if len(lines) < 2 or not lines[0].strip():
        raise Refused(f"{path}: want the username, then the password, one per line")
    return lines[0].strip(), lines[1]


def askpass() -> int:
    """SSH_ASKPASS: the password, from the file named in ASKPASS_ENV."""
    print(read_cred(os.environ[ASKPASS_ENV])[1])
    return 0


def parse(text: str) -> tuple[str, str]:
    """(REGISTERED or DISCONNECTED, the Port 1 line) from `status`."""
    m = PORT1.search(text)
    if not m:
        raise Refused("no 'Port 1:' line in status")
    line = m.group(1)
    ok = "Registered" in line and "Not Registered" not in line
    return (REGISTERED if ok else DISCONNECTED), line


def askpass_program() -> str:
    """This program's console script, beside the interpreter in the venv."""
    return str(Path(sys.executable).with_name("sbgame-netcheck"))


class Ata:
    """One SSH session per look."""

    def __init__(self, host: str = HOST, cred_file: str = CRED_FILE,
                 known_hosts: str = KNOWN_HOSTS) -> None:
        self.host = host
        self.cred_file = cred_file
        self.known_hosts = known_hosts
        self.refused_at = 0.0           # monotonic time of the last refused login
        self.last = ""                  # the last state, logged when it changes

    def command(self, user: str) -> list[str]:
        return ["ssh", "-T", "-F", "/dev/null",
                "-o", f"UserKnownHostsFile={self.known_hosts}",
                "-o", "GlobalKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=yes",
                "-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password",
                "-o", "NumberOfPasswordPrompts=1", "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
                "-o", "LogLevel=ERROR", f"{user}@{self.host}"]

    def run(self, cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, input="status\nexit\n", env=env, capture_output=True,
                              text=True, timeout=TIMEOUT)

    def status(self) -> str:
        """The ATA's `status` text. Raises OSError (unreachable) or Refused."""
        if self.refused_at and time.monotonic() - self.refused_at < LOGIN_BACKOFF:
            raise Refused("login refused; waiting before trying again")
        try:
            user, _ = read_cred(self.cred_file)
        except OSError as e:            # not the ATA's fault: not offline
            raise Refused(str(e)) from None
        env = dict(os.environ, SSH_ASKPASS=askpass_program(), SSH_ASKPASS_REQUIRE="force",
                   DISPLAY=":0", **{ASKPASS_ENV: self.cred_file})
        try:
            r = self.run(self.command(user), env)
        except subprocess.TimeoutExpired:
            raise Refused(f"no answer to status in {TIMEOUT:.0f}s") from None
        if r.returncode == 0:
            return r.stdout
        lines = r.stderr.strip().splitlines()
        err = lines[-1] if lines else f"ssh exit {r.returncode}"
        if any(s in r.stderr for s in UNREACHABLE):
            raise OSError(err)
        if any(s in r.stderr for s in REFUSED):
            self.refused_at = time.monotonic()
        raise Refused(err)

    def state(self) -> str:
        """One of REGISTERED, DISCONNECTED, OFFLINE, ERROR."""
        try:
            s, why = parse(self.status())
        except OSError as e:
            s, why = OFFLINE, str(e)
        except Refused as e:
            s, why = ERROR, str(e)
        if s != self.last:
            log.info("public trunk %s (%s)", s, why)
            self.last = s
        return s

"""The public-address service (mqtt.md §6.3), with no broker and no network.

    cd engine && PYTHONPATH=.:tests ./.venv/bin/python tests/test_netcheck.py
"""

import asyncio
import socket
import ssl
import sys
import tempfile
import time
import urllib.error

from sbgame import ata, netcheck
from sbgame.netcheck import Looker, parse, why

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<58} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


async def main() -> int:
    answers: list = ["203.0.113.7\n", OSError("no route"), "2001:db8::1", "<html>"]

    def look() -> str:
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return parse(a)

    up = [True]

    print("== lookups")
    lk = Looker(look, lambda: up[0])
    check(lk.due(False) and lk.due(True), "due at once before any lookup")
    out = dict(await lk.check())
    check(out["host/public_ip"] == "203.0.113.7" and out["host/public_ip/error"] == "",
          "a good one: the address, no error")
    check(abs(int(out["host/public_ip/checked"]) - time.time()) < 2, "checked is host Unix time")
    check(not lk.due(False) and not lk.due(True), "not due again at once, asked or not")
    lk.last -= netcheck.LEAST
    check(lk.due(True) and not lk.due(False), "asked: due after 5s; by itself: after 5 min")
    out = dict(await lk.check())
    check(out["host/public_ip"] == "203.0.113.7" and out["host/public_ip/error"] == "no route",
          "a failure keeps the last address and says why")
    out = dict(await lk.check())
    check(out["host/public_ip"] == "2001:db8::1" and out["host/public_ip/error"] == "",
          "IPv6 is an address too")
    answers.insert(0, OSError("no route"))
    up[0] = False
    out = dict(await lk.check())
    check(out["host/public_ip/error"] == "offline", "a failure with no internet: offline")
    up[0] = True
    out = dict(await lk.check())
    check(out["host/public_ip"] == "2001:db8::1" and out["host/public_ip/error"] == "not an address",
          "a page that is not an address is a failure")

    print("\n== why, in a word")
    check(why(urllib.error.HTTPError("u", 503, "x", {}, None)) == "HTTP 503", "HTTP status")
    check(why(urllib.error.URLError(socket.timeout("timed out"))) == "timed out", "timeout")
    check(why(urllib.error.URLError(socket.gaierror(-3, "Temporary failure in name resolution")))
          .endswith("name resolution"), "no DNS")

    print("\n== the public trunk (ata.py)")
    cred = tempfile.NamedTemporaryFile("w", suffix=".cred", delete=False)
    cred.write("admin\nsecret\n")
    cred.close()
    replies: list = []
    sent: list = []

    def post(path, data):
        sent.append((path, dict(data)))
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    a = ata.Ata("ata.test", cred.name)
    a.post = post
    login_ok = {"response": "success", "body": {"session_token": "t1"}}
    replies[:] = [login_ok, {"response": "success", "body": {"P4921": "Registered"}}]
    check(a.state() == "registered", "Registered: registered")
    check(sent[0] == ("/cgi-bin/dologin", {"username": "admin", "P2": "c2VjcmV0"}),
          "logs in with the file's username and password, base64")
    check(sent[1][1] == {"request": "P4921", "session_token": "t1"}, "asks for P4921 with the token")
    sent.clear()
    replies[:] = [{"response": "success", "body": {"P4921": "Not Registered"}}]
    check(a.state() == "disconnected" and len(sent) == 1,
          "Not Registered: disconnected, on the same login")
    replies[:] = [{"response": "error", "body": "session expired"}, login_ok,
                  {"response": "success", "body": {"P4921": "Registered"}}]
    check(a.state() == "registered", "an expired session: logs in again")
    replies[:] = [urllib.error.URLError(TimeoutError("timed out"))]
    check(a.state() == "offline", "no answer: offline")
    replies[:] = [urllib.error.URLError(ConnectionRefusedError(111, "refused"))]
    check(a.state() == "offline", "refused: offline")
    replies[:] = [urllib.error.URLError(ssl.SSLCertVerificationError("bad cert"))]
    check(a.state() == "error", "a certificate that is not the pinned one: error")
    replies[:] = [urllib.error.HTTPError("u", 500, "x", {}, None)]
    check(a.state() == "error", "HTTP 500: error")
    a.token = ""
    sent.clear()
    replies[:] = [{"response": "error", "body": "wrong password"}]
    check(a.state() == "error", "a refused login: error")
    check(a.state() == "error" and len(sent) == 1, "and no second login for 5 min")
    b = ata.Ata("ata.test", cred.name + ".missing")
    b.post = post
    check(b.state() == "error", "no credentials file: error")

    print("\nFAILURES" if failures else "\nall ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

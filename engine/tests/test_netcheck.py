"""The public-address service (mqtt.md §6.3), with no broker and no network.

    cd engine && PYTHONPATH=.:tests ./.venv/bin/python tests/test_netcheck.py
"""

import asyncio
import contextlib
import io
import os
import socket
import subprocess
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
    STATUS = ("Grandstream HT801V2 Command Shell\nHT801V2> Product Model: HT801V2\n"
              "Port Status:\n    Port 1: On Hook\t{}\nSystem uptime: 7934\nHT801V2> ")

    def run(cmd, env):
        sent.append((cmd, env))
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        code, out, err = r
        return subprocess.CompletedProcess(cmd, code, out, err)

    a = ata.Ata("ata.test", cred.name, "/k")
    a.run = run
    replies[:] = [(0, STATUS.format("Registered"), "")]
    check(a.state() == "registered", "Registered: registered")
    cmd, env = sent[0]
    check(cmd[-1] == "admin@ata.test" and "StrictHostKeyChecking=yes" in cmd
          and "UserKnownHostsFile=/k" in cmd, "ssh as the file's user, host key pinned")
    check("secret" not in " ".join(cmd) and "secret" not in "".join(env.values()),
          "the password is on no command line and in no environment")
    check(env[ata.ASKPASS_ENV] == cred.name and env["SSH_ASKPASS_REQUIRE"] == "force",
          "askpass reads it from the file")
    os.environ[ata.ASKPASS_ENV] = cred.name
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ata.askpass()
    del os.environ[ata.ASKPASS_ENV]
    check(out.getvalue() == "secret\n", "askpass prints the password")
    replies[:] = [(0, STATUS.format("Not Registered"), "")]
    check(a.state() == "disconnected", "Not Registered: disconnected")
    replies[:] = [(255, "", "ssh: connect to host ata.test port 22: Connection timed out\n")]
    check(a.state() == "offline", "no answer: offline")
    replies[:] = [(255, "", "ssh: Could not resolve hostname ata.test: Name or service not known\n")]
    check(a.state() == "offline", "no name: offline")
    replies[:] = [(255, "", "ssh: connect to host ata.test port 22: Connection refused\n")]
    check(a.state() == "offline", "refused: offline")
    replies[:] = [(255, "", "Host key verification failed.\n")]
    check(a.state() == "error", "a host key that is not the pinned one: error")
    replies[:] = [(0, "HT801V2> ", "")]
    check(a.state() == "error", "no Port 1 line: error")
    replies[:] = [subprocess.TimeoutExpired("ssh", 15)]
    check(a.state() == "error", "a session that hangs: error")
    sent.clear()
    replies[:] = [(255, "", "admin@ata.test: Permission denied (publickey,password).\n")]
    check(a.state() == "error", "a refused login: error")
    check(a.state() == "error" and len(sent) == 1, "and no second login for 5 min")
    b = ata.Ata("ata.test", cred.name + ".missing", "/k")
    b.run = run
    check(b.state() == "error", "no credentials file: error")

    print("\nFAILURES" if failures else "\nall ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""The public-address service (mqtt.md §6.3), with no broker and no network.

    cd engine && PYTHONPATH=.:tests ./.venv/bin/python tests/test_publicip.py
"""

import asyncio
import socket
import sys
import time
import urllib.error

from sbgame import publicip
from sbgame.publicip import Looker, parse, why

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

    print("== lookups")
    lk = Looker(look)
    check(lk.due(False) and lk.due(True), "due at once before any lookup")
    out = dict(await lk.check())
    check(out["host/public_ip"] == "203.0.113.7" and out["host/public_ip/error"] == "",
          "a good one: the address, no error")
    check(abs(int(out["host/public_ip/checked"]) - time.time()) < 2, "checked is host Unix time")
    check(not lk.due(False) and not lk.due(True), "not due again at once, asked or not")
    lk.last -= publicip.LEAST
    check(lk.due(True) and not lk.due(False), "asked: due after 5s; by itself: after 5 min")
    out = dict(await lk.check())
    check(out["host/public_ip"] == "203.0.113.7" and out["host/public_ip/error"] == "no route",
          "a failure keeps the last address and says why")
    out = dict(await lk.check())
    check(out["host/public_ip"] == "2001:db8::1" and out["host/public_ip/error"] == "",
          "IPv6 is an address too")
    out = dict(await lk.check())
    check(out["host/public_ip"] == "2001:db8::1" and out["host/public_ip/error"] == "not an address",
          "a page that is not an address is a failure")

    print("\n== why, in a word")
    check(why(urllib.error.HTTPError("u", 503, "x", {}, None)) == "HTTP 503", "HTTP status")
    check(why(urllib.error.URLError(socket.timeout("timed out"))) == "timed out", "timeout")
    check(why(urllib.error.URLError(socket.gaierror(-3, "Temporary failure in name resolution")))
          .endswith("name resolution"), "no DNS")

    print("\nFAILURES" if failures else "\nall ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""sbgame-netcheck: the host's public address and the public trunk, for the
page's health column (mqtt.md §6.3). `sbgame-publicip` until mqtt.md Rev 41.

A service of its own, not part of the game program: finding the address means
asking a server outside the house, and the game makes no network calls during
a session (CLAUDE.md). This does, every five minutes and when the page asks,
and a lookup that fails touches nothing but the line on the page.

Publishes, retained:

  host/public_ip           the address the last good lookup found, "" before one
  host/public_ip/checked   host Unix time of the last lookup, good or not
  host/public_ip/error     "" if it was good, "offline" if the internet cannot
                           be reached at all, else why not

and takes `host/public_ip/check/set` (any payload, QoS 0) to look now.

It also looks every 10s at the trunk 8 ATA's registration, `host/public_trunk`
(`ata.py`): another look at something outside the game, on the same account.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import os
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import aiomqtt

from . import ata

log = logging.getLogger("netcheck")

PREFIX = "sbgame/"
USERNAME = "sbgame-host"
PASSWORD_FILE = "/etc/sbgame/mqtt-host.pass"
CLIENT_ID = "sbgame-netcheck"
URL = "https://checkip.amazonaws.com/"
EVERY = 300.0           # seconds between lookups
TIMEOUT = 10.0          # for one lookup
LEAST = 5.0             # seconds between lookups the page asks for
TRUNK_EVERY = 10.0      # seconds between looks at the ATA
# After a failed lookup, whether the internet is there at all: a TCP connect to
# either of these, by number, so a DNS fault alone does not read as offline.
PROBES = (("1.1.1.1", 443), ("8.8.8.8", 443))
PROBE_TIMEOUT = 3.0
OFFLINE = "offline"


def lookup(url: str = URL, timeout: float = TIMEOUT) -> str:
    """The address as the server sees it. Raises ValueError or OSError."""
    req = urllib.request.Request(url, headers={"User-Agent": CLIENT_ID})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse(r.read(64).decode("ascii", "replace"))


def parse(text: str) -> str:
    """The server's answer as an address. ValueError if it is not one."""
    return str(ipaddress.ip_address(text.strip()))


def online(probes=PROBES, timeout: float = PROBE_TIMEOUT) -> bool:
    """True if any probe accepts a connection."""
    for host, port in probes:
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except OSError:
            pass
    return False


def why(e: Exception) -> str:
    """One short line for the page."""
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        e = e.reason if isinstance(e.reason, Exception) else OSError(str(e.reason))
    if isinstance(e, TimeoutError):
        return "timed out"
    if isinstance(e, ValueError):
        return "not an address"
    return str(e) or type(e).__name__


class Looker:
    """When to look, and what to publish. No I/O of its own, for the tests."""

    def __init__(self, look=lookup, reach=online) -> None:
        self.look = look
        self.reach = reach
        self.address = ""
        self.last = 0.0                 # monotonic time of the last lookup

    async def check(self) -> list[tuple[str, str]]:
        self.last = time.monotonic()
        try:
            self.address = await asyncio.to_thread(self.look)
            error = ""
        except (OSError, ValueError) as e:
            error = why(e)
            if not await asyncio.to_thread(self.reach):
                error = OFFLINE
        log.info("public ip %s%s", self.address or "unknown",
                 f" (lookup failed: {error})" if error else "")
        return [("host/public_ip", self.address),
                ("host/public_ip/checked", str(int(time.time()))),
                ("host/public_ip/error", error)]

    def due(self, asked: bool) -> bool:
        gap = LEAST if asked else EVERY
        return self.last == 0.0 or time.monotonic() - self.last >= gap


async def run(args: argparse.Namespace) -> int:
    looker = Looker()
    trunk_ata = ata.Ata(args.ata_host, args.ata_cred, args.ata_known_hosts)
    asked = asyncio.Event()
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)
    password = Path(args.password_file).read_text(encoding="utf-8").strip()

    async def session() -> None:
        async with aiomqtt.Client(
                hostname=args.broker, port=args.port, username=args.user,
                password=password, identifier=CLIENT_ID,
                clean_session=True, keepalive=10) as c:
            log.info("connected to %s:%d as %s", args.broker, args.port, args.user)
            await c.subscribe(PREFIX + "host/public_ip/check/set", qos=0)

            async def listen() -> None:
                async for _ in c.messages:
                    asked.set()

            async def looking() -> None:
                while True:
                    try:
                        await asyncio.wait_for(asked.wait(), EVERY)
                    except asyncio.TimeoutError:
                        pass
                    by_hand = asked.is_set()
                    asked.clear()
                    if not looker.due(by_hand):
                        continue
                    for topic, value in await looker.check():
                        await c.publish(PREFIX + topic, value, qos=1, retain=True)

            async def trunk() -> None:
                while True:
                    state = await asyncio.to_thread(trunk_ata.state)
                    for topic, value in (("host/public_trunk", state),
                                         ("host/public_trunk/checked", str(int(time.time())))):
                        await c.publish(PREFIX + topic, value, qos=1, retain=True)
                    await asyncio.sleep(TRUNK_EVERY)

            asked.set()                 # look at once on connecting
            looker.last = 0.0
            await asyncio.gather(listen(), looking(), trunk())

    async def forever() -> None:
        delay = 1.0
        while True:
            try:
                await session()
            except aiomqtt.MqttError as e:
                log.warning("mqtt: %s; retrying in %.0fs", e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)

    task = asyncio.create_task(forever())
    await stopping.wait()
    log.info("stopping")
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    if ata.ASKPASS_ENV in os.environ:   # run by ssh as SSH_ASKPASS (ata.py)
        return ata.askpass()
    p = argparse.ArgumentParser(
        description="Publish the host's public address for the page (mqtt.md 6.3).")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--user", default=USERNAME)
    p.add_argument("--password-file", default=PASSWORD_FILE)
    p.add_argument("--ata-host", default=ata.HOST, help="the trunk 8 ATA")
    p.add_argument("--ata-cred", default=ata.CRED_FILE,
                   help="its username, then its password, one per line")
    p.add_argument("--ata-known-hosts", default=ata.KNOWN_HOSTS,
                   help="its SSH host key, pinned")
    p.add_argument("--once", action="store_true",
                   help="look once at both, print them, and exit; no broker")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    if args.once:
        rc = 0
        try:
            print(f"public ip     {lookup()}")
        except (OSError, ValueError) as e:
            print(f"public ip     lookup failed: {why(e)}")
            rc = 1
        state = ata.Ata(args.ata_host, args.ata_cred, args.ata_known_hosts).state()
        print(f"public trunk  {state}")
        return rc if state != ata.ERROR else 1
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

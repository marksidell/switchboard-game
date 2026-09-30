"""MQTT link: keeps the Board fed, carries the game's commands out, and
brings the status page's commands in.

One task, run(), owns the connection. It reconnects forever. On each connect,
in the order mqtt.md §8.4 gives for the game program:
  1. the client connects with its will: "offline" on ctl/game_status
  2. on_birth() publishes the game's own state (run, pacing, tallies, call
     slots, log, board/ map), retained; state before birth
  3. ctl/game_status "online", retained
  4. forget the old hardware state (Board.reset_for_resync), then subscribe to
     sbgame/#, which brings every retained value back
  5. after a short settle, mark the broker up and publish ctl/sync
  6. run the 1 s game_heartbeat (host Unix time) and the controller
     heartbeat watchdog
  7. feed every hardware and audio message to Board.update(), and pass every
     page command (sbgame/game/<name>/set) to on_command(name, payload)

Scenes command hardware through Hw, never through the client directly. The
client object is new on every reconnect, and Hw raises Offline if there is
none right now, instead of quietly dropping a command.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

import aiomqtt

from .board import Board, Offline

log = logging.getLogger("link")

PREFIX = "sbgame/"
CLIENT_ID = "sbgame-game"
USERNAME = "sbgame-game"  # mqtt.md §9; password from /etc/sbgame/mqtt-game.pass
SETTLE = 0.5  # s after subscribe for the retained flood to land before waits may pass

# Topics the game program publishes itself and receives back on the wildcard.
_OWN = {"ctl/game_heartbeat", "ctl/sync", "ctl/game_status"}
_OWN_PREFIXES = ("game/", "board/")  # the game's own retained state

Birth = Callable[["Link"], Awaitable[None]]
CommandHandler = Callable[[str, str], Awaitable[None]]


async def _no_birth(link: "Link") -> None:
    return None


async def _no_command(name: str, payload: str) -> None:
    log.info("page command %s=%r (no handler)", name, payload)


class Link:
    def __init__(self, board: Board, host: str, port: int = 1883, *,
                 username: str | None = USERNAME, password: str | None = None,
                 on_birth: Birth = _no_birth,
                 on_command: CommandHandler = _no_command) -> None:
        self.board = board
        self._on_birth = on_birth
        self._on_command = on_command
        will = aiomqtt.Will(PREFIX + "ctl/game_status", "offline", qos=1, retain=True)
        self._args = dict(hostname=host, port=port, username=username,
                          password=password, identifier=CLIENT_ID,
                          clean_session=True,  # mqtt.md §2: no queued stale commands
                          keepalive=5, will=will)
        self._client: aiomqtt.Client | None = None

    async def publish(self, key: str, payload: str = "") -> None:
        """A command: never retained, QoS 1 (mqtt.md §2)."""
        c = self._client
        if c is None:
            raise Offline(f"broker (dropping {key}={payload!r})")
        await c.publish(PREFIX + key, payload, qos=1, retain=False)

    async def state(self, key: str, value: str) -> None:
        """Game state for the page (mqtt.md §6.1): retained, QoS 1.

        An empty value clears the retained topic (mqtt.md §7).
        """
        c = self._client
        if c is None:
            raise Offline(f"broker (dropping state {key}={value!r})")
        await c.publish(PREFIX + key, value, qos=1, retain=True)

    async def run(self) -> None:
        delay = 1.0
        while True:
            try:
                async with aiomqtt.Client(**self._args) as client:
                    log.info("connected")
                    delay = 1.0
                    await self._session(client)
            except* aiomqtt.MqttError as eg:
                log.warning("mqtt: %s; retrying in %.0fs", eg.exceptions[0], delay)
            finally:
                self._client = None
                await self.board.set_broker(False)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)

    async def _session(self, client: aiomqtt.Client) -> None:
        self._client = client
        await self._on_birth(self)  # game state first...
        await self.state("ctl/game_status", "online")  # ...then birth
        await self.board.reset_for_resync()
        await client.subscribe(PREFIX + "#", qos=1)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._heartbeat())
            tg.create_task(self._watchdog())
            tg.create_task(self._go_live())
            async for msg in client.messages:
                key = msg.topic.value.removeprefix(PREFIX)
                payload = msg.payload.decode() if isinstance(msg.payload, bytes) else str(msg.payload or "")

                if key.startswith("game/") and key.endswith("/set"):
                    # A page command (mqtt.md §6.2). Keep the handler quick:
                    # validate, publish the echo, start tasks. The dispatcher
                    # waits for it.
                    # The name is what lies between game/ and /set: "run", or
                    # for a diagnostic "diag/station/3/tone" (mqtt.md §6.2).
                    await self._on_command(key.removeprefix("game/").removesuffix("/set"), payload)
                    continue
                if key.endswith("/set") or key in _OWN or key.startswith(_OWN_PREFIXES):
                    continue  # our own commands and state, echoed back by the wildcard

                was_up = self.board.control_up
                await self.board.update(key, payload)
                if self.board.control_up and not was_up:
                    # status went online, or heartbeat came back (mqtt.md §8.3)
                    log.info("controller up; sending sync")
                    await self.publish("ctl/sync")

    async def _go_live(self) -> None:
        # Let the retained flood land before any wait can pass on it.
        await asyncio.sleep(SETTLE)
        await self.board.set_broker(True)
        await self.publish("ctl/sync")

    async def _heartbeat(self) -> None:
        while True:
            # Host Unix time, to a tenth of a second (mqtt.md §7, Rev 10).
            # The page takes the host's clock from it.
            await self.publish("ctl/game_heartbeat", f"{time.time():.1f}")
            await asyncio.sleep(1.0)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            if await self.board.check_control_beat() == "lost":
                log.warning("controller heartbeat lost")


def read_password(path: str = "/etc/sbgame/mqtt-game.pass") -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


class Hw:
    """Game commands, one method per /set topic in mqtt.md §6.

    A circuit is the id string used on the wire: "station/12", "trunk/3".
    """

    def __init__(self, link) -> None:
        self._p = link.publish

    async def hook(self, station: int, off_hook: bool) -> None:
        await self._p(f"station/{station}/hook/set", "on" if off_hook else "off")

    async def ring_trunk(self, trunk: int, on: bool = True) -> None:
        await self._p(f"trunk/{trunk}/ring/set", "on" if on else "off")

    async def play(self, circuit: str, name: str) -> None:
        await self._p(f"{circuit}/play/set", name)

    async def stop(self, circuit: str) -> None:
        await self._p(f"{circuit}/play/set", "stop")

    async def tone(self, trunk: int, tone: str) -> None:  # dial, ringback, busy, off
        await self._p(f"trunk/{trunk}/tone/set", tone)

    async def listen(self, circuit: str, seconds: float) -> None:
        await self._p(f"{circuit}/listen/set", f"{seconds:g}")

    async def monitor_source(self, source: str) -> None:  # "tap" or a circuit id
        await self._p("audio/monitor/source/set", source)

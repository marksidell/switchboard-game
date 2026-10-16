"""Board: the game program's picture of the switchboard, built from MQTT.

Every retained topic under sbgame/ is one plain-string value (mqtt.md §2), so
the model is a flat dict keyed by the topic minus the prefix:

    "trunk/3/seize"   -> "on"
    "station/12/peer" -> "station/2"

A key is absent when its value is empty (an empty retained payload clears it,
mqtt.md §7), so get() returns "" for both "cleared" and "never heard".

Scenes never read MQTT. They wait for predicates over this model with
wait_until(). The dispatcher applies each message and wakes every waiter.
Anything that wants a running report of what changed (console log, SQLite
session log, the iPad page) reads the same changes from watch().

Everything here runs on one event loop. Nothing is thread-safe, and nothing
needs to be.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

log = logging.getLogger("board")

# Liveness pseudo-keys. They go through the same change stream as real topics
# so a log or UI shows "control went away" in line with everything else.
LIVE_BROKER = "live/broker"
LIVE_CONTROL = "live/control"
LIVE_AUDIO = "live/audio"

CONTROL_BEAT_LIMIT = 2.5  # seconds: two missed 1 s beats, plus slack (mqtt.md §8.2)


class Offline(Exception):
    """A wait was failed because a client it depends on is gone."""


class Abandoned(Exception):
    """A wait was failed because its abort condition came true."""


@dataclass(frozen=True)
class Change:
    key: str
    old: str
    new: str
    t: float  # time.time(), for logs


Predicate = Callable[["Board"], Any]


class Board:
    # A connection that goes away is believed only after HOLD seconds gone
    # (game_control.md §5, Rev 45). Moving a cord pair's switch breaks both
    # lines for about 0.2s, as do dial pulses; the detector reports that as
    # `deaf` and then idle, and the call must ride through it.
    HOLD = 1.0

    def __init__(self, hold: float | None = None) -> None:
        self._v: dict[str, str] = {}
        self.cond = asyncio.Condition()
        self.hold = self.HOLD if hold is None else hold
        self._held: dict[str, asyncio.TimerHandle] = {}   # key -> its pending fall
        self._watchers: set[asyncio.Queue[Change]] = set()

        self.broker_up = False
        self._control_status = ""  # retained sbgame/ctl/status
        self._audio_status = ""  # retained sbgame/ctl/audio_status
        self._control_beat_ok = False
        self._last_control_beat = 0.0
        self._live = {LIVE_BROKER: False, LIVE_CONTROL: False, LIVE_AUDIO: False}

    # ---- reading ---------------------------------------------------------

    def get(self, key: str) -> str:
        return self._v.get(key, "")

    def on(self, key: str) -> bool:
        return self._v.get(key) == "on"

    def dialled(self, trunk: int) -> str:
        """Digits dialled on this trunk since it was last seized."""
        return self._v.get(f"trunk/{trunk}/dialled", "")

    @property
    def control_up(self) -> bool:
        return self._live[LIVE_CONTROL]

    @property
    def audio_up(self) -> bool:
        return self._live[LIVE_AUDIO]

    # ---- applying messages ----------------------------------------------

    async def update(self, key: str, payload: str) -> None:
        """Apply one message and wake waiters if anything changed."""
        async with self.cond:
            if self._apply(key, payload):
                self.cond.notify_all()

    async def expect(self, key: str, value: str = "pending") -> None:
        """Mark a result as pending before sending the command that produces it.

        For commands whose finished state is the same as the starting state:
        play goes "" -> name -> "", and a listen's last "silence" persists
        until the next one. Waiting for "" or "silence" would pass at once on
        the old value. So say() sets play to "pending" first, sends the
        command, then waits for "" or "missing". The audio program's echo
        replaces "pending", and the log shows whether it ever acted.

        Call this before sending the command: the echo can arrive while the
        send is still awaiting the broker's acknowledgement.
        """
        async with self.cond:
            if self._set(key, value):
                self.cond.notify_all()

    def _apply(self, key: str, payload: str) -> bool:
        # Keep this a plain def that only updates values. Anything that needs
        # await (SQLite log, iPad push, a command in reaction to a change)
        # goes in its own task reading watch(). The Condition's lock is mostly
        # there because its API requires it; it matters only if this ever awaits.
        if key == "ctl/esp_heartbeat":
            # Every second. Not stored: it isn't state, and storing it would
            # wake every waiter once a second for nothing.
            self._last_control_beat = time.monotonic()
            if not self._control_beat_ok:
                self._control_beat_ok = True
                return self._relive()
            return False

        if key.startswith("trunk/") and key.endswith("/digit"):
            # The one event topic (mqtt.md §7). Turn it into state here: the
            # string dialled since seizure. Scenes then wait on its length
            # like anything else, and nothing is queued or consumed.
            n = key.split("/")[1]
            return self._set(f"trunk/{n}/dialled", self.dialled(int(n)) + payload)

        held = self._hold(key, payload)
        if held is not None:
            return held

        changed = self._set(key, payload)
        if not changed:
            return False  # react to changes, not arrivals (mqtt.md §8.3)

        if key == "ctl/status":
            self._control_status = payload
            self._relive()
        elif key == "ctl/audio_status":
            self._audio_status = payload
            self._relive()
        elif key.startswith("trunk/") and key.endswith("/seize"):
            # New seizure or release: start a fresh number.
            n = key.split("/")[1]
            self._set(f"trunk/{n}/dialled", "")
        return True

    def _hold(self, key: str, payload: str) -> bool | None:
        """A circuit's `peer` and `op` going away, held (§5, Rev 45).

        `deaf` is a circuit not hearing its own pilot, which says nothing
        about what it is patched to: the last value stands. A `peer` going
        empty or `op` going off is applied only if it is still the latest
        after HOLD seconds. Returns whether anything changed, or None for a
        message this does not handle.
        """
        kind = key.rsplit("/", 1)[-1]
        if not (key.startswith(("station/", "trunk/")) and kind in ("peer", "op")):
            return None
        pending = self._held.pop(key, None)
        if pending is not None:
            pending.cancel()
        if kind == "peer" and payload == "deaf":
            return False
        going = (payload == "") if kind == "peer" else (payload != "on")
        if going and self._v.get(key) and self.hold > 0:
            loop = asyncio.get_running_loop()
            self._held[key] = loop.call_later(
                self.hold, lambda: asyncio.ensure_future(self._settle(key, payload)))
            return False
        return self._set(key, payload)

    async def _settle(self, key: str, payload: str) -> None:
        async with self.cond:
            self._held.pop(key, None)
            if self._set(key, payload):
                self.cond.notify_all()

    def _set(self, key: str, value: str) -> bool:
        old = self._v.get(key, "")
        if old == value:
            return False
        if value:
            self._v[key] = value
        else:
            self._v.pop(key, None)
        self._emit(key, old, value)
        return True

    def _emit(self, key: str, old: str, new: str) -> None:
        ch = Change(key, old, new, time.time())
        for q in self._watchers:
            q.put_nowait(ch)

    def _relive(self) -> bool:
        """Recompute the three liveness flags; emit and report any change."""
        want = {
            LIVE_BROKER: self.broker_up,
            LIVE_CONTROL: self.broker_up and self._control_status == "online" and self._control_beat_ok,
            LIVE_AUDIO: self.broker_up and self._audio_status == "online",
        }
        changed = False
        for k, v in want.items():
            if self._live[k] != v:
                self._live[k] = v
                self._emit(k, "on" if not v else "off", "on" if v else "off")
                changed = True
        return changed

    # ---- connection lifecycle (called by the MQTT link) -----------------

    async def set_broker(self, up: bool) -> None:
        async with self.cond:
            self.broker_up = up
            if not up:
                self._control_beat_ok = False
            if self._relive():
                self.cond.notify_all()

    async def reset_for_resync(self) -> None:
        """Forget every value before resubscribing.

        This is needed, not tidiness. A topic cleared during the outage had
        its retained value deleted at the broker, so resubscribing brings
        nothing for it, and without a reset the old value would stay here
        forever.
        """
        async with self.cond:
            for h in self._held.values():
                h.cancel()
            self._held.clear()
            self._v.clear()
            self._control_status = self._audio_status = ""
            self._relive()
            self._emit("resync", "", "")
            self.cond.notify_all()

    async def check_control_beat(self) -> str | None:
        """Called periodically. Returns "lost" or None."""
        if self._control_beat_ok and time.monotonic() - self._last_control_beat > CONTROL_BEAT_LIMIT:
            async with self.cond:
                self._control_beat_ok = False
                self._relive()
                self.cond.notify_all()
            return "lost"
        return None

    # ---- waiting ---------------------------------------------------------

    async def wait_until(
        self,
        pred: Predicate,
        timeout: float | None,
        *,
        abort_if: Predicate | None = None,
        needs: tuple[str, ...] = (LIVE_CONTROL, LIVE_AUDIO),
    ) -> Any:
        """Wait until pred(board) is truthy and return its value.

        Checked at once, so a condition that is already true returns without
        waiting, and there is nothing to clear or re-arm between uses.

        Raises TimeoutError, Offline if any client in `needs` is down (checked
        before pred, so a stale retained value can never satisfy a wait), or
        Abandoned if abort_if(board) comes true first.
        """
        async with asyncio.timeout(timeout):
            async with self.cond:
                while True:
                    down = [k for k in needs if not self._live[k]]
                    if down:
                        raise Offline(", ".join(down))
                    if abort_if is not None and (why := abort_if(self)):
                        raise Abandoned(why if isinstance(why, str) else "")
                    if r := pred(self):
                        return r
                    await self.cond.wait()

    async def wait_live(self, timeout: float | None = None) -> None:
        """Wait until everything is up, e.g. before starting a scene."""
        async with asyncio.timeout(timeout):
            async with self.cond:
                await self.cond.wait_for(lambda: self.control_up and self.audio_up)

    # ---- reporting -------------------------------------------------------

    async def watch(self) -> AsyncIterator[Change]:
        """Every change, in order, for as long as the caller keeps reading."""
        q: asyncio.Queue[Change] = asyncio.Queue()
        self._watchers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._watchers.discard(q)

    def snapshot(self) -> dict[str, str]:
        """Whole state, e.g. for a newly connected iPad page."""
        return dict(self._v) | {k: ("on" if v else "off") for k, v in self._live.items()}

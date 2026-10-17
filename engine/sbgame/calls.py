"""Calls in progress, their stages, and the tallies (game_control.md §5, §6.1).

Eight slots, because the page shows eight and a ninth call is not started.
Each slot is a handful of retained topics under `game/call/<1-8>/`, and this
module owns the order they are published in, which the specification is
particular about for reasons that only show up on the page:

  - `since` and `deadline` go out **before** `stage`, so the page never draws
    a new stage against the old times;
  - at a call's end `scene` is cleared **first**, so the page frees the slot
    before the other values empty and never draws a half-erased call.

Stages here are the page's eight names. A flow's own state machine may be
finer; it maps onto these.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

N_SLOTS = 8


class Stage:
    SIGNALLING = "signalling"
    REQUEST = "request"
    ROUTING = "routing"
    DIALLING = "dialling"
    RINGING = "ringing"
    BUSY = "busy"
    TALKING = "talking"
    OPERATOR = "operator"


class Reason:
    """§5's failure reasons. A wrong connection is not one of them."""
    NO_ANSWER = "no answer"
    NOT_CONNECTED = "not connected"
    CUT_OFF = "cut off"
    TIMEOUT = "timeout"
    MISDIALLED = "misdialled"     # too many digits or too few (Rev 56)


@dataclass
class Tallies:
    started: int = 0
    success: int = 0
    fail: int = 0

    def zero(self) -> None:
        self.started = self.success = self.fail = 0

    @property
    def handled(self) -> int:
        return self.success + self.fail


@dataclass
class Call:
    """One call in progress, and the slot it publishes into."""
    slot: int                  # 1-8
    number: int                # the call number within this game
    scene: str
    from_line: str
    to_line: str
    trunk: str = ""            # circuit id once known
    stage: str = ""
    since: float = 0.0
    deadline: float | None = None
    digits: str = ""
    # Not published. The scheduler asks for it (§4.3) and an `after:` scene
    # is dropped unless the scene it follows reached it (§4.4).
    connected: bool = False

    def topics(self) -> dict[str, str]:
        """Every value this slot carries, as the page reads them."""
        return {
            "number": str(self.number),
            "scene": self.scene,
            "from": self.from_line,
            "to": self.to_line,
            "trunk": self.trunk,
            "stage": self.stage,
            "since": _t(self.since),
            "deadline": _t(self.deadline),
            "digits": self.digits,
        }


def _t(v: float | None) -> str:
    """Host Unix seconds as the page wants them, or empty (§7.2)."""
    return "" if not v else f"{v:.0f}"


class Slots:
    """The eight slots, and the publishing order the page depends on."""

    def __init__(self, publish) -> None:
        # publish(key, value) -> awaitable; Link.state in the real program.
        self._publish = publish
        self._calls: dict[int, Call] = {}
        # Tutor mode (game_control.md §4.9): no stage has a deadline, so the
        # page shows none.
        self.timeless = False

    def __len__(self) -> int:
        return len(self._calls)

    def __iter__(self):
        return iter(self._calls.values())

    def free_slot(self) -> int | None:
        for n in range(1, N_SLOTS + 1):
            if n not in self._calls:
                return n
        return None          # a ninth call is not started (§4.4)

    def get(self, slot: int) -> Call | None:
        return self._calls.get(slot)

    async def open(self, call: Call) -> None:
        self._calls[call.slot] = call
        for k, v in call.topics().items():
            await self._publish(f"game/call/{call.slot}/{k}", v)

    async def set_stage(self, call: Call, stage: str,
                        deadline: float | None = None) -> None:
        """§6.1: since and deadline before stage."""
        call.since = time.time()
        call.deadline = None if self.timeless else deadline
        call.stage = stage
        await self._publish(f"game/call/{call.slot}/since", _t(call.since))
        await self._publish(f"game/call/{call.slot}/deadline", _t(call.deadline))
        await self._publish(f"game/call/{call.slot}/stage", stage)

    async def set(self, call: Call, field_: str, value: str) -> None:
        setattr(call, {"trunk": "trunk", "digits": "digits"}[field_], value)
        await self._publish(f"game/call/{call.slot}/{field_}", value)

    async def close(self, call: Call) -> None:
        """§6.1: scene first, so the page frees the slot before the rest empty."""
        self._calls.pop(call.slot, None)
        await self._publish(f"game/call/{call.slot}/scene", "")
        for k in ("number", "from", "to", "trunk", "stage", "since",
                  "deadline", "digits"):
            await self._publish(f"game/call/{call.slot}/{k}", "")

    async def clear_all(self) -> None:
        """Stop, or birth: every slot empty (§3)."""
        for call in list(self._calls.values()):
            await self.close(call)
        for n in range(1, N_SLOTS + 1):
            if n not in self._calls:
                await self._publish(f"game/call/{n}/scene", "")
                for k in ("number", "from", "to", "trunk", "stage", "since",
                          "deadline", "digits"):
                    await self._publish(f"game/call/{n}/{k}", "")

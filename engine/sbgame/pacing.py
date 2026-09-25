"""When the next call starts (game_control.md §4.1 to §4.3).

Manual: the page asks, one tap one call.

Automatic: the next call starts `gap_now` seconds after the most recent call
to be **connected** or to end, whichever came first. Timing from the most
recent call rather than from every call is what keeps at most one call waiting
for the operator — calls overlap, but she is never asked to route two at once.

    gap_now = max(floor, gap - ramp * connected)

so the game tightens as it goes. A change to gap, ramp, floor or jitter takes
effect at the next scheduling, not on a call already scheduled, which is why
the value is read when the timer is set rather than held.

`jitter` (§4.3, Rev 12) takes the regularity out: each wait is drawn evenly
from gap_now × (1 ± jitter/100). Its mean is still gap_now, so the pace the
three settings describe is unchanged and only the rhythm goes. The floor
bounds gap_now, the centre, and not the draw — bounding the draw would push
the short ones up to the floor and lift the mean near it. The draws come
from the game's seed, so a replay draws the same sequence.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field


@dataclass
class Pacing:
    pace: str = "manual"       # "manual" or "auto"
    gap: float = 20.0
    ramp: float = 0.0
    floor: float = 5.0
    jitter: float = 0.0        # percent, 0-100: each wait is gap_now × (1 ± jitter/100)

    # Set when a call is connected or ends; None while a call is waiting to be
    # connected, which is when no next call is scheduled and next_at is empty.
    next_at: float | None = None
    connected: int = 0         # calls connected this game, the ramp's input
    _rng: random.Random = field(default_factory=random.Random, repr=False)

    def seed(self, seed: int) -> None:
        """At game start, from the deck's seed: the waits replay with the deck.

        A string, so the sequence is not the deck's own shuffle sequence
        over again, and str seeds are hashed the same on every run.
        """
        self._rng = random.Random(f"pacing-{seed}")

    def wait(self) -> float:
        """One wait: gap_now, spread by the jitter. Never negative."""
        centre = self.gap_now()
        if self.jitter <= 0:
            return centre
        return max(0.0, centre * (1 + self.jitter / 100 * self._rng.uniform(-1, 1)))

    def gap_now(self) -> float:
        """§4.3. Never below the floor, and the floor is never above the gap."""
        return max(min(self.floor, self.gap), self.gap - self.ramp * self.connected)

    def clamp(self, name: str, value: float) -> float:
        """§4.3's ranges. The page's values are clamped and echoed as applied."""
        if name == "gap":
            return min(600.0, max(0.0, value))
        if name == "ramp":
            return min(60.0, max(0.0, value))
        if name == "jitter":
            return min(100.0, max(0.0, value))
        if name == "floor":
            # "0-600s and not above gap"
            return min(600.0, max(0.0, min(value, self.gap)))
        raise ValueError(name)

    def schedule(self, now: float | None = None) -> float | None:
        """A call was connected or ended: set the next start time.

        Only in automatic pacing. Returns the new next_at, or None in manual.
        """
        if self.pace != "auto":
            self.next_at = None
            return None
        self.next_at = (time.time() if now is None else now) + self.wait()
        return self.next_at

    def waiting_to_connect(self) -> None:
        """A call is out and unconnected: nothing is scheduled (§4.2)."""
        self.next_at = None

    def due(self, now: float | None = None) -> bool:
        return (self.pace == "auto" and self.next_at is not None
                and (time.time() if now is None else now) >= self.next_at)

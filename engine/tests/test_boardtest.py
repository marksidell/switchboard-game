"""sbgame-boardtest against simulated boards: a good pair, and faults."""

from __future__ import annotations

import asyncio
import sys

from sbgame.boardtest import BoardTest, Timing, preflight

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<58} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


FAST = Timing(ring=0.5, clear=0.5, seize=0.5, peer=0.5, digit=0.5)


class Boards:
    """Trunk k wired to the k-th station: ring reaches the station, the
    station's off-hook seizes the trunk, the pilots cross while it is, and a
    station's dial/set reaches the trunk as digits, as the controller would
    report them (control.md §7.3, §8.2)."""

    def __init__(self, stations: list[int], dead_ring: int = 0, noisy: str = "",
                 quick_release: bool = False, misdial: int = 0) -> None:
        self.state: dict[str, str] = {}
        self.stations = stations
        self.dead_ring = dead_ring          # this station never detects ring
        self.noisy = noisy                  # this circuit goes off-hook by itself
        self.quick_release = quick_release  # a trunk that drops its seizure on a pulse
        self.misdial = misdial              # this station's trunk miscounts a 7 as 8
        self.test: BoardTest | None = None

    def set(self, key: str, value: str) -> None:
        if self.test:
            self.test.note(key, value)
        self.state[key] = value

    async def publish(self, key: str, value: str) -> None:
        await asyncio.sleep(0.001)
        kind, n, what, _ = key.split("/")
        n = int(n)
        if kind == "trunk" and what == "ring":
            st = self.stations[n - 1]
            self.set(f"trunk/{n}/ring", value)
            if st != self.dead_ring:
                self.set(f"station/{st}/ring", value)
            if self.noisy and value == "on":
                self.set(f"{self.noisy}/hook", "on")
        if kind == "station" and what == "hook":
            k = self.stations.index(n) + 1
            self.set(f"station/{n}/hook", value)
            self.set(f"trunk/{k}/seize", value)
            self.set(f"trunk/{k}/peer", f"station/{n}" if value == "on" else "")
            self.set(f"station/{n}/peer", f"trunk/{k}" if value == "on" else "")
        if kind == "station" and what == "dial":
            asyncio.create_task(self.dial(n, value))

    async def dial(self, n: int, digits: str) -> None:
        k = self.stations.index(n) + 1
        for i, d in enumerate(digits):
            self.set(f"station/{n}/dial", digits[i:])
            await asyncio.sleep(0.01)
            if self.quick_release and i == 0:
                self.set(f"trunk/{k}/seize", "off")
                self.set(f"trunk/{k}/seize", "on")
            if n == self.misdial and d == "7":
                d = "8"
            if self.test:
                self.test.note(f"trunk/{k}/digit", d)
        self.set(f"station/{n}/dial", "")


async def run(boards: Boards, audio: bool = True):
    lines: list[str] = []
    t = BoardTest(boards.state, boards.publish, boards.stations, audio, FAST, out=lines.append)
    boards.test = t
    r = await t.run()
    return r, lines


async def main() -> int:
    print("== board a, everything works")
    r, lines = await run(Boards(list(range(1, 9))))
    check(not r.failed, f"no failures ({r.passed} checks)")
    check(sum(1 for l in lines if l.lstrip().startswith("pair ")) == 8, "eight pairs, one at a time")
    check(any("station/1 detects ring" in l for l in lines), "reports ring detection")
    check(any("trunk/8 hears station/8" in l for l in lines), "reports the pilots crossing")

    check(sum(1 for l in lines if "5 dial" in l and "decodes" in l) == 80,
          "every pair dials all ten digits, each decoded")
    check(sum(1 for l in lines if "held the seizure" in l) == 8, "and holds its seizure throughout")

    print("\n== a trunk that releases on a dial pulse")
    r, _ = await run(Boards(list(range(1, 9)), quick_release=True))
    check(any("released its seizure during dialling" in f for f in r.failed),
          "fails the seizure check")

    print("\n== a trunk that miscounts a digit")
    r, _ = await run(Boards(list(range(1, 9)), misdial=4))
    check(r.failed == ["5 dial: station/4 dials 7, trunk/4 reports 8"],
          f"names the digit and what was decoded: {r.failed}")

    print("\n== board c: six stations, 17-22")
    r, lines = await run(Boards(list(range(17, 23))))
    check(not r.failed and sum(1 for l in lines if l.lstrip().startswith("pair ")) == 6, "six pairs, no failures")
    check(any("trunk/6 <-> station/22" in l for l in lines), "trunk 6 is wired to station 22")

    print("\n== a station that never detects ring")
    r, _ = await run(Boards(list(range(1, 9)), dead_ring=3))
    check(any("station/3 detects ring" in f for f in r.failed), "fails on station 3's ring")
    check(len(r.failed) == 1, f"and nothing else: {r.failed}")

    print("\n== another channel moves during a pair's test")
    r, _ = await run(Boards(list(range(1, 9)), noisy="station/5"))
    check(any("others not idle" in f and "station/5" in f for f in r.failed),
          "names the channel that did not stay idle")

    print("\n== --no-audio")
    r, lines = await run(Boards(list(range(9, 17))), audio=False)
    check(not r.failed and not any("pilots" in l for l in lines), "no pilot checks, no failures")

    print("\n== preflight")
    ok = {"ctl/status": "online", "ctl/audio_status": "online", "ctl/i2c": "ok"}
    check(preflight(ok, "a", True) == [], "all present: nothing stops it")
    check(any("station board b" in b for b in preflight({**ok, "ctl/i2c": "missing: 0x21"}, "b", True)),
          "a missing station board stops it")
    check(any("game is running" in b for b in preflight({**ok, "game/run": "on"}, "a", True)),
          "a running game stops it")
    check(preflight({**ok, "ctl/audio_status": "offline"}, "a", False) == [],
          "--no-audio does not need the audio program")

    print("\n" + ("FAILURES" if failures else "the board test passed"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

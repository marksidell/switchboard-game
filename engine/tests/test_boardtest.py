"""sbgame-boardtest against simulated boards: a good pair, and faults."""

from __future__ import annotations

import asyncio

from sbgame.boardtest import BoardTest, Timing, preflight

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


async def test_board_a_everything_works():
    """Board a, everything works."""
    r, lines = await run(Boards(list(range(1, 9))))
    assert not r.failed, f"no failures ({r.passed} checks)"
    assert sum(1 for l in lines if l.lstrip().startswith("pair ")) == 8, "eight pairs, one at a time"
    assert any("station/1 detects ring" in l for l in lines), "reports ring detection"
    assert any("trunk/8 hears station/8" in l for l in lines), "reports the pilots crossing"

    assert sum(1 for l in lines if "5 dial" in l and "decodes" in l) == 80, "every pair dials all ten digits, each decoded"
    assert sum(1 for l in lines if "held the seizure" in l) == 8, "and holds its seizure throughout"


async def test_a_trunk_that_releases_on_a_dial_pulse():
    """A trunk that releases on a dial pulse."""
    r, _ = await run(Boards(list(range(1, 9)), quick_release=True))
    assert any("released its seizure during dialling" in f for f in r.failed), "fails the seizure check"


async def test_every_trunk_reads_seized_from_the_start():
    """Every trunk reads seized from the start (a dead seize detector)."""
    b = Boards(list(range(1, 9)))
    for k in range(1, 9):
        b.state[f"trunk/{k}/seize"] = "on"
    r, lines = await run(b)
    assert len(r.stopped) == 8 and not any("detects ring" in l for l in lines), "skips every pair: nothing is rung or dialled"
    assert any("no pair is idle" in l for l in lines), "and says why it stopped"


async def test_one_station_not_idle_at_the_start():
    """One station not idle at the start."""
    b = Boards(list(range(1, 9)))
    b.state["station/6/hook"] = "on"
    r, lines = await run(b)
    assert any("station/6: not idle" in s for s in r.stopped) and len(r.stopped) == 1, f"skips that pair only: {r.stopped}"
    assert sum(1 for l in lines if "decodes" in l) == 70, "and tests the other seven in full"


async def test_a_trunk_that_miscounts_a_digit():
    """A trunk that miscounts a digit."""
    r, _ = await run(Boards(list(range(1, 9)), misdial=4))
    assert r.failed == ["5 dial: station/4 dials 7, trunk/4 reports 8"], f"names the digit and what was decoded: {r.failed}"


async def test_board_c_six_stations_17_22():
    """Board c: six stations, 17-22."""
    r, lines = await run(Boards(list(range(17, 23))))
    assert not r.failed and sum(1 for l in lines if l.lstrip().startswith("pair ")) == 6, "six pairs, no failures"
    assert any("trunk/6 <-> station/22" in l for l in lines), "trunk 6 is wired to station 22"


async def test_a_station_that_never_detects_ring():
    """A station that never detects ring."""
    r, _ = await run(Boards(list(range(1, 9)), dead_ring=3))
    assert any("station/3 detects ring" in f for f in r.failed), "fails on station 3's ring"
    assert len(r.failed) == 1, f"and nothing else: {r.failed}"
    assert len(r.stopped) == 1 and "station/3" in r.stopped[0] and "2 ring" in r.stopped[0], f"stops that pair at ring, the rest of it depending on it: {r.stopped}"


async def test_another_channel_moves_during_a_pairs_test():
    """Another channel moves during a pair's test."""
    r, _ = await run(Boards(list(range(1, 9)), noisy="station/5"))
    assert any("others not idle" in f and "station/5" in f for f in r.failed), "names the channel that did not stay idle"


async def test_no_audio():
    """--no-audio."""
    r, lines = await run(Boards(list(range(9, 17))), audio=False)
    assert not r.failed and not any("pilots" in l for l in lines), "no pilot checks, no failures"


async def test_preflight():
    """Preflight."""
    ok = {"ctl/status": "online", "ctl/audio_status": "online", "ctl/i2c": "ok"}
    assert preflight(ok, "a", True) == [], "all present: nothing stops it"
    assert any("station board b" in b for b in preflight({**ok, "ctl/i2c": "missing: 0x21"}, "b", True)), "a missing station board stops it"
    assert any("game is running" in b for b in preflight({**ok, "game/run": "on"}, "a", True)), "a running game stops it"
    assert preflight({**ok, "ctl/audio_status": "offline"}, "a", False) == [], "--no-audio does not need the audio program"

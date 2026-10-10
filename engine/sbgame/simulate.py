"""A stand-in for the controller, the audio program and — optionally — the
operator, so the game can be played before the boards exist.

The PCBs have not arrived. Without them the game program starts, deals a call,
and stops at once: every scene wait fails with `Offline` because neither
`ctl/status` nor `ctl/audio_status` is online, and game_control.md §3 says
losing a client stops the game. That is correct, and it makes the page
untestable. This fills both roles on the real broker.

    sbgame-sim                  hardware only; you are the operator
    sbgame-sim --operator       it answers and connects the calls as well

What it pretends to be:

  **the controller** — `ctl/status` online and a heartbeat every second, and
  the hook, ring and peer echoes for every `/set` it is sent (control.md §8).
  **the audio program** — `ctl/audio_status` online, and `play`, `listen`,
  `tone` and the monitor source echoed as audio.md describes, with each file
  taking as long as the wav really is.

What it is not. It does not model dial pulse timing, ring cadence, seizure
debounce or anything electrical; it is not a substitute for the bench. It
exists so the page and the game program can be exercised, and so a scene can
be watched end to end.

The operator, with --operator, uses only what the page shows it — the call
slots and the board map — plus script.yml for the line names, because the
slots carry line names and the board carries circuits and nothing publishes
the mapping between them.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import time
import wave
from pathlib import Path

import aiomqtt

from .config import Config
from .script_data import build

log = logging.getLogger("sim")
PREFIX = "sbgame/"
SITE_CONFIG = "/etc/sbgame/game.toml"

N_STATIONS, N_TRUNKS = 22, 8


class Sim:
    def __init__(self, cfg: Config, gs, operator: bool, delay: float,
                 control: tuple[str, str] = ("", ""),
                 audio: tuple[str, str] = ("", "")) -> None:
        self.control_user, self.control_pass = control
        self.audio_user, self.audio_pass = audio
        self.cfg = cfg
        self.gs = gs
        self.operator = operator
        self.delay = delay              # how long "the operator" takes to act
        # Two connections, not one. A will carries a single topic, so one
        # client pretending to be two leaves the second one's status retained
        # as "online" after the simulator dies — the game then believes the
        # audio program is still there. Each identity gets its own client, its
        # own will, and publishes the topics it actually owns.
        self.cc: aiomqtt.Client | None = None   # the controller
        self.ac: aiomqtt.Client | None = None   # the audio program
        self.v: dict[str, str] = {}     # what we have published, by topic tail
        self.busy: set[str] = set()     # slots this operator is already acting on
        # Trunks this operator has committed to. Chosen synchronously, because
        # `seize` does not become true until the echo comes back and two
        # overlapping calls would otherwise pick the same trunk and dial each
        # other's numbers into it.
        self.taken: set[int] = set()
        self.wav = cfg.resolved("wav_dir")
        # line name -> circuit id, which nothing on MQTT carries.
        self.circuit_of: dict[str, str] = {}
        for name, e in gs.script.stations.items():
            self.circuit_of[name] = f"station/{e['number']}"

    # ---- publishing ------------------------------------------------------

    # Which client owns which topic. The controller has the relays, the hook
    # and seizure detectors and the ring generator; the audio program has
    # playback, listening, the trunk tones and the monitor (mqtt.md 5, 6).
    AUDIO_LEAVES = ("play", "listen", "tone", "peer", "op")
    AUDIO_KEYS = ("ctl/audio_status", "audio/optone", "audio/monitor",
                  "audio/monitor/source")

    def _client_for(self, key: str) -> aiomqtt.Client | None:
        if key in self.AUDIO_KEYS or key.startswith("audio/"):
            return self.ac
        if key.rsplit("/", 1)[-1] in self.AUDIO_LEAVES:
            return self.ac
        return self.cc

    async def pub(self, key: str, value: str, retain: bool = True) -> None:
        c = self._client_for(key)
        if c is None:
            return
        self.v[key] = value
        await c.publish(PREFIX + key, value, qos=1, retain=retain)

    def get(self, key: str) -> str:
        return self.v.get(key, "")

    async def birth(self) -> None:
        """Come up as both clients would (mqtt.md §8.4)."""
        for n in range(1, N_STATIONS + 1):
            for f in ("hook", "ring", "peer", "op", "play", "listen"):
                await self.pub(f"station/{n}/{f}", "")
        for n in range(1, N_TRUNKS + 1):
            for f in ("seize", "ring", "peer", "op", "play", "listen", "tone", "fault"):
                await self.pub(f"trunk/{n}/{f}", "")
        await self.pub("ctl/i2c", "ok")
        await self.pub("audio/optone", "off")
        await self.pub("audio/monitor", "off")
        await self.pub("audio/monitor/source", "tap")
        await self.pub("audio/monitor/play", "")           # the tutor (audio.md §10.4)
        await self.pub("ctl/status", "online")
        await self.pub("ctl/audio_status", "online")
        log.info("controller and audio program are up")

    async def heartbeat(self) -> None:
        while True:
            await self.pub("ctl/esp_heartbeat", f"{time.time():.0f}", retain=False)
            await asyncio.sleep(1.0)

    # ---- the hardware's echoes ------------------------------------------

    def _seconds(self, name: str) -> float:
        try:
            with wave.open(str(self.wav / f"{name}.wav"), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except OSError:
            return 0.0

    async def on_set(self, base: str, payload: str) -> None:
        """One `/set`, echoed as the real client would echo it."""
        leaf = base.rsplit("/", 1)[-1]

        if leaf == "shortring":                  # control.md §8.4, Rev 25: one burst
            ring = base.rsplit("/", 1)[0] + "/ring"
            await self.pub(ring, payload)
            if payload == "on":
                asyncio.create_task(self._end_burst(ring))
            return

        if leaf in ("hook", "ring", "seize"):
            await self.pub(base, payload)
            if leaf == "hook" and payload == "off":
                await self._drop_peer(base.rsplit("/", 1)[0])
            return

        if leaf == "play":
            if payload in ("", "stop"):
                await self.pub(base, "")
                return
            secs = self._seconds(payload)
            if secs <= 0:
                await self.pub(base, "missing")
                log.warning("no wav for %s", payload)
                return
            await self.pub(base, payload)
            asyncio.create_task(self._finish_play(base, payload, secs))
            return

        if leaf == "listen":
            if payload in ("", "0"):
                await self.pub(base, "")
                return
            asyncio.create_task(self._do_listen(base, float(payload)))
            return

        if leaf == "tone":
            await self.pub(base, "" if payload == "off" else payload)
            return

        if base == "audio/monitor/source":
            await self.pub(base, payload)
            log.info("monitor source -> %s", payload)
            return

        if base == "audio/monitor":
            await self.pub(base, payload)
            return

    async def _finish_play(self, key: str, name: str, secs: float) -> None:
        await asyncio.sleep(secs)
        if self.get(key) == name:           # not replaced or stopped meanwhile
            await self.pub(key, "")

    async def _do_listen(self, key: str, within: float) -> None:
        """The operator speaks, then stops (audio.md §9)."""
        await self.pub(key, "listening")
        if self.operator:
            await asyncio.sleep(min(self.delay, within))
            await self.pub(key, "speech")
            await asyncio.sleep(1.2)        # she says her piece
            await self.pub(key, "silence")
        else:
            # Waiting for a real person at the board: time out if nobody speaks.
            await asyncio.sleep(within)
            if self.get(key) == "listening":
                await self.pub(key, "timeout")

    async def _drop_peer(self, circuit: str) -> None:
        peer = self.get(f"{circuit}/peer")
        if peer:
            await self.pub(f"{circuit}/peer", "")
            await self.pub(f"{peer}/peer", "")

    async def _connect(self, a: str, b: str) -> None:
        """A cord joins two circuits: both ends see it (control.md §8)."""
        await self.pub(f"{a}/peer", b)
        await self.pub(f"{b}/peer", a)

    # ---- the operator, with --operator ----------------------------------

    async def work_the_board(self) -> None:
        """Answer and connect each call, using what the page shows."""
        while True:
            await asyncio.sleep(0.2)
            if not self.operator:
                continue
            for slot in range(1, 9):
                if self.get(f"game/call/{slot}/scene") and slot not in self.busy:
                    self.busy.add(slot)
                    asyncio.create_task(self._handle(slot))

    async def _handle(self, slot: int) -> None:
        g = lambda f: self.get(f"game/call/{slot}/{f}")
        try:
            scene_id = g("scene")
            scene = self.gs.scenes.get(scene_id)
            if scene is None:
                return
            caller = (self.circuit_of.get(scene.from_line) or g("trunk")
                      or await self._wait_for(lambda: g("trunk"), 10))
            if not caller:
                return

            # Answer: throw the listening key on the calling line.
            await self._wait_for(lambda: g("stage") == "signalling", 20)
            await asyncio.sleep(self.delay)
            await self.pub(f"{caller}/op", "on")

            # The request plays; then route it.
            await self._wait_for(lambda: g("stage") in ("routing", "operator", ""), 60)
            if g("stage") in ("", "operator"):
                return                      # a call to the operator needs no cord

            await asyncio.sleep(self.delay)
            if scene.to_station is not None:
                called = f"station/{scene.to_station}"
                await self.pub(f"{called}/ring", "on")
                # The game takes it off-hook when it answers; then the cord is up.
                await self._wait_for(lambda: self.get(f"{called}/hook") == "on", 30)
                await self.pub(f"{called}/ring", "off")
                await self._connect(caller, called)
            else:
                trunk = self._free_trunk_now()
                if trunk is None:
                    log.warning("no free trunk for slot %d", slot)
                    return
                await self.pub(f"trunk/{trunk}/seize", "on")
                await self._connect(caller, f"trunk/{trunk}")
                await self._wait_for(
                    lambda: self.get(f"trunk/{trunk}/tone") == "dial", 20)
                for d in "".join(c for c in scene.dial if c.isdigit()):
                    await asyncio.sleep(0.12)
                    await self.pub(f"trunk/{trunk}/digit", d, retain=False)
        except Exception:
            log.exception("operator on slot %d", slot)
        finally:
            # Wait for the call to end, then put the board back as an operator
            # would: pull the cords and restore the listening key.
            await self._wait_for(lambda: not self.get(f"game/call/{slot}/scene"), 600)
            await self._restore()
            self.busy.discard(slot)

    async def _restore(self) -> None:
        """Clear what the operator did, once her call has ended.

        `op` and `seize` are the operator's own actions, reported by the
        controller; the game never sets them and cannot clear them. Without
        this every line she ever answered stays lit as "operator on" for the
        rest of the session, which is exactly what it did.
        """
        for n in range(1, N_STATIONS + 1):
            c = f"station/{n}"
            if self.get(f"{c}/op") and not self._in_a_call(c):
                await self.pub(f"{c}/op", "")
        for n in range(1, N_TRUNKS + 1):
            c = f"trunk/{n}"
            if self._in_a_call(c):
                continue
            if self.get(f"{c}/op"):
                await self.pub(f"{c}/op", "")
            if self.get(f"{c}/seize"):
                await self.pub(f"{c}/seize", "")      # she releases the trunk
                await self._drop_peer(c)
            self.taken.discard(n)
            if self.get(f"{c}/tone"):
                await self.pub(f"{c}/tone", "")

    def _in_a_call(self, circuit: str) -> bool:
        """Is this circuit still carrying one of the open calls?"""
        for slot in range(1, 9):
            if not self.get(f"game/call/{slot}/scene"):
                continue
            if self.get(f"game/call/{slot}/trunk") == circuit:
                return True
            scene = self.gs.scenes.get(self.get(f"game/call/{slot}/scene"))
            if scene is None:
                continue
            for line in (scene.from_line, scene.to_line):
                if line and self.circuit_of.get(line) == circuit:
                    return True
        return False

    async def _end_burst(self, ring: str) -> None:
        await asyncio.sleep(1.0)            # control.md Rev 30: the burst is 1s
        if self.get(ring) == "on":
            await self.pub(ring, "off")

    def _free_trunk_now(self) -> int | None:
        """Pick a trunk and commit to it in the same breath, no await between."""
        for n in range(1, N_TRUNKS + 1):
            if n in self.taken:
                continue
            if not self.get(f"trunk/{n}/seize") and not self.get(f"trunk/{n}/ring"):
                self.taken.add(n)
                return n
        return None

    async def _wait_for(self, pred, timeout: float):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            v = pred()
            if v:
                return v
            await asyncio.sleep(0.1)
        return None

    # ---- the connection --------------------------------------------------

    async def run(self) -> None:
        """Both identities, each with its own will, for as long as it lives."""
        while True:
            try:
                async with aiomqtt.Client(
                        **self._args("sbgame-sim-control", self.control_user,
                                     self.control_pass, "ctl/status")) as cc, \
                           aiomqtt.Client(
                        **self._args("sbgame-sim-audio", self.audio_user,
                                     self.audio_pass, "ctl/audio_status")) as ac:
                    self.cc, self.ac = cc, ac
                    log.info("controller as %s, audio program as %s",
                             self.control_user, self.audio_user)
                    await self.birth()
                    await cc.subscribe(PREFIX + "#", qos=1)
                    try:
                        async with asyncio.TaskGroup() as tg:
                            tg.create_task(self.heartbeat())
                            tg.create_task(self.work_the_board())
                            tg.create_task(self._dispatch(cc))
                    except asyncio.CancelledError:
                        # Ctrl-C. Leaving the `async with` disconnects
                        # cleanly, and a clean disconnect is the one case in
                        # which the broker discards a will: both statuses
                        # would stay retained "online" with no heartbeat
                        # behind them. So say it ourselves, as the wills
                        # would have.
                        await asyncio.shield(self._goodbye(cc, ac))
                        raise
            except* Exception as eg:
                log.warning("mqtt: %s; retrying", eg.exceptions[0])
                self.cc = self.ac = None
                await asyncio.sleep(2)

    async def _goodbye(self, cc: aiomqtt.Client, ac: aiomqtt.Client) -> None:
        try:
            async with asyncio.timeout(2):
                await cc.publish(PREFIX + "ctl/status", "offline", qos=1, retain=True)
                await ac.publish(PREFIX + "ctl/audio_status", "offline", qos=1, retain=True)
            log.info("offline")
        except Exception as e:
            log.warning("could not say offline: %s", e)

    def _args(self, ident: str, user: str, password: str, will_topic: str) -> dict:
        return dict(hostname=self.cfg.broker_host, port=self.cfg.broker_port,
                    username=user, password=password, identifier=ident,
                    clean_session=True, keepalive=10,
                    will=aiomqtt.Will(PREFIX + will_topic, "offline",
                                      qos=1, retain=True))

    async def _dispatch(self, c: aiomqtt.Client) -> None:
        async for m in c.messages:
            topic = str(m.topic)
            if not topic.startswith(PREFIX):
                continue
            key = topic[len(PREFIX):]
            payload = m.payload.decode()
            if key.endswith("/set"):
                await self.on_set(key[:-4], payload)
            elif key.startswith("game/"):
                was = self.v.get(key)
                self.v[key] = payload          # the operator reads the slots
                # Stop tears every call down at once (game_control.md 3). The
                # operator's own keys and cords are hers to put back.
                if key == "game/run" and was == "on" and payload == "off":
                    asyncio.create_task(self._restore())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # The daemon's own configuration has everything this needs — broker,
    # script, wavs — and is world-readable, so there is no second file to keep
    # in step. Only the identity differs, and that is below.
    p.add_argument("-c", "--config", type=Path, default=Path(SITE_CONFIG),
                   help=f"TOML configuration ({SITE_CONFIG} if it exists)")
    p.add_argument("--operator", action="store_true",
                   help="answer and connect the calls too, so a game runs by itself")
    p.add_argument("--delay", type=float, default=1.5,
                   help="how long the operator takes to act, seconds (1.5)")
    # It stands in for the controller and the audio program, so it connects as
    # one of them, not as the game. sbgame-control's password is compiled into
    # the firmware and is not on the host; sbgame-audio's is, and the access
    # list gives both the same rights (mqtt.md 9).
    p.add_argument("--user", default="sbgame-audio")
    p.add_argument("--pass-file", default="/etc/sbgame/mqtt-audio.pass")
    p.add_argument("--secrets", default="~/s/sbgame/control/secrets.h",
                   help="the firmware's credentials, for the controller identity")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(name)-4s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    cfg = Config.load(args.config if args.config.exists() else None)
    if not args.config.exists():
        log.warning("%s not found; using the built-in defaults", args.config)

    audio_pw = Path(args.pass_file).expanduser().read_text().strip()

    # The controller's own password is compiled into the firmware, in
    # control/secrets.h, which is gitignored and readable here. Use it when it
    # is there, so the simulator connects as the controller really does;
    # otherwise fall back to the audio identity, which the access list gives
    # the same rights (mqtt.md 9).
    control_user, control_pw = args.user, audio_pw
    secrets = Path(args.secrets).expanduser()
    if secrets.is_file():
        import re
        text = secrets.read_text()
        u = re.search(r'MQTT_USERNAME\s+"([^"]*)"', text)
        w = re.search(r'MQTT_PASSWORD\s+"([^"]*)"', text)
        if u and w:
            control_user, control_pw = u.group(1), w.group(1)
    else:
        log.info("%s not found; the controller will connect as %s",
                 secrets, args.user)

    gs = build(cfg.resolved("script"), cfg.resolved("wav_dir"))
    sim = Sim(cfg, gs, args.operator, args.delay,
              control=(control_user, control_pw), audio=(args.user, audio_pw))
    print(f"simulating the controller and the audio program"
          f"{' and the operator' if args.operator else ''}; ^C to stop")
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

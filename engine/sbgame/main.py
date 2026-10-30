"""The game program's entry point.

Starts the pieces in an order that matters: the script is loaded and validated
before anything connects, so a bad script.yml is a refusal to start with the
faults listed, rather than a program that runs and cannot deal a call
(game_control.md §6.3).

Then one task each for the link, the scheduler and the client watchdog, and a
clean shutdown on SIGINT or SIGTERM — which under systemd is what `stop` and
`restart` send. A clean exit publishes `ctl/game_status` `"offline"` itself: a
will fires only when a client vanishes, and a normal disconnect does not
trigger it (mqtt.md §8.4).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .board import Board
from .config import Config
from .game import Game
from . import cue
from .link import Hw, Link
from .script_data import build, fit
from .session import SessionLog
from tts.script import ScriptError

log = logging.getLogger("main")


def _password(cfg: Config) -> str | None:
    """The broker password, from its file (mqtt.md §9).

    A file rather than an argument, so it never appears in the process table
    or in a unit file. Missing is not fatal here: the broker refuses the
    connection and the link retries, which says so once a second in the log.
    """
    p = cfg.resolved("password_file")
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError as e:
        log.warning("no broker password: %s", e)
        return None


async def run(cfg: Config) -> int:
    board = Board()

    # Before anything connects: a bad script is a refusal to start, with every
    # fault named, not one at a time (tts_task.md §3.1).
    try:
        gs = build(cfg.resolved("script"), cfg.resolved("wav_dir"))
    except ScriptError as e:
        print(f"{e.path}: {len(e.failures)} problem(s)", file=sys.stderr)
        for f in e.failures:
            print(f"  {f}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(f"script: {e}", file=sys.stderr)
        return 2
    gs, left_out = fit(gs, cfg.stations, len(cfg.working_trunks()), cfg.stations_out())
    for w in left_out:
        log.info("left out: %s", w)
    log.info("circuits fitted: %d stations, %d trunks; %d scenes left out",
             cfg.stations, cfg.trunks, len(left_out))
    for kind in ("trunks", "stations"):
        for n, why in sorted((cfg.out_of_service.get(kind) or {}).items(),
                             key=lambda kv: int(kv[0])):
            log.info("%s %s out of service: %s", kind[:-1], n, why)
    log.info("script: %d active scenes of %d, %d in the deck, %d jacks",
             len(gs.scenes), len(gs.script.scenes), len(gs.deck_scenes()),
             sum(1 for j in gs.jacks if j.circuit))
    log.info("tutor: %d lines, %d with no wav%s", len(gs.tutor) + len(gs.tutor_missing),
             len(gs.tutor_missing), " — tutor mode is refused" if gs.tutor_missing else "")

    session = SessionLog(cfg.resolved("session_db"))
    await session.open()
    game = Game(board, gs, cfg, session)

    link = Link(board, cfg.broker_host, cfg.broker_port,
                username=cfg.username, password=_password(cfg),
                on_birth=game.on_birth, on_command=game.on_command)

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)

    tasks = [
        asyncio.create_task(link.run(), name="link"),
        asyncio.create_task(game.run_scheduler(), name="scheduler"),
        asyncio.create_task(game.watch_clients(), name="clients"),
        asyncio.create_task(game.free.run(), name="free-calls"),     # §8, Rev 74
    ]
    if cfg.ring_cue:                                # §9.2, Rev 51
        if (cfg.resolved("wav_dir") / f"{cue.CUE}.wav").is_file():
            tasks.append(asyncio.create_task(cue.RingCue(board, Hw(link)).run(), name="ring-cue"))
        else:
            log.warning("ring cue: no %s.wav in %s; off (tts/cue makes it)",
                        cue.CUE, cfg.resolved("wav_dir"))
    log.info("running; broker %s:%d as %s",
             cfg.broker_host, cfg.broker_port, cfg.username)
    try:
        await stopping.wait()
        log.info("stopping")
        # Tear down a game in progress first, so the controller and the audio
        # program are left idle rather than holding a call we walked away from.
        await game.stop("the game program is shutting down")
        await game.free.close()
        try:
            await asyncio.wait_for(link.state("ctl/game_status", "offline"), 2)
        except (Exception, asyncio.TimeoutError) as e:
            log.warning("could not say goodbye: %s", e)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await session.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="The 551 switchboard simulator's game program.")
    p.add_argument("-c", "--config", type=Path,
                   help="TOML configuration; without it, the built-in defaults")
    p.add_argument("--script", help="override the script.yml path")
    p.add_argument("--broker", help="override the broker host")
    p.add_argument("--stations", type=int, metavar="N",
                   help="stations fitted, 0-22: the first N (game_control.md 12.2)")
    p.add_argument("--trunks", type=int, metavar="N",
                   help="trunks fitted, 0-8: the first N")
    p.add_argument("--check", action="store_true",
                   help="load and validate the script, then exit")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)-8s %(message)s", datefmt="%H:%M:%S",
        stream=sys.stdout)

    try:
        cfg = Config.load(args.config)
    except (OSError, ValueError) as e:
        print(f"configuration: {e}", file=sys.stderr)
        return 2
    if args.script:
        cfg.script = args.script
    if args.broker:
        cfg.broker_host = args.broker
    if args.stations is not None:
        cfg.stations = args.stations
    if args.trunks is not None:
        cfg.trunks = args.trunks
    try:
        cfg.check()
    except ValueError as e:
        print(f"configuration: {e}", file=sys.stderr)
        return 2

    if args.check:
        try:
            gs = build(cfg.resolved("script"), cfg.resolved("wav_dir"))
        except ScriptError as e:
            print(f"{e.path}: {len(e.failures)} problem(s)", file=sys.stderr)
            for f in e.failures:
                print(f"  {f}", file=sys.stderr)
            return 1
        gs, left_out = fit(gs, cfg.stations, len(cfg.working_trunks()), cfg.stations_out())
        for w in left_out:
            print(f"  left out: {w}")
        for kind in ("trunks", "stations"):
            for n, why in sorted((cfg.out_of_service.get(kind) or {}).items(),
                                 key=lambda kv: int(kv[0])):
                print(f"  {kind[:-1]} {n} out of service: {why}")
        print(f"{cfg.resolved('script')}: {len(gs.scenes)} active scenes "
              f"of {len(gs.script.scenes)}, "
              f"{len(gs.deck_scenes())} in the deck, "
              f"{sum(1 for j in gs.jacks if j.circuit)} jacks cabled")
        print(f"tutor (§7): {len(gs.tutor) + len(gs.tutor_missing)} lines, "
              f"{len(gs.tutor_missing)} with no wav")
        return 0

    return asyncio.run(run(cfg))


if __name__ == "__main__":
    raise SystemExit(main())

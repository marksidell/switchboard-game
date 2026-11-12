# The game program

`game_control.md` is the specification; `mqtt.md` owns the topics. Runs on
the game host as a systemd service, as the user `sbgame`.

```text
sbgame/board.py        the switchboard and the audio program, from MQTT
sbgame/link.py         the connection: reconnect, will and birth, heartbeat
sbgame/scenes.py       say/hear and the scene helpers
sbgame/flows.py        the five call shapes
sbgame/dialling.py     a number read off a trunk, for flows and free calls
sbgame/freecall.py     free calls, Lenny mode
sbgame/cue.py          the ring cue on the loudspeaker
sbgame/diag.py         diagnostics from the page
sbgame/sweep.py        board sweeps
sbgame/config.py       the configuration, game.toml
sbgame/script_data.py  script.yml resolved into scenes, wavs and the jack map
sbgame/deck.py         which scene comes next (4.4)
sbgame/pacing.py       tutor, manual, auto and listen, and the ramp (4.1-4.3)
sbgame/calls.py        the eight slots, the stages, the tallies (5, 6.1)
sbgame/gamelog.py      the page's log (6.2)
sbgame/session.py      the SQLite record
sbgame/game.py         start, stop, dealing, page commands (3-8)
sbgame/tutor.py        tutor mode's voice on the loudspeaker (4.9)
sbgame/main.py         the entry point
sbgame/simulate.py     a stand-in for the hardware, until the boards arrive
sbgame/streamdeck.py   the Stream Deck+ that carries the controls (7.4)
web/                   the status page (2, 7)
```

## Running it

```sh
sudo systemctl status sbgame          # it is a service
sudo journalctl -u sbgame -f
/opt/sbgame/venv/bin/sbgame --check   # validate script.yml and exit
```

After changing anything it runs — `script.yml`, `wav/`, the engine, the
loader in `tts/`, or the page — release the checkout and restart:

```sh
./release        # from the top of the repo
```

It installs the two private voices if `private/` is present; `./release --public`
leaves them out (`docs/tts_task.md` §5.1).

The daemon runs its own installed copies: the code in `/opt/sbgame/venv`, and
`script.yml` and the wavs under `/srv/sbgame`, because it cannot read the
checkout in a home directory. `release` installs all three and the page, checks the
installed script before restarting, and leaves the running daemon alone if the
check fails. Copying `script.yml` alone (`make -C host sbgame-data`) is not
enough when its form has changed, since the installed loader is the one that
reads it. The Home Screen page picks up a new build by itself when it next
comes into view.

**While the switchboard is being built** (game_control.md §12.2), tell the game
how many circuits exist: `stations` and `trunks` in `host/etc/sbgame/game.toml`
(installed to `/etc/sbgame/game.toml` by `./release`), or `--stations N` and
`--trunks N` on the command line, which override the file. Scenes that need a
station above N, or an outside line with no trunk, are left out and named in
the log at start; `--check` lists them too:

```sh
/opt/sbgame/venv/bin/sbgame --check -c /etc/sbgame/game.toml --stations 8 --trunks 2
```

**Tutor mode** (game_control.md §7) is the pacing Tutor. It is
refused, on the page's error line, until every one of the tutor's lines has a
wav in `/srv/sbgame/wav`; `tts/README.md` has how to make them.

## The Stream Deck

`sbgame-streamdeck` is a separate service, `sbgame-streamdeck`, running from
the same venv as the user `sbgame-deck`; `host/README.md` has the one-time
setup. It needs `libhidapi-libusb0` from apt. `./release` restarts it if it is
running.

Without a deck, `--fake DIR` writes the eight keys and the strip as PNGs
instead, which is how to see a layout change before it reaches the deck:

```sh
engine/.venv/bin/sbgame-streamdeck --fake /tmp/deck \
    --user sbgame-web --password-file /etc/sbgame/mqtt-web.pass
```

As `sbgame-web` it has the same rights it will have as `sbgame-deck`.

## Testing the boards without the switchboard

Cable the trunk board straight to one station board, trunk n to its n-th
station, and:

```sh
engine/.venv/bin/sbgame-boardtest --stations a      # a = 1-8, b = 9-16, c = 17-22
engine/.venv/bin/sbgame-boardtest --stations c --no-audio
```

One pair at a time it rings the station from the trunk, takes the station
off-hook and looks for the trunk's seizure, checks the two hear each other's
pilot, has the station dial 1 to 0 and checks the trunk decodes every digit
without losing the seizure, and puts it back on-hook; every other channel must
stay idle throughout. The controller times the dial pulses (control.md §7.3),
so it needs firmware with `dial/set`. Board c has six stations, since its strips 7 and 8 are the tap and
the monitor. It needs the controller and the audio program online
(`--no-audio` needs only the controller) and no game running, and sends the
game program's heartbeat itself if the game program is not there, since the
controller releases every relay without one. `tests/test_boardtest.py` runs it
against simulated boards.

## Without the boards

With no controller and no audio program the game
starts, deals a call and stops at once — every scene wait fails while a client
it needs is down, and `game_control.md` §2 stops the game when one goes. That
is correct, and it makes the page untestable, so there is a stand-in:

```sh
./run-sim -o      # it answers and connects the calls too
./run-sim         # the boards only; nothing works the board
```

It reads `/etc/sbgame/game.toml`, the same file the daemon uses, and connects
as `sbgame-audio` — the controller's password is compiled into the firmware
and is not on the host, and the access list gives the two the same rights.
Foreground, Ctrl-C to stop; it is a tool, not a service.

**It is not the bench.** No dial pulse timing, no ring cadence, no seizure
debounce, nothing electrical. It exists so the page and the game program can
be exercised, and so a scene can be watched end to end.

## Tests

The tests run under a checkout venv, not the installed one. Once, from the top
of the repo (editable, so edits to `engine/` and `tts/` take effect at once):

```sh
python3 -m venv engine/.venv && engine/.venv/bin/pip install -e 'engine[test]' -e tts
```

`sbgame` imports `tts`, the `script.yml` loader in this repository's `tts/`,
which is why both are installed; it is not on PyPI, so `pyproject.toml` cannot
list it. Then, from `engine/`:

```sh
.venv/bin/pytest
```

`pyproject.toml` puts the checkout's own `sbgame` and `tts` first on the path,
so the tests see the working tree whatever the venv has installed. No
hardware and no broker: `test_live.py` starts its own `mosquitto` on port
18830, and is skipped without one; the JavaScript parse in `test_web.py` needs
`gjs`, and is skipped without it. `tests/harness.py` is the simulated
controller and audio program the others share.

`test_streamdeck.py` checks every rule of §10 — keys, Stop's second press,
Next Call's guard, the dials' target, errors, staleness — and draws each state
once. `test_sim.py` covers say/hear and the Board. `test_flows.py` covers every
scene shape and every failure reason. `test_game.py` drives whole games against
the real `script.yml`. `test_web.py` parses the page's JavaScript with gjs and
checks the service worker's cache list — a 404 in that list poisons the cache.

None of it has met hardware. When the boards arrive, expect the simulator to
have been wrong about something.

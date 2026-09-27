"""The SQLite session log — the record, where game/log is only a display.

One row per game in `sessions`, one per call in `calls`, one per event in
`events`, and the deck's seed and every shuffled order in `decks` so a game can
be replayed (game_control.md §4.4).

Every call here goes through `asyncio.to_thread`. sqlite3 blocks, and rule 4 of
the handover is that nothing on the event loop may: a blocked loop stops the
heartbeat, and two missed beats make the controller release every relay. This
is the reason the writes are queued in a task rather than awaited from a flow —
a flow that waited on a disk write would hold up its own call for it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("session")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id        INTEGER PRIMARY KEY,
    started   REAL NOT NULL,
    ended     REAL,
    why       TEXT,               -- 'stop', 'client lost', or the client's name
    seed      INTEGER NOT NULL,
    pace      TEXT, gap REAL, ramp REAL, floor REAL,
    jitter    REAL,               -- percent; added with game_control.md Rev 12
    pause     REAL,               -- listen's wait; added with Rev 17
    started_n INTEGER DEFAULT 0,
    success   INTEGER DEFAULT 0,
    fail      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS calls (
    id        INTEGER PRIMARY KEY,
    session   INTEGER NOT NULL REFERENCES sessions(id),
    number    INTEGER NOT NULL,
    scene     TEXT NOT NULL,
    from_line TEXT, to_line TEXT, trunk TEXT,
    started   REAL NOT NULL,
    connected REAL,               -- when it reached the 4.3 milestone, or null
    ended     REAL,
    outcome   TEXT,               -- 'success', or 5's reason
    digits    TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY,
    session   INTEGER NOT NULL REFERENCES sessions(id),
    call      INTEGER,            -- the call number, not the row id
    t         REAL NOT NULL,
    text      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decks (
    id        INTEGER PRIMARY KEY,
    session   INTEGER NOT NULL REFERENCES sessions(id),
    n         INTEGER NOT NULL,   -- 1 for the first deck, 2 after the first reshuffle
    order_    TEXT NOT NULL       -- JSON list of scene ids
);
CREATE INDEX IF NOT EXISTS events_session ON events(session);
CREATE INDEX IF NOT EXISTS calls_session ON calls(session);
"""


class SessionLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._db: sqlite3.Connection | None = None
        self.session_id: int | None = None
        # Writes go through one queue and one task, so the order is the order
        # they happened and no flow ever waits on the disk.
        self._q: asyncio.Queue[tuple] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await asyncio.to_thread(self._connect)
        self._task = asyncio.create_task(self._drain(), name="session-log")
        log.info("session log at %s", self.path)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, check_same_thread=False)
        db.executescript(SCHEMA)
        # CREATE IF NOT EXISTS leaves an older table as it was. Columns added
        # since are added here, so an existing record keeps its games.
        have = {r[1] for r in db.execute("PRAGMA table_info(sessions)")}
        if "jitter" not in have:
            db.execute("ALTER TABLE sessions ADD COLUMN jitter REAL")
        if "pause" not in have:
            db.execute("ALTER TABLE sessions ADD COLUMN pause REAL")
        db.commit()
        return db

    async def close(self) -> None:
        if self._task:
            await self._q.join()
            self._task.cancel()
            self._task = None
        if self._db:
            await asyncio.to_thread(self._db.close)
            self._db = None

    async def _drain(self) -> None:
        while True:
            sql, args = await self._q.get()
            try:
                if self._db is not None:
                    await asyncio.to_thread(self._write, sql, args)
            except Exception:
                # A failed write must not take the game down. It is the record,
                # and losing a line of it is better than stopping a player's game.
                log.exception("session log write failed")
            finally:
                self._q.task_done()

    def _write(self, sql: str, args: tuple) -> None:
        assert self._db is not None
        self._db.execute(sql, args)
        self._db.commit()

    def _queue(self, sql: str, *args) -> None:
        self._q.put_nowait((sql, args))

    # ---- the game's calls ------------------------------------------------

    async def start_game(self, seed: int, pace: str, gap: float, ramp: float,
                         floor: float, jitter: float = 0.0, pause: float = 3.0) -> int:
        """Synchronous, because everything after it needs the session id."""
        assert self._db is not None
        cur = await asyncio.to_thread(
            self._db.execute,
            "INSERT INTO sessions (started, seed, pace, gap, ramp, floor, jitter, pause) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), seed, pace, gap, ramp, floor, jitter, pause))
        await asyncio.to_thread(self._db.commit)
        self.session_id = int(cur.lastrowid)
        return self.session_id

    async def end_game(self, why: str, started: int, success: int, fail: int) -> None:
        if self.session_id is None:
            return
        self._queue("UPDATE sessions SET ended=?, why=?, started_n=?, success=?, "
                    "fail=? WHERE id=?",
                    time.time(), why, started, success, fail, self.session_id)
        await self._q.join()          # the game is over; it can wait for this one
        self.session_id = None

    def deck(self, n: int, order: list[str]) -> None:
        if self.session_id is not None:
            self._queue("INSERT INTO decks (session, n, order_) VALUES (?,?,?)",
                        self.session_id, n, json.dumps(order))

    def call_started(self, number: int, scene: str, from_line: str, to_line: str) -> None:
        if self.session_id is not None:
            self._queue("INSERT INTO calls (session, number, scene, from_line, "
                        "to_line, started) VALUES (?,?,?,?,?,?)",
                        self.session_id, number, scene, from_line, to_line, time.time())

    def call_connected(self, number: int) -> None:
        if self.session_id is not None:
            self._queue("UPDATE calls SET connected=? WHERE session=? AND number=?",
                        time.time(), self.session_id, number)

    def call_ended(self, number: int, outcome: str, trunk: str = "",
                   digits: str = "") -> None:
        if self.session_id is not None:
            self._queue("UPDATE calls SET ended=?, outcome=?, trunk=?, digits=? "
                        "WHERE session=? AND number=?",
                        time.time(), outcome, trunk, digits, self.session_id, number)

    def event(self, text: str, call: int | None = None) -> None:
        if self.session_id is not None:
            self._queue("INSERT INTO events (session, call, t, text) VALUES (?,?,?,?)",
                        self.session_id, call, time.time(), text)

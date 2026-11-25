"""Which scene comes next (game_control.md §6.1).

Every scene without `after:` is shuffled into a list at game start and dealt
from, so every scene is played once before any is played twice, in an order
that differs from game to game. A scene whose lines or people are busy is
passed over and stays where it is, so it comes up at the next call rather than
being lost or stalling the deck behind it.

The busy test is what makes this more than a shuffle. A line is busy if it
belongs to a call in progress *or* to an `after:` scene that is waiting to
start — otherwise the deck could deal a scene using the very line a caller is
about to call back on. People are held the same way: one voice cannot be in
two calls at once.

A scene with `follows:` is passed over the same way while a scene it names is
still to come this round (§6.1), so a guest's story is dealt in order.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .script_data import GameScript, SceneDef


@dataclass
class Holding:
    """What a call or a waiting `after:` scene occupies while it lives."""
    lines: frozenset[str]
    people: frozenset[str]


class Deck:
    def __init__(self, gs: GameScript, seed: int | None = None) -> None:
        self.gs = gs
        # The seed goes in the SQLite session record so a game can be replayed
        # (§6.1). It is not published: the page is not told the order.
        self.seed = random.randrange(2**32) if seed is None else seed
        self._rng = random.Random(self.seed)
        self._cards: list[str] = []
        self._last_dealt = ""
        self.shuffles = 0
        self.orders: list[list[str]] = []   # every deck this game, for the record
        self._shuffle()

    def _shuffle(self) -> None:
        cards = self.gs.deck_scenes()
        self._rng.shuffle(cards)
        # No scene twice in a row across a reshuffle: if the new deck would
        # start with the one just dealt, move it to second place.
        if len(cards) > 1 and cards[0] == self._last_dealt:
            cards[0], cards[1] = cards[1], cards[0]
        self._cards = cards
        self.shuffles += 1
        self.orders.append(list(cards))

    def _free(self, scene: SceneDef, held: list[Holding]) -> bool:
        # A scene with if_busy: is dealt though its called line is busy (§6.6).
        lines = set(scene.needs)
        people = set(self.gs.needs_people(scene.id))
        for h in held:
            if lines & h.lines or people & h.people:
                return False
        return True

    def _to_come(self, sid: str, live: frozenset[str] | set[str]) -> bool:
        """Whether the scene can still play this round (§6.1): in the
        deck, in progress or waiting to start, or an `after:` scene whose
        predecessor is still to come. A chain has no loop (the loader's check)."""
        if sid in self._cards or sid in live:
            return True
        sc = self.gs.scenes.get(sid)
        return sc is not None and bool(sc.after) and self._to_come(sc.after, live)

    def _ready(self, scene: SceneDef, live: frozenset[str] | set[str]) -> bool:
        return not any(self._to_come(f, live) for f in scene.follows)

    def deal(self, held: list[Holding],
             live: frozenset[str] | set[str] = frozenset()) -> tuple[SceneDef | None, str]:
        """Take the first scene whose lines and people are all free, and
        whose `follows:` have all played. `live` is the scenes in progress or
        waiting to start.

        Returns the scene and "", or None and the reason nothing could be
        dealt — which the caller logs, and reports on game/error if the page
        asked for the call (§5.1).
        """
        if not self.gs.deck_scenes():
            return None, "no scenes in the script"

        # Two passes at most: the deck as it stands, then a fresh one if this
        # one is exhausted. Without the bound, an empty deck whose every scene
        # is busy would reshuffle forever.
        for _ in range(2):
            for i, sid in enumerate(self._cards):
                scene = self.gs.scenes[sid]
                if self._free(scene, held) and self._ready(scene, live):
                    del self._cards[i]
                    self._last_dealt = sid
                    return scene, ""
            if self._cards:
                # Some remain, all of them blocked. Do not reshuffle: they
                # keep their places and come up when the lines free.
                return None, ("every scene left in the deck is using a busy line"
                              " or waits for a scene still to come")
            self._shuffle()
        return None, "every scene is using a busy line"

    def take(self, scene: SceneDef, held: list[Holding]) -> bool:
        """Deal this scene next if it is free (§6.4), taking it out of
        the current deck so it does not come round again before the reshuffle."""
        if not self._free(scene, held):
            return False
        if scene.id in self._cards:
            self._cards.remove(scene.id)
        self._last_dealt = scene.id
        return True

    @property
    def left(self) -> list[str]:
        """The scenes still to deal from this shuffle, in order."""
        return list(self._cards)

    @property
    def remaining(self) -> int:
        return len(self._cards)

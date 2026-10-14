"""Which scene comes next (game_control.md §4.4).

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
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

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
        # (§4.4). It is not published: the page is not told the order.
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
        # A scene with if_busy: is dealt though its called line is busy (§4.11).
        lines = set(scene.needs)
        people = set(self.gs.needs_people(scene.id))
        for h in held:
            if lines & h.lines or people & h.people:
                return False
        return True

    def deal(self, held: list[Holding]) -> tuple[SceneDef | None, str]:
        """Take the first scene whose lines and people are all free.

        Returns the scene and "", or None and the reason nothing could be
        dealt — which the caller logs, and reports on game/error if the page
        asked for the call (§4.1).
        """
        if not self.gs.deck_scenes():
            return None, "no scenes in the script"

        # Two passes at most: the deck as it stands, then a fresh one if this
        # one is exhausted. Without the bound, an empty deck whose every scene
        # is busy would reshuffle forever.
        for _ in range(2):
            for i, sid in enumerate(self._cards):
                scene = self.gs.scenes[sid]
                if self._free(scene, held):
                    del self._cards[i]
                    self._last_dealt = sid
                    return scene, ""
            if self._cards:
                # Some remain, all of them blocked. Do not reshuffle: they
                # keep their places and come up when the lines free.
                return None, "every scene left in the deck is using a busy line"
            self._shuffle()
        return None, "every scene is using a busy line"

    def take(self, scene: SceneDef, held: list[Holding]) -> bool:
        """Deal this scene next if it is free (§4.8, Rev 25), taking it out of
        the current deck so it does not come round again before the reshuffle."""
        if not self._free(scene, held):
            return False
        if scene.id in self._cards:
            self._cards.remove(scene.id)
        self._last_dealt = scene.id
        return True

    @property
    def remaining(self) -> int:
        return len(self._cards)

"""A long-distance call's far voices (tts_task.md §7): who is how many hops away."""

from tts.script import far_hops, load

from harness import REPO


def test_far_voices_by_hop():
    """The toll operators in order, the far party at the last, Seattle near"""
    s = load(REPO / "script.yml")
    h = far_hops(s)
    who = {u.name: u.speaker for u in s.utterances}

    def at(scene: str) -> dict[str, set[int]]:
        out: dict[str, set[int]] = {}
        for n, v in h.items():
            if n.rsplit(".", 1)[0] == scene:
                out.setdefault(who[n], set()).add(v)
        return out

    assert at("beaumont-sister") == {"toll_b": {1}, "toll_d": {2}, "toll_c": {3}, "lucinda": {3}}, \
        f"Chicago, Atlanta, Savannah, and Lucinda as far as Savannah: {at('beaumont-sister')}"
    assert at("finch-wife") == {"toll_d": {1}, "toll_a": {2}, "edna_finch": {2}}, \
        "the same voice is as far as the scene puts it: toll_d is one hop here"
    assert at("ld-pike") == {"gruber": {1}}, "a call in, with no toll operator: the caller one hop away"
    assert at("dobbs-callback")["wilbur"] == {2}, "every far party, not only the one asked for"
    near = {"operator", "local_operator", "rate_operator", "hotel_operator"}
    assert not any(who[n] in near for n in h), "the Seattle operators are never far"
    assert not any(n.startswith(("tc-", "nbn-")) for n in h), "nor a time-and-charges call or a local one"

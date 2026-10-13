"""
The runs your test needs. ← UNIT 4, MILESTONE 3

Each of your five criteria needs something run against it. A criterion about
the empty-search branch needs an impossible query. One about the fit card needs
the same item run more than once. Working that out is Milestone 3's first step,
and this file is where you write it down.

`run_eval.py` runs everything here five times and writes the run log — five
because your criteria are written out of five.

Three scenarios are filled in to show the shape. Add or change whatever your
own criteria need — these are a starting point, not a fixed set.
"""

SCENARIOS = [
    {
        # A query the data can match. Criterion 1 — all three tools, a fit card.
        # A different item from criterion 4 so the two rows don't measure the
        # same run twice.
        "name": "matching query completes",
        "query": "90s track jacket in size M",
        "wardrobe": "example",
        "criterion": 1,
    },
    {
        # A query nothing can match. Criterion 2 — the branch.
        "name": "impossible query stops early",
        "query": "designer ballgown size XXS under $5",
        "wardrobe": "example",
        "criterion": 2,
    },
    {
        # Criterion 3 — the same item id all the way through the session, and
        # the fit card's price equal to session["selected_item"]["price"].
        "name": "selected item passed through the session",
        "query": "platform sneakers size 8",
        "wardrobe": "example",
        "criterion": 3,
    },
    {
        # Criterion 4 — the query criteria.md names, run five times: a title
        # word, the exact price and the platform in every fit card.
        "name": "fit card has title word, price, platform",
        "query": "vintage graphic tee under $30",
        "wardrobe": "example",
        "criterion": 4,
    },
    {
        # Criterion 5 — a price ceiling; every search result must be at or
        # under it.
        "name": "results stay within budget",
        "query": "vintage jeans under $35",
        "wardrobe": "example",
        "criterion": 5,
    },
    {
        # A user with nothing saved. One of unit 4's three failure modes.
        "name": "empty wardrobe",
        "query": "denim jacket under $50",
        "wardrobe": "empty",
        "criterion": None,
    },
    # ── Probes added in unit 4 after the before-run met every target ──────────
    # Not one of the five criteria. Each one checks something the five can't
    # see: whether the item the agent picked is the KIND of item that was asked
    # for. "expect" is a word that has to be in the selected item's title (or
    # the run has to stop at the empty-search branch). Search is deterministic,
    # so these isolate the search ranking from the model.
    {
        # Suede Chelsea Boots exist in the data ($44). Does the agent pick them?
        "name": "probe: colour word vs item type",
        "query": "black boots",
        "wardrobe": "example",
        "criterion": None,
        "expect": "boots",
    },
    {
        # Two jackets are within $45. Does the agent pick a jacket?
        "name": "probe: material word vs item type",
        "query": "leather jacket under $45",
        "wardrobe": "example",
        "criterion": None,
        "expect": "jacket",
    },
    {
        # No ballgown exists. The right answer is the empty-search branch.
        "name": "probe: impossible item with a common colour",
        "query": "black ballgown",
        "wardrobe": "example",
        "criterion": None,
        "expect": "ballgown",
    },
]

WARDROBES = ("example", "empty")


def validate() -> list[str]:
    """Complain about anything malformed, before a long run rather than during."""
    problems = []
    for i, scenario in enumerate(SCENARIOS, 1):
        if not scenario.get("query", "").strip():
            problems.append(f"scenario {i} has no query")
        if scenario.get("wardrobe") not in WARDROBES:
            problems.append(
                f"scenario {i} has wardrobe {scenario.get('wardrobe')!r} — "
                f"it should be one of {WARDROBES}"
            )
    return problems

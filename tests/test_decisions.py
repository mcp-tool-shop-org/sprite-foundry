"""decisions.canonical_winners tests (backend F-005).

The fix replaced list-index ranking (max(..., key=LIFECYCLE_STATES.index)) with
an explicit PROGRESS_RANK map. The bug: a rejected/superseded attempt could
outrank an in-progress one because of declaration order. These tests assert:

- when a finish_accepted attempt exists, it is the winner and siblings are
  listed as defeated with their fail reasons;
- when there is NO winner, the "best so far" is the furthest-PROGRESSED attempt,
  NOT a rejected/superseded sibling (the core of the F-005 fix);
- an empty direction reports winner=None.
"""

import pytest

from foundry import decisions


@pytest.fixture
def base(registry):
    registry.subject()
    registry.run()
    return registry


def _front(winners):
    return next(w for w in winners if w["direction"] == "front")


def test_finish_accepted_is_the_winner(base, db_conn):
    win = base.attempt(direction="front", state="finish_accepted")
    base.attempt(direction="front", state="rejected")
    result = _front(decisions.canonical_winners(db_conn, "run1"))
    assert result["winner"] is not None
    assert result["winner"]["id"] == win
    # The rejected sibling is listed as defeated.
    assert any(d["state"] == "rejected" for d in result["defeated"])


def test_progress_rank_prefers_in_progress_over_superseded(base, db_conn):
    """A superseded attempt (rank -2) must never be picked as 'best so far' over
    a still-progressing attempt. With the old LIFECYCLE_STATES.index ranking,
    'superseded' (last in the list) would have ranked HIGHEST and won — this is
    the exact regression PROGRESS_RANK fixes."""
    # No finish_accepted exists, so the fallback "best so far" branch runs.
    superseded = base.attempt(direction="front", state="superseded")
    in_progress = base.attempt(direction="front", state="accepted")  # rank 5
    result = _front(decisions.canonical_winners(db_conn, "run1"))
    assert result["winner"] is None
    # Explanation must name the in-progress attempt, not the superseded one.
    assert f"#{in_progress}" in result["explanation"]
    assert f"#{superseded}" not in result["explanation"].split("best is")[-1]


def test_progress_rank_prefers_in_progress_over_rejected(base, db_conn):
    rejected = base.attempt(direction="front", state="rejected")  # rank -1
    in_progress = base.attempt(direction="front", state="raw_accepted")  # rank 3
    result = _front(decisions.canonical_winners(db_conn, "run1"))
    assert result["winner"] is None
    assert f"#{in_progress}" in result["explanation"]
    assert "raw_accepted" in result["explanation"]
    assert str(rejected) not in result["explanation"].split("best is")[-1]


def test_furthest_progressed_among_in_progress_wins(base, db_conn):
    early = base.attempt(direction="front", state="mechanical_pass")  # rank 1
    later = base.attempt(direction="front", state="finish_review_pending")  # rank 6
    result = _front(decisions.canonical_winners(db_conn, "run1"))
    assert f"#{later}" in result["explanation"]
    assert "finish_review_pending" in result["explanation"]
    assert str(early) not in result["explanation"].split("best is")[-1]


def test_empty_direction_has_no_winner(base, db_conn):
    # No attempts at all for any direction.
    winners = decisions.canonical_winners(db_conn, "run1")
    result = _front(winners)
    assert result["winner"] is None
    assert "no attempts" in result["explanation"]


def test_no_crash_on_any_valid_lifecycle_state(base, db_conn):
    """canonical_winners must never crash on any state present in the lifecycle —
    the old code could ValueError if a state wasn't in LIFECYCLE_STATES; the new
    PROGRESS_RANK.get(..., -3) default makes it total over the enum."""
    from foundry import db
    for i, state in enumerate(db.LIFECYCLE_STATES):
        # one attempt per state, spread across directions to dodge the unique
        # finish_accepted index.
        base.attempt(direction=db.DIRECTIONS[i % len(db.DIRECTIONS)], state=state)
    # Should not raise.
    winners = decisions.canonical_winners(db_conn, "run1")
    assert len(winners) == len(db.DIRECTIONS)

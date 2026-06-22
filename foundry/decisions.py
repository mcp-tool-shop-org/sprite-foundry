"""
Phase 2D — Decision projections.

Assembles attempt stories, winner explanations, lineage summaries, and
failure patterns from DB truth. Pure read-only projections — no mutations.
"""

import sqlite3
from . import db


# ── 2D.1: Attempt Story ────────────────────────────────────

def attempt_story(conn: sqlite3.Connection, attempt_id: int) -> dict:
    """
    Reconstruct the full story of a single attempt.

    Returns a dict with: attempt info, timeline of events (gates, reviews,
    state transitions), artifacts, finish captures, and lineage context.
    """
    attempt = conn.execute(
        """SELECT a.*, r.subject_id, r.stack, r.seed as run_seed,
                  r.gen_width, r.gen_height, r.sprite_target,
                  s.display_name
           FROM attempts a
           JOIN runs r ON a.run_id = r.id
           JOIN subjects s ON r.subject_id = s.id
           WHERE a.id = ?""",
        (attempt_id,),
    ).fetchone()
    if not attempt:
        raise ValueError(f"Attempt {attempt_id} not found")

    attempt = dict(attempt)

    # Collect all events into a unified timeline
    timeline = []

    # Creation event
    timeline.append(dict(
        timestamp=attempt["created_at"],
        event="created",
        detail=f"seed={attempt['seed']}",
    ))
    if attempt["parent_attempt_id"]:
        timeline[-1]["detail"] += f", regen of #{attempt['parent_attempt_id']}: {attempt['regen_reason']}"
        if attempt["regen_note"]:
            timeline[-1]["detail"] += f" ({attempt['regen_note']})"

    # Gate results
    gates = db.get_attempt_gates(conn, attempt_id)
    for g in gates:
        timeline.append(dict(
            timestamp=g["created_at"],
            event=f"gate:{g['gate_name']}",
            detail=f"{g['result']} — measured={g['measured']}, expected={g['expected']}",
        ))

    # Reviews
    reviews = db.get_attempt_reviews(conn, attempt_id)
    for r in reviews:
        detail = f"{r['decision']}"
        if r["code"]:
            detail += f" [{r['code']}]"
        if r["note"]:
            detail += f" — {r['note']}"
        detail += f" (by {r['reviewer']})"
        timeline.append(dict(
            timestamp=r["created_at"],
            event=f"review:{r['review_type']}",
            detail=detail,
        ))

    # Finish captures
    captures = conn.execute(
        "SELECT lighting_state, created_at FROM finish_captures WHERE attempt_id = ? ORDER BY created_at",
        (attempt_id,),
    ).fetchall()
    for c in captures:
        timeline.append(dict(
            timestamp=c["created_at"],
            event="finish_capture",
            detail=c["lighting_state"],
        ))

    # Child regens (forward links)
    children = conn.execute(
        "SELECT id, state, regen_reason, created_at FROM attempts WHERE parent_attempt_id = ? ORDER BY id",
        (attempt_id,),
    ).fetchall()
    for child in children:
        timeline.append(dict(
            timestamp=child["created_at"],
            event="child_created",
            detail=f"#{child['id']} (reason: {child['regen_reason']}, now: {child['state']})",
        ))

    # Sort by timestamp
    timeline.sort(key=lambda e: e["timestamp"])

    # Artifacts
    artifacts = db.get_attempt_artifacts(conn, attempt_id)

    # Lineage (ancestors)
    lineage = db.get_attempt_lineage(conn, attempt_id)

    return dict(
        attempt=attempt,
        timeline=timeline,
        gates=gates,
        reviews=reviews,
        artifacts=artifacts,
        lineage=lineage,
        children=[dict(c) for c in children],
    )


# ── 2D.2: Lineage Chain ────────────────────────────────────

def direction_lineage(conn: sqlite3.Connection, run_id: str, direction: str) -> list[dict]:
    """
    Get all attempts for a direction in a run, ordered by creation.

    Each entry includes: attempt info, gate summary, review summary,
    why it was rejected/superseded, and whether it's the current winner.
    """
    attempts = conn.execute(
        """SELECT id, direction, state, seed, parent_attempt_id,
                  regen_reason, regen_note, created_at
           FROM attempts
           WHERE run_id = ? AND direction = ?
           ORDER BY id""",
        (run_id, direction),
    ).fetchall()

    chain = []
    for a in attempts:
        a = dict(a)
        aid = a["id"]

        # Gate summary
        gates = db.get_attempt_gates(conn, aid)
        gate_pass = sum(1 for g in gates if g["result"] == "pass")
        gate_fail = sum(1 for g in gates if g["result"] == "fail")
        gate_fail_names = [g["gate_name"] for g in gates if g["result"] == "fail"]

        # Review summary
        reviews = db.get_attempt_reviews(conn, aid)
        reject_codes = [r["code"] for r in reviews if r["decision"] in ("fail", "reject") and r["code"]]
        accept_types = [r["review_type"] for r in reviews if r["decision"] in ("pass", "accept")]

        # Is this the winner?
        is_winner = a["state"] == "finish_accepted"

        chain.append(dict(
            **a,
            gate_pass=gate_pass,
            gate_fail=gate_fail,
            gate_fail_names=gate_fail_names,
            reject_codes=reject_codes,
            accept_types=accept_types,
            is_winner=is_winner,
        ))

    return chain


def run_lineage_summary(conn: sqlite3.Connection, run_id: str) -> dict:
    """
    Full lineage summary for a run: every direction's chain with winner highlighted.
    """
    run = conn.execute(
        "SELECT r.*, s.display_name FROM runs r JOIN subjects s ON r.subject_id = s.id WHERE r.id = ?",
        (run_id,),
    ).fetchone()
    if not run:
        raise ValueError(f"Run '{run_id}' not found")

    directions = {}
    for d in db.DIRECTIONS:
        chain = direction_lineage(conn, run_id, d)
        directions[d] = chain

    return dict(
        run=dict(run),
        directions=directions,
    )


# ── 2D.3: Canonical Winner Query ───────────────────────────

# Explicit lifecycle PROGRESS rank for "best so far" selection. Unlike the
# declaration order of db.LIFECYCLE_STATES, this is monotonic *only* along the
# success path; fail/terminal/superseded states get low/negative ranks so a
# rejected or superseded attempt never outranks one still progressing.
PROGRESS_RANK = {
    "generated": 0,
    "mechanical_pass": 1,
    "raw_review_pending": 2,
    "raw_accepted": 3,
    "pixel_review_pending": 4,
    "accepted": 5,
    "finish_review_pending": 6,
    "finish_accepted": 7,
    # Terminal-fail and superseded: never "best" while anything is in progress.
    "mechanical_fail": -1,
    "raw_rejected": -1,
    "rejected": -1,
    "finish_rejected": -1,
    "superseded": -2,
}


def canonical_winners(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    """
    For each direction, return the canonical winner with explanation.

    Returns: direction, winner attempt, what it beat, why alternatives lost.
    """
    winners = []

    for direction in db.DIRECTIONS:
        attempts = conn.execute(
            """SELECT id, state, seed, parent_attempt_id, regen_reason, created_at
               FROM attempts
               WHERE run_id = ? AND direction = ?
               ORDER BY id""",
            (run_id, direction),
        ).fetchall()

        if not attempts:
            winners.append(dict(
                direction=direction,
                winner=None,
                explanation="no attempts registered",
                defeated=[],
            ))
            continue

        winner = None
        defeated = []

        for a in attempts:
            a = dict(a)
            if a["state"] == "finish_accepted":
                winner = a
            else:
                # Collect why this one lost
                reviews = db.get_attempt_reviews(conn, a["id"])
                gates = db.get_attempt_gates(conn, a["id"])

                fail_reasons = []
                for r in reviews:
                    if r["decision"] in ("fail", "reject") and r["code"]:
                        fail_reasons.append(f"{r['review_type']}:{r['code']}")
                for g in gates:
                    if g["result"] == "fail":
                        fail_reasons.append(f"gate:{g['gate_name']}")

                defeated.append(dict(
                    id=a["id"],
                    state=a["state"],
                    fail_reasons=fail_reasons or [a["state"]],
                ))

        if winner:
            # Build explanation
            winner_reviews = db.get_attempt_reviews(conn, winner["id"])
            accept_trail = [
                f"{r['review_type']}:{r['decision']}"
                for r in winner_reviews
                if r["decision"] in ("pass", "accept")
            ]

            explanation = f"#{winner['id']} passed all stages: {', '.join(accept_trail)}"
            if defeated:
                beaten = [f"#{d['id']} ({'; '.join(d['fail_reasons'])})" for d in defeated]
                explanation += f" | defeated: {', '.join(beaten)}"
        else:
            # No winner yet — find the furthest-advanced attempt by PROGRESS
            # rank (not list position), breaking ties by most-recent creation so
            # the latest in-progress attempt wins among equal-rank states.
            best = max(
                attempts,
                key=lambda a: (PROGRESS_RANK.get(a["state"], -3), a["created_at"]),
            )
            explanation = f"no winner yet — best is #{best['id']} at {best['state']}"

        winners.append(dict(
            direction=direction,
            winner=dict(winner) if winner else None,
            explanation=explanation,
            defeated=defeated,
        ))

    return winners


# ── 2D.4: Failure Summary ──────────────────────────────────

def failure_summary(conn: sqlite3.Connection, run_id: str = None) -> dict:
    """
    Lightweight failure/drift report.

    If run_id is given, scoped to that run. Otherwise, foundry-wide.

    Returns: top reject codes, top gate failures, pass rates by stage,
    regen reasons.
    """
    where = ""
    params = ()
    if run_id:
        where = "WHERE a.run_id = ?"
        params = (run_id,)

    # Reject codes
    reject_rows = conn.execute(
        f"""SELECT r.code, COUNT(*) as cnt
            FROM reviews r
            JOIN attempts a ON r.attempt_id = a.id
            {where.replace('a.run_id', 'a.run_id') if where else ''}
            {"AND" if where else "WHERE"} r.decision IN ('fail', 'reject') AND r.code IS NOT NULL
            GROUP BY r.code ORDER BY cnt DESC""",
        params,
    ).fetchall()
    top_reject_codes = [dict(r) for r in reject_rows]

    # Gate failures
    gate_rows = conn.execute(
        f"""SELECT g.gate_name, COUNT(*) as cnt
            FROM gate_results g
            JOIN attempts a ON g.attempt_id = a.id
            {where}
            {"AND" if where else "WHERE"} g.result = 'fail'
            GROUP BY g.gate_name ORDER BY cnt DESC""",
        params,
    ).fetchall()
    top_gate_failures = [dict(r) for r in gate_rows]

    # Pass rate by review stage
    stage_rows = conn.execute(
        f"""SELECT r.review_type,
                   SUM(CASE WHEN r.decision IN ('pass', 'accept') THEN 1 ELSE 0 END) as passes,
                   SUM(CASE WHEN r.decision IN ('fail', 'reject') THEN 1 ELSE 0 END) as failures,
                   COUNT(*) as total
            FROM reviews r
            JOIN attempts a ON r.attempt_id = a.id
            {where}
            GROUP BY r.review_type""",
        params,
    ).fetchall()
    pass_rates = []
    for s in stage_rows:
        s = dict(s)
        s["pass_rate"] = f"{s['passes'] / max(s['total'], 1) * 100:.0f}%"
        pass_rates.append(s)

    # Regen reasons
    regen_rows = conn.execute(
        f"""SELECT a.regen_reason, COUNT(*) as cnt
            FROM attempts a
            {where.replace('a.run_id', 'a.run_id') if where else ''}
            {"AND" if where else "WHERE"} a.regen_reason IS NOT NULL
            GROUP BY a.regen_reason ORDER BY cnt DESC""",
        params,
    ).fetchall()
    regen_reasons = [dict(r) for r in regen_rows]

    # Attempt state distribution
    state_rows = conn.execute(
        f"""SELECT a.state, COUNT(*) as cnt
            FROM attempts a
            {where}
            GROUP BY a.state ORDER BY cnt DESC""",
        params,
    ).fetchall()
    state_dist = [dict(r) for r in state_rows]

    return dict(
        top_reject_codes=top_reject_codes,
        top_gate_failures=top_gate_failures,
        pass_rates=pass_rates,
        regen_reasons=regen_reasons,
        state_distribution=state_dist,
    )

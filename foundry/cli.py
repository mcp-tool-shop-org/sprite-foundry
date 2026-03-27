"""Foundry CLI — asset registry and review commands."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_file(path: Path) -> str:
    """SHA256 hash of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# -- foundry init ---------------------------------------------

def cmd_init(args):
    """Initialize the foundry database."""
    conn = db.init_db()
    print(f"Foundry database initialized: {db.DB_PATH}")
    conn.close()


# -- foundry subject add -------------------------------------

def cmd_subject_add(args):
    """Register a subject in the foundry."""
    conn = db.init_db()

    # Check for duplicate
    existing = conn.execute("SELECT id FROM subjects WHERE id = ?", (args.id,)).fetchone()
    if existing:
        print(f"Subject '{args.id}' already exists.")
        conn.close()
        return

    conn.execute(
        """INSERT INTO subjects (id, display_name, role, consumer, subject_sheet_path, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (args.id, args.name, args.role, args.consumer, args.sheet, now_iso()),
    )
    conn.commit()
    print(f"Subject registered: {args.id} ({args.name})")
    conn.close()


# -- foundry register-run -------------------------------------

def cmd_register_run(args):
    """Register an existing generation run (for backfilling Phase 1 survivors)."""
    conn = db.init_db()

    # Verify subject exists
    subj = conn.execute("SELECT id FROM subjects WHERE id = ?", (args.subject,)).fetchone()
    if not subj:
        print(f"Error: subject '{args.subject}' not found. Register it first.")
        conn.close()
        sys.exit(1)

    # Check for duplicate run
    existing = conn.execute("SELECT id FROM runs WHERE id = ?", (args.run_id,)).fetchone()
    if existing:
        print(f"Run '{args.run_id}' already registered.")
        conn.close()
        return

    # Hash subject sheet if it exists
    sheet_hash = None
    subj_row = conn.execute(
        "SELECT subject_sheet_path FROM subjects WHERE id = ?", (args.subject,)
    ).fetchone()
    if subj_row and subj_row["subject_sheet_path"]:
        sheet_path = db.FOUNDRY_ROOT / subj_row["subject_sheet_path"]
        if sheet_path.exists():
            sheet_hash = hash_file(sheet_path)

    # Load recipe if provided
    recipe_json = None
    if args.recipe:
        recipe_path = Path(args.recipe)
        if recipe_path.exists():
            recipe_json = recipe_path.read_text()

    conn.execute(
        """INSERT INTO runs (id, subject_id, stack, seed, gen_width, gen_height,
                             sprite_target, prompt_hash, subject_sheet_hash, recipe_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (args.run_id, args.subject, args.stack, args.seed,
         args.width, args.height, args.target, args.prompt_hash,
         sheet_hash, recipe_json, now_iso()),
    )
    conn.commit()
    print(f"Run registered: {args.run_id}")
    conn.close()


# -- foundry register-attempt ---------------------------------

def cmd_register_attempt(args):
    """Register an attempt (direction within a run) and its artifacts."""
    conn = db.init_db()

    # Verify run exists
    run = conn.execute("SELECT id FROM runs WHERE id = ?", (args.run_id,)).fetchone()
    if not run:
        print(f"Error: run '{args.run_id}' not found.")
        conn.close()
        sys.exit(1)

    cursor = conn.execute(
        """INSERT INTO attempts (run_id, direction, seed, state, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (args.run_id, args.direction, args.seed, args.state or "generated", now_iso()),
    )
    attempt_id = cursor.lastrowid

    # Register artifacts if paths provided
    artifact_count = 0
    for kind, path_str in (args.artifacts or []):
        p = Path(path_str).resolve()
        if not p.exists():
            print(f"  Warning: artifact not found: {p}")
            continue

        # Get dimensions for images
        width, height = None, None
        try:
            from PIL import Image
            with Image.open(p) as img:
                width, height = img.size
        except Exception:
            pass

        # Store as relative path if inside foundry root, otherwise absolute
        try:
            rel_path = str(p.relative_to(db.FOUNDRY_ROOT.resolve()))
        except ValueError:
            rel_path = str(p)

        conn.execute(
            """INSERT INTO artifacts (attempt_id, kind, path, width, height, hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (attempt_id, kind, rel_path, width, height, hash_file(p), now_iso()),
        )
        artifact_count += 1

    conn.commit()
    print(f"Attempt {attempt_id} registered: {args.direction} [{args.state or 'generated'}] ({artifact_count} artifacts)")
    conn.close()


# -- foundry check --------------------------------------------

def _resolve_body_class(subject_id: str) -> str | None:
    """Look up body_class from the character config JSON, if it exists."""
    config_path = db.FOUNDRY_ROOT / "pipeline" / "chars" / f"{subject_id}.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
            return config.get("body_class")
        except (json.JSONDecodeError, OSError):
            pass
    return None


def cmd_check(args):
    """Run mechanical gates on a run's attempts with durable evidence."""
    from . import mechanical

    conn = db.init_db()

    run = conn.execute("SELECT id, subject_id, sprite_target FROM runs WHERE id = ?", (args.run_id,)).fetchone()
    if not run:
        print(f"Run '{args.run_id}' not found.")
        conn.close()
        sys.exit(1)

    target = run["sprite_target"]
    body_class = _resolve_body_class(run["subject_id"])
    if body_class:
        print(f"  Body class: {body_class} (gate thresholds adjusted)")

    attempts = conn.execute(
        "SELECT id, direction, state FROM attempts WHERE run_id = ? ORDER BY direction",
        (args.run_id,),
    ).fetchall()

    if not attempts:
        print(f"No attempts found for run '{args.run_id}'.")
        conn.close()
        return

    # Direction count gate (run-level, not per-attempt)
    dir_count = len(set(a["direction"] for a in attempts))
    if dir_count < 8:
        print(f"  WARNING: only {dir_count}/8 directions registered for this run")

    pass_count = 0
    fail_count = 0

    for attempt in attempts:
        attempt_id = attempt["id"]
        direction = attempt["direction"]

        # Skip attempts not in 'generated' state (already checked or advanced)
        if attempt["state"] != "generated":
            print(f"  [{direction}] SKIP -- state is '{attempt['state']}', not 'generated'")
            continue

        # Run all gates — body_class relaxes thresholds for monster sprites
        gate_results = mechanical.run_all_gates(conn, attempt_id, target, body_class=body_class)

        # Store every gate result durably
        for gr in gate_results:
            db.add_gate_result(
                conn,
                attempt_id=attempt_id,
                gate_name=gr["gate_name"],
                result=gr["result"],
                measured=gr["measured"],
                expected=gr["expected"],
                artifact_kind=gr.get("artifact_kind"),
                artifact_path=gr.get("artifact_path"),
            )

        # Collect failures
        failures = [gr for gr in gate_results if gr["result"] == "fail"]
        fail_codes = [
            mechanical.GATE_FAIL_CODES.get(gr["gate_name"], gr["gate_name"])
            for gr in failures
        ]

        # Record mechanical review (append-only)
        if failures:
            for code in fail_codes:
                db.add_review(conn, attempt_id, "mechanical", "fail", "auto", code=code)
            db.transition_attempt(conn, attempt_id, "mechanical_fail")
            fail_count += 1
            print(f"  [{direction}] FAIL: {', '.join(fail_codes)}")
            for gr in failures:
                print(f"    {gr['gate_name']}: measured={gr['measured']}, expected={gr['expected']}")
        else:
            db.add_review(conn, attempt_id, "mechanical", "pass", "auto")
            db.transition_attempt(conn, attempt_id, "mechanical_pass")
            pass_count += 1
            print(f"  [{direction}] PASS (5 gates)")

    conn.commit()

    # Auto-advance passing attempts to raw_review_pending
    advanced = 0
    for attempt in attempts:
        row = conn.execute(
            "SELECT id, state FROM attempts WHERE id = ?", (attempt["id"],)
        ).fetchone()
        if row and row["state"] == "mechanical_pass":
            db.transition_attempt(conn, row["id"], "raw_review_pending")
            advanced += 1
    if advanced:
        conn.commit()
        print(f"\n  {advanced} attempts advanced to raw_review_pending")

    print(f"\nMechanical check: {pass_count} pass, {fail_count} fail, {len(attempts)} total")
    conn.close()


# -- foundry review show --------------------------------------

def cmd_review_show(args):
    """Display review status for a run."""
    conn = db.init_db()

    run = conn.execute(
        "SELECT r.*, s.display_name FROM runs r JOIN subjects s ON r.subject_id = s.id WHERE r.id = ?",
        (args.run_id,),
    ).fetchone()

    if not run:
        print(f"Run '{args.run_id}' not found.")
        conn.close()
        return

    print(f"\n{'=' * 60}")
    print(f"Run: {run['id']}")
    print(f"Subject: {run['display_name']} ({run['subject_id']})")
    print(f"Stack: {run['stack']}  Seed: {run['seed']}  Target: {run['sprite_target']}px")
    print(f"Gen: {run['gen_width']}x{run['gen_height']}")
    if run["subject_sheet_hash"]:
        print(f"Sheet hash: {run['subject_sheet_hash'][:16]}...")
    print(f"{'=' * 60}")

    attempts = db.get_run_status(conn, args.run_id)

    # Group by direction
    by_dir = {}
    for a in attempts:
        by_dir.setdefault(a["direction"], []).append(a)

    for direction in db.DIRECTIONS:
        dir_attempts = by_dir.get(direction, [])
        if not dir_attempts:
            print(f"\n  {direction}: (no attempts)")
            continue

        for a in dir_attempts:
            parent_str = f" (regen of #{a['parent_attempt_id']}: {a['regen_reason']})" if a["parent_attempt_id"] else ""
            print(f"\n  {direction} [#{a['id']}] state={a['state']}{parent_str}")

            # Show artifacts
            artifacts = db.get_attempt_artifacts(conn, a["id"])
            if artifacts:
                art_kinds = [art["kind"] for art in artifacts]
                print(f"    artifacts: {', '.join(art_kinds)}")

            # Show gate evidence
            gates = db.get_attempt_gates(conn, a["id"])
            if gates:
                gate_fails = [g for g in gates if g["result"] == "fail"]
                if gate_fails:
                    for g in gate_fails:
                        print(f"    GATE FAIL [{g['gate_name']}]: {g['measured']} (expected: {g['expected']})")
                else:
                    print(f"    gates: {len(gates)}/{len(gates)} pass")

            # Show reviews
            reviews = db.get_attempt_reviews(conn, a["id"])
            for rev in reviews:
                code_str = f" code={rev['code']}" if rev["code"] else ""
                note_str = f" -- {rev['note']}" if rev["note"] else ""
                print(f"    [{rev['review_type']}] {rev['decision']}{code_str}{note_str} (by {rev['reviewer']})")

            # Show finish captures
            captures = conn.execute(
                "SELECT lighting_state FROM finish_captures WHERE attempt_id = ?",
                (a["id"],),
            ).fetchall()
            if captures:
                states = [c["lighting_state"] for c in captures]
                print(f"    finish captures: {', '.join(states)}")

    # Summary
    state_counts = {}
    for a in attempts:
        state_counts[a["state"]] = state_counts.get(a["state"], 0) + 1

    print(f"\n{'-' * 60}")
    print("Summary:")
    for state, count in sorted(state_counts.items()):
        print(f"  {state}: {count}")

    # Pending review count
    pending = [a for a in attempts if a["state"] in db.REVIEW_PENDING_STATES]
    if pending:
        print(f"\n  WARNING: {len(pending)} attempts awaiting review")

    # Generate run board image
    from . import boards
    board_dir = db.FOUNDRY_ROOT / "boards"
    board_path = board_dir / f"run_{args.run_id}.png"
    try:
        boards.generate_run_board(conn, args.run_id, board_path)
        print(f"\n  Run board: {board_path}")
    except Exception as e:
        print(f"\n  Board generation failed: {e}")

    conn.close()


# -- foundry review accept ------------------------------------

def cmd_review_accept(args):
    """Accept an attempt at its current review stage."""
    conn = db.init_db()

    attempt = conn.execute(
        "SELECT id, state, run_id, direction, parent_attempt_id FROM attempts WHERE id = ?",
        (args.attempt_id,),
    ).fetchone()

    if not attempt:
        print(f"Attempt {args.attempt_id} not found.")
        conn.close()
        sys.exit(1)

    state = attempt["state"]

    transitions = {
        "raw_review_pending": ("raw_accepted", "raw_source"),
        "pixel_review_pending": ("accepted", "pixel"),
        "finish_review_pending": ("finish_accepted", "finish"),
    }

    if state not in transitions:
        print(f"Cannot accept attempt {args.attempt_id}: state is '{state}', not a review-pending state.")
        conn.close()
        sys.exit(1)

    new_state, review_type = transitions[state]

    # Add review record
    db.add_review(conn, attempt["id"], review_type, "accept", args.reviewer or "human", note=args.note)

    # Transition
    db.transition_attempt(conn, attempt["id"], new_state)

    # If reaching finish_accepted, check for parent to supersede
    if new_state == "finish_accepted" and attempt["parent_attempt_id"]:
        parent = conn.execute(
            "SELECT id, state FROM attempts WHERE id = ?",
            (attempt["parent_attempt_id"],),
        ).fetchone()
        if parent and parent["state"] == "finish_accepted":
            db.transition_attempt(conn, parent["id"], "superseded")
            print(f"  Parent attempt #{parent['id']} -> superseded")

    conn.commit()
    print(f"Attempt #{attempt['id']} ({attempt['direction']}): {state} -> {new_state}")
    conn.close()


# -- foundry review reject ------------------------------------

def cmd_review_reject(args):
    """Reject an attempt at its current review stage."""
    conn = db.init_db()

    attempt = conn.execute(
        "SELECT id, state, direction FROM attempts WHERE id = ?",
        (args.attempt_id,),
    ).fetchone()

    if not attempt:
        print(f"Attempt {args.attempt_id} not found.")
        conn.close()
        sys.exit(1)

    state = attempt["state"]

    transitions = {
        "raw_review_pending": ("raw_rejected", "raw_source"),
        "pixel_review_pending": ("rejected", "pixel"),
        "finish_review_pending": ("finish_rejected", "finish"),
    }

    if state not in transitions:
        print(f"Cannot reject attempt {args.attempt_id}: state is '{state}', not a review-pending state.")
        conn.close()
        sys.exit(1)

    if not args.code:
        print("Error: --code is required for rejections.")
        conn.close()
        sys.exit(1)

    new_state, review_type = transitions[state]

    db.add_review(conn, attempt["id"], review_type, "reject", args.reviewer or "human",
                  code=args.code, note=args.note)
    db.transition_attempt(conn, attempt["id"], new_state)

    conn.commit()
    print(f"Attempt #{attempt['id']} ({attempt['direction']}): {state} -> {new_state} [{args.code}]")
    conn.close()


# -- foundry regen --------------------------------------------

def cmd_regen(args):
    """Create a child regen attempt from a failed or accepted parent."""
    conn = db.init_db()

    parent = conn.execute(
        "SELECT id, run_id, direction, seed, state FROM attempts WHERE id = ?",
        (args.attempt_id,),
    ).fetchone()

    if not parent:
        print(f"Attempt {args.attempt_id} not found.")
        conn.close()
        sys.exit(1)

    # Regen allowed from terminal-fail states or finish_accepted (for improvement)
    allowed_states = db.TERMINAL_FAIL_STATES | {"finish_accepted"}
    if parent["state"] not in allowed_states:
        print(f"Cannot regen attempt #{args.attempt_id}: state is '{parent['state']}'. "
              f"Must be one of: {sorted(allowed_states)}")
        conn.close()
        sys.exit(1)

    if not args.code:
        print("Error: --code is required for regens.")
        conn.close()
        sys.exit(1)

    new_seed = args.seed if args.seed else parent["seed"]

    cursor = conn.execute(
        """INSERT INTO attempts (run_id, direction, seed, state, parent_attempt_id,
                                regen_reason, regen_note, created_at)
           VALUES (?, ?, ?, 'generated', ?, ?, ?, ?)""",
        (parent["run_id"], parent["direction"], new_seed,
         parent["id"], args.code, args.note, now_iso()),
    )
    child_id = cursor.lastrowid
    conn.commit()

    print(f"Regen attempt #{child_id} created for {parent['direction']} "
          f"(parent #{parent['id']}, code={args.code}, seed={new_seed})")
    conn.close()


# -- foundry status -------------------------------------------

def cmd_status(args):
    """Operator dashboard — one screen, all decisions visible."""
    conn = db.init_db()

    if args.subject:
        subjects = conn.execute(
            "SELECT * FROM subjects WHERE id = ? ORDER BY id", (args.subject,)
        ).fetchall()
    else:
        subjects = conn.execute("SELECT * FROM subjects ORDER BY id").fetchall()
    if not subjects:
        print("Foundry is empty. Register subjects with 'foundry subject-add'.")
        conn.close()
        return

    # ── Collect per-run data ──────────────────────────────
    run_data = []
    for subj in subjects:
        runs = conn.execute(
            "SELECT id, stack, seed, created_at FROM runs WHERE subject_id = ? ORDER BY created_at",
            (subj["id"],),
        ).fetchall()

        for run in runs:
            rid = run["id"]
            attempts = conn.execute(
                "SELECT id, direction, state FROM attempts WHERE run_id = ? ORDER BY direction",
                (rid,),
            ).fetchall()

            states = {}
            for a in attempts:
                states[a["state"]] = states.get(a["state"], 0) + 1

            finish_dirs = conn.execute(
                "SELECT COUNT(DISTINCT direction) as c FROM attempts WHERE run_id = ? AND state = 'finish_accepted'",
                (rid,),
            ).fetchone()["c"]

            captures = conn.execute(
                "SELECT COUNT(*) as c FROM finish_captures fc JOIN attempts a ON fc.attempt_id = a.id WHERE a.run_id = ?",
                (rid,),
            ).fetchone()["c"]

            reject_codes = conn.execute(
                """SELECT r.code, COUNT(*) as c FROM reviews r
                   JOIN attempts a ON r.attempt_id = a.id
                   WHERE a.run_id = ? AND r.decision IN ('fail', 'reject') AND r.code IS NOT NULL
                   GROUP BY r.code ORDER BY c DESC LIMIT 3""",
                (rid,),
            ).fetchall()

            # Determine run phase and next action
            pending_states = {s: n for s, n in states.items() if s in db.REVIEW_PENDING_STATES}
            terminal_fails = sum(states.get(s, 0) for s in db.TERMINAL_FAIL_STATES)
            n_accepted = states.get("accepted", 0)

            if finish_dirs == 8:
                phase = "DONE"
                next_cmd = None
            elif pending_states:
                # Find which review stage is pending
                if "finish_review_pending" in pending_states:
                    phase = "FINISH REVIEW"
                    next_cmd = f"foundry batch-accept {rid} --stage finish"
                elif "pixel_review_pending" in pending_states:
                    phase = "PIXEL REVIEW"
                    next_cmd = f"foundry batch-accept {rid} --stage pixel"
                elif "raw_review_pending" in pending_states:
                    phase = "RAW REVIEW"
                    next_cmd = f"foundry batch-accept {rid} --stage raw"
                else:
                    phase = "REVIEW"
                    next_cmd = f"foundry review-show {rid}"
            elif n_accepted > 0:
                phase = "PRODUCE"
                next_cmd = f"foundry produce {rid}"
            elif states.get("generated", 0) > 0:
                phase = "CHECK"
                next_cmd = f"foundry check {rid}"
            elif terminal_fails == len(attempts):
                phase = "FAILED"
                next_cmd = None
            else:
                phase = "MIXED"
                next_cmd = f"foundry review-show {rid}"

            run_data.append({
                "subject": subj["display_name"],
                "subject_id": subj["id"],
                "run_id": rid,
                "stack": run["stack"],
                "seed": run["seed"],
                "n_attempts": len(attempts),
                "states": states,
                "finish_dirs": finish_dirs,
                "captures": captures,
                "reject_codes": reject_codes,
                "terminal_fails": terminal_fails,
                "phase": phase,
                "next_cmd": next_cmd,
            })

    # ── Header ────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("FOUNDRY OPERATOR DASHBOARD")
    print(f"{'=' * 70}")

    # ── Action Required ───────────────────────────────────
    actionable = [r for r in run_data if r["next_cmd"]]
    if actionable:
        print(f"\n--- ACTION REQUIRED ({len(actionable)}) ---")
        for r in actionable:
            print(f"  [{r['phase']:14s}] {r['subject']:12s}  {r['run_id']}")
            print(f"                   -> {r['next_cmd']}")
    else:
        print(f"\n  No actions pending. All runs complete or failed.")

    # ── Run Summary ───────────────────────────────────────
    print(f"\n--- RUNS ---")
    for r in run_data:
        finish_str = f"{r['finish_dirs']}/8"
        fail_str = f"  FAIL:{r['terminal_fails']}" if r['terminal_fails'] else ""
        cap_str = f"  cap:{r['captures']}" if r['captures'] else ""

        status_badge = {
            "DONE": "[DONE]",
            "FAILED": "[FAIL]",
        }.get(r["phase"], f"[{r['phase']}]")

        print(f"  {r['subject']:12s} {status_badge:16s} finish={finish_str}{fail_str}{cap_str}  {r['run_id']}")

        if args.verbose:
            for state, count in sorted(r["states"].items()):
                print(f"    {state}: {count}")

    # ── Failure Summary ───────────────────────────────────
    all_rejects = []
    for r in run_data:
        all_rejects.extend(r["reject_codes"])

    if all_rejects:
        print(f"\n--- REJECT CODES ---")
        # Aggregate across runs
        code_totals = {}
        for rc in all_rejects:
            code_totals[rc["code"]] = code_totals.get(rc["code"], 0) + rc["c"]
        for code, cnt in sorted(code_totals.items(), key=lambda x: -x[1]):
            print(f"  {code:36s}  {cnt}x")

    # ── Yield ─────────────────────────────────────────────
    total_attempts = sum(r["n_attempts"] for r in run_data)
    total_finish = sum(r["finish_dirs"] for r in run_data)
    total_fails = sum(r["terminal_fails"] for r in run_data)
    total_captures = sum(r["captures"] for r in run_data)
    total_runs = len(run_data)
    total_subjects = len(subjects)
    run_ids = [r["run_id"] for r in run_data]
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        total_reviews = conn.execute(
            f"SELECT COUNT(*) as c FROM reviews r JOIN attempts a ON r.attempt_id = a.id WHERE a.run_id IN ({placeholders})",
            run_ids,
        ).fetchone()["c"]
    else:
        total_reviews = 0

    yield_pct = f"{100 * total_finish / max(total_attempts, 1):.0f}%"

    print(f"\n--- YIELD ---")
    print(f"  Subjects: {total_subjects}  Runs: {total_runs}  Attempts: {total_attempts}")
    print(f"  Finish-accepted: {total_finish}  Rejects: {total_fails}  Reviews: {total_reviews}")
    print(f"  Captures: {total_captures}  Yield: {total_finish}/{total_attempts} ({yield_pct})")

    conn.close()


# -- foundry attempt-detail ------------------------------------

def cmd_attempt_detail(args):
    """Generate attempt detail view image."""
    from . import boards
    conn = db.init_db()

    board_dir = db.FOUNDRY_ROOT / "boards"
    board_path = board_dir / f"attempt_{args.attempt_id}.png"

    try:
        boards.generate_attempt_detail(conn, args.attempt_id, board_path)
        print(f"Attempt detail: {board_path}")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    conn.close()


# -- foundry finish-board -------------------------------------

def cmd_finish_board(args):
    """Generate finish review board for a run."""
    from . import boards
    conn = db.init_db()

    board_dir = db.FOUNDRY_ROOT / "boards"
    board_path = board_dir / f"finish_{args.run_id}.png"

    try:
        boards.generate_finish_board(conn, args.run_id, board_path)
        print(f"Finish board: {board_path}")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    conn.close()


# -- foundry story --------------------------------------------

def cmd_story(args):
    """Reconstruct the full decision story of an attempt."""
    from . import decisions
    conn = db.init_db()

    try:
        story = decisions.attempt_story(conn, args.attempt_id)
    except ValueError as e:
        print(f"Error: {e}")
        conn.close()
        sys.exit(1)

    a = story["attempt"]
    print(f"\n{'=' * 70}")
    print(f"STORY: Attempt #{a['id']} -- {a['display_name']} / {a['direction']}")
    print(f"{'=' * 70}")
    print(f"State: {a['state']}  |  Seed: {a['seed']}  |  Run: {a['run_id']}")
    if a["parent_attempt_id"]:
        print(f"Regen of: #{a['parent_attempt_id']} ({a['regen_reason']})")

    # Timeline
    print(f"\n--- Timeline ({len(story['timeline'])} events) ---")
    for ev in story["timeline"]:
        ts = ev["timestamp"][:19] if ev["timestamp"] else "?"
        print(f"  {ts}  {ev['event']:24s}  {ev['detail']}")

    # Artifacts
    if story["artifacts"]:
        print(f"\n--- Artifacts ({len(story['artifacts'])}) ---")
        for art in story["artifacts"]:
            dim = f"  {art['width']}x{art['height']}" if art["width"] else ""
            print(f"  {art['kind']:16s} {art['path']}{dim}")

    # Lineage
    if len(story["lineage"]) > 1:
        print(f"\n--- Lineage (depth {len(story['lineage'])}) ---")
        for i, anc in enumerate(story["lineage"]):
            prefix = ">> " if i == 0 else "   "
            reason = f" (regen: {anc['regen_reason']})" if anc["regen_reason"] else ""
            print(f"  {prefix}#{anc['id']} {anc['state']}{reason}")

    # Children
    if story["children"]:
        print(f"\n--- Children ({len(story['children'])}) ---")
        for child in story["children"]:
            print(f"  #{child['id']} {child['state']} (reason: {child['regen_reason']})")

    conn.close()


# -- foundry lineage ------------------------------------------

def cmd_lineage(args):
    """Show attempt lineage for a run, optionally filtered by direction."""
    from . import decisions
    conn = db.init_db()

    if args.direction:
        # Single direction
        chain = decisions.direction_lineage(conn, args.run_id, args.direction)
        if not chain:
            print(f"No attempts for {args.direction} in run {args.run_id}.")
            conn.close()
            return

        print(f"\n{'=' * 70}")
        print(f"LINEAGE: {args.run_id} / {args.direction} ({len(chain)} attempts)")
        print(f"{'=' * 70}")

        for a in chain:
            marker = " ** WINNER **" if a["is_winner"] else ""
            parent = f"  regen of #{a['parent_attempt_id']}: {a['regen_reason']}" if a["parent_attempt_id"] else ""
            print(f"\n  #{a['id']}  state={a['state']}  seed={a['seed']}{marker}")
            if parent:
                print(f"    {parent}")
                if a.get("regen_note"):
                    print(f"    note: {a['regen_note']}")
            if a["gate_fail"] > 0:
                print(f"    gates: {a['gate_pass']} pass, {a['gate_fail']} fail ({', '.join(a['gate_fail_names'])})")
            elif a["gate_pass"] > 0:
                print(f"    gates: {a['gate_pass']}/{a['gate_pass']} pass")
            if a["reject_codes"]:
                print(f"    rejected: {', '.join(a['reject_codes'])}")
            if a["accept_types"]:
                print(f"    accepted: {', '.join(a['accept_types'])}")
    else:
        # All directions
        try:
            summary = decisions.run_lineage_summary(conn, args.run_id)
        except ValueError as e:
            print(f"Error: {e}")
            conn.close()
            sys.exit(1)

        run = summary["run"]
        print(f"\n{'=' * 70}")
        print(f"LINEAGE: {run['display_name']} -- {args.run_id}")
        print(f"{'=' * 70}")

        for direction in db.DIRECTIONS:
            chain = summary["directions"][direction]
            if not chain:
                print(f"\n  {direction}: (no attempts)")
                continue

            winner = next((a for a in chain if a["is_winner"]), None)
            total = len(chain)
            failed = sum(1 for a in chain if a["state"] in db.TERMINAL_FAIL_STATES)

            if winner:
                print(f"\n  {direction}: #{winner['id']} WINNER ({total} attempts, {failed} failed)")
            else:
                best = chain[-1]
                print(f"\n  {direction}: no winner -- best is #{best['id']} at {best['state']} ({total} attempts)")

            for a in chain:
                marker = " **" if a["is_winner"] else ""
                codes = ""
                if a["reject_codes"]:
                    codes = f" [{', '.join(a['reject_codes'])}]"
                elif a["gate_fail_names"]:
                    codes = f" [gate: {', '.join(a['gate_fail_names'])}]"
                print(f"    #{a['id']:3d} {a['state']:24s}{codes}{marker}")

    conn.close()


# -- foundry winner -------------------------------------------

def cmd_winner(args):
    """Show canonical winner per direction with explanation."""
    from . import decisions
    conn = db.init_db()

    winners = decisions.canonical_winners(conn, args.run_id)

    print(f"\n{'=' * 70}")
    print(f"WINNERS: {args.run_id}")
    print(f"{'=' * 70}")

    accepted = 0
    for w in winners:
        d = w["direction"]
        if w["winner"]:
            accepted += 1
            defeated_str = ""
            if w["defeated"]:
                d_list = [f"#{x['id']}" for x in w["defeated"]]
                defeated_str = f"  defeated: {', '.join(d_list)}"
            print(f"  {d:14s}  #{w['winner']['id']}  ACCEPTED{defeated_str}")
        else:
            print(f"  {d:14s}  -- {w['explanation']}")

    print(f"\n{accepted}/8 directions have a canonical winner")

    # Verbose: show explanations
    if args.verbose:
        print(f"\n--- Explanations ---")
        for w in winners:
            print(f"\n  {w['direction']}:")
            print(f"    {w['explanation']}")
            for d in w["defeated"]:
                print(f"    #{d['id']} lost: {', '.join(d['fail_reasons'])}")

    conn.close()


# -- foundry drift --------------------------------------------

def cmd_drift(args):
    """Show failure patterns and pass rates."""
    from . import decisions
    conn = db.init_db()

    summary = decisions.failure_summary(conn, args.run_id)

    scope = f"run {args.run_id}" if args.run_id else "all runs"
    print(f"\n{'=' * 70}")
    print(f"DRIFT REPORT: {scope}")
    print(f"{'=' * 70}")

    # State distribution
    print(f"\n--- State Distribution ---")
    for s in summary["state_distribution"]:
        print(f"  {s['state']:24s}  {s['cnt']}")

    # Pass rates
    if summary["pass_rates"]:
        print(f"\n--- Pass Rate by Stage ---")
        for pr in summary["pass_rates"]:
            print(f"  {pr['review_type']:14s}  {pr['passes']} pass / {pr['failures']} fail  ({pr['pass_rate']})")

    # Top reject codes
    if summary["top_reject_codes"]:
        print(f"\n--- Top Reject Codes ---")
        for rc in summary["top_reject_codes"]:
            print(f"  {rc['code']:36s}  {rc['cnt']}x")

    # Top gate failures
    if summary["top_gate_failures"]:
        print(f"\n--- Top Gate Failures ---")
        for gf in summary["top_gate_failures"]:
            print(f"  {gf['gate_name']:24s}  {gf['cnt']}x")

    # Regen reasons
    if summary["regen_reasons"]:
        print(f"\n--- Regen Reasons ---")
        for rr in summary["regen_reasons"]:
            print(f"  {rr['regen_reason']:36s}  {rr['cnt']}x")

    if not any([summary["top_reject_codes"], summary["top_gate_failures"], summary["regen_reasons"]]):
        print(f"\n  No failures or regens recorded. Clean run.")

    conn.close()


# -- foundry produce ------------------------------------------

def cmd_produce(args):
    """One-command batch progression: maps -> finish captures -> finish_review_pending.

    Takes a run whose attempts are at 'accepted' and drives them through
    map derivation, Godot finish capture, and state advancement.
    Resumes cleanly if interrupted mid-pipeline.
    """
    import time as _time

    conn = db.init_db()

    run = conn.execute(
        "SELECT r.*, s.display_name FROM runs r JOIN subjects s ON r.subject_id = s.id WHERE r.id = ?",
        (args.run_id,),
    ).fetchone()
    if not run:
        print(f"Run '{args.run_id}' not found.")
        conn.close()
        sys.exit(1)

    subject_id = run["subject_id"]
    char_name = run["display_name"]
    start_time = _time.time()

    print(f"\n{'=' * 60}")
    print(f"PRODUCE: {char_name}")
    print(f"Run: {args.run_id}")
    print(f"{'=' * 60}")

    # Survey current state
    attempts = conn.execute(
        """SELECT id, direction, state FROM attempts
           WHERE run_id = ? AND direction IN ({})
           ORDER BY direction""".format(",".join("?" for _ in db.DIRECTIONS)),
        (args.run_id, *db.DIRECTIONS),
    ).fetchall()

    state_counts = {}
    for a in attempts:
        state_counts[a["state"]] = state_counts.get(a["state"], 0) + 1

    accepted = [a for a in attempts if a["state"] == "accepted"]
    finish_pending = [a for a in attempts if a["state"] == "finish_review_pending"]
    finish_done = [a for a in attempts if a["state"] == "finish_accepted"]

    print(f"\n  State survey: {dict(state_counts)}")

    if finish_done:
        print(f"\n  {len(finish_done)} directions already finish_accepted. Nothing to produce.")
        conn.close()
        return

    if finish_pending and not accepted:
        print(f"\n  {len(finish_pending)} directions at finish_review_pending. Ready for review.")
        conn.close()
        return

    if not accepted and not finish_pending:
        print(f"\n  No accepted attempts to produce. Run review-accept first.")
        conn.close()
        return

    conn.close()  # Close before subprocess calls

    # Step 1: Map derivation (skip if maps already exist)
    print(f"\n--- Step 1: Map derivation ---")
    conn = db.init_db()
    needs_maps = False
    for a in accepted:
        normal = conn.execute(
            "SELECT id FROM artifacts WHERE attempt_id = ? AND kind = 'normal'",
            (a["id"],),
        ).fetchone()
        if not normal:
            needs_maps = True
            break
    conn.close()

    if needs_maps:
        print("  Deriving normal + depth maps...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pipeline.foundry_maps", "--run", args.run_id],
            cwd=str(db.FOUNDRY_ROOT), capture_output=True, text=True, timeout=600,
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n")[-5:]:
                print(f"  {line}")
        if result.returncode != 0:
            print(f"  Map derivation failed!")
            if result.stderr:
                print(f"  {result.stderr.strip()}")
            sys.exit(1)
    else:
        print("  Maps already derived (skipping)")

    # Step 2: Finish captures (skip if already done)
    print(f"\n--- Step 2: Finish captures ---")
    conn = db.init_db()
    needs_captures = False
    for a in accepted:
        cap = conn.execute(
            "SELECT id FROM finish_captures WHERE attempt_id = ?",
            (a["id"],),
        ).fetchone()
        if not cap:
            needs_captures = True
            break
    conn.close()

    if needs_captures:
        print("  Running finish capture pipeline...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pipeline.foundry_finish", "--run", args.run_id],
            cwd=str(db.FOUNDRY_ROOT), capture_output=True, text=True, timeout=600,
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n")[-8:]:
                print(f"  {line}")
        if result.returncode != 0:
            print(f"  Finish capture failed!")
            if result.stderr:
                print(f"  {result.stderr.strip()}")
            sys.exit(1)
    else:
        print("  Finish captures already exist (skipping)")

    # Step 3: Verify final state
    print(f"\n--- Result ---")
    conn = db.init_db()
    final = conn.execute(
        """SELECT state, COUNT(*) as c FROM attempts
           WHERE run_id = ? AND direction IN ({})
           GROUP BY state""".format(",".join("?" for _ in db.DIRECTIONS)),
        (args.run_id, *db.DIRECTIONS),
    ).fetchall()

    captures = conn.execute(
        """SELECT COUNT(*) as c FROM finish_captures fc
           JOIN attempts a ON fc.attempt_id = a.id
           WHERE a.run_id = ?""",
        (args.run_id,),
    ).fetchone()["c"]

    elapsed = _time.time() - start_time

    for row in final:
        print(f"  {row['state']}: {row['c']}")
    print(f"  Finish captures: {captures}")
    print(f"  Time: {elapsed:.1f}s")

    conn.close()

    print(f"\n{'=' * 60}")
    print(f"PRODUCE COMPLETE: {char_name}")
    print(f"Next: foundry batch-accept {args.run_id} --stage finish")
    print(f"{'=' * 60}")


# -- foundry batch-accept -------------------------------------

def cmd_batch_accept(args):
    """Accept all attempts at a given review stage for a run."""
    conn = db.init_db()

    run = conn.execute(
        "SELECT r.*, s.display_name FROM runs r JOIN subjects s ON r.subject_id = s.id WHERE r.id = ?",
        (args.run_id,),
    ).fetchone()
    if not run:
        print(f"Run '{args.run_id}' not found.")
        conn.close()
        sys.exit(1)

    # Map stage name to pending state
    stage_map = {
        "raw": ("raw_review_pending", "raw_accepted", "raw_source"),
        "pixel": ("pixel_review_pending", "accepted", "pixel"),
        "finish": ("finish_review_pending", "finish_accepted", "finish"),
    }

    if args.stage:
        if args.stage not in stage_map:
            print(f"Invalid stage '{args.stage}'. Must be: raw, pixel, finish")
            conn.close()
            sys.exit(1)
        stages = {args.stage: stage_map[args.stage]}
    else:
        # Auto-detect: find whichever pending state has attempts
        stages = {}
        for name, vals in stage_map.items():
            count = conn.execute(
                "SELECT COUNT(*) as c FROM attempts WHERE run_id = ? AND state = ?",
                (args.run_id, vals[0]),
            ).fetchone()["c"]
            if count > 0:
                stages[name] = vals
        if not stages:
            print(f"No review-pending attempts in run '{args.run_id}'.")
            conn.close()
            return

    reviewer = args.reviewer or "batch_review"
    note = args.note

    total_accepted = 0
    for stage_name, (pending_state, new_state, review_type) in stages.items():
        attempts = conn.execute(
            """SELECT id, direction, state, parent_attempt_id FROM attempts
               WHERE run_id = ? AND state = ?
               ORDER BY direction""",
            (args.run_id, pending_state),
        ).fetchall()

        if not attempts:
            continue

        print(f"\n  {stage_name} review: {len(attempts)} attempts")

        for a in attempts:
            db.add_review(conn, a["id"], review_type, "accept", reviewer, note=note)
            db.transition_attempt(conn, a["id"], new_state)

            # Supersession logic for finish_accepted
            if new_state == "finish_accepted" and a["parent_attempt_id"]:
                parent = conn.execute(
                    "SELECT id, state FROM attempts WHERE id = ?",
                    (a["parent_attempt_id"],),
                ).fetchone()
                if parent and parent["state"] == "finish_accepted":
                    db.transition_attempt(conn, parent["id"], "superseded")
                    print(f"    #{a['id']} ({a['direction']}): {pending_state} -> {new_state}  (parent #{parent['id']} -> superseded)")
                    continue

            print(f"    #{a['id']} ({a['direction']}): {pending_state} -> {new_state}")
            total_accepted += 1

    conn.commit()

    # Auto-advance through intermediate states
    # raw_accepted -> pixel_review_pending
    # accepted -> finish_review_pending (only if produce hasn't run yet — skip this one)
    auto_advances = {
        "raw_accepted": "pixel_review_pending",
    }
    auto_count = 0
    for a_state, next_state in auto_advances.items():
        to_advance = conn.execute(
            "SELECT id, direction FROM attempts WHERE run_id = ? AND state = ?",
            (args.run_id, a_state),
        ).fetchall()
        for a in to_advance:
            db.transition_attempt(conn, a["id"], next_state)
            auto_count += 1
    if auto_count:
        conn.commit()
        print(f"  Auto-advanced {auto_count} to next review stage")

    print(f"\n  Batch accepted: {total_accepted} attempts")
    conn.close()


# -- foundry batch-reject -------------------------------------

def cmd_batch_reject(args):
    """Reject all attempts at a given review stage for a run with a single code."""
    conn = db.init_db()

    run = conn.execute("SELECT id FROM runs WHERE id = ?", (args.run_id,)).fetchone()
    if not run:
        print(f"Run '{args.run_id}' not found.")
        conn.close()
        sys.exit(1)

    stage_map = {
        "raw": ("raw_review_pending", "raw_rejected", "raw_source"),
        "pixel": ("pixel_review_pending", "rejected", "pixel"),
        "finish": ("finish_review_pending", "finish_rejected", "finish"),
    }

    if args.stage:
        if args.stage not in stage_map:
            print(f"Invalid stage '{args.stage}'. Must be: raw, pixel, finish")
            conn.close()
            sys.exit(1)
        stages = {args.stage: stage_map[args.stage]}
    else:
        stages = {}
        for name, vals in stage_map.items():
            count = conn.execute(
                "SELECT COUNT(*) as c FROM attempts WHERE run_id = ? AND state = ?",
                (args.run_id, vals[0]),
            ).fetchone()["c"]
            if count > 0:
                stages[name] = vals

    if not stages:
        print(f"No review-pending attempts in run '{args.run_id}'.")
        conn.close()
        return

    reviewer = args.reviewer or "batch_review"
    total_rejected = 0

    for stage_name, (pending_state, new_state, review_type) in stages.items():
        attempts = conn.execute(
            """SELECT id, direction FROM attempts
               WHERE run_id = ? AND state = ?
               ORDER BY direction""",
            (args.run_id, pending_state),
        ).fetchall()

        if not attempts:
            continue

        print(f"\n  {stage_name} reject: {len(attempts)} attempts (code={args.code})")

        for a in attempts:
            db.add_review(conn, a["id"], review_type, "reject", reviewer,
                          code=args.code, note=args.note)
            db.transition_attempt(conn, a["id"], new_state)
            print(f"    #{a['id']} ({a['direction']}): {pending_state} -> {new_state}")
            total_rejected += 1

    conn.commit()
    print(f"\n  Batch rejected: {total_rejected} attempts ({args.code})")
    conn.close()


# -- foundry metrics ------------------------------------------

def cmd_metrics(args):
    """Throughput metrics for a run or the whole foundry."""
    conn = db.init_db()

    if args.run_id:
        runs = conn.execute("SELECT * FROM runs WHERE id = ?", (args.run_id,)).fetchall()
    else:
        runs = conn.execute("SELECT * FROM runs ORDER BY created_at").fetchall()

    if not runs:
        print("No runs found.")
        conn.close()
        return

    print(f"\n{'=' * 70}")
    print(f"THROUGHPUT METRICS")
    print(f"{'=' * 70}")

    total_attempts = 0
    total_accepted_dirs = 0
    total_regens = 0
    total_rejects = 0
    silhouette_data = {}

    for run in runs:
        rid = run["id"]
        sid = run["subject_id"]

        subject = conn.execute(
            "SELECT display_name FROM subjects WHERE id = ?", (sid,)
        ).fetchone()
        char_name = subject["display_name"] if subject else sid

        attempts = conn.execute(
            "SELECT id, direction, state, parent_attempt_id, regen_reason, created_at FROM attempts WHERE run_id = ?",
            (rid,),
        ).fetchall()

        if not attempts:
            continue

        n_attempts = len(attempts)
        n_regens = sum(1 for a in attempts if a["parent_attempt_id"] is not None)
        accepted_dirs = conn.execute(
            "SELECT COUNT(DISTINCT direction) as c FROM attempts WHERE run_id = ? AND state = 'finish_accepted'",
            (rid,),
        ).fetchone()["c"]

        rejected = [a for a in attempts if a["state"] in db.TERMINAL_FAIL_STATES]
        n_rejected = len(rejected)

        # Attempts per accepted direction
        apd = f"{n_attempts / max(accepted_dirs, 1):.1f}" if accepted_dirs else "n/a"

        # Finish captures
        captures = conn.execute(
            "SELECT COUNT(*) as c FROM finish_captures fc JOIN attempts a ON fc.attempt_id = a.id WHERE a.run_id = ?",
            (rid,),
        ).fetchone()["c"]

        # Reviews count
        reviews = conn.execute(
            "SELECT COUNT(*) as c FROM reviews r JOIN attempts a ON r.attempt_id = a.id WHERE a.run_id = ?",
            (rid,),
        ).fetchone()["c"]

        # Reject codes
        reject_codes = conn.execute(
            """SELECT code, COUNT(*) as c FROM reviews r
               JOIN attempts a ON r.attempt_id = a.id
               WHERE a.run_id = ? AND r.decision IN ('fail', 'reject') AND r.code IS NOT NULL
               GROUP BY code ORDER BY c DESC""",
            (rid,),
        ).fetchall()

        print(f"\n  {char_name} ({rid})")
        print(f"    Attempts: {n_attempts}  Accepted dirs: {accepted_dirs}/8  Attempts/dir: {apd}")
        print(f"    Regens: {n_regens}  Rejects: {n_rejected}  Reviews: {reviews}")
        print(f"    Captures: {captures}")
        if reject_codes:
            codes_str = ", ".join(f"{rc['code']}({rc['c']}x)" for rc in reject_codes)
            print(f"    Reject codes: {codes_str}")

        total_attempts += n_attempts
        total_accepted_dirs += accepted_dirs
        total_regens += n_regens
        total_rejects += n_rejected

        # Track per-subject for silhouette class summary
        silhouette_data[char_name] = {
            "attempts": n_attempts,
            "accepted_dirs": accepted_dirs,
            "regens": n_regens,
            "rejects": n_rejected,
        }

    # Global summary
    print(f"\n{'=' * 70}")
    print(f"TOTALS")
    print(f"{'=' * 70}")
    print(f"  Runs: {len(runs)}")
    print(f"  Attempts: {total_attempts}")
    print(f"  Accepted directions: {total_accepted_dirs}")
    print(f"  Regens: {total_regens}")
    print(f"  Rejects: {total_rejects}")
    if total_accepted_dirs > 0:
        print(f"  Global attempts/accepted-dir: {total_attempts / total_accepted_dirs:.2f}")
    print(f"  Yield: {total_accepted_dirs}/{total_attempts} ({100 * total_accepted_dirs / max(total_attempts, 1):.0f}%)")

    conn.close()


# -- foundry export -------------------------------------------

EXPORT_SCHEMA_VERSION = "1.0.0"
CANONICAL_DIRECTION_ORDER = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]


def cmd_export(args):
    """Export a finish-accepted run as a deterministic asset pack."""
    import shutil
    import subprocess

    conn = db.init_db()
    run_id = args.run_id

    # -- Validate run exists and is fully finish_accepted --
    run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        print(f"Error: run '{run_id}' not found.")
        conn.close()
        sys.exit(1)

    subject_id = run["subject_id"]
    subject = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    display_name = subject["display_name"] if subject else subject_id

    # Check all 8 directions are finish_accepted
    accepted = conn.execute(
        """SELECT direction FROM attempts
           WHERE run_id = ? AND state = 'finish_accepted'
           ORDER BY direction""",
        (run_id,),
    ).fetchall()
    accepted_dirs = {r["direction"] for r in accepted}
    missing = set(CANONICAL_DIRECTION_ORDER) - accepted_dirs
    if missing:
        print(f"Error: run '{run_id}' is not fully finish_accepted.")
        print(f"  Missing directions: {', '.join(sorted(missing))}")
        print(f"  Accepted: {len(accepted_dirs)}/8")
        conn.close()
        sys.exit(1)

    # -- Build export target path --
    export_root = db.FOUNDRY_ROOT / "exports" / subject_id / run_id
    if export_root.exists() and not args.overwrite:
        print(f"Error: export already exists at {export_root}")
        print(f"  Use --overwrite to replace.")
        conn.close()
        sys.exit(1)

    # -- Locate source files --
    bakeoff_dir = db.FOUNDRY_ROOT / "bakeoff" / run_id
    maps_dir = db.FOUNDRY_ROOT / "bakeoff" / f"{run_id}_maps"

    if not bakeoff_dir.exists():
        print(f"Error: bakeoff directory not found: {bakeoff_dir}")
        conn.close()
        sys.exit(1)
    if not maps_dir.exists():
        print(f"Error: maps directory not found: {maps_dir}")
        conn.close()
        sys.exit(1)

    # -- Verify all source files exist before copying --
    source_map = {}  # (layer, direction) -> source_path
    for d in CANONICAL_DIRECTION_ORDER:
        albedo_src = bakeoff_dir / f"{d}.png"
        normal_src = maps_dir / f"{d}_normal.png"
        depth_src = maps_dir / f"{d}_depth.png"

        for layer, src in [("albedo", albedo_src), ("normal", normal_src), ("depth", depth_src)]:
            if not src.exists():
                print(f"Error: missing source file: {src}")
                conn.close()
                sys.exit(1)
            source_map[(layer, d)] = src

    contact_src = bakeoff_dir / "contact_sheet.png"

    # -- Create export directory structure --
    if export_root.exists():
        shutil.rmtree(export_root)

    for subdir in ["albedo", "normal", "depth", "preview"]:
        (export_root / subdir).mkdir(parents=True, exist_ok=True)

    print(f"{'=' * 60}")
    print(f"EXPORT: {display_name}")
    print(f"Run: {run_id}")
    print(f"Target: {export_root}")
    print(f"{'=' * 60}")

    # -- Copy files and compute checksums --
    file_checksums = {}

    for (layer, d), src in source_map.items():
        dst = export_root / layer / f"{d}.png"
        shutil.copy2(src, dst)
        rel = f"{layer}/{d}.png"
        file_checksums[rel] = hash_file(dst)
        print(f"  [{layer}] {d}.png  OK")

    # Copy contact sheet if it exists
    if contact_src.exists():
        dst = export_root / "preview" / "contact_sheet.png"
        shutil.copy2(contact_src, dst)
        file_checksums["preview/contact_sheet.png"] = hash_file(dst)
        print(f"  [preview] contact_sheet.png  OK")

    # -- Gather provenance data --
    # Reject/regen counts for this run
    reject_count = conn.execute(
        "SELECT COUNT(*) as c FROM attempts WHERE run_id = ? AND state IN ('raw_rejected', 'rejected', 'finish_rejected')",
        (run_id,),
    ).fetchone()["c"]

    regen_count = conn.execute(
        "SELECT COUNT(*) as c FROM attempts WHERE run_id = ? AND parent_attempt_id IS NOT NULL",
        (run_id,),
    ).fetchone()["c"]

    # Accepted timestamp (latest finish_accepted review)
    accepted_at = conn.execute(
        """SELECT MAX(r.created_at) as t FROM reviews r
           JOIN attempts a ON r.attempt_id = a.id
           WHERE a.run_id = ? AND r.decision = 'accept' AND r.review_type = 'finish'""",
        (run_id,),
    ).fetchone()
    accepted_at_str = accepted_at["t"] if accepted_at else None

    # Parse recipe for generation details
    recipe = {}
    recipe_path = bakeoff_dir / "recipe.json"
    if recipe_path.exists():
        with open(recipe_path) as f:
            recipe = json.load(f)

    # Git hash
    git_hash = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(db.FOUNDRY_ROOT),
        )
        if result.returncode == 0:
            git_hash = result.stdout.strip()
    except Exception:
        pass

    # Sprite dimensions from first albedo
    first_albedo = export_root / "albedo" / "front.png"
    width, height = 0, 0
    try:
        from PIL import Image
        with Image.open(first_albedo) as img:
            width, height = img.size
    except Exception:
        pass

    # -- Build manifest --
    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": now_iso(),
        "foundry_version": git_hash,
        "identity": {
            "subject_slug": subject_id,
            "display_name": display_name,
            "body_family": recipe.get("body_family", "bipedal"),
        },
        "provenance": {
            "run_id": run_id,
            "seed": run["seed"],
            "generated_at": run["created_at"],
            "accepted_at": accepted_at_str,
            "regen_count": regen_count,
            "reject_count": reject_count,
            "git_hash": git_hash,
        },
        "generation": {
            "stack_id": run["stack"],
            "checkpoint": recipe.get("checkpoint", "unknown"),
            "lora": recipe.get("lora", "unknown"),
            "controlnet_depth": recipe.get("controlnet_depth"),
            "controlnet_depth_strength": recipe.get("controlnet_depth_strength"),
            "controlnet_depth_end_percent": recipe.get("controlnet_depth_end_percent"),
            "controlnet_edge": recipe.get("controlnet_edge"),
            "controlnet_edge_strength": recipe.get("controlnet_edge_strength"),
        },
        "render_contract": {
            "width": width,
            "height": height,
            "direction_order": CANONICAL_DIRECTION_ORDER,
            "pivot": "center_bottom",
            "transparency": True,
        },
        "files": file_checksums,
        "source": {
            "bakeoff_dir": str(bakeoff_dir.relative_to(db.FOUNDRY_ROOT)),
            "maps_dir": str(maps_dir.relative_to(db.FOUNDRY_ROOT)),
        },
        "notes": None,
    }

    manifest_path = export_root / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  manifest.json written ({len(file_checksums)} files checksummed)")

    # -- Summary --
    print(f"\n{'=' * 60}")
    print(f"EXPORT COMPLETE: {display_name}")
    print(f"  Pack: {export_root}")
    print(f"  Files: {len(file_checksums)} assets + manifest")
    print(f"  Schema: v{EXPORT_SCHEMA_VERSION}")
    print(f"{'=' * 60}")

    conn.close()


# -- foundry ship-check ----------------------------------------

def cmd_ship_check(args):
    """Run ship-specific mechanical gates on a run's attempts."""
    from . import mechanical_ships

    conn = db.init_db()

    run = conn.execute("SELECT id, sprite_target FROM runs WHERE id = ?", (args.run_id,)).fetchone()
    if not run:
        print(f"Run '{args.run_id}' not found.")
        conn.close()
        sys.exit(1)

    target = run["sprite_target"]

    attempts = conn.execute(
        "SELECT id, direction, state FROM attempts WHERE run_id = ? ORDER BY direction",
        (args.run_id,),
    ).fetchall()

    if not attempts:
        print(f"No attempts found for run '{args.run_id}'.")
        conn.close()
        return

    dir_count = len(set(a["direction"] for a in attempts))
    expected_dirs = args.direction_count or 8
    if dir_count < expected_dirs:
        print(f"  WARNING: only {dir_count}/{expected_dirs} directions registered for this run")

    pass_count = 0
    fail_count = 0

    checkable = [a for a in attempts if a["state"] == "generated"]
    if not checkable:
        print(f"  No attempts in 'generated' state to check.")
        conn.close()
        return

    for attempt in checkable:
        attempt_id = attempt["id"]
        direction = attempt["direction"]

        gate_results = mechanical_ships.run_per_attempt_gates(conn, attempt_id, target)

        for gr in gate_results:
            db.add_gate_result(
                conn,
                attempt_id=attempt_id,
                gate_name=gr["gate_name"],
                result=gr["result"],
                measured=gr["measured"],
                expected=gr["expected"],
                artifact_kind=gr.get("artifact_kind"),
                artifact_path=gr.get("artifact_path"),
            )

        failures = [gr for gr in gate_results if gr["result"] == "fail"]
        fail_codes = [
            mechanical_ships.GATE_FAIL_CODES.get(gr["gate_name"], gr["gate_name"])
            for gr in failures
        ]

        if failures:
            for code in fail_codes:
                db.add_review(conn, attempt_id, "mechanical", "fail", "auto", code=code)
            db.transition_attempt(conn, attempt_id, "mechanical_fail")
            fail_count += 1
            print(f"  [{direction}] FAIL: {', '.join(fail_codes)}")
            for gr in failures:
                print(f"    {gr['gate_name']}: measured={gr['measured']}, expected={gr['expected']}")
        else:
            db.add_review(conn, attempt_id, "mechanical", "pass", "auto")
            db.transition_attempt(conn, attempt_id, "mechanical_pass")
            pass_count += 1
            print(f"  [{direction}] PASS (5 ship gates)")

    conn.commit()

    # Auto-advance passing attempts to raw_review_pending
    advanced = 0
    for attempt in checkable:
        row = conn.execute(
            "SELECT id, state FROM attempts WHERE id = ?", (attempt["id"],)
        ).fetchone()
        if row and row["state"] == "mechanical_pass":
            db.transition_attempt(conn, row["id"], "raw_review_pending")
            advanced += 1
    conn.commit()

    print(f"\n  Ship check: {pass_count} pass, {fail_count} fail")
    if advanced:
        print(f"  Auto-advanced {advanced} to raw_review_pending")

    # Run-level footprint consistency gate (informational, does not block)
    run_results = mechanical_ships.gate_ship_footprint_consistency(conn, args.run_id)
    if run_results:
        print(f"\n  --- Run-level footprint consistency ---")
        for gr in run_results:
            status = "PASS" if gr["result"] == "pass" else "WARN"
            print(f"  [{status}] {gr['gate_name']}: {gr['measured']}")
            # Store run-level results against first attempt for traceability
            if checkable:
                db.add_gate_result(
                    conn,
                    attempt_id=checkable[0]["id"],
                    gate_name=gr["gate_name"],
                    result=gr["result"],
                    measured=gr["measured"],
                    expected=gr["expected"],
                    artifact_kind=gr.get("artifact_kind"),
                    artifact_path=gr.get("artifact_path"),
                )
        conn.commit()

    conn.close()


# -- foundry ship-export --------------------------------------

SHIP_EXPORT_SCHEMA_VERSION = "2.0.0"
SHIP_STATES = ["new", "damaged", "destroyed"]


def cmd_ship_export(args):
    """Export an accepted ship run into the 3-state ship export schema.

    Ship closeout path: exports from 'accepted' state (after pixel review).
    No maps, no Godot finish capture — albedo only.

    Export structure (3-state aware):
      exports/ships/{class_slug}/
        new/albedo/{dir}.png          ← from --state new (default)
        damaged/albedo/{dir}.png      ← from --state damaged
        destroyed/albedo/{dir}.png    ← from --state destroyed
        preview/contact_sheet_new.png
        preview/contact_sheet_damaged.png
        preview/contact_sheet_destroyed.png
        manifest.json                 ← tracks which states are populated

    Each invocation populates one state slot. Manifest accumulates across invocations.
    """
    import shutil
    import subprocess

    conn = db.init_db()
    run_id = args.run_id
    state = args.state or "new"

    if state not in SHIP_STATES:
        print(f"Error: invalid state '{state}'. Must be one of: {', '.join(SHIP_STATES)}")
        conn.close()
        sys.exit(1)

    run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        print(f"Error: run '{run_id}' not found.")
        conn.close()
        sys.exit(1)

    subject_id = run["subject_id"]
    subject = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    display_name = subject["display_name"] if subject else subject_id

    # Derive class_slug from subject_id (strip "ship_" prefix if present)
    class_slug = subject_id.replace("ship_", "") if subject_id.startswith("ship_") else subject_id

    # Ship export accepts from 'accepted' state (pixel-reviewed) — no finish required
    accepted = conn.execute(
        """SELECT direction FROM attempts
           WHERE run_id = ? AND state = 'accepted'
           ORDER BY direction""",
        (run_id,),
    ).fetchall()
    accepted_dirs = [r["direction"] for r in accepted]

    if not accepted_dirs:
        accepted = conn.execute(
            """SELECT direction FROM attempts
               WHERE run_id = ? AND state = 'finish_accepted'
               ORDER BY direction""",
            (run_id,),
        ).fetchall()
        accepted_dirs = [r["direction"] for r in accepted]

    if not accepted_dirs:
        print(f"Error: run '{run_id}' has no accepted or finish_accepted attempts.")
        print(f"  Ship export requires pixel-reviewed attempts (state='accepted').")
        conn.close()
        sys.exit(1)

    # Export root is per-class (not per-run), states accumulate
    export_root = db.FOUNDRY_ROOT / "exports" / "ships" / class_slug
    state_dir = export_root / state / "albedo"
    preview_dir = export_root / "preview"

    # Check if this state slot is already populated
    if state_dir.exists() and any(state_dir.iterdir()) and not args.overwrite:
        print(f"Error: state '{state}' already exported at {state_dir}")
        print(f"  Use --overwrite to replace.")
        conn.close()
        sys.exit(1)

    bakeoff_dir = db.FOUNDRY_ROOT / "bakeoff" / run_id
    if not bakeoff_dir.exists():
        print(f"Error: bakeoff directory not found: {bakeoff_dir}")
        conn.close()
        sys.exit(1)

    # Verify source files
    source_map = {}
    for d in accepted_dirs:
        albedo_src = bakeoff_dir / f"{d}.png"
        if not albedo_src.exists():
            print(f"Error: missing source file: {albedo_src}")
            conn.close()
            sys.exit(1)
        source_map[d] = albedo_src

    contact_src = bakeoff_dir / "contact_sheet.png"

    # Create export structure
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'=' * 60}")
    print(f"SHIP EXPORT: {display_name} [{state}]")
    print(f"Run: {run_id}")
    print(f"Target: {export_root}")
    print(f"State: {state}")
    print(f"Directions: {len(accepted_dirs)}")
    print(f"{'=' * 60}")

    # Copy files and compute checksums
    file_checksums = {}

    for d, src in source_map.items():
        dst = state_dir / f"{d}.png"
        shutil.copy2(src, dst)
        rel = f"{state}/albedo/{d}.png"
        file_checksums[rel] = hash_file(dst)
        print(f"  [{state}/albedo] {d}.png  OK")

    if contact_src.exists():
        dst = preview_dir / f"contact_sheet_{state}.png"
        shutil.copy2(contact_src, dst)
        file_checksums[f"preview/contact_sheet_{state}.png"] = hash_file(dst)
        print(f"  [preview] contact_sheet_{state}.png  OK")

    # Provenance
    reject_count = conn.execute(
        "SELECT COUNT(*) as c FROM attempts WHERE run_id = ? AND state IN ('raw_rejected', 'rejected')",
        (run_id,),
    ).fetchone()["c"]

    regen_count = conn.execute(
        "SELECT COUNT(*) as c FROM attempts WHERE run_id = ? AND parent_attempt_id IS NOT NULL",
        (run_id,),
    ).fetchone()["c"]

    accepted_at = conn.execute(
        """SELECT MAX(r.created_at) as t FROM reviews r
           JOIN attempts a ON r.attempt_id = a.id
           WHERE a.run_id = ? AND r.decision = 'accept' AND r.review_type = 'pixel'""",
        (run_id,),
    ).fetchone()
    accepted_at_str = accepted_at["t"] if accepted_at else None

    recipe = {}
    recipe_path = bakeoff_dir / "recipe.json"
    if recipe_path.exists():
        with open(recipe_path) as f:
            recipe = json.load(f)

    git_hash = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(db.FOUNDRY_ROOT),
        )
        if result.returncode == 0:
            git_hash = result.stdout.strip()
    except Exception:
        pass

    # Sprite dimensions
    first_albedo = state_dir / f"{accepted_dirs[0]}.png"
    width, height = 0, 0
    try:
        from PIL import Image
        with Image.open(first_albedo) as img:
            width, height = img.size
    except Exception:
        pass

    # Load existing manifest if present (accumulate states)
    manifest_path = export_root / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = {
            "schema_version": SHIP_EXPORT_SCHEMA_VERSION,
            "asset_family": "ship",
            "identity": {
                "subject_slug": subject_id,
                "display_name": display_name,
                "body_family": "ship",
                "class_slug": class_slug,
            },
            "render_contract": {
                "width": width,
                "height": height,
                "sprite_size": width,
                "direction_count": len(accepted_dirs),
                "direction_order": accepted_dirs,
                "layers": ["albedo"],
                "states": SHIP_STATES,
                "pivot": "center",
                "transparency": True,
            },
            "states": {},
            "files": {},
        }

    # Update manifest with this state's data
    manifest["exported_at"] = now_iso()
    manifest["foundry_version"] = git_hash

    manifest["states"][state] = {
        "run_id": run_id,
        "seed": run["seed"],
        "generated_at": run["created_at"],
        "accepted_at": accepted_at_str,
        "regen_count": regen_count,
        "reject_count": reject_count,
        "direction_count": len(accepted_dirs),
        "generation": {
            "stack_id": run["stack"],
            "checkpoint": recipe.get("checkpoint", "unknown"),
            "lora": recipe.get("lora", "none"),
            "style": recipe.get("body_family", "rendered"),
        },
        "source": {
            "bakeoff_dir": str(bakeoff_dir.relative_to(db.FOUNDRY_ROOT)),
        },
    }

    # Merge file checksums
    manifest["files"].update(file_checksums)

    # Write updated manifest
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    populated = [s for s in SHIP_STATES if s in manifest["states"]]
    print(f"\n  manifest.json written ({len(manifest['files'])} total files)")
    print(f"  States populated: {', '.join(populated)} ({len(populated)}/{len(SHIP_STATES)})")

    print(f"\n{'=' * 60}")
    print(f"SHIP EXPORT COMPLETE: {display_name} [{state}]")
    print(f"  Pack: {export_root}")
    print(f"  State: {state} ({len(accepted_dirs)} directions)")
    print(f"  Total files: {len(manifest['files'])}")
    print(f"  Schema: v{SHIP_EXPORT_SCHEMA_VERSION}")
    print(f"{'=' * 60}")

    conn.close()


# -- CLI argument parser --------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="foundry", description="Star Freight Foundry — asset registry")
    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="Initialize the foundry database")

    # subject-add
    p = sub.add_parser("subject-add", help="Register a subject")
    p.add_argument("id", help="Subject slug (e.g. sera_vale)")
    p.add_argument("--name", required=True, help="Display name")
    p.add_argument("--role", help="Character role")
    p.add_argument("--consumer", help="Game/project consumer")
    p.add_argument("--sheet", help="Path to subject sheet (relative to foundry root)")

    # register-run
    p = sub.add_parser("register-run", help="Register a generation run")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("--subject", required=True, help="Subject ID")
    p.add_argument("--stack", required=True, help="Stack name (e.g. A_v2)")
    p.add_argument("--seed", type=int, required=True, help="Generation seed")
    p.add_argument("--width", type=int, default=576, help="Gen width")
    p.add_argument("--height", type=int, default=768, help="Gen height")
    p.add_argument("--target", type=int, default=48, help="Sprite target size")
    p.add_argument("--prompt-hash", help="SHA256 of positive prompt")
    p.add_argument("--recipe", help="Path to recipe.json")

    # register-attempt
    p = sub.add_parser("register-attempt", help="Register an attempt within a run")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("direction", help="Direction name")
    p.add_argument("--seed", type=int, required=True, help="Seed used")
    p.add_argument("--state", help="Initial state (default: generated)")
    p.add_argument("--artifacts", nargs=2, action="append", metavar=("KIND", "PATH"),
                   help="Artifact to register (e.g. --artifacts raw path/to/raw.png)")

    # check
    p = sub.add_parser("check", help="Run mechanical gates on a run")
    p.add_argument("run_id", help="Run ID")

    # review show
    p = sub.add_parser("review-show", help="Show review status for a run")
    p.add_argument("run_id", help="Run ID")

    # review accept
    p = sub.add_parser("review-accept", help="Accept an attempt")
    p.add_argument("attempt_id", type=int, help="Attempt ID")
    p.add_argument("--note", help="Reviewer note")
    p.add_argument("--reviewer", default="human", help="Reviewer name")

    # review reject
    p = sub.add_parser("review-reject", help="Reject an attempt")
    p.add_argument("attempt_id", type=int, help="Attempt ID")
    p.add_argument("--code", required=True, help="Decision code")
    p.add_argument("--note", help="Reviewer note")
    p.add_argument("--reviewer", default="human", help="Reviewer name")

    # regen
    p = sub.add_parser("regen", help="Create a regen child attempt")
    p.add_argument("attempt_id", type=int, help="Parent attempt ID")
    p.add_argument("--code", required=True, help="Reason code")
    p.add_argument("--seed", type=int, help="New seed (default: inherit parent)")
    p.add_argument("--note", help="Reviewer note")

    # attempt-detail
    p = sub.add_parser("attempt-detail", help="Generate attempt detail view")
    p.add_argument("attempt_id", type=int, help="Attempt ID")

    # finish-board
    p = sub.add_parser("finish-board", help="Generate finish review board for a run")
    p.add_argument("run_id", help="Run ID")

    # status
    p = sub.add_parser("status", help="Foundry dashboard")
    p.add_argument("--subject", help="Filter to one subject")
    p.add_argument("--verbose", "-v", action="store_true", help="Show state breakdown")

    # story
    p = sub.add_parser("story", help="Full decision story of an attempt")
    p.add_argument("attempt_id", type=int, help="Attempt ID")

    # lineage
    p = sub.add_parser("lineage", help="Attempt lineage for a run")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("--direction", "-d", help="Filter to one direction")

    # winner
    p = sub.add_parser("winner", help="Canonical winner per direction")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("--verbose", "-v", action="store_true", help="Show full explanations")

    # drift
    p = sub.add_parser("drift", help="Failure patterns and pass rates")
    p.add_argument("run_id", nargs="?", help="Run ID (omit for foundry-wide)")

    # produce (Phase 4A)
    p = sub.add_parser("produce", help="One-command: maps + finish captures for an accepted run")
    p.add_argument("run_id", help="Run ID")

    # batch-accept (Phase 4A)
    p = sub.add_parser("batch-accept", help="Accept all pending attempts in a run")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("--stage", choices=["raw", "pixel", "finish"], help="Review stage (auto-detect if omitted)")
    p.add_argument("--note", help="Reviewer note applied to all")
    p.add_argument("--reviewer", help="Reviewer name (default: batch_review)")

    # batch-reject (Phase 4A)
    p = sub.add_parser("batch-reject", help="Reject all pending attempts in a run with one code")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("--code", required=True, help="Decision code applied to all")
    p.add_argument("--stage", choices=["raw", "pixel", "finish"], help="Review stage (auto-detect if omitted)")
    p.add_argument("--note", help="Reviewer note applied to all")
    p.add_argument("--reviewer", help="Reviewer name (default: batch_review)")

    # metrics (Phase 4A)
    p = sub.add_parser("metrics", help="Throughput metrics for a run or the whole foundry")
    p.add_argument("run_id", nargs="?", help="Run ID (omit for foundry-wide)")

    # export (Phase 6A)
    p = sub.add_parser("export", help="Export a finish-accepted run as a deterministic asset pack")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing export")

    # ship-check (Ship Lane)
    p = sub.add_parser("ship-check", help="Run ship-specific mechanical gates on a run")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("--direction-count", type=int, default=8, help="Expected direction count (default: 8)")

    # ship-export (Ship Lane)
    p = sub.add_parser("ship-export", help="Export an accepted ship run into 3-state schema")
    p.add_argument("run_id", help="Run ID")
    p.add_argument("--state", choices=["new", "damaged", "destroyed"], default="new",
                   help="Ship state slot to populate (default: new)")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing state slot")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "subject-add": cmd_subject_add,
        "register-run": cmd_register_run,
        "register-attempt": cmd_register_attempt,
        "check": cmd_check,
        "review-show": cmd_review_show,
        "review-accept": cmd_review_accept,
        "review-reject": cmd_review_reject,
        "regen": cmd_regen,
        "attempt-detail": cmd_attempt_detail,
        "finish-board": cmd_finish_board,
        "status": cmd_status,
        "story": cmd_story,
        "lineage": cmd_lineage,
        "winner": cmd_winner,
        "drift": cmd_drift,
        "produce": cmd_produce,
        "batch-accept": cmd_batch_accept,
        "batch-reject": cmd_batch_reject,
        "metrics": cmd_metrics,
        "export": cmd_export,
        "ship-check": cmd_ship_check,
        "ship-export": cmd_ship_export,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

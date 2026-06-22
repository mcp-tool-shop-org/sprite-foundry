"""
Phase 2B — Review boards generated from DB records only.

Three views:
1. Run board: raw-source strip + 48px tiles + state + latest code per direction
2. Attempt detail: artifacts + full review trail + lineage + finish captures
3. Finish board: finish captures grouped by lighting state per direction

Rule: if an image is not registered as an artifact or finish_capture, it does not exist.
Missing artifacts fail loudly.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timezone

from . import db

FOUNDRY_ROOT = db.FOUNDRY_ROOT


def _fonts():
    """Load fonts, falling back to default."""
    try:
        return (
            ImageFont.truetype("consola.ttf", 10),
            ImageFont.truetype("consola.ttf", 12),
            ImageFont.truetype("consola.ttf", 14),
        )
    except (OSError, IOError):
        d = ImageFont.load_default()
        return d, d, d


def _open_decoupled(p: Path) -> Image.Image:
    """Open an image and return a copy with the file handle already closed.

    PIL's Image.open is lazy and holds the file open until the image is closed
    or GC'd, which leaks Windows file locks on the exact PNGs the rest of the
    pipeline (export copy, map derivation) may need to read or replace. Loading
    a decoupled copy here releases the handle immediately.
    """
    with Image.open(p) as img:
        return img.copy()


def _load_artifact_image(conn, attempt_id: int, kind: str) -> Image.Image | None:
    """Load an image from a registered artifact. Returns None if missing."""
    row = conn.execute(
        "SELECT path FROM artifacts WHERE attempt_id = ? AND kind = ?",
        (attempt_id, kind),
    ).fetchone()
    if not row:
        return None
    p = FOUNDRY_ROOT / row["path"]
    if not p.exists():
        return None
    return _open_decoupled(p)


def _load_finish_capture(conn, attempt_id: int, lighting_state: str) -> Image.Image | None:
    """Load a finish capture image. Returns None if missing."""
    row = conn.execute(
        "SELECT path FROM finish_captures WHERE attempt_id = ? AND lighting_state = ?",
        (attempt_id, lighting_state),
    ).fetchone()
    if not row:
        return None
    p = FOUNDRY_ROOT / row["path"]
    if not p.exists():
        return None
    return _open_decoupled(p)


def _latest_review(conn, attempt_id: int, review_type: str) -> dict | None:
    """Get the most recent review of a given type for an attempt."""
    row = conn.execute(
        """SELECT decision, code, note, reviewer, created_at
           FROM reviews WHERE attempt_id = ? AND review_type = ?
           ORDER BY created_at DESC LIMIT 1""",
        (attempt_id, review_type),
    ).fetchone()
    return dict(row) if row else None


def _state_color(state: str) -> tuple:
    """Color for a lifecycle state."""
    if state == "finish_accepted":
        return (80, 200, 80)
    elif state in ("accepted", "raw_accepted"):
        return (120, 200, 120)
    elif state in db.TERMINAL_FAIL_STATES:
        return (200, 80, 80)
    elif state in db.REVIEW_PENDING_STATES:
        return (200, 200, 80)
    elif state == "superseded":
        return (120, 120, 140)
    else:
        return (160, 160, 170)


def _draw_missing(draw, x, y, w, h, font):
    """Draw a MISSING placeholder cell."""
    draw.rectangle([x, y, x + w, y + h], fill=(50, 25, 25), outline=(80, 40, 40))
    draw.text((x + 4, y + h // 2 - 5), "NOT IN DB", fill=(200, 80, 80), font=font)


# ── Run Board ────────────────────────────────────────────────

def generate_run_board(conn, run_id: str, output_path: Path) -> Path:
    """
    Generate a run-level review board.

    Per direction: raw-source thumbnail + 48px tile + state badge + latest decision code.
    All images loaded from registered artifacts only.
    """
    run = conn.execute(
        "SELECT r.*, s.display_name FROM runs r JOIN subjects s ON r.subject_id = s.id WHERE r.id = ?",
        (run_id,),
    ).fetchone()
    if not run:
        raise ValueError(f"Run '{run_id}' not found in registry")

    font_sm, font_md, font_lg = _fonts()

    # Layout constants
    RAW_W = 120
    RAW_H = int(RAW_W * run["gen_height"] / run["gen_width"])
    PIXEL_CELL = 96
    STATE_H = 16
    CODE_H = 14
    COL_W = max(RAW_W, PIXEL_CELL) + 16
    GATE_H = 14
    ROW_H = RAW_H + 8 + PIXEL_CELL + 8 + STATE_H + GATE_H + CODE_H + 12
    HEADER_H = 60
    LABEL_W = 90
    PAD = 4
    BG = (18, 18, 24)
    TEXT = (200, 200, 210)
    ACCENT = (120, 160, 200)
    GRID = (40, 40, 50)

    cols = 8
    total_w = LABEL_W + cols * COL_W + 20
    total_h = HEADER_H + ROW_H + 60

    img = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((10, 8), f"RUN BOARD: {run['display_name']}", fill=ACCENT, font=font_lg)
    draw.text((10, 26), f"Run: {run_id}  |  Stack: {run['stack']}  |  Seed: {run['seed']}  |  Target: {run['sprite_target']}px", fill=TEXT, font=font_sm)
    if run["subject_sheet_hash"]:
        draw.text((10, 38), f"Sheet: {run['subject_sheet_hash'][:16]}...  |  Gen: {run['gen_width']}x{run['gen_height']}", fill=(140, 140, 150), font=font_sm)

    # Column headers
    for col, direction in enumerate(db.DIRECTIONS):
        cx = LABEL_W + col * COL_W + PAD
        label = direction.replace("_", "\n")
        draw.text((cx, HEADER_H - 24), label, fill=TEXT, font=font_sm)

    # Get the canonical (most recent non-superseded) attempt per direction
    attempts_by_dir = {}
    all_attempts = conn.execute(
        """SELECT id, direction, state, seed FROM attempts
           WHERE run_id = ? ORDER BY direction, id DESC""",
        (run_id,),
    ).fetchall()

    for a in all_attempts:
        d = a["direction"]
        # Take the first (most recent) non-superseded attempt per direction
        if d not in attempts_by_dir and a["state"] != "superseded":
            attempts_by_dir[d] = dict(a)

    # Row labels
    oy = HEADER_H
    draw.text((4, oy + 4), "Raw\nSource", fill=(200, 120, 120), font=font_sm)
    draw.text((4, oy + RAW_H + 12), "48px\nPixel", fill=(120, 200, 120), font=font_sm)

    missing_artifacts = []

    for col, direction in enumerate(db.DIRECTIONS):
        cx = LABEL_W + col * COL_W + PAD
        attempt = attempts_by_dir.get(direction)

        if not attempt:
            _draw_missing(draw, cx, oy, COL_W - 8, ROW_H - 20, font_sm)
            missing_artifacts.append(f"{direction}: no attempt")
            continue

        aid = attempt["id"]
        state = attempt["state"]

        # Raw source thumbnail
        raw_img = _load_artifact_image(conn, aid, "raw")
        if raw_img:
            raw_thumb = raw_img.resize((RAW_W, RAW_H), Image.LANCZOS)
            if raw_thumb.mode == "RGBA":
                bg_rect = Image.new("RGB", (RAW_W, RAW_H), (30, 30, 38))
                bg_rect.paste(raw_thumb, (0, 0), raw_thumb)
                img.paste(bg_rect, (cx, oy))
            else:
                img.paste(raw_thumb.convert("RGB"), (cx, oy))
        else:
            _draw_missing(draw, cx, oy, RAW_W, RAW_H, font_sm)
            missing_artifacts.append(f"{direction}: raw")

        # 48px pixel tile
        py = oy + RAW_H + 8
        pixel_img = _load_artifact_image(conn, aid, "pixel")
        if pixel_img:
            display = pixel_img.resize((PIXEL_CELL, PIXEL_CELL), Image.NEAREST)
            # Checkerboard background
            checker = Image.new("RGB", (PIXEL_CELL, PIXEL_CELL))
            cd = ImageDraw.Draw(checker)
            for y2 in range(0, PIXEL_CELL, 8):
                for x2 in range(0, PIXEL_CELL, 8):
                    c = (45, 45, 55) if (x2 // 8 + y2 // 8) % 2 == 0 else (35, 35, 45)
                    cd.rectangle([x2, y2, x2 + 7, y2 + 7], fill=c)
            if display.mode == "RGBA":
                checker.paste(display, (0, 0), display)
            else:
                checker.paste(display, (0, 0))
            img.paste(checker, (cx, py))
        else:
            _draw_missing(draw, cx, py, PIXEL_CELL, PIXEL_CELL, font_sm)
            missing_artifacts.append(f"{direction}: pixel")

        # State badge
        sy = py + PIXEL_CELL + 6
        state_label = state.replace("_", " ")
        draw.text((cx, sy), state_label, fill=_state_color(state), font=font_sm)

        # Gate summary badge
        cy = sy + STATE_H
        gates = db.get_attempt_gates(conn, aid)
        if gates:
            gate_fails = [g for g in gates if g["result"] == "fail"]
            if gate_fails:
                fail_names = [g["gate_name"] for g in gate_fails]
                draw.text((cx, cy), f"GATE FAIL: {fail_names[0]}", fill=(200, 80, 80), font=font_sm)
            else:
                draw.text((cx, cy), f"GATES OK ({len(gates)})", fill=(80, 180, 80), font=font_sm)
            cy += 12

        # Latest decision code
        for rtype in ["finish", "pixel", "raw_source", "mechanical"]:
            rev = _latest_review(conn, aid, rtype)
            if rev and rev["code"]:
                draw.text((cx, cy), f"{rev['code']}", fill=(200, 160, 80), font=font_sm)
                break

    # Footer
    fy = HEADER_H + ROW_H + 8
    draw.line([(10, fy), (total_w - 10, fy)], fill=GRID)
    fy += 6

    accepted = sum(1 for a in attempts_by_dir.values() if a and a["state"] == "finish_accepted")
    draw.text((10, fy), f"Directions: {accepted}/8 finish_accepted", fill=ACCENT, font=font_md)

    if missing_artifacts:
        fy += 16
        draw.text((10, fy), f"MISSING ARTIFACTS: {', '.join(missing_artifacts)}", fill=(200, 80, 80), font=font_sm)

    fy += 16
    draw.text((10, fy), f"Generated from foundry.db at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", fill=(100, 100, 110), font=font_sm)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


# ── Attempt Detail ───────────────────────────────────────────

def generate_attempt_detail(conn, attempt_id: int, output_path: Path) -> Path:
    """
    Generate an attempt-level detail view.

    Shows: all registered artifacts, full review trail, parent/child lineage,
    finish captures if present.
    """
    attempt = conn.execute(
        """SELECT a.*, r.subject_id, r.stack, r.gen_width, r.gen_height, r.sprite_target,
                  s.display_name
           FROM attempts a
           JOIN runs r ON a.run_id = r.id
           JOIN subjects s ON r.subject_id = s.id
           WHERE a.id = ?""",
        (attempt_id,),
    ).fetchone()
    if not attempt:
        raise ValueError(f"Attempt {attempt_id} not found")

    font_sm, font_md, font_lg = _fonts()

    # Collect data
    artifacts = db.get_attempt_artifacts(conn, attempt_id)
    reviews = db.get_attempt_reviews(conn, attempt_id)
    lineage = db.get_attempt_lineage(conn, attempt_id)
    gate_results = db.get_attempt_gates(conn, attempt_id)
    finish_caps = conn.execute(
        "SELECT lighting_state, path FROM finish_captures WHERE attempt_id = ? ORDER BY lighting_state",
        (attempt_id,),
    ).fetchall()

    # Layout
    BG = (18, 18, 24)
    TEXT = (200, 200, 210)
    ACCENT = (120, 160, 200)

    # Image columns: raw, pixel, normal, depth (if they exist)
    img_kinds = ["raw", "pixel", "normal", "depth"]
    IMG_W = 140
    IMG_H = int(IMG_W * attempt["gen_height"] / max(attempt["gen_width"], 1))
    PIXEL_H = 140  # square for pixel art

    # Finish capture row
    FINISH_W = 140
    FINISH_H = 140

    # Calculate total height
    header_h = 80
    img_row_h = max(IMG_H, PIXEL_H) + 30
    gate_h = (20 + len(gate_results) * 14 + 8) if gate_results else 0
    review_h = 20 + len(reviews) * 14
    lineage_h = 20 + len(lineage) * 14
    finish_h = (FINISH_H + 30) if finish_caps else 0
    total_h = header_h + img_row_h + gate_h + review_h + lineage_h + finish_h + 40

    # Width: 4 image columns + labels
    LABEL_W = 80
    total_w = LABEL_W + len(img_kinds) * (IMG_W + 8) + 20
    if finish_caps:
        finish_total_w = LABEL_W + len(finish_caps) * (FINISH_W + 8) + 20
        total_w = max(total_w, finish_total_w)

    img = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(img)

    # Header
    oy = 8
    draw.text((10, oy), f"ATTEMPT #{attempt_id}: {attempt['display_name']} - {attempt['direction']}", fill=ACCENT, font=font_lg)
    oy += 18
    state_color = _state_color(attempt["state"])
    draw.text((10, oy), f"State: {attempt['state']}  |  Seed: {attempt['seed']}  |  Run: {attempt['run_id']}", fill=TEXT, font=font_sm)
    oy += 14
    if attempt["parent_attempt_id"]:
        draw.text((10, oy), f"Regen of #{attempt['parent_attempt_id']}: {attempt['regen_reason']}", fill=(200, 160, 80), font=font_sm)
        oy += 14
    oy += 10

    # Artifact images
    draw.text((10, oy), "Artifacts", fill=ACCENT, font=font_md)
    oy += 18

    for i, kind in enumerate(img_kinds):
        cx = LABEL_W + i * (IMG_W + 8)
        draw.text((cx, oy - 14), kind, fill=TEXT, font=font_sm)

        art_img = _load_artifact_image(conn, attempt_id, kind)
        if art_img:
            if kind == "pixel":
                display = art_img.resize((PIXEL_H, PIXEL_H), Image.NEAREST)
                # Checkerboard
                checker = Image.new("RGB", (PIXEL_H, PIXEL_H))
                cd = ImageDraw.Draw(checker)
                for y2 in range(0, PIXEL_H, 8):
                    for x2 in range(0, PIXEL_H, 8):
                        c = (45, 45, 55) if (x2 // 8 + y2 // 8) % 2 == 0 else (35, 35, 45)
                        cd.rectangle([x2, y2, x2 + 7, y2 + 7], fill=c)
                if display.mode == "RGBA":
                    checker.paste(display, (0, 0), display)
                else:
                    checker.paste(display, (0, 0))
                img.paste(checker, (cx, oy))
            else:
                h = IMG_H if kind == "raw" else min(IMG_H, IMG_W)
                display = art_img.resize((IMG_W, h), Image.LANCZOS)
                if display.mode == "RGBA":
                    bg_rect = Image.new("RGB", (IMG_W, h), (30, 30, 38))
                    bg_rect.paste(display, (0, 0), display)
                    img.paste(bg_rect, (cx, oy))
                else:
                    img.paste(display.convert("RGB"), (cx, oy))
        else:
            _draw_missing(draw, cx, oy, IMG_W, min(IMG_H, PIXEL_H), font_sm)

    oy += max(IMG_H, PIXEL_H) + 12

    # Gate evidence
    gate_results = db.get_attempt_gates(conn, attempt_id)
    if gate_results:
        draw.text((10, oy), "Gate Evidence", fill=ACCENT, font=font_md)
        oy += 16
        for gr in gate_results:
            color = (80, 200, 80) if gr["result"] == "pass" else (200, 80, 80)
            measured = gr["measured"] or ""
            if len(measured) > 60:
                measured = measured[:57] + "..."
            draw.text((20, oy), f"{gr['gate_name']:22s} {gr['result']:5s}  {measured}", fill=color, font=font_sm)
            oy += 14
        oy += 8

    # Review trail
    draw.text((10, oy), "Review Trail", fill=ACCENT, font=font_md)
    oy += 16
    for rev in reviews:
        code_str = f" [{rev['code']}]" if rev["code"] else ""
        note_str = f" -- {rev['note']}" if rev["note"] else ""
        color = (80, 200, 80) if rev["decision"] in ("pass", "accept") else (200, 80, 80) if rev["decision"] in ("fail", "reject") else TEXT
        draw.text((20, oy), f"{rev['review_type']:12s} {rev['decision']:8s}{code_str}{note_str}", fill=color, font=font_sm)
        oy += 14

    oy += 8

    # Lineage
    if len(lineage) > 1:
        draw.text((10, oy), "Lineage", fill=ACCENT, font=font_md)
        oy += 16
        for i, ancestor in enumerate(lineage):
            prefix = ">> " if i == 0 else "   "
            reason = f" (regen: {ancestor['regen_reason']})" if ancestor["regen_reason"] else ""
            draw.text((20, oy), f"{prefix}#{ancestor['id']} {ancestor['state']}{reason}", fill=TEXT, font=font_sm)
            oy += 14
        oy += 8

    # Finish captures
    if finish_caps:
        draw.text((10, oy), "Finish Captures", fill=ACCENT, font=font_md)
        oy += 18

        for i, cap in enumerate(finish_caps):
            cx = LABEL_W + i * (FINISH_W + 8)
            draw.text((cx, oy - 14), cap["lighting_state"], fill=TEXT, font=font_sm)

            cap_path = FOUNDRY_ROOT / cap["path"]
            if cap_path.exists():
                with Image.open(cap_path) as _cap:
                    cap_img = _cap.convert("RGB")  # decoupled; handle closes here
                # Center-crop to sprite area
                w, h = cap_img.size
                crop_margin = int(w * 0.2)
                cropped = cap_img.crop((crop_margin, crop_margin // 2, w - crop_margin, h - crop_margin))
                display = cropped.resize((FINISH_W, FINISH_H), Image.NEAREST)
                img.paste(display, (cx, oy))
            else:
                _draw_missing(draw, cx, oy, FINISH_W, FINISH_H, font_sm)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


# ── Finish Board ─────────────────────────────────────────────

def generate_finish_board(conn, run_id: str, output_path: Path) -> Path:
    """
    Generate a finish-level review board.

    8 directions x 4 lighting states, all from registered finish_captures only.
    """
    run = conn.execute(
        "SELECT r.*, s.display_name FROM runs r JOIN subjects s ON r.subject_id = s.id WHERE r.id = ?",
        (run_id,),
    ).fetchone()
    if not run:
        raise ValueError(f"Run '{run_id}' not found")

    font_sm, font_md, font_lg = _fonts()

    LIGHTING_STATES = ["baseline", "moonlight", "torch", "moon_particles_depth"]
    STATE_LABELS = ["Baseline", "Moonlight", "Torch", "Moon+Part+Depth"]
    CROP_BOX = (106, 70, 406, 420)  # sprite area in 512x512 viewport

    CELL = 140
    PAD = 3
    LABEL_W = 120
    HEADER_H = 50
    BG = (18, 18, 24)
    TEXT = (200, 200, 210)
    ACCENT = (120, 160, 200)
    GRID = (40, 40, 50)

    cols = 8
    rows = len(LIGHTING_STATES)
    total_w = LABEL_W + cols * (CELL + PAD) + 20
    total_h = HEADER_H + rows * (CELL + PAD) + 60

    img = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((10, 8), f"FINISH BOARD: {run['display_name']}", fill=ACCENT, font=font_lg)
    draw.text((10, 26), f"Run: {run_id}  |  4 lighting states x 8 directions", fill=TEXT, font=font_sm)

    # Column headers
    for col, direction in enumerate(db.DIRECTIONS):
        cx = LABEL_W + col * (CELL + PAD) + PAD
        draw.text((cx, HEADER_H - 20), direction.replace("_", "\n"), fill=TEXT, font=font_sm)

    # Get canonical attempt per direction
    attempts_by_dir = {}
    all_attempts = conn.execute(
        """SELECT id, direction, state FROM attempts
           WHERE run_id = ? AND state IN ('finish_review_pending', 'finish_accepted')
           ORDER BY direction""",
        (run_id,),
    ).fetchall()
    for a in all_attempts:
        attempts_by_dir[a["direction"]] = a["id"]

    missing = []

    for row, (ls, label) in enumerate(zip(LIGHTING_STATES, STATE_LABELS)):
        ry = HEADER_H + row * (CELL + PAD)
        draw.text((4, ry + CELL // 2 - 6), label, fill=ACCENT, font=font_md)

        for col, direction in enumerate(db.DIRECTIONS):
            cx = LABEL_W + col * (CELL + PAD)
            aid = attempts_by_dir.get(direction)

            if not aid:
                _draw_missing(draw, cx, ry, CELL, CELL, font_sm)
                missing.append(f"{direction}_{ls}")
                continue

            cap_img = _load_finish_capture(conn, aid, ls)
            if cap_img:
                cap_rgb = cap_img.convert("RGB")
                w, h = cap_rgb.size
                # Apply crop if image is the expected viewport size
                if w >= 400 and h >= 400:
                    cropped = cap_rgb.crop(CROP_BOX)
                else:
                    cropped = cap_rgb
                display = cropped.resize((CELL, CELL), Image.NEAREST)
                img.paste(display, (cx, ry))
            else:
                _draw_missing(draw, cx, ry, CELL, CELL, font_sm)
                missing.append(f"{direction}_{ls}")

    # Footer
    fy = HEADER_H + rows * (CELL + PAD) + 8
    draw.line([(10, fy), (total_w - 10, fy)], fill=GRID)
    fy += 6

    total_cells = cols * rows
    present = total_cells - len(missing)
    color = ACCENT if not missing else (200, 160, 80)
    draw.text((10, fy), f"Finish captures: {present}/{total_cells} from registry", fill=color, font=font_md)

    if missing:
        fy += 16
        draw.text((10, fy), f"Missing: {len(missing)} (not registered in finish_captures)", fill=(200, 80, 80), font=font_sm)

    fy += 16
    draw.text((10, fy), f"Generated from foundry.db at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", fill=(100, 100, 110), font=font_sm)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path

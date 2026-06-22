"""
Trellis bridge — ingest an externally-rendered 8-direction sprite set into the
foundry lifecycle.

Sprite GENERATION lives in the sibling repo ``trellis-sprite-pipeline`` (single
image -> Trellis 3D mesh -> Blender 8-direction render). sprite-foundry's role is
QA + finish-lab + export + packaging. This module is the missing bridge: it takes
a directory of externally-rendered 8-direction PNGs and registers them into the
foundry SQLite lifecycle as a run + 8 attempts — so ``foundry check`` / review /
``foundry produce`` / ``foundry export`` then work on them EXACTLY as if
``foundry_gen`` had produced them.

Input contract (matches trellis-sprite-pipeline/render_views.py +
downsample_sprites.py):
    - 8 direction PNGs: front, front_right, right, back_right, back, back_left,
      left, front_left (transparent background, square, typically 512px).
    - Optional per-direction maps ``<dir>_normal.png`` / ``<dir>_depth.png`` —
      ingested if present, skipped cleanly if absent.

Processing reuses ``foundry_gen``'s content-bbox crop + square pad + NEAREST
downscale (the F-018 fix) to produce the 48x48 transparent pixel artifact from
each render. Registration reuses the foundry CLI's ``register-run`` /
``register-attempt`` command logic so the lifecycle contract is identical to the
generation path.

Usage:
    python -m pipeline.foundry_ingest --dir <render_dir> --subject <subject_id> \
        [--seed N] [--run-id ID] [--source trellis]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from foundry import cli, db

# Reuse the exact processing helpers from the generation path (do not
# re-implement). remove_bg is a safety no-op on already-transparent trellis
# renders; crop_to_square is the F-018 content-bbox crop + square pad.
from pipeline.foundry_gen import (
    DIRECTIONS,
    SPRITE_TARGET,
    apply_crop_box,
    content_crop_box,
    crop_to_square,
    remove_bg,
)

# Direction filenames, in the trellis render order. We register in this order so
# the run reads naturally; the foundry sorts by direction internally anyway.
DIRECTION_NAMES = [d[0] for d in DIRECTIONS]

# Optional per-direction map kinds. The foundry artifact vocabulary
# (db.ARTIFACT_KINDS) already includes 'normal' and 'depth', so we register them
# directly when the source files are present.
MAP_KINDS = ("normal", "depth")


def _ns(**kwargs):
    """Build an argparse.Namespace for an in-process foundry CLI call."""
    return argparse.Namespace(**kwargs)


def validate_render_dir(render_dir: Path) -> list[str]:
    """Return the list of MISSING required direction PNGs (empty == all present).

    All 8 sprite PNGs must be present up front. We never partial-register: if any
    are missing the caller fails with an actionable error naming exactly which.
    """
    missing = []
    for name in DIRECTION_NAMES:
        if not (render_dir / f"{name}.png").exists():
            missing.append(f"{name}.png")
    return missing


def process_direction(
    render_dir: Path, out_dir: Path, maps_dir: Path, direction: str
) -> dict:
    """Process one direction's render into foundry artifacts.

    Produces:
        - ``<dir>_raw.png``  : the source render copied into the run out_dir
                               (the foundry's 'raw' artifact convention).
        - ``<dir>.png``      : the 48x48 transparent pixel artifact.
        - ``<dir>_normal.png`` / ``<dir>_depth.png`` : if the source provided
          them, cropped+downscaled to match the 48x48 albedo and written into
          ``maps_dir`` (the run's ``<run_id>_maps`` directory).

    Returns a dict of {artifact_kind: Path} for everything written.
    """
    src = render_dir / f"{direction}.png"
    artifacts: dict[str, Path] = {}

    # --- raw: keep the original render bytes as the run's raw source ---
    raw_img = Image.open(src).convert("RGBA")
    raw_path = out_dir / f"{direction}_raw.png"
    raw_img.save(str(raw_path))
    artifacts["raw"] = raw_path

    # --- pixel: bg-safety no-op -> content-bbox square crop -> NEAREST 48x48 ---
    # Trellis renders are already transparent, so remove_bg's corner check finds
    # no green screen and falls back to corner-color matching against fully
    # transparent corners — a clean no-op that leaves the alpha untouched.
    cleaned = remove_bg(raw_img)
    pixel_img = crop_to_square(cleaned).resize(
        (SPRITE_TARGET, SPRITE_TARGET), Image.NEAREST
    )
    pixel_path = out_dir / f"{direction}.png"
    pixel_img.save(str(pixel_path))
    artifacts["pixel"] = pixel_path

    # --- optional maps: align to the albedo, downscale, write into _maps ---
    # If the source rendered normal/depth maps, they share the albedo's framing,
    # so we apply the SAME content-bbox crop computed from the albedo's alpha (not
    # each map's own bbox) and the SAME NEAREST downscale to SPRITE_TARGET. This
    # keeps the maps pixel-aligned with the 48x48 albedo instead of passing them
    # through at source resolution (the F-014 export-contract violation: the
    # export contract requires "8 × matching normal/depth maps").
    #
    # NEAREST selects existing pixels rather than averaging neighbours, so normal
    # vectors stay unit-length and need no renormalization — matching
    # foundry_maps.pixelate_map, the derivation path this mirrors.
    #
    # Maps are written into maps_dir (``<run_id>_maps``), NOT the bakeoff dir,
    # because `foundry export` resolves normal/depth strictly from that directory.
    # Registering them as 'normal'/'depth' artifacts also makes `foundry produce`
    # skip ComfyUI map derivation, correctly preserving the higher-fidelity
    # geometry maps the renderer already produced.
    box_result = content_crop_box(cleaned)
    for kind in MAP_KINDS:
        map_src = render_dir / f"{direction}_{kind}.png"
        if not map_src.exists():
            continue
        map_img = Image.open(map_src)
        if box_result is not None:
            box, side = box_result
            aligned = apply_crop_box(map_img, box, side)
        else:
            # Fully transparent albedo (no silhouette to align to): fall back to a
            # plain square downscale so we still emit a SPRITE_TARGET-sized map.
            aligned = map_img.convert("RGBA")
        map_out = aligned.resize((SPRITE_TARGET, SPRITE_TARGET), Image.NEAREST)
        maps_dir.mkdir(parents=True, exist_ok=True)
        map_path = maps_dir / f"{direction}_{kind}.png"
        map_out.save(str(map_path))
        artifacts[kind] = map_path

    return artifacts


def ingest(
    render_dir,
    subject_id: str,
    seed: int = 0,
    run_id: str = None,
    source: str = "trellis",
    display_name: str = None,
):
    """Ingest an 8-direction render set into the foundry lifecycle.

    Validates all 8 directions up front (no partial registration), processes each
    into raw + pixel (+ optional normal/depth) artifacts under the foundry's
    bakeoff convention, then registers a run + 8 attempts via the foundry CLI's
    own command logic. Result: 8 attempts in state 'generated', ready for
    ``foundry check``.

    Returns the run_id.
    """
    render_dir = Path(render_dir)

    if not render_dir.is_dir():
        raise FileNotFoundError(
            f"Render directory not found: {render_dir}. "
            f"Point --dir at the trellis 8-direction output folder."
        )

    # --- Validate the full directional set up front (andon: fail before any
    # registration so we never leave a half-registered run) ---
    missing = validate_render_dir(render_dir)
    if missing:
        raise FileNotFoundError(
            f"Incomplete render set in {render_dir}: missing {len(missing)} "
            f"required direction PNG(s): {', '.join(missing)}. "
            f"Expected all 8 of: {', '.join(f'{d}.png' for d in DIRECTION_NAMES)}. "
            f"Nothing was registered."
        )

    # --- Ensure the subject exists (register-run requires it) ---
    conn = db.init_db()
    existing = conn.execute(
        "SELECT id FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    if not existing:
        conn.execute(
            """INSERT INTO subjects (id, display_name, role, consumer,
                                     subject_sheet_path, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (subject_id, display_name or subject_id, None, None, None,
             cli.now_iso()),
        )
        conn.commit()
        print(f"  Subject '{subject_id}' registered (was not present).")
    conn.close()

    # --- Build the run out_dir (same convention foundry_gen uses) ---
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if not run_id:
        run_id = f"{subject_id}_ingest_{ts}"
    out_dir = db.FOUNDRY_ROOT / "bakeoff" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # Maps land in the `<run_id>_maps` sibling dir — the same convention
    # foundry_maps.derive_maps uses and the only place `foundry export` looks for
    # normal/depth. Created lazily by process_direction when a map is present.
    maps_dir = db.FOUNDRY_ROOT / "bakeoff" / f"{run_id}_maps"

    print(f"\n{'=' * 60}")
    print(f"FOUNDRY INGEST ({source}): {subject_id}")
    print(f"Run: {run_id}  Seed: {seed}")
    print(f"Source: {render_dir}")
    print(f"Output: {out_dir}")
    print(f"{'=' * 60}\n")

    # --- Process each direction into artifacts ---
    per_direction: dict[str, dict] = {}
    has_maps = False
    for direction in DIRECTION_NAMES:
        artifacts = process_direction(render_dir, out_dir, maps_dir, direction)
        per_direction[direction] = artifacts
        map_tags = [k for k in MAP_KINDS if k in artifacts]
        if map_tags:
            has_maps = True
        suffix = f" (+ {', '.join(map_tags)})" if map_tags else ""
        print(f"  [{direction}] processed{suffix}")

    # --- Write a recipe describing the ingest provenance ---
    recipe_path = out_dir / "recipe.json"
    with open(recipe_path, "w") as f:
        json.dump(
            {
                "stack": source,
                "source": source,
                "ingested": True,
                "render_dir": str(render_dir),
                "pixelate": SPRITE_TARGET,
                "seed": seed,
                "maps_ingested": has_maps,
            },
            f,
            indent=2,
        )

    # --- Register the run via the foundry CLI's own command logic ---
    print(f"\n--- Registering in foundry ---")
    cli.cmd_register_run(
        _ns(
            run_id=run_id,
            subject=subject_id,
            stack=source,
            seed=seed,
            width=0,
            height=0,
            target=SPRITE_TARGET,
            prompt_hash=None,
            recipe=str(recipe_path),
        )
    )

    # --- Register each attempt with its artifacts ---
    for direction in DIRECTION_NAMES:
        artifacts = per_direction[direction]

        # Assert every artifact path exists before register-attempt (F-008): a
        # path pointing at nothing must never enter the DB.
        artifact_args = []
        for kind in ("raw", "pixel", *MAP_KINDS):
            if kind not in artifacts:
                continue
            p = artifacts[kind]
            if not p.exists():
                raise FileNotFoundError(
                    f"Refusing to register a dangling artifact: {kind} for "
                    f"{direction} was not written to {p}."
                )
            artifact_args.append([kind, str(p)])

        cli.cmd_register_attempt(
            _ns(
                run_id=run_id,
                direction=direction,
                seed=seed,
                state="generated",
                artifacts=artifact_args,
            )
        )

    # --- Next-step guidance ---
    print(f"\n{'=' * 60}")
    print(f"INGEST COMPLETE: {subject_id}")
    print(f"Run: {run_id}  ({len(DIRECTION_NAMES)} attempts in 'generated')")
    print(f"Next steps:")
    print(f"  python -m foundry check {run_id}")
    print(f"  python -m foundry review-show {run_id}")
    print(f"  python -m foundry produce {run_id}")
    print(f"  python -m foundry export {run_id}")
    print(f"{'=' * 60}")

    return run_id


def main():
    parser = argparse.ArgumentParser(
        prog="foundry_ingest",
        description="Ingest an externally-rendered 8-direction sprite set into "
                    "the foundry lifecycle (trellis bridge).",
    )
    parser.add_argument(
        "--dir", required=True,
        help="Directory of externally-rendered 8-direction PNGs",
    )
    parser.add_argument(
        "--subject", required=True,
        help="Subject ID to register the run under (created if absent)",
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="Seed to record on the run + attempts (default: 0)",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Run ID (default: <subject>_ingest_<timestamp>)",
    )
    parser.add_argument(
        "--source", default="trellis",
        help="Source/stack label recorded on the run (default: trellis)",
    )
    parser.add_argument(
        "--display-name", default=None,
        help="Display name if the subject must be created (default: subject id)",
    )
    args = parser.parse_args()

    try:
        ingest(
            render_dir=args.dir,
            subject_id=args.subject,
            seed=args.seed,
            run_id=args.run_id,
            source=args.source,
            display_name=args.display_name,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

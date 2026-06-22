"""
Phase 3 — Foundry-integrated generation runner.

Generates 8-direction sprites for a character, then registers the run,
attempts, and artifacts in the foundry registry automatically.
Runs mechanical gates after registration.

Usage:
    python -m pipeline.foundry_gen --config pipeline/chars/thal.json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import urlopen, Request

from PIL import Image, ImageDraw, ImageFont
import numpy as np

COMFY_URL = "http://127.0.0.1:8188"
FOUNDRY_ROOT = Path(__file__).parent.parent
SPRITE_TARGET = 48

# HTTP timeouts for all ComfyUI calls (seconds). A dead server should fail fast,
# not hang a urlopen() indefinitely (F-007).
HTTP_TIMEOUT = 30

DIRECTIONS = [
    ("front", "facing the viewer, front view, looking at camera"),
    ("front_left", "facing front-left, 3/4 view from the left, looking slightly left"),
    ("left", "facing left, left side profile view"),
    ("back_left", "facing back-left, 3/4 rear view from the left"),
    ("back", "facing away from viewer, rear view, back of character"),
    ("back_right", "facing back-right, 3/4 rear view from the right"),
    ("right", "facing right, right side profile view"),
    ("front_right", "facing front-right, 3/4 view from the right, looking slightly right"),
]

STYLE_SUFFIX = (
    "pixel art sprite, game character sprite, 2D RPG, clean pixel art, "
    "bright green background, #00FF00 green screen background, centered composition, full body shot, "
    "character centered in frame, HD-2D inspired, crisp pixel edges, "
    "single character portrait, character design, isolated figure"
)

# Chroma key color for background removal (bright green = green screen)
CHROMA_KEY = (0, 255, 0)

# Generation canvas + batch size.
# Defaults below preserve the current sprite output (576x768, batch_size=1) and
# were tuned for the old RTX 5080 (16 GB VRAM). The rig is now an RTX 5090
# (32 GB) with headroom to raise SPRITE_FOUNDRY_BATCH_SIZE (and/or batch
# directions per KSampler call) to cut wall-clock time. Override via env without
# changing the committed defaults so the canonical sprite output is unchanged.
GEN_WIDTH = int(os.environ.get("SPRITE_FOUNDRY_GEN_WIDTH", "576"))
GEN_HEIGHT = int(os.environ.get("SPRITE_FOUNDRY_GEN_HEIGHT", "768"))
BATCH_SIZE = int(os.environ.get("SPRITE_FOUNDRY_BATCH_SIZE", "1"))


NEGATIVE_BG = "white background, gray background, grey background, beige background, gradient background"

def make_workflow(subject_prompt: str, negative_prompt: str, direction_prompt: str,
                  seed: int, filename_prefix: str) -> dict:
    """Stack A v2: JuggernautXL + pixel-art-xl @ 0.85, portrait aspect."""
    # Enforce green screen in negative prompt
    full_negative = f"{negative_prompt}, {NEGATIVE_BG}" if negative_prompt else NEGATIVE_BG
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "juggernautXL_ragnarokBy.safetensors"},
        },
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0], "clip": ["1", 1],
                "lora_name": "pixel-art-xl.safetensors",
                "strength_model": 0.85, "strength_clip": 0.85,
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": f"{subject_prompt}, {direction_prompt}, {STYLE_SUFFIX}",
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 1], "text": full_negative},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": GEN_WIDTH, "height": GEN_HEIGHT, "batch_size": BATCH_SIZE},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                "latent_image": ["5", 0], "seed": seed,
                "steps": 30, "cfg": 7.5,
                "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0,
            },
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": filename_prefix},
        },
    }


def check_comfy_reachable():
    """Fail fast if ComfyUI is not reachable, before queueing 8 directions (F-007)."""
    try:
        with urlopen(f"{COMFY_URL}/system_stats", timeout=HTTP_TIMEOUT) as resp:
            resp.read()
    except (URLError, HTTPError, OSError) as e:
        raise RuntimeError(
            f"ComfyUI not reachable at {COMFY_URL} ({e}). "
            f"Start ComfyUI (default 127.0.0.1:8188) and retry."
        ) from e


def queue_prompt(workflow):
    data = json.dumps({"prompt": workflow}).encode()
    req = Request(f"{COMFY_URL}/prompt", data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read())


def _check_history_status(prompt_id, entry):
    """Raise RuntimeError if ComfyUI recorded an execution error for this prompt.

    ComfyUI stores FAILED prompts in /history too, with
    status.status_str == 'error' and status.messages describing the failure.
    Without this check the caller sees a 'completed' entry that has no outputs
    and misreports it as a generic extract failure (F-006).
    """
    status = entry.get("status", {})
    if status.get("status_str") == "error" or status.get("completed") is False:
        messages = status.get("messages", [])
        detail = "; ".join(str(m) for m in messages) if messages else "no detail provided"
        raise RuntimeError(f"ComfyUI execution error for prompt {prompt_id[:8]}: {detail}")


def wait_for_completion(prompt_id, timeout=180):
    start = time.time()
    connect_failures = 0
    while time.time() - start < timeout:
        try:
            with urlopen(f"{COMFY_URL}/history/{prompt_id}", timeout=HTTP_TIMEOUT) as resp:
                history = json.loads(resp.read())
            connect_failures = 0
            if prompt_id in history:
                entry = history[prompt_id]
                _check_history_status(prompt_id, entry)
                return entry
        except RuntimeError:
            # Execution error surfaced by _check_history_status — propagate.
            raise
        except (URLError, HTTPError, OSError) as e:
            # Distinguish "server gone" from "not ready yet": after a few
            # consecutive connection failures, abort instead of polling the
            # full timeout against a dead server (F-007).
            connect_failures += 1
            if connect_failures >= 3:
                raise RuntimeError(
                    f"ComfyUI became unreachable at {COMFY_URL} while waiting "
                    f"for prompt {prompt_id[:8]} ({e})."
                ) from e
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f"Prompt {prompt_id} timed out after {timeout}s")


def get_image(filename, subfolder=""):
    params = f"filename={filename}&subfolder={subfolder}&type=output"
    with urlopen(f"{COMFY_URL}/view?{params}", timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


def remove_bg(img, tolerance=35):
    """Remove background using chroma key (green screen) or corner-color fallback.

    Primary: match bright green (#00FF00) chroma key — clean, deterministic.
    Fallback: if corners aren't green, use corner-color matching (legacy behavior).
    """
    arr = np.array(img.convert("RGBA")).copy()
    h, w = arr.shape[:2]

    # Check if corners are green (chroma key generation worked)
    corners = [arr[0, 0, :3], arr[0, w-1, :3], arr[h-1, 0, :3], arr[h-1, w-1, :3]]
    avg_corner = np.mean(corners, axis=0)
    is_green_screen = avg_corner[1] > 200 and avg_corner[0] < 100 and avg_corner[2] < 100

    if is_green_screen:
        # Chroma key removal — remove pixels where green channel dominates
        rgb = arr[:, :, :3].astype(np.float32)
        green_dominant = (rgb[:, :, 1] > 150) & (rgb[:, :, 1] > rgb[:, :, 0] + 50) & (rgb[:, :, 1] > rgb[:, :, 2] + 50)
        arr[green_dominant, 3] = 0
        # Also handle green fringe on edges — reduce alpha for semi-green pixels
        green_ratio = rgb[:, :, 1] / (rgb[:, :, 0] + rgb[:, :, 2] + 1)
        fringe = (green_ratio > 0.8) & (~green_dominant)
        arr[fringe, 3] = (arr[fringe, 3] * 0.5).astype(np.uint8)
    else:
        # Fallback: corner-color removal (for sprites not generated with green screen)
        bg_color = avg_corner.astype(np.float32)
        rgb = arr[:, :, :3].astype(np.float32)
        diff = np.sqrt(np.sum((rgb - bg_color) ** 2, axis=2))
        arr[diff < tolerance, 3] = 0

    return Image.fromarray(arr)


def crop_to_square(cleaned):
    """Content-bounding-box crop + square pad (preserves the whole subject).

    Replaces the fixed top=(h-w)//4 heuristic, which assumed the subject sits in
    a fixed vertical band of the 576x768 canvas and silently truncated tall,
    short, or off-center figures (F-018). Ported from
    foundry_gen_zero123.process_to_pixel.
    """
    arr = np.array(cleaned.convert("RGBA"))
    visible = arr[:, :, 3] > 0
    if not np.any(visible):
        return cleaned  # nothing to crop; let downstream resize handle it
    rows = np.any(visible, axis=1)
    cols = np.any(visible, axis=0)
    top, bottom = np.where(rows)[0][[0, -1]]
    left, right = np.where(cols)[0][[0, -1]]
    cropped = cleaned.crop((left, top, right + 1, bottom + 1))
    w, h = cropped.size
    side = max(w, h)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(cropped, ((side - w) // 2, (side - h) // 2))
    return square


def make_contact_sheets(raw_images, pixel_images, config, run_id, out_dir):
    """Generate raw inspection and pixel contact sheets."""
    CELL = 192
    PAD = 4
    LABEL_W = 90
    HEADER_H = 28
    CELL_W = CELL + PAD * 2
    CELL_H = int(CELL * GEN_HEIGHT / GEN_WIDTH) + PAD * 2
    BG = (24, 24, 32)
    TEXT = (200, 200, 210)
    ACCENT = (200, 120, 120)
    GRID = (50, 50, 60)

    try:
        font_sm = ImageFont.truetype("consola.ttf", 11)
        font_lg = ImageFont.truetype("consola.ttf", 15)
    except (OSError, IOError):
        font_sm = font_lg = ImageFont.load_default()

    dir_names = [d[0] for d in DIRECTIONS]
    char_name = config["display_name"]

    # Raw inspection sheet
    total_w = LABEL_W + 8 * CELL_W + 20
    total_h = 10 + 24 + HEADER_H + CELL_H + 10 + 60 + 20
    img = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(img)

    ox, oy = 10, 10
    draw.text((ox, oy), f"RAW SOURCE INSPECTION -- {char_name}", fill=ACCENT, font=font_lg)
    oy += 24
    for col, name in enumerate(dir_names):
        draw.text((ox + LABEL_W + col * CELL_W + PAD, oy + 2), name.replace("_", "\n"), fill=TEXT, font=font_sm)
    oy += HEADER_H
    draw.text((ox + 2, oy + CELL_H // 2 - 6), "Raw\n576x768", fill=ACCENT, font=font_sm)
    cell_h_inner = int(CELL * GEN_HEIGHT / GEN_WIDTH)
    for col, name in enumerate(dir_names):
        cx = ox + LABEL_W + col * CELL_W + PAD
        cy = oy + PAD
        if name in raw_images:
            raw = raw_images[name].resize((CELL, cell_h_inner), Image.LANCZOS)
            img.paste(raw, (cx, cy))
        else:
            draw.rectangle([cx, cy, cx + CELL, cy + cell_h_inner], fill=(60, 30, 30), outline=GRID)

    raw_sheet = out_dir / "raw_inspection.png"
    raw_sheet.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(raw_sheet), "PNG")

    # Pixel contact sheet
    PCELL = 128
    PCELL_W = PCELL + PAD * 2
    PCELL_H = PCELL + PAD * 2
    total_w = 80 + 8 * PCELL_W + 20
    total_h = 10 + 24 + HEADER_H + PCELL_H + 10 + 60 + 20
    img = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(img)

    ox, oy = 10, 10
    draw.text((ox, oy), f"Phase 3 -- {char_name} -- Stack A v2 (48x48)", fill=(120, 200, 120), font=font_lg)
    oy += 24
    for col, name in enumerate(dir_names):
        draw.text((ox + 80 + col * PCELL_W + PAD, oy + 2), name.replace("_", "\n"), fill=TEXT, font=font_sm)
    oy += HEADER_H
    for col, name in enumerate(dir_names):
        cx = ox + 80 + col * PCELL_W + PAD
        cy = oy + PAD
        if name in pixel_images:
            display = pixel_images[name].resize((PCELL, PCELL), Image.NEAREST)
            checker = Image.new("RGB", (PCELL, PCELL))
            cd = ImageDraw.Draw(checker)
            for y2 in range(0, PCELL, 8):
                for x2 in range(0, PCELL, 8):
                    c = (45, 45, 55) if (x2 // 8 + y2 // 8) % 2 == 0 else (35, 35, 45)
                    cd.rectangle([x2, y2, x2 + 7, y2 + 7], fill=c)
            if display.mode == "RGBA":
                checker.paste(display, (0, 0), display)
            else:
                checker.paste(display, (0, 0))
            img.paste(checker, (cx, cy))

    pixel_sheet = out_dir / "contact_sheet.png"
    img.save(str(pixel_sheet), "PNG")

    return raw_sheet, pixel_sheet


def foundry_cmd(*args):
    """Run a foundry CLI command via subprocess."""
    cmd = [sys.executable, "-m", "foundry.cli"] + list(args)
    result = subprocess.run(cmd, cwd=str(FOUNDRY_ROOT), capture_output=True, text=True)
    if result.stdout:
        print(f"    {result.stdout.strip()}")
    if result.returncode != 0 and result.stderr:
        print(f"    ERROR: {result.stderr.strip()}")
    return result.returncode


def generate_and_register(config: dict):
    """Generate 8-direction sprites and register everything in the foundry."""
    subject_id = config["subject_id"]
    char_name = config["display_name"]
    seed = config["seed"]
    subject_prompt = config["subject_prompt"]
    negative_prompt = config["negative_prompt"]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{subject_id}_p3_{ts}"
    out_dir = FOUNDRY_ROOT / "bakeoff" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"PHASE 3 GENERATION: {char_name}")
    print(f"Run: {run_id}  Seed: {seed}")
    print(f"Output: {out_dir}")
    print(f"{'=' * 60}\n")

    # Fail fast if ComfyUI is down before queueing 8 directions (F-007).
    check_comfy_reachable()

    raw_images = {}
    pixel_images = {}
    generated_dirs = []

    for dir_name, dir_prompt in DIRECTIONS:
        print(f"  [{dir_name}] submitting...", end=" ", flush=True)

        workflow = make_workflow(subject_prompt, negative_prompt, dir_prompt, seed, f"{subject_id}_p3")
        try:
            resp = queue_prompt(workflow)
            pid = resp["prompt_id"]
        except Exception as e:
            print(f"SUBMIT FAIL: {e}")
            continue

        print(f"queued ({pid[:8]}), waiting...", end=" ", flush=True)

        try:
            history = wait_for_completion(pid)
        except TimeoutError:
            print("TIMEOUT")
            continue

        try:
            img_info = history["outputs"]["8"]["images"][0]
            img_data = get_image(img_info["filename"], img_info.get("subfolder", ""))

            raw_path = out_dir / f"{dir_name}_raw.png"
            with open(raw_path, "wb") as f:
                f.write(img_data)
            raw_img = Image.open(raw_path)
            raw_images[dir_name] = raw_img

            # Remove background + crop to subject bounding box + pixelate
            cleaned = remove_bg(raw_img.convert("RGBA"))
            cleaned = crop_to_square(cleaned)

            pixel_img = cleaned.resize((SPRITE_TARGET, SPRITE_TARGET), Image.NEAREST)
            pixel_path = out_dir / f"{dir_name}.png"
            pixel_img.save(str(pixel_path))
            pixel_images[dir_name] = pixel_img

            generated_dirs.append(dir_name)
            print("OK")
        except Exception as e:
            print(f"EXTRACT FAIL: {e}")
            continue

    # Contact sheets
    raw_sheet, pixel_sheet = make_contact_sheets(raw_images, pixel_images, config, run_id, out_dir)
    print(f"\n  Raw inspection: {raw_sheet}")
    print(f"  Pixel contact:  {pixel_sheet}")

    # Save recipe
    with open(out_dir / "recipe.json", "w") as f:
        json.dump({
            "stack": "A_v2", "character": char_name,
            "checkpoint": "juggernautXL_ragnarokBy.safetensors",
            "lora": "pixel-art-xl @ 0.85",
            "sampler": "euler_ancestral", "scheduler": "normal",
            "steps": 30, "cfg": 7.5,
            "gen_size": f"{GEN_WIDTH}x{GEN_HEIGHT}",
            "pixelate": SPRITE_TARGET, "seed": seed,
            "subject_prompt": subject_prompt,
            "negative": negative_prompt,
        }, f, indent=2)

    # Save manifest
    with open(out_dir / "manifest.json", "w") as f:
        json.dump({
            "run_id": run_id, "stack": "A_v2", "character": char_name,
            "phase": "3", "seed": seed,
            "gen_size": f"{GEN_WIDTH}x{GEN_HEIGHT}",
            "timestamp": ts, "directions": generated_dirs,
        }, f, indent=2)

    print(f"\n  Generated {len(generated_dirs)}/8 directions")

    # ── Registry Integration ────────────────────────────
    print(f"\n--- Registering in foundry ---")

    # Register run
    foundry_cmd(
        "register-run", run_id,
        "--subject", subject_id,
        "--stack", "A_v2",
        "--seed", str(seed),
        "--width", str(GEN_WIDTH),
        "--height", str(GEN_HEIGHT),
        "--target", str(SPRITE_TARGET),
        "--recipe", str(out_dir / "recipe.json"),
    )

    # Register each attempt with artifacts
    for dir_name in generated_dirs:
        raw_path = out_dir / f"{dir_name}_raw.png"
        pixel_path = out_dir / f"{dir_name}.png"

        # Don't register a dangling artifact path — a partial/failed write would
        # otherwise put a path pointing at nothing into the DB (F-008).
        missing = [str(p) for p in (raw_path, pixel_path) if not p.exists()]
        if missing:
            print(f"  [{dir_name}] SKIP register-attempt -- missing artifact(s): {', '.join(missing)}")
            continue

        foundry_cmd(
            "register-attempt", run_id, dir_name,
            "--seed", str(seed),
            "--artifacts", "raw", str(raw_path),
            "--artifacts", "pixel", str(pixel_path),
        )

    # Contact sheets are run-level review artifacts, not direction attempts.
    # They are saved to disk but not registered as attempts (they would
    # pollute gate results and drift reports with false failures).

    # Run mechanical gates
    print(f"\n--- Running mechanical gates ---")
    foundry_cmd("check", run_id)

    print(f"\n{'=' * 60}")
    print(f"GENERATION COMPLETE: {char_name}")
    print(f"Run: {run_id}")
    print(f"Next: foundry review-show {run_id}")
    print(f"{'=' * 60}")

    return run_id


def main():
    parser = argparse.ArgumentParser(description="Foundry-integrated generation")
    parser.add_argument("--config", required=True, help="Path to character config JSON")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    generate_and_register(config)


if __name__ == "__main__":
    main()

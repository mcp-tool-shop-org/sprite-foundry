"""
Turnaround sprite generation pipeline.

Generates a single turnaround sheet (multiple views in one image) using
the CharTurn XL LoRA, then crops each view into individual sprites.

One txt2img call. One seed. All directions from one generation.

Usage:
    python -m pipeline.foundry_gen_turnaround --config pipeline/chars/claude_opus.json
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

from PIL import Image, ImageDraw, ImageFont
import numpy as np

COMFY_URL = "http://127.0.0.1:8188"
FOUNDRY_ROOT = Path(__file__).parent.parent
SPRITE_TARGET = 48

# Sheet layout: 3 views left-to-right (front, side, back)
SHEET_VIEWS = ["front", "right", "back"]

# Generation canvas — SDXL works best near 1M total pixels
# 2048x1024 = 2M pixels is the practical wide limit before quality degrades
GEN_WIDTH = 2048
GEN_HEIGHT = 1024

STYLE_SUFFIX = (
    "multiple_views, character turnaround, character sheet, "
    "front view, side view, back view, three views, "
    "full body, standing pose, "
    "pixel art sprite, game character, 2D RPG, clean pixel art, "
    "bright green background, #00FF00 green screen background, "
    "crisp pixel edges, isolated figures, "
    "evenly spaced, wide gaps between figures, figures far apart, "
    "each figure clearly separated"
)

NEGATIVE_PROMPT = (
    "blurry, smooth, photorealistic, 3D render, low quality, deformed, "
    "text, watermark, signature, frame, border, "
    "white background, gray background, gradient background, "
    "cropped, cut off, partial body, multiple characters, crowd, "
    "overlapping figures, figures touching, cramped, bunched together"
)


def make_turnaround_workflow(subject_prompt, negative_prompt, seed, filename_prefix, width=None, height=None):
    """Single txt2img with CharTurn LoRA -- produces a multi-view turnaround sheet."""
    w = width or GEN_WIDTH
    h = height or GEN_HEIGHT
    full_negative = f"{negative_prompt}, {NEGATIVE_PROMPT}"
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "juggernautXL_ragnarokBy.safetensors"},
        },
        # LoRA 1: CharTurn XL (the turnaround LoRA -- primary)
        # Strength 0.55: still gets multi-view layout, looser figure spacing
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0], "clip": ["1", 1],
                "lora_name": "charturn-xl.safetensors",
                "strength_model": 0.55, "strength_clip": 0.55,
            },
        },
        # LoRA 2: pixel-art-xl (style)
        "20": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["2", 0], "clip": ["2", 1],
                "lora_name": "pixel-art-xl.safetensors",
                "strength_model": 0.5, "strength_clip": 0.5,
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["20", 1],
                "text": f"{subject_prompt}, {STYLE_SUFFIX}",
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["20", 1], "text": full_negative},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": w, "height": h, "batch_size": 1},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["20", 0], "positive": ["3", 0], "negative": ["4", 0],
                "latent_image": ["5", 0], "seed": seed,
                "steps": 25, "cfg": 7.0,
                "sampler_name": "euler_ancestral", "scheduler": "normal",
                "denoise": 1.0,
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


def queue_prompt(workflow):
    data = json.dumps({"prompt": workflow}).encode()
    req = Request(f"{COMFY_URL}/prompt", data=data, headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def wait_for_completion(prompt_id, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urlopen(f"{COMFY_URL}/history/{prompt_id}") as resp:
                history = json.loads(resp.read())
            if prompt_id in history:
                return history[prompt_id]
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f"Prompt {prompt_id} timed out after {timeout}s")


def get_image(filename, subfolder=""):
    params = f"filename={filename}&subfolder={subfolder}&type=output"
    with urlopen(f"{COMFY_URL}/view?{params}") as resp:
        return resp.read()


def remove_bg(img, tolerance=35):
    """Remove background via chroma key or corner-color fallback."""
    arr = np.array(img.convert("RGBA")).copy()
    h, w = arr.shape[:2]

    corners = [arr[0, 0, :3], arr[0, w-1, :3], arr[h-1, 0, :3], arr[h-1, w-1, :3]]
    avg_corner = np.mean(corners, axis=0)
    is_green_screen = avg_corner[1] > 200 and avg_corner[0] < 100 and avg_corner[2] < 100

    if is_green_screen:
        rgb = arr[:, :, :3].astype(np.float32)
        green_dominant = (rgb[:, :, 1] > 150) & (rgb[:, :, 1] > rgb[:, :, 0] + 50) & (rgb[:, :, 1] > rgb[:, :, 2] + 50)
        arr[green_dominant, 3] = 0
        green_ratio = rgb[:, :, 1] / (rgb[:, :, 0] + rgb[:, :, 2] + 1)
        fringe = (green_ratio > 0.8) & (~green_dominant)
        arr[fringe, 3] = (arr[fringe, 3] * 0.5).astype(np.uint8)
    else:
        bg_color = avg_corner.astype(np.float32)
        rgb = arr[:, :, :3].astype(np.float32)
        diff = np.sqrt(np.sum((rgb - bg_color) ** 2, axis=2))
        arr[diff < tolerance, 3] = 0

    return Image.fromarray(arr)


def find_figures(rgba_img):
    """Find individual figures in a transparent image by detecting contiguous non-transparent columns.

    Returns list of (left, top, right, bottom) bounding boxes, one per figure.
    """
    arr = np.array(rgba_img)
    # Column has content if any pixel in it is non-transparent
    col_has_content = np.any(arr[:, :, 3] > 30, axis=0)

    # Find contiguous runs of content columns
    figures = []
    in_figure = False
    start = 0
    min_gap = 2  # minimum transparent gap between figures (pixels)

    for x in range(len(col_has_content)):
        if col_has_content[x] and not in_figure:
            start = x
            in_figure = True
        elif not col_has_content[x] and in_figure:
            # Check if this is a real gap or just a thin line
            gap_end = x
            while gap_end < len(col_has_content) and not col_has_content[gap_end]:
                gap_end += 1
            if gap_end - x >= min_gap or gap_end >= len(col_has_content):
                # Real gap -- end this figure
                figures.append(start)
                figures.append(x)
                in_figure = False
            # else: skip thin gap, stay in figure

    if in_figure:
        figures.append(start)
        figures.append(len(col_has_content))

    # Convert column pairs to bounding boxes with vertical bounds
    boxes = []
    for i in range(0, len(figures), 2):
        left = figures[i]
        right = figures[i + 1]
        # Find vertical extent for this column range
        region = arr[:, left:right, 3]
        row_has_content = np.any(region > 30, axis=1)
        rows = np.where(row_has_content)[0]
        if len(rows) > 0:
            top = rows[0]
            bottom = rows[-1] + 1
            boxes.append((left, top, right, bottom))

    return boxes


def crop_figures_from_sheet(sheet_img, target=SPRITE_TARGET):
    """Remove background, find each figure, crop and downscale to target size.

    Returns list of (bbox, pixel_img) tuples.
    """
    cleaned = remove_bg(sheet_img.convert("RGBA"))
    boxes = find_figures(cleaned)

    results = []
    for (left, top, right, bottom) in boxes:
        fig = cleaned.crop((left, top, right, bottom))
        w, h = fig.size

        # Pad to square (don't crop -- we want the whole figure)
        side = max(w, h)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        paste_x = (side - w) // 2
        paste_y = (side - h) // 2
        square.paste(fig, (paste_x, paste_y))

        # Downscale to target
        pixel = square.resize((target, target), Image.NEAREST)
        results.append(((left, top, right, bottom), pixel))

    return results


def make_contact_sheet(pixel_images, config, run_id, out_dir):
    """Generate pixel contact sheet."""
    PAD = 4
    PCELL = 128
    PCELL_W = PCELL + PAD * 2
    HEADER_H = 28
    BG = (24, 24, 32)
    TEXT = (200, 200, 210)
    ACCENT = (200, 160, 80)

    try:
        font_sm = ImageFont.truetype("consola.ttf", 11)
        font_lg = ImageFont.truetype("consola.ttf", 15)
    except (OSError, IOError):
        font_sm = font_lg = ImageFont.load_default()

    char_name = config["display_name"]
    views = list(pixel_images.keys())

    total_w = 80 + len(views) * PCELL_W + 20
    total_h = 10 + 24 + HEADER_H + PCELL + PAD * 2 + 40
    img = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(img)

    ox, oy = 10, 10
    draw.text((ox, oy), f"TURNAROUND -- {char_name} -- (48x48)", fill=ACCENT, font=font_lg)
    oy += 24
    for col, name in enumerate(views):
        draw.text((ox + 80 + col * PCELL_W + PAD, oy + 2), name, fill=TEXT, font=font_sm)
    oy += HEADER_H
    for col, name in enumerate(views):
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

    sheet_path = out_dir / "contact_sheet.png"
    img.save(str(sheet_path), "PNG")
    return sheet_path


def generate_turnaround(config: dict):
    """Generate a turnaround sheet and crop into individual sprites."""
    subject_id = config["subject_id"]
    char_name = config["display_name"]
    seed = config["seed"]
    subject_prompt = config["subject_prompt"]
    negative_prompt = config.get("negative_prompt", "")

    # Per-character canvas override (wide creatures need more room)
    gen_w = config.get("gen_width", GEN_WIDTH)
    gen_h = config.get("gen_height", GEN_HEIGHT)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{subject_id}_turn_{ts}"
    out_dir = FOUNDRY_ROOT / "bakeoff" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"TURNAROUND GENERATION: {char_name}")
    print(f"Run: {run_id}  Seed: {seed}")
    print(f"Output: {out_dir}")
    print(f"{'=' * 60}")

    # Generate the turnaround sheet
    print(f"\n  Generating turnaround sheet ({gen_w}x{gen_h})...", end=" ", flush=True)
    workflow = make_turnaround_workflow(subject_prompt, negative_prompt, seed, f"{subject_id}_turn", gen_w, gen_h)

    resp = queue_prompt(workflow)
    pid = resp["prompt_id"]
    print(f"queued ({pid[:8]}), waiting...", end=" ", flush=True)

    history = wait_for_completion(pid)
    img_info = history["outputs"]["8"]["images"][0]
    img_data = get_image(img_info["filename"], img_info.get("subfolder", ""))

    # Save the raw sheet
    sheet_path = out_dir / "turnaround_sheet.png"
    with open(sheet_path, "wb") as f:
        f.write(img_data)
    sheet_img = Image.open(sheet_path)
    print(f"OK ({sheet_img.size[0]}x{sheet_img.size[1]})")

    # Find and crop individual figures from the sheet
    print(f"\n  Finding figures in sheet...")
    figures = crop_figures_from_sheet(sheet_img)
    print(f"  Found {len(figures)} figures")

    # Map figures to view names (left-to-right order)
    # CharTurn typically produces: front, 3/4 views, side, back
    # We take the first, middle, and last as front/side/back
    pixel_images = {}
    if len(figures) >= 3:
        # Assign: first = front, middle = side (right), last = back
        assignments = []
        if len(figures) == 3:
            assignments = [("front", 0), ("right", 1), ("back", 2)]
        elif len(figures) == 4:
            assignments = [("front", 0), ("front_right", 1), ("right", 2), ("back", 3)]
        elif len(figures) == 5:
            assignments = [("front", 0), ("front_right", 1), ("right", 2), ("back_right", 3), ("back", 4)]
        elif len(figures) >= 6:
            assignments = [("front", 0), ("front_right", 1), ("right", 2), ("back_right", 3), ("back", 4), ("back_left", 5)]
            if len(figures) >= 7:
                assignments.append(("left", 6))

        for view_name, idx in assignments:
            if idx < len(figures):
                bbox, pixel_img = figures[idx]
                pixel_path = out_dir / f"{view_name}.png"
                pixel_img.save(str(pixel_path))
                pixel_images[view_name] = pixel_img

                arr = np.array(pixel_img.convert("RGBA"))
                occ = np.sum(arr[:, :, 3] > 0) / (arr.shape[0] * arr.shape[1])
                print(f"    {view_name}: {occ:.0%} occupancy (bbox {bbox[2]-bbox[0]}x{bbox[3]-bbox[1]}px)")
    else:
        print(f"  WARNING: Only found {len(figures)} figures, expected 3+")
        for i, (bbox, pixel_img) in enumerate(figures):
            name = f"view_{i}"
            pixel_img.save(str(out_dir / f"{name}.png"))
            pixel_images[name] = pixel_img

    # Mirror to fill missing directions
    if "right" in pixel_images and "left" not in pixel_images:
        pixel_images["left"] = pixel_images["right"].transpose(Image.FLIP_LEFT_RIGHT)
        pixel_images["left"].save(str(out_dir / "left.png"))
        print(f"    left: mirrored from right")
    if "front_right" in pixel_images and "front_left" not in pixel_images:
        pixel_images["front_left"] = pixel_images["front_right"].transpose(Image.FLIP_LEFT_RIGHT)
        pixel_images["front_left"].save(str(out_dir / "front_left.png"))
        print(f"    front_left: mirrored from front_right")
    if "back_right" in pixel_images and "back_left" not in pixel_images:
        pixel_images["back_left"] = pixel_images["back_right"].transpose(Image.FLIP_LEFT_RIGHT)
        pixel_images["back_left"].save(str(out_dir / "back_left.png"))
        print(f"    back_left: mirrored from back_right")

    # Contact sheet
    sheet = make_contact_sheet(pixel_images, config, run_id, out_dir)
    print(f"\n  Contact sheet: {sheet}")

    # Save recipe
    with open(out_dir / "recipe.json", "w") as f:
        json.dump({
            "pipeline": "turnaround",
            "character": char_name,
            "checkpoint": "juggernautXL_ragnarokBy.safetensors",
            "loras": ["charturn-xl @ 0.7", "pixel-art-xl @ 0.5"],
            "sampler": "euler_ancestral", "scheduler": "normal",
            "steps": 25, "cfg": 7.0,
            "gen_size": f"{GEN_WIDTH}x{GEN_HEIGHT}",
            "pixelate": SPRITE_TARGET, "seed": seed,
            "subject_prompt": subject_prompt,
            "negative": negative_prompt,
            "views": SHEET_VIEWS,
        }, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"TURNAROUND COMPLETE: {char_name}")
    print(f"Run: {run_id}")
    print(f"Views: {list(pixel_images.keys())}")
    print(f"{'=' * 60}")

    return run_id


def main():
    parser = argparse.ArgumentParser(description="Turnaround sprite generation")
    parser.add_argument("--config", required=True, help="Path to character config JSON")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    generate_turnaround(config)


if __name__ == "__main__":
    main()

"""
Zero123-based multi-angle sprite generation.

Phase 1 (Option B): Single seed -> 8 directions via StableZero123.
Phase 2 (Option B+): Multiple seeds (front/side/back) -> pick closest seed per angle.

Uses ComfyUI's built-in StableZero123_Conditioning node.

Usage:
    # Single seed (front view)
    python -m pipeline.foundry_gen_zero123 --seed-image path/to/front.png

    # Multi-seed (front + side + back)
    python -m pipeline.foundry_gen_zero123 --front path/to/front.png --side path/to/side.png --back path/to/back.png
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

from PIL import Image, ImageDraw, ImageFont
import numpy as np

COMFY_URL = "http://127.0.0.1:8188"
FOUNDRY_ROOT = Path(__file__).parent.parent
SPRITE_TARGET = 48

# 8 target directions with their azimuth angles (degrees)
# 0 = front, 90 = right, 180 = back, 270 = left
DIRECTIONS = [
    ("front",       0),
    ("front_right", 45),
    ("right",       90),
    ("back_right",  135),
    ("back",        180),
    ("back_left",   225),
    ("left",        270),
    ("front_left",  315),
]

ELEVATION = 5.0  # slight top-down angle for game sprite perspective

ZERO123_CHECKPOINT = "stable_zero123.ckpt"


# -- ComfyUI API -------------------------------------------------

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


def upload_image(image_path):
    """Upload an image to ComfyUI input folder."""
    filename = Path(image_path).name
    with open(image_path, "rb") as f:
        file_data = f.read()

    boundary = "----Zero123Boundary"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode()
    body += b"Content-Type: image/png\r\n\r\n"
    body += file_data
    body += f"\r\n--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="subfolder"\r\n\r\n'
    body += f"\r\n--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="type"\r\n\r\ninput'
    body += f"\r\n--{boundary}--\r\n".encode()

    req = Request(
        f"{COMFY_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(req) as resp:
        result = json.loads(resp.read())
    return result.get("name", filename)


# -- Workflow builders --------------------------------------------

def make_zero123_workflow(input_image_name, azimuth, elevation, filename_prefix):
    """StableZero123 workflow: single image -> rotated view."""
    return {
        # Load the Zero123 checkpoint (ImageOnly gives MODEL, CLIP_VISION, VAE)
        "1": {
            "class_type": "ImageOnlyCheckpointLoader",
            "inputs": {"ckpt_name": ZERO123_CHECKPOINT},
        },
        # Load the seed image
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": input_image_name},
        },
        # StableZero123 conditioning
        "3": {
            "class_type": "StableZero123_Conditioning",
            "inputs": {
                "clip_vision": ["1", 1],
                "init_image": ["2", 0],
                "vae": ["1", 2],
                "width": 256,
                "height": 256,
                "batch_size": 1,
                "elevation": elevation,
                "azimuth": azimuth,
            },
        },
        # KSampler: model from checkpoint, pos/neg/latent from Zero123 conditioning
        "4": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["3", 1],
                "latent_image": ["3", 2],
                "seed": 0,
                "steps": 20,
                "cfg": 5.0,
                "sampler_name": "euler",
                "scheduler": "sgm_uniform",
                "denoise": 1.0,
            },
        },
        # Decode: VAE from checkpoint (output 2)
        "5": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["4", 0], "vae": ["1", 2]},
        },
        # Save
        "6": {
            "class_type": "SaveImage",
            "inputs": {"images": ["5", 0], "filename_prefix": filename_prefix},
        },
    }


# -- Image processing ---------------------------------------------

def remove_bg(img, tolerance=35):
    """Remove background via corner-color matching."""
    arr = np.array(img.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    corners = np.array([arr[0,0,:3], arr[0,w-1,:3], arr[h-1,0,:3], arr[h-1,w-1,:3]], dtype=np.float32)
    bg = np.mean(corners, axis=0)
    rgb = arr[:,:,:3].astype(np.float32)
    diff = np.sqrt(np.sum((rgb - bg) ** 2, axis=2))
    arr[diff < tolerance, 3] = 0
    return Image.fromarray(arr)


def process_to_pixel(raw_img, target=SPRITE_TARGET):
    """Remove BG, pad to square, downscale."""
    cleaned = remove_bg(raw_img.convert("RGBA"))
    # Find bounding box of visible pixels
    arr = np.array(cleaned)
    visible = arr[:,:,3] > 0
    if not np.any(visible):
        return cleaned.resize((target, target), Image.NEAREST)
    rows = np.any(visible, axis=1)
    cols = np.any(visible, axis=0)
    top, bottom = np.where(rows)[0][[0, -1]]
    left, right = np.where(cols)[0][[0, -1]]
    cropped = cleaned.crop((left, top, right + 1, bottom + 1))
    # Pad to square
    w, h = cropped.size
    side = max(w, h)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(cropped, ((side - w) // 2, (side - h) // 2))
    return square.resize((target, target), Image.NEAREST)


# -- Contact sheet ------------------------------------------------

def make_contact_sheet(pixel_images, label, out_dir):
    PAD = 4
    PCELL = 128
    PCELL_W = PCELL + PAD * 2
    BG = (24, 24, 32)
    TEXT = (200, 200, 210)
    ACCENT = (120, 200, 160)

    try:
        font_sm = ImageFont.truetype("consola.ttf", 11)
        font_lg = ImageFont.truetype("consola.ttf", 15)
    except (OSError, IOError):
        font_sm = font_lg = ImageFont.load_default()

    views = [d[0] for d in DIRECTIONS]
    total_w = 80 + len(views) * PCELL_W + 20
    total_h = 10 + 24 + 28 + PCELL + PAD * 2 + 20
    img = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(img)

    ox, oy = 10, 10
    draw.text((ox, oy), f"ZERO123 -- {label} -- (48x48)", fill=ACCENT, font=font_lg)
    oy += 24
    for col, name in enumerate(views):
        draw.text((ox + 80 + col * PCELL_W + PAD, oy + 2), name.replace("_", "\n"), fill=TEXT, font=font_sm)
    oy += 28
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
        else:
            draw.rectangle([cx, cy, cx + PCELL, cy + PCELL], fill=(60, 30, 30))

    sheet_path = out_dir / "contact_sheet.png"
    img.save(str(sheet_path), "PNG")
    return sheet_path


# -- Seed selection (Option B multi-seed) -------------------------

def angle_distance(a, b):
    """Shortest angular distance between two angles in degrees."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def select_seed(target_azimuth, seeds):
    """Pick the seed image closest to the target azimuth.

    seeds: list of (azimuth, uploaded_image_name, label)
    Returns: (uploaded_image_name, label, distance)
    """
    best = None
    best_dist = 999
    for seed_az, seed_name, seed_label in seeds:
        dist = angle_distance(target_azimuth, seed_az)
        if dist < best_dist:
            best_dist = dist
            best = (seed_name, seed_label, best_dist)
    return best


# -- Main pipeline ------------------------------------------------

def generate_zero123(args):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"zero123_{ts}"
    out_dir = FOUNDRY_ROOT / "bakeoff" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build seed list
    seeds = []
    if args.front:
        name = upload_image(args.front)
        seeds.append((0, name, "front"))
        print(f"  Uploaded front seed: {args.front}")
    if args.side:
        name = upload_image(args.side)
        seeds.append((90, name, "side"))
        print(f"  Uploaded side seed: {args.side}")
    if args.back:
        name = upload_image(args.back)
        seeds.append((180, name, "back"))
        print(f"  Uploaded back seed: {args.back}")
    if args.seed_image and not seeds:
        name = upload_image(args.seed_image)
        seeds.append((0, name, "front"))
        print(f"  Uploaded single seed: {args.seed_image}")

    if not seeds:
        print("ERROR: No seed images provided")
        return

    multi = len(seeds) > 1
    mode = f"multi-seed ({len(seeds)} views)" if multi else "single-seed"

    print(f"\n{'=' * 60}")
    print(f"ZERO123 GENERATION: {mode}")
    print(f"Run: {run_id}")
    print(f"Seeds: {', '.join(s[2] for s in seeds)}")
    print(f"Output: {out_dir}")
    print(f"{'=' * 60}")

    pixel_images = {}

    for dir_name, target_az in DIRECTIONS:
        # Select best seed for this angle
        seed_name, seed_label, dist = select_seed(target_az, seeds)

        # Compute relative azimuth from seed's perspective
        seed_az = next(s[0] for s in seeds if s[1] == seed_name)
        relative_az = (target_az - seed_az) % 360
        if relative_az > 180:
            relative_az -= 360  # range: -180 to 180

        print(f"  [{dir_name}] seed={seed_label}, relative az={relative_az:.0f}...",
              end=" ", flush=True)

        workflow = make_zero123_workflow(
            seed_name, relative_az, ELEVATION,
            f"z123_{dir_name}",
        )

        try:
            resp = queue_prompt(workflow)
            pid = resp["prompt_id"]
            history = wait_for_completion(pid)
            img_info = history["outputs"]["6"]["images"][0]
            img_data = get_image(img_info["filename"], img_info.get("subfolder", ""))

            raw_path = out_dir / f"{dir_name}_raw.png"
            with open(raw_path, "wb") as f:
                f.write(img_data)

            raw_img = Image.open(raw_path)
            pixel_img = process_to_pixel(raw_img)
            pixel_img.save(str(out_dir / f"{dir_name}.png"))
            pixel_images[dir_name] = pixel_img

            arr = np.array(pixel_img.convert("RGBA"))
            occ = np.sum(arr[:,:,3] > 0) / (arr.shape[0] * arr.shape[1])
            print(f"OK (occ {occ:.0%})")
        except Exception as e:
            print(f"FAIL: {e}")

    # Contact sheet
    sheet = make_contact_sheet(pixel_images, mode, out_dir)
    print(f"\n  Contact sheet: {sheet}")

    # Recipe
    with open(out_dir / "recipe.json", "w") as f:
        json.dump({
            "pipeline": "zero123_option_b",
            "mode": mode,
            "seeds": [{"azimuth": s[0], "label": s[2]} for s in seeds],
            "checkpoint": ZERO123_CHECKPOINT,
            "elevation": ELEVATION,
            "directions": [d[0] for d in DIRECTIONS],
            "target": SPRITE_TARGET,
        }, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"ZERO123 COMPLETE: {len(pixel_images)}/8 directions")
    print(f"Run: {run_id}")
    print(f"{'=' * 60}")

    return run_id


def main():
    parser = argparse.ArgumentParser(description="Zero123 multi-angle sprite generation")
    parser.add_argument("--seed-image", help="Single seed image (front view)")
    parser.add_argument("--front", help="Front view seed image")
    parser.add_argument("--side", help="Side view seed image")
    parser.add_argument("--back", help="Back view seed image")
    args = parser.parse_args()

    generate_zero123(args)


if __name__ == "__main__":
    main()

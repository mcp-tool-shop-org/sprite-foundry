"""
Iterative sprite generation pipeline.

Instead of 8 independent txt2img calls, this pipeline:
  1. txt2img  — generate a strong front-view hero sprite
  2. img2img  — refine the front view (denoise 0.3-0.5)
  3. img2img  — derive other 7 directions from the refined front (denoise ~0.5)

The front view is the structural anchor. All other directions inherit
identity, palette, and proportions from it.

Usage:
    python -m pipeline.foundry_gen_iterative --config pipeline/chars/claude_opus.json
"""

import argparse
import base64
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen, Request

from PIL import Image, ImageDraw, ImageFont
import numpy as np

COMFY_URL = "http://127.0.0.1:8188"
FOUNDRY_ROOT = Path(__file__).parent.parent
SPRITE_TARGET = 48

# Directions: front is generated first via txt2img, rest via img2img from front
FRONT = ("front", "facing the viewer, front view, looking at camera")
OTHER_DIRECTIONS = [
    ("front_left", "facing front-left, 3/4 view from the left, looking slightly left"),
    ("left", "facing left, left side profile view"),
    ("back_left", "facing back-left, 3/4 rear view from the left"),
    ("back", "facing away from viewer, rear view, back of character"),
    ("back_right", "facing back-right, 3/4 rear view from the right"),
    ("right", "facing right, right side profile view"),
    ("front_right", "facing front-right, 3/4 view from the right, looking slightly right"),
]
ALL_DIRECTIONS = [FRONT] + OTHER_DIRECTIONS

STYLE_SUFFIX = (
    "pixel art sprite, game character sprite, 2D RPG, clean pixel art, "
    "orthographic view, clear silhouette, strong negative-space composition, "
    "bright green background, #00FF00 green screen background, "
    "centered composition, full body shot, character centered in frame, "
    "crisp pixel edges, single character portrait, isolated figure"
)

NEGATIVE_BG = "white background, gray background, grey background, beige background, gradient background"

GEN_WIDTH = 576
GEN_HEIGHT = 768


# -- ComfyUI Workflow Builders ----------------------------─

def _base_nodes(subject_prompt, direction_prompt, negative_prompt, seed):
    """Shared nodes: checkpoint + dual LoRA + CLIP encode."""
    full_negative = f"{negative_prompt}, {NEGATIVE_BG}" if negative_prompt else NEGATIVE_BG
    return {
        # Checkpoint
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "juggernautXL_ragnarokBy.safetensors"},
        },
        # LoRA 1: pixel-art-xl
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0], "clip": ["1", 1],
                "lora_name": "pixel-art-xl.safetensors",
                "strength_model": 0.80, "strength_clip": 0.80,
            },
        },
        # LoRA 2: Sprite Shaper
        "20": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["2", 0], "clip": ["2", 1],
                "lora_name": "pixelArtDiffusionXL_spriteShaper.safetensors",
                "strength_model": 0.45, "strength_clip": 0.45,
            },
        },
        # Positive prompt
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["20", 1],
                "text": f"{subject_prompt}, {direction_prompt}, {STYLE_SUFFIX}",
            },
        },
        # Negative prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["20", 1], "text": full_negative},
        },
    }


def make_txt2img_workflow(subject_prompt, negative_prompt, direction_prompt,
                          seed, filename_prefix):
    """Phase 1: txt2img hero — full denoise, generate from scratch."""
    nodes = _base_nodes(subject_prompt, direction_prompt, negative_prompt, seed)
    nodes.update({
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": GEN_WIDTH, "height": GEN_HEIGHT, "batch_size": 1},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["20", 0], "positive": ["3", 0], "negative": ["4", 0],
                "latent_image": ["5", 0], "seed": seed,
                "steps": 30, "cfg": 7.5,
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
    })
    return nodes


def make_img2img_workflow(subject_prompt, negative_prompt, direction_prompt,
                          seed, filename_prefix, denoise, steps,
                          source_image_path):
    """Phase 2: img2img refine (low denoise, preserves structure)."""
    nodes = _base_nodes(subject_prompt, direction_prompt, negative_prompt, seed)
    nodes.update({
        "10": {
            "class_type": "LoadImage",
            "inputs": {"image": source_image_path},
        },
        "11": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["10", 0], "vae": ["1", 2]},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["20", 0], "positive": ["3", 0], "negative": ["4", 0],
                "latent_image": ["11", 0], "seed": seed,
                "steps": steps, "cfg": 7.5,
                "sampler_name": "euler_ancestral", "scheduler": "normal",
                "denoise": denoise,
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
    })
    return nodes


def make_ipadapter_rotate_workflow(subject_prompt, negative_prompt, direction_prompt,
                                   seed, filename_prefix, reference_image_path):
    """Phase 3: txt2img + IPAdapter for direction rotation.

    Uses EMPTY latent (full denoise) so the model freely generates the new pose.
    IPAdapter injects the front hero as identity reference to keep colors,
    style, and proportions consistent. Prompt drives the pose. Image drives identity.
    """
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
                "strength_model": 0.80, "strength_clip": 0.80,
            },
        },
        "20": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["2", 0], "clip": ["2", 1],
                "lora_name": "pixelArtDiffusionXL_spriteShaper.safetensors",
                "strength_model": 0.45, "strength_clip": 0.45,
            },
        },
        # Load front hero as IPAdapter reference
        "30": {
            "class_type": "LoadImage",
            "inputs": {"image": reference_image_path},
        },
        # IPAdapter unified loader (handles model + clip vision automatically)
        "31": {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {
                "model": ["20", 0],
                "preset": "PLUS (high strength)",
            },
        },
        # IPAdapter Advanced: lock identity from front hero
        "32": {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": ["31", 0],
                "ipadapter": ["31", 1],
                "image": ["30", 0],
                "weight": 0.4,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 0.6,
                "embeds_scaling": "V only",
            },
        },
        # Positive prompt (direction-specific)
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["20", 1],
                "text": f"{subject_prompt}, {direction_prompt}, {STYLE_SUFFIX}",
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["20", 1], "text": full_negative},
        },
        # Empty latent -- txt2img, model generates freely
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": GEN_WIDTH, "height": GEN_HEIGHT, "batch_size": 1},
        },
        # KSampler -- full denoise, IPAdapter-enhanced model
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["32", 0],
                "positive": ["3", 0], "negative": ["4", 0],
                "latent_image": ["5", 0], "seed": seed,
                "steps": 30, "cfg": 7.5,
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


# -- ComfyUI API ------------------------------------------─

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


def upload_image(image_path, subfolder="", image_type="input"):
    """Upload an image to ComfyUI's input folder for img2img use."""
    import mimetypes
    from urllib.request import urlopen, Request

    filename = Path(image_path).name
    mime = mimetypes.guess_type(image_path)[0] or "image/png"

    with open(image_path, "rb") as f:
        file_data = f.read()

    # Multipart form data
    boundary = "----ComfyUIBoundary"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode()
    body += f"Content-Type: {mime}\r\n\r\n".encode()
    body += file_data
    body += f"\r\n--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="subfolder"\r\n\r\n{subfolder}'.encode()
    body += f"\r\n--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="type"\r\n\r\n{image_type}'.encode()
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


# -- Image Processing --------------------------------------

def remove_bg(img, tolerance=35):
    """Remove background via chroma key (green screen) or corner-color fallback."""
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


def check_occupancy(img, occ_min=0.18, occ_max=0.55):
    """Quick occupancy check on a pixel sprite. Returns (pass, occupancy_pct)."""
    arr = np.array(img.convert("RGBA"))
    visible = np.sum(arr[:, :, 3] > 0)
    total = arr.shape[0] * arr.shape[1]
    occ = visible / total
    return (occ_min <= occ <= occ_max), occ


def process_raw_to_pixel(raw_img, target=SPRITE_TARGET):
    """Remove BG, crop to square, downscale to target size."""
    cleaned = remove_bg(raw_img.convert("RGBA"))
    w, h = cleaned.size
    if h > w:
        top = (h - w) // 4
        cleaned = cleaned.crop((0, top, w, top + w))
    return cleaned.resize((target, target), Image.NEAREST)


# -- Contact Sheet ----------------------------------------─

def make_contact_sheet(pixel_images, config, run_id, out_dir):
    """Generate a pixel contact sheet for all directions."""
    PAD = 4
    PCELL = 128
    PCELL_W = PCELL + PAD * 2
    PCELL_H = PCELL + PAD * 2
    HEADER_H = 28
    BG = (24, 24, 32)
    TEXT = (200, 200, 210)
    ACCENT = (200, 160, 80)

    try:
        font_sm = ImageFont.truetype("consola.ttf", 11)
        font_lg = ImageFont.truetype("consola.ttf", 15)
    except (OSError, IOError):
        font_sm = font_lg = ImageFont.load_default()

    dir_names = [d[0] for d in ALL_DIRECTIONS]
    char_name = config["display_name"]

    total_w = 80 + 8 * PCELL_W + 20
    total_h = 10 + 24 + HEADER_H + PCELL_H + 10 + 40
    img = Image.new("RGB", (total_w, total_h), BG)
    draw = ImageDraw.Draw(img)

    ox, oy = 10, 10
    draw.text((ox, oy), f"ITERATIVE -- {char_name} -- (48x48)", fill=ACCENT, font=font_lg)
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
        else:
            draw.rectangle([cx, cy, cx + PCELL, cy + PCELL], fill=(60, 30, 30))
            draw.text((cx + 10, cy + PCELL // 2 - 6), "MISSING", fill=(180, 60, 60), font=font_sm)

    sheet_path = out_dir / "contact_sheet.png"
    img.save(str(sheet_path), "PNG")
    return sheet_path


# -- Foundry CLI ------------------------------------------─

def foundry_cmd(*args):
    cmd = [sys.executable, "-m", "foundry.cli"] + list(args)
    result = subprocess.run(cmd, cwd=str(FOUNDRY_ROOT), capture_output=True, text=True)
    if result.stdout:
        print(f"    {result.stdout.strip()}")
    if result.returncode != 0 and result.stderr:
        print(f"    ERROR: {result.stderr.strip()}")
    return result.returncode


# -- Main Pipeline ----------------------------------------─

def submit_and_wait(workflow, label=""):
    """Submit a workflow to ComfyUI and wait for the result image."""
    resp = queue_prompt(workflow)
    pid = resp["prompt_id"]
    print(f"queued ({pid[:8]}), waiting...", end=" ", flush=True)
    history = wait_for_completion(pid)
    img_info = history["outputs"]["8"]["images"][0]
    img_data = get_image(img_info["filename"], img_info.get("subfolder", ""))
    return img_data


def generate_iterative(config: dict):
    """Main iterative pipeline: hero → refine -> rotate."""
    subject_id = config["subject_id"]
    char_name = config["display_name"]
    seed = config["seed"]
    subject_prompt = config["subject_prompt"]
    negative_prompt = config["negative_prompt"]

    # Iterative config with defaults
    iter_cfg = config.get("iterative", {})
    refine_denoise = iter_cfg.get("refine_denoise", 0.35)
    refine_steps = iter_cfg.get("refine_steps", 20)
    rotate_denoise = iter_cfg.get("rotate_denoise", 0.55)
    rotate_steps = iter_cfg.get("rotate_steps", 25)
    max_regen = iter_cfg.get("max_regen_attempts", 3)
    occ_min = iter_cfg.get("occupancy_min", 0.18)
    occ_max = iter_cfg.get("occupancy_max", 0.55)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{subject_id}_iter_{ts}"
    out_dir = FOUNDRY_ROOT / "bakeoff" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"ITERATIVE GENERATION: {char_name}")
    print(f"Run: {run_id}  Seed: {seed}")
    print(f"Pipeline: txt2img -> refine (d={refine_denoise}) -> IPAdapter rotate")
    print(f"Output: {out_dir}")
    print(f"{'=' * 60}")

    raw_images = {}
    pixel_images = {}
    generated_dirs = []

    # -- PHASE 1: txt2img hero (front view) ----------------
    print(f"\n-- PHASE 1: Hero generation (front view) --")
    hero_raw = None
    hero_pixel = None

    for attempt in range(max_regen):
        print(f"  [front] attempt {attempt + 1}/{max_regen}...", end=" ", flush=True)

        workflow = make_txt2img_workflow(
            subject_prompt, negative_prompt, FRONT[1],
            seed + attempt, f"{subject_id}_hero",
        )
        try:
            img_data = submit_and_wait(workflow, "hero")
            raw_path = out_dir / "front_raw.png"
            with open(raw_path, "wb") as f:
                f.write(img_data)
            hero_raw = Image.open(raw_path)
            hero_pixel = process_raw_to_pixel(hero_raw)

            occ_pass, occ_val = check_occupancy(hero_pixel, occ_min, occ_max)
            if occ_pass:
                print(f"OK (occupancy {occ_val:.0%})")
                break
            else:
                print(f"occupancy {occ_val:.0%} out of range [{occ_min:.0%}-{occ_max:.0%}], retrying...")
                hero_raw = None
                hero_pixel = None
        except Exception as e:
            print(f"FAIL: {e}")

    if hero_raw is None:
        print(f"\n  ABORT: Could not generate acceptable front view after {max_regen} attempts")
        return None

    # Save hero
    hero_pixel.save(str(out_dir / "front.png"))
    raw_images["front"] = hero_raw
    pixel_images["front"] = hero_pixel
    generated_dirs.append("front")

    # -- PHASE 2: img2img refine (front view) --------------
    print(f"\n-- PHASE 2: Refine front view (denoise {refine_denoise}) --")
    print(f"  [front refine] submitting...", end=" ", flush=True)

    # Upload the raw hero to ComfyUI input
    hero_raw_path = out_dir / "front_raw.png"
    uploaded_name = upload_image(str(hero_raw_path))

    workflow = make_img2img_workflow(
        subject_prompt, negative_prompt, FRONT[1],
        seed, f"{subject_id}_refine",
        denoise=refine_denoise, steps=refine_steps,
        source_image_path=uploaded_name,
    )
    try:
        img_data = submit_and_wait(workflow, "refine")
        refined_raw_path = out_dir / "front_refined_raw.png"
        with open(refined_raw_path, "wb") as f:
            f.write(img_data)
        refined_raw = Image.open(refined_raw_path)
        refined_pixel = process_raw_to_pixel(refined_raw)

        occ_pass, occ_val = check_occupancy(refined_pixel, occ_min, occ_max)
        if occ_pass:
            print(f"OK (occupancy {occ_val:.0%})")
            # Replace front with refined version
            refined_pixel.save(str(out_dir / "front.png"))
            raw_images["front"] = refined_raw
            pixel_images["front"] = refined_pixel
            hero_raw = refined_raw  # use refined as anchor for rotations
            hero_raw_path = refined_raw_path
        else:
            print(f"refined occupancy {occ_val:.0%} out of range, keeping original")
    except Exception as e:
        print(f"FAIL: {e} — keeping original front")

    # -- PHASE 3: IPAdapter rotation (7 other directions) ---
    print(f"\n-- PHASE 3: IPAdapter rotation (identity-locked, new poses) --")

    # Upload the anchor image (refined front) as IPAdapter reference
    anchor_name = upload_image(str(hero_raw_path))

    for dir_name, dir_prompt in OTHER_DIRECTIONS:
        success = False
        for attempt in range(max_regen):
            print(f"  [{dir_name}] attempt {attempt + 1}/{max_regen}...", end=" ", flush=True)

            workflow = make_ipadapter_rotate_workflow(
                subject_prompt, negative_prompt, dir_prompt,
                seed + attempt, f"{subject_id}_{dir_name}",
                reference_image_path=anchor_name,
            )
            try:
                img_data = submit_and_wait(workflow, dir_name)
                raw_path = out_dir / f"{dir_name}_raw.png"
                with open(raw_path, "wb") as f:
                    f.write(img_data)
                raw_img = Image.open(raw_path)
                pixel_img = process_raw_to_pixel(raw_img)

                occ_pass, occ_val = check_occupancy(pixel_img, occ_min, occ_max)
                if occ_pass:
                    pixel_img.save(str(out_dir / f"{dir_name}.png"))
                    raw_images[dir_name] = raw_img
                    pixel_images[dir_name] = pixel_img
                    generated_dirs.append(dir_name)
                    print(f"OK (occupancy {occ_val:.0%})")
                    success = True
                    break
                else:
                    print(f"occupancy {occ_val:.0%} out of range, retrying...")
            except Exception as e:
                print(f"FAIL: {e}")

        if not success:
            print(f"  [{dir_name}] FAILED after {max_regen} attempts")

    # -- Contact sheet ------------------------------------─
    sheet_path = make_contact_sheet(pixel_images, config, run_id, out_dir)
    print(f"\n  Contact sheet: {sheet_path}")

    # -- Save recipe --------------------------------------─
    with open(out_dir / "recipe.json", "w") as f:
        json.dump({
            "pipeline": "iterative",
            "character": char_name,
            "checkpoint": "juggernautXL_ragnarokBy.safetensors",
            "loras": [
                "pixel-art-xl @ 0.80",
                "pixelArtDiffusionXL_spriteShaper @ 0.45",
            ],
            "sampler": "euler_ancestral", "scheduler": "normal",
            "txt2img": {"steps": 30, "cfg": 7.5, "denoise": 1.0},
            "refine": {"steps": refine_steps, "cfg": 7.5, "denoise": refine_denoise},
            "rotate": {"steps": rotate_steps, "cfg": 7.5, "denoise": rotate_denoise},
            "gen_size": f"{GEN_WIDTH}x{GEN_HEIGHT}",
            "pixelate": SPRITE_TARGET, "seed": seed,
            "occupancy_range": [occ_min, occ_max],
            "subject_prompt": subject_prompt,
            "negative": negative_prompt,
        }, f, indent=2)

    # -- Save manifest ------------------------------------─
    with open(out_dir / "manifest.json", "w") as f:
        json.dump({
            "run_id": run_id, "pipeline": "iterative",
            "character": char_name, "seed": seed,
            "gen_size": f"{GEN_WIDTH}x{GEN_HEIGHT}",
            "timestamp": ts, "directions": generated_dirs,
            "phases": {
                "hero": "front",
                "refine_denoise": refine_denoise,
                "rotate_denoise": rotate_denoise,
            },
        }, f, indent=2)

    # -- Registry Integration ------------------------------
    print(f"\n--- Registering in foundry ---")
    foundry_cmd(
        "register-run", run_id,
        "--subject", subject_id,
        "--stack", "iterative_v1",
        "--seed", str(seed),
        "--width", str(GEN_WIDTH),
        "--height", str(GEN_HEIGHT),
        "--target", str(SPRITE_TARGET),
        "--recipe", str(out_dir / "recipe.json"),
    )

    for dir_name in generated_dirs:
        raw_path = str(out_dir / f"{dir_name}_raw.png")
        pixel_path = str(out_dir / f"{dir_name}.png")
        # Use refined raw for front if it exists
        if dir_name == "front" and (out_dir / "front_refined_raw.png").exists():
            raw_path = str(out_dir / "front_refined_raw.png")
        foundry_cmd(
            "register-attempt", run_id, dir_name,
            "--seed", str(seed),
            "--artifacts", "raw", raw_path,
            "--artifacts", "pixel", pixel_path,
        )

    print(f"\n--- Running mechanical gates ---")
    foundry_cmd("check", run_id)

    print(f"\n{'=' * 60}")
    print(f"ITERATIVE GENERATION COMPLETE: {char_name}")
    print(f"Run: {run_id}")
    print(f"Directions: {len(generated_dirs)}/8")
    print(f"Next: foundry review-show {run_id}")
    print(f"{'=' * 60}")

    return run_id


def main():
    parser = argparse.ArgumentParser(description="Iterative sprite generation pipeline")
    parser.add_argument("--config", required=True, help="Path to character config JSON")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    generate_iterative(config)


if __name__ == "__main__":
    main()

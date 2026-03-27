"""
Phase 5A — Morphology-controlled generation runner.

Like foundry_gen.py but adds ControlNet Depth guidance from
pre-generated depth reference silhouettes to enforce non-humanoid body plans.

Usage:
    python -m pipeline.foundry_gen_morph --config pipeline/chars/drift_maw_v2.json \
        --depth-refs pipeline/morph_refs/drift_maw_depth
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
MORPH_REFS_DIR = FOUNDRY_ROOT / "pipeline" / "morph_refs"

# Body class presets — auto-select depth refs + ControlNet params
BODY_CLASS_PRESETS = {
    "humanoid": {
        "depth_refs": None,  # humanoid lane uses foundry_gen.py, not morph
        "depth_strength": 0.60,
        "depth_end_pct": 0.85,
        "canny": False,
    },
    "arthropod": {
        "depth_refs": "skitter_drone_depth",
        "depth_strength": 0.55,
        "depth_end_pct": 0.80,
        "canny": False,
    },
    "quadruped": {
        "depth_refs": "cargo_beast_depth",
        "depth_strength": 0.65,
        "depth_end_pct": 0.90,
        "canny": False,
    },
    "crouching_predator": {
        "depth_refs": "drift_lurker_depth",
        "depth_strength": 0.55,
        "depth_end_pct": 0.80,
        "canny": False,
    },
    "winged": {
        "depth_refs": "void_raptor_depth",
        "edge_refs": "void_raptor_edge",
        "depth_strength": 0.55,
        "depth_end_pct": 0.90,
        "canny": True,
        "canny_strength": 0.45,
        "canny_end_pct": 0.85,
    },
    # Monster lane body classes
    "amorphous": {
        "depth_refs": "amorphous_depth",
        "depth_strength": 0.35,
        "depth_end_pct": 0.65,
        "canny": False,
    },
    "wide_squat": {
        "depth_refs": "wide_squat_depth",
        "depth_strength": 0.40,
        "depth_end_pct": 0.70,
        "canny": False,
    },
    "tall_thin": {
        "depth_refs": "tall_thin_depth",
        "depth_strength": 0.40,
        "depth_end_pct": 0.70,
        "canny": False,
    },
}

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
    "solid color background, centered composition, full body shot, "
    "character centered in frame, HD-2D inspired, crisp pixel edges, "
    "single character portrait, character design, isolated figure"
)

GEN_WIDTH = 576
GEN_HEIGHT = 768

CONTROLNET_MODEL = "controlnet-depth-sdxl-1.0.safetensors"
CONTROLNET_STRENGTH = 0.55  # enough to constrain shape, not enough to kill detail


def make_workflow_morph(subject_prompt: str, negative_prompt: str, direction_prompt: str,
                        seed: int, filename_prefix: str, depth_image_name: str,
                        cn_strength: float = CONTROLNET_STRENGTH,
                        cn_end_percent: float = 0.8,
                        edge_image_name: str = None,
                        edge_strength: float = 0.45,
                        edge_end_percent: float = 0.85) -> dict:
    """Stack A v2 + ControlNet Depth (+ optional Canny edge): morphology-constrained generation."""
    workflow = {
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
            "inputs": {"clip": ["2", 1], "text": negative_prompt},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": GEN_WIDTH, "height": GEN_HEIGHT, "batch_size": 1},
        },
        # ControlNet Depth branch
        "10": {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": CONTROLNET_MODEL},
        },
        "11": {
            "class_type": "LoadImage",
            "inputs": {"image": depth_image_name},
        },
        "12": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "control_net": ["10", 0],
                "image": ["11", 0],
                "strength": cn_strength,
                "start_percent": 0.0,
                "end_percent": cn_end_percent,
            },
        },
    }

    # Determine what feeds into the KSampler
    final_positive = ["12", 0]
    final_negative = ["12", 1]

    # Optional Canny edge ControlNet — stacks on top of depth conditioning
    if edge_image_name:
        workflow["20"] = {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": "controlnet-canny-sdxl-1.0.safetensors"},
        }
        workflow["21"] = {
            "class_type": "LoadImage",
            "inputs": {"image": edge_image_name},
        }
        workflow["22"] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["12", 0],   # chain from depth output
                "negative": ["12", 1],
                "control_net": ["20", 0],
                "image": ["21", 0],
                "strength": edge_strength,
                "start_percent": 0.0,
                "end_percent": edge_end_percent,
            },
        }
        final_positive = ["22", 0]
        final_negative = ["22", 1]

    workflow["6"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["2", 0],
            "positive": final_positive,
            "negative": final_negative,
            "latent_image": ["5", 0], "seed": seed,
            "steps": 30, "cfg": 7.5,
            "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0,
        },
    }
    workflow["7"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
    }
    workflow["8"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["7", 0], "filename_prefix": filename_prefix},
    }

    return workflow


def queue_prompt(workflow):
    data = json.dumps({"prompt": workflow}).encode()
    req = Request(f"{COMFY_URL}/prompt", data=data, headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def wait_for_completion(prompt_id, timeout=180):
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


def upload_image(filepath: Path) -> str:
    import mimetypes
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    filename = filepath.name
    mime = mimetypes.guess_type(str(filepath))[0] or "image/png"

    with open(filepath, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = Request(
        f"{COMFY_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["name"]


def remove_bg(img, tolerance=45):
    arr = np.array(img.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    # Sample top corners + bottom corners separately to handle ground planes.
    # Use top corners as primary bg estimate (sky/empty space).
    # If top and bottom corners differ significantly, also remove bottom bg.
    top_corners = np.array([arr[0, 0, :3], arr[0, w-1, :3]], dtype=np.float32)
    bot_corners = np.array([arr[h-1, 0, :3], arr[h-1, w-1, :3]], dtype=np.float32)
    top_bg = np.mean(top_corners, axis=0)
    bot_bg = np.mean(bot_corners, axis=0)

    rgb = arr[:, :, :3].astype(np.float32)

    # Remove pixels close to top bg estimate
    diff_top = np.sqrt(np.sum((rgb - top_bg) ** 2, axis=2))
    arr[diff_top < tolerance, 3] = 0

    # If bottom corners differ from top, also remove bottom bg
    corner_diff = np.sqrt(np.sum((top_bg - bot_bg) ** 2))
    if corner_diff > 30:
        diff_bot = np.sqrt(np.sum((rgb - bot_bg) ** 2, axis=2))
        arr[diff_bot < tolerance, 3] = 0

    return Image.fromarray(arr)


def foundry_cmd(*args):
    cmd = [sys.executable, "-m", "foundry.cli"] + list(args)
    result = subprocess.run(cmd, cwd=str(FOUNDRY_ROOT), capture_output=True, text=True)
    if result.stdout:
        print(f"    {result.stdout.strip()}")
    if result.returncode != 0 and result.stderr:
        print(f"    ERROR: {result.stderr.strip()}")
    return result.returncode


def generate_morph(config: dict, depth_refs_dir: Path,
                   cn_strength: float = CONTROLNET_STRENGTH,
                   cn_end_percent: float = 0.8,
                   edge_refs_dir: Path = None,
                   edge_strength: float = 0.45,
                   edge_end_percent: float = 0.85):
    """Generate 8-direction sprites with morphology control and register in foundry."""
    subject_id = config["subject_id"]
    char_name = config["display_name"]
    seed = config["seed"]
    subject_prompt = config["subject_prompt"]
    negative_prompt = config["negative_prompt"]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{subject_id}_p5a_{ts}"
    out_dir = FOUNDRY_ROOT / "bakeoff" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    stack_name = "A_v2_morph"
    if edge_refs_dir:
        stack_name = "A_v2_morph_dual"

    print(f"\n{'=' * 60}")
    print(f"PHASE 5B MORPH GENERATION: {char_name}")
    print(f"Run: {run_id}  Seed: {seed}")
    print(f"Depth CN: {CONTROLNET_MODEL} @ {cn_strength} (end: {cn_end_percent})")
    if edge_refs_dir:
        print(f"Edge CN: controlnet-canny-sdxl-1.0 @ {edge_strength} (end: {edge_end_percent})")
        print(f"Edge refs: {edge_refs_dir}")
    print(f"Depth refs: {depth_refs_dir}")
    print(f"Output: {out_dir}")
    print(f"{'=' * 60}\n")

    # Upload all depth references first
    print("  Uploading depth references...")
    depth_names = {}
    for dir_name, _ in DIRECTIONS:
        ref_path = depth_refs_dir / f"{dir_name}_depth_ref.png"
        if not ref_path.exists():
            print(f"  WARNING: No depth ref for {dir_name}: {ref_path}")
            continue
        depth_names[dir_name] = upload_image(ref_path)
        print(f"    {dir_name}: {depth_names[dir_name]}")

    # Upload edge references if provided
    edge_names = {}
    if edge_refs_dir:
        print("  Uploading edge references...")
        for dir_name, _ in DIRECTIONS:
            ref_path = edge_refs_dir / f"{dir_name}_edge_ref.png"
            if not ref_path.exists():
                print(f"  WARNING: No edge ref for {dir_name}: {ref_path}")
                continue
            edge_names[dir_name] = upload_image(ref_path)
            print(f"    {dir_name}: {edge_names[dir_name]}")

    raw_images = {}
    pixel_images = {}
    generated_dirs = []

    for dir_name, dir_prompt in DIRECTIONS:
        if dir_name not in depth_names:
            print(f"  [{dir_name}] SKIP -- no depth reference")
            continue

        print(f"  [{dir_name}] submitting...", end=" ", flush=True)

        workflow = make_workflow_morph(
            subject_prompt, negative_prompt, dir_prompt,
            seed, f"{subject_id}_p5a",
            depth_names[dir_name],
            cn_strength=cn_strength,
            cn_end_percent=cn_end_percent,
            edge_image_name=edge_names.get(dir_name),
            edge_strength=edge_strength,
            edge_end_percent=edge_end_percent,
        )
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

            # Remove background + pixelate
            cleaned = remove_bg(raw_img.convert("RGBA"))
            w, h = cleaned.size
            if h > w:
                top = (h - w) // 4
                cleaned = cleaned.crop((0, top, w, top + w))

            pixel_img = cleaned.resize((SPRITE_TARGET, SPRITE_TARGET), Image.NEAREST)
            pixel_path = out_dir / f"{dir_name}.png"
            pixel_img.save(str(pixel_path))
            pixel_images[dir_name] = pixel_img

            generated_dirs.append(dir_name)
            print("OK")
        except Exception as e:
            print(f"EXTRACT FAIL: {e}")
            continue

    # Save recipe
    recipe = {
        "stack": stack_name, "character": char_name,
        "checkpoint": "juggernautXL_ragnarokBy.safetensors",
        "lora": "pixel-art-xl @ 0.85",
        "controlnet_depth": CONTROLNET_MODEL,
        "controlnet_depth_strength": cn_strength,
        "controlnet_depth_end_percent": cn_end_percent,
        "sampler": "euler_ancestral", "scheduler": "normal",
        "steps": 30, "cfg": 7.5,
        "gen_size": f"{GEN_WIDTH}x{GEN_HEIGHT}",
        "pixelate": SPRITE_TARGET, "seed": seed,
        "subject_prompt": subject_prompt,
        "negative": negative_prompt,
        "depth_refs_dir": str(depth_refs_dir),
    }
    if edge_refs_dir:
        recipe["controlnet_canny"] = "controlnet-canny-sdxl-1.0.safetensors"
        recipe["controlnet_canny_strength"] = edge_strength
        recipe["controlnet_canny_end_percent"] = edge_end_percent
        recipe["edge_refs_dir"] = str(edge_refs_dir)
    with open(out_dir / "recipe.json", "w") as f:
        json.dump(recipe, f, indent=2)

    print(f"\n  Generated {len(generated_dirs)}/8 directions")

    # Registry
    print(f"\n--- Registering in foundry ---")
    foundry_cmd(
        "register-run", run_id,
        "--subject", subject_id,
        "--stack", stack_name,
        "--seed", str(seed),
        "--width", str(GEN_WIDTH),
        "--height", str(GEN_HEIGHT),
        "--target", str(SPRITE_TARGET),
        "--recipe", str(out_dir / "recipe.json"),
    )

    for dir_name in generated_dirs:
        raw_path = str(out_dir / f"{dir_name}_raw.png")
        pixel_path = str(out_dir / f"{dir_name}.png")
        foundry_cmd(
            "register-attempt", run_id, dir_name,
            "--seed", str(seed),
            "--artifacts", "raw", raw_path,
            "--artifacts", "pixel", pixel_path,
        )

    print(f"\n--- Running mechanical gates ---")
    foundry_cmd("check", run_id)

    print(f"\n{'=' * 60}")
    print(f"MORPH GENERATION COMPLETE: {char_name}")
    print(f"Run: {run_id}")
    print(f"Next: foundry review-show {run_id}")
    print(f"{'=' * 60}")

    return run_id


def resolve_body_class(config: dict, cli_body_class: str = None,
                       cli_depth_refs: str = None) -> tuple[Path, float, float, Path | None, float, float]:
    """Resolve depth refs and ControlNet params from body_class or CLI overrides.

    Priority: CLI flags > config body_class > manual --depth-refs (required fallback).
    Returns: (depth_dir, strength, end_pct, edge_dir, edge_strength, edge_end_pct)
    """
    body_class = cli_body_class or config.get("body_class")

    if body_class:
        if body_class not in BODY_CLASS_PRESETS:
            print(f"Unknown body_class: {body_class}")
            print(f"Available: {', '.join(BODY_CLASS_PRESETS.keys())}")
            sys.exit(1)

        preset = BODY_CLASS_PRESETS[body_class]
        print(f"  Body class: {body_class}")

        # Config-level controlnet overrides take precedence over preset defaults
        config_cn = config.get("controlnet", {})

        depth_refs_name = preset["depth_refs"]
        if not depth_refs_name:
            print(f"  Body class '{body_class}' has no morph depth refs (use foundry_gen.py instead)")
            sys.exit(1)

        depth_dir = cli_depth_refs and Path(cli_depth_refs) or (MORPH_REFS_DIR / depth_refs_name)
        strength = config_cn.get("depth_strength", preset["depth_strength"])
        end_pct = config_cn.get("depth_end_pct", preset["depth_end_pct"])

        edge_dir = None
        edge_strength = 0.45
        edge_end_pct = 0.85
        if preset.get("canny"):
            edge_refs_name = preset.get("edge_refs")
            if edge_refs_name:
                edge_dir = MORPH_REFS_DIR / edge_refs_name
            edge_strength = config_cn.get("canny_strength", preset.get("canny_strength", 0.45))
            edge_end_pct = config_cn.get("canny_end_pct", preset.get("canny_end_pct", 0.85))

        return depth_dir, strength, end_pct, edge_dir, edge_strength, edge_end_pct

    return None, None, None, None, None, None


def main():
    parser = argparse.ArgumentParser(description="Morphology-controlled generation")
    parser.add_argument("--config", required=True, help="Path to character config JSON")
    parser.add_argument("--depth-refs", default=None, help="Directory with depth reference images (auto-resolved from body_class if set)")
    parser.add_argument("--body-class", default=None, help=f"Body class preset ({', '.join(BODY_CLASS_PRESETS.keys())})")
    parser.add_argument("--strength", type=float, default=None, help="Depth ControlNet strength (overrides body_class preset)")
    parser.add_argument("--end-percent", type=float, default=None, help="Depth ControlNet end_percent (overrides body_class preset)")
    parser.add_argument("--edge-refs", default=None, help="Directory with Canny edge reference images (optional, for dual control)")
    parser.add_argument("--edge-strength", type=float, default=0.45, help="Edge ControlNet strength (default 0.45)")
    parser.add_argument("--edge-end-percent", type=float, default=0.85, help="Edge ControlNet end_percent (default 0.85)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    # Resolve body_class → depth refs + ControlNet params
    bc_depth, bc_strength, bc_end, bc_edge, bc_edge_str, bc_edge_end = \
        resolve_body_class(config, args.body_class, args.depth_refs)

    # CLI flags override body_class presets
    depth_dir = Path(args.depth_refs) if args.depth_refs else bc_depth
    if depth_dir is None:
        print("ERROR: No depth refs specified. Use --depth-refs or --body-class or add body_class to config JSON.")
        sys.exit(1)
    if not depth_dir.exists():
        print(f"Depth refs directory not found: {depth_dir}")
        sys.exit(1)

    strength = args.strength if args.strength is not None else (bc_strength or CONTROLNET_STRENGTH)
    end_pct = args.end_percent if args.end_percent is not None else (bc_end or 0.8)

    edge_dir = None
    if args.edge_refs:
        edge_dir = Path(args.edge_refs)
    elif bc_edge:
        edge_dir = bc_edge
    if edge_dir and not edge_dir.exists():
        print(f"Edge refs directory not found: {edge_dir}")
        sys.exit(1)

    edge_strength = args.edge_strength if args.edge_refs else (bc_edge_str or 0.45)
    edge_end_pct = args.edge_end_percent if args.edge_refs else (bc_edge_end or 0.85)

    generate_morph(config, depth_dir,
                   cn_strength=strength, cn_end_percent=end_pct,
                   edge_refs_dir=edge_dir, edge_strength=edge_strength,
                   edge_end_percent=edge_end_pct)


if __name__ == "__main__":
    main()

"""
Phase 3 — Foundry-integrated map derivation.

Derives normal + depth maps for all 8 directions of a run's accepted sprites.
Registers map artifacts in the foundry registry.

Usage:
    python -m pipeline.foundry_maps --run <run_id>
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import urlopen, Request

from PIL import Image
import numpy as np

COMFY_URL = "http://127.0.0.1:8188"
FOUNDRY_ROOT = Path(__file__).parent.parent
SPRITE_TARGET = 48

# HTTP timeouts for all ComfyUI calls (seconds) — a dead server fails fast (F-007).
HTTP_TIMEOUT = 30

DIRECTIONS = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]


def make_normal_workflow(image_filename: str, prefix: str) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_filename}},
        "2": {
            "class_type": "MiDaS-NormalMapPreprocessor",
            "inputs": {
                "image": ["1", 0],
                "a": 6.283185307179586,
                "bg_threshold": 0.1,
                "resolution": 768,
            },
        },
        "3": {
            "class_type": "SaveImage",
            "inputs": {"images": ["2", 0], "filename_prefix": f"{prefix}_normal"},
        },
    }


def make_depth_workflow(image_filename: str, prefix: str) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_filename}},
        "2": {
            "class_type": "DepthAnythingPreprocessor",
            "inputs": {
                "image": ["1", 0],
                "ckpt_name": "depth_anything_vitl14.pth",
                "resolution": 768,
            },
        },
        "3": {
            "class_type": "SaveImage",
            "inputs": {"images": ["2", 0], "filename_prefix": f"{prefix}_depth"},
        },
    }


def check_comfy_reachable():
    """Fail fast if ComfyUI is not reachable, before processing directions (F-007)."""
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
    """Raise RuntimeError if ComfyUI recorded an execution error (F-006)."""
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
            raise
        except (URLError, HTTPError, OSError) as e:
            connect_failures += 1
            if connect_failures >= 3:
                raise RuntimeError(
                    f"ComfyUI became unreachable at {COMFY_URL} while waiting "
                    f"for prompt {prompt_id[:8]} ({e})."
                ) from e
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Prompt {prompt_id} timed out after {timeout}s")


def get_image(filename, subfolder=""):
    params = f"filename={filename}&subfolder={subfolder}&type=output"
    with urlopen(f"{COMFY_URL}/view?{params}", timeout=HTTP_TIMEOUT) as resp:
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
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        result = json.loads(resp.read())
    return result["name"]


def pixelate_map(raw_img: Image.Image, target: int) -> Image.Image:
    """Crop a derived map to the subject bounding box + square pad, then pixelate.

    Uses the same content-bounding-box crop as the sprite gen lanes (F-018) so the
    normal/depth maps stay aligned with the pixel sprite they were derived from.
    The old fixed top=(h-w)//4 crop would now misalign with the bbox-cropped sprite.

    Maps may be RGB (normals) or grayscale (depth) without an alpha channel; in
    that case we fall back to the legacy fixed crop since there is no transparency
    to find a bounding box from.
    """
    rgba = raw_img.convert("RGBA")
    arr = np.array(rgba)
    has_alpha = raw_img.mode in ("RGBA", "LA", "PA") or (
        raw_img.mode == "P" and "transparency" in raw_img.info
    )
    visible = arr[:, :, 3] > 0

    if has_alpha and np.any(visible):
        rows = np.any(visible, axis=1)
        cols = np.any(visible, axis=0)
        top, bottom = np.where(rows)[0][[0, -1]]
        left, right = np.where(cols)[0][[0, -1]]
        cropped = raw_img.crop((left, top, right + 1, bottom + 1))
        w, h = cropped.size
        side = max(w, h)
        square = Image.new(raw_img.mode, (side, side))
        square.paste(cropped, ((side - w) // 2, (side - h) // 2))
        cropped = square
    else:
        # No usable alpha (opaque normal/depth map) — keep the legacy center crop.
        w, h = raw_img.size
        if h > w:
            top = (h - w) // 4
            cropped = raw_img.crop((0, top, w, top + w))
        else:
            cropped = raw_img
    return cropped.resize((target, target), Image.NEAREST)


def derive_maps(run_id: str):
    """Derive normal + depth maps for a run and register in foundry."""
    # Import foundry modules
    sys.path.insert(0, str(FOUNDRY_ROOT))
    from foundry import db
    from foundry.cli import hash_file, now_iso

    conn = db.init_db()

    run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        print(f"Run '{run_id}' not found.")
        return

    subject = conn.execute(
        "SELECT display_name FROM subjects WHERE id = ?", (run["subject_id"],)
    ).fetchone()
    char_name = subject["display_name"] if subject else run["subject_id"]

    # Get accepted attempts (state = 'accepted' means passed pixel review)
    attempts = conn.execute(
        """SELECT id, direction, state FROM attempts
           WHERE run_id = ? AND direction IN ({})
           AND state IN ('accepted', 'finish_review_pending', 'finish_accepted')
           ORDER BY direction""".format(",".join("?" for _ in DIRECTIONS)),
        (run_id, *DIRECTIONS),
    ).fetchall()

    if not attempts:
        print(f"No accepted attempts found for run '{run_id}'.")
        conn.close()
        return

    # Fail fast if ComfyUI is down before processing directions (F-007).
    try:
        check_comfy_reachable()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        conn.close()
        return

    # Output directory for maps
    maps_dir = FOUNDRY_ROOT / "bakeoff" / f"{run_id}_maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    prefix = run["subject_id"]

    print(f"\n{'=' * 60}")
    print(f"MAP DERIVATION: {char_name}")
    print(f"Run: {run_id}  ({len(attempts)} directions)")
    print(f"Output: {maps_dir}")
    print(f"{'=' * 60}\n")

    normal_count = 0
    depth_count = 0

    for attempt in attempts:
        aid = attempt["id"]
        direction = attempt["direction"]

        # Get raw artifact path
        raw_art = conn.execute(
            "SELECT path FROM artifacts WHERE attempt_id = ? AND kind = 'raw'",
            (aid,),
        ).fetchone()

        if not raw_art:
            print(f"  [{direction}] SKIP -- no raw artifact")
            continue

        raw_path = FOUNDRY_ROOT / raw_art["path"]
        if not raw_path.exists():
            print(f"  [{direction}] SKIP -- raw file missing: {raw_path}")
            continue

        # Upload raw to ComfyUI
        print(f"  [{direction}] uploading...", end=" ", flush=True)
        try:
            uploaded_name = upload_image(raw_path)
        except Exception as e:
            print(f"UPLOAD FAIL: {e}")
            continue
        print(f"OK", end="")

        # Normal map
        print(f" | normal...", end=" ", flush=True)
        try:
            wf = make_normal_workflow(uploaded_name, f"{prefix}_{direction}")
            resp = queue_prompt(wf)
            history = wait_for_completion(resp["prompt_id"])
            img_info = history["outputs"]["3"]["images"][0]
            img_data = get_image(img_info["filename"], img_info.get("subfolder", ""))

            normal_raw_path = maps_dir / f"{direction}_normal_raw.png"
            with open(normal_raw_path, "wb") as f:
                f.write(img_data)

            normal_raw = Image.open(normal_raw_path)
            normal_px = pixelate_map(normal_raw, SPRITE_TARGET)
            normal_px_path = maps_dir / f"{direction}_normal.png"
            normal_px.save(str(normal_px_path))

            # Register artifacts
            for kind, p in [("normal_raw", normal_raw_path), ("normal", normal_px_path)]:
                rel = str(p.relative_to(FOUNDRY_ROOT))
                img_obj = Image.open(p)
                conn.execute(
                    """INSERT INTO artifacts (attempt_id, kind, path, width, height, hash, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (aid, kind, rel, img_obj.size[0], img_obj.size[1], hash_file(p), now_iso()),
                )

            normal_count += 1
            print("OK", end="")
        except Exception as e:
            print(f"FAIL({e})", end="")

        # Depth map
        print(f" | depth...", end=" ", flush=True)
        try:
            wf = make_depth_workflow(uploaded_name, f"{prefix}_{direction}")
            resp = queue_prompt(wf)
            history = wait_for_completion(resp["prompt_id"])
            img_info = history["outputs"]["3"]["images"][0]
            img_data = get_image(img_info["filename"], img_info.get("subfolder", ""))

            depth_raw_path = maps_dir / f"{direction}_depth_raw.png"
            with open(depth_raw_path, "wb") as f:
                f.write(img_data)

            depth_raw = Image.open(depth_raw_path)
            depth_px = pixelate_map(depth_raw, SPRITE_TARGET)
            depth_px_path = maps_dir / f"{direction}_depth.png"
            depth_px.save(str(depth_px_path))

            for kind, p in [("depth_raw", depth_raw_path), ("depth", depth_px_path)]:
                rel = str(p.relative_to(FOUNDRY_ROOT))
                img_obj = Image.open(p)
                conn.execute(
                    """INSERT INTO artifacts (attempt_id, kind, path, width, height, hash, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (aid, kind, rel, img_obj.size[0], img_obj.size[1], hash_file(p), now_iso()),
                )

            depth_count += 1
            print("OK")
        except Exception as e:
            print(f"FAIL({e})")

    conn.commit()
    conn.close()

    print(f"\n  Normals: {normal_count}/{len(attempts)}")
    print(f"  Depths:  {depth_count}/{len(attempts)}")
    print(f"  Output:  {maps_dir}")


def main():
    parser = argparse.ArgumentParser(description="Foundry map derivation")
    parser.add_argument("--run", required=True, help="Run ID")
    args = parser.parse_args()
    derive_maps(args.run)


if __name__ == "__main__":
    main()

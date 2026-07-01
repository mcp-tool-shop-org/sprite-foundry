"""Restylize the pirate-pack 8-dir sprite renders into the painterly HOUSE STYLE.
Per frame: composite the transparent render on the house pale bg -> canny -> base-Qwen +
InstantX ControlNet(canny) + sfhd LoRA @1.75 img2img @ denoise -> painterly. Per-character prompt
from the roster `subject` (carries species+identity+weapon); per-direction hint stops view-flipping.
Run: <COMFY_PY> _pack_restylize.py [--only <slug>] [--denoise 0.7] [--ctrl 0.9]
"""
import argparse, json, time, uuid, urllib.request
from pathlib import Path
import cv2, numpy as np
from PIL import Image
import config

COMFY_URL = config.COMFY_URL
COMFY_ROOT = config.COMFY_ROOT
COMFY_IN = COMFY_ROOT / "input"; COMFY_OUT = config.COMFY_OUT
UNET = config.UNET; LORA = config.LORA
CLIP = config.CLIP; VAE = config.VAE
CTRL = config.CTRL; DIM = 1024
PACK = config.PACK
ROSTER = config.ROSTER
BG = config.BG  # house pale bg
# my orbit convention: dir_0=front (-Y), CCW -> front, front-right, right, back-right, back, back-left, left, front-left
DIRHINT = [
    "viewed from the front, facing the viewer",
    "a three-quarter view from the front-right",
    "a clean right-side profile view",
    "a three-quarter view from behind on the right",
    "a full BACK view from directly behind, the back of the head and back, facing away, NO face visible",
    "a three-quarter view from behind on the left",
    "a clean left-side profile view",
    "a three-quarter view from the front-left",
]
NEG = ("anime, manga, cel shaded, 3d render, cgi, smooth plastic, glossy, video game screenshot, photorealistic, "
       "multiple characters, two people, duplicate, blurry, low quality, deformed, extra limbs, text, watermark, cropped")

def prep(render_png, tag):
    m = Image.open(render_png).convert("RGBA").resize((DIM, DIM), Image.LANCZOS)
    cv = Image.new("RGBA", (DIM, DIM), BG + (255,)); cv.alpha_composite(m)
    init = cv.convert("RGB"); init.save(COMFY_IN / f"pr_{tag}_init.png")
    g = cv2.cvtColor(np.asarray(init), cv2.COLOR_RGB2GRAY)
    e = cv2.dilate(cv2.Canny(g, 60, 150), np.ones((2, 2), np.uint8), 1)
    cv2.imwrite(str(COMFY_IN / f"pr_{tag}_canny.png"), e)
    return f"pr_{tag}_init.png", f"pr_{tag}_canny.png"

def graph(init_name, ctrl_name, pos, seed, denoise, ctrl_strength, prefix):
    return {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "80": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["37", 0], "lora_name": LORA, "strength_model": 1.75}},
        "66": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.1, "model": ["80", 0]}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "qwen_image", "device": "cpu"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "84": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": CTRL}},
        "10c": {"class_type": "LoadImage", "inputs": {"image": ctrl_name}},
        "10i": {"class_type": "LoadImage", "inputs": {"image": init_name}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": pos}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": NEG}},
        "85": {"class_type": "ControlNetApplyAdvanced",
               "inputs": {"positive": ["6", 0], "negative": ["7", 0], "control_net": ["84", 0], "image": ["10c", 0],
                          "vae": ["39", 0], "strength": ctrl_strength, "start_percent": 0.0, "end_percent": 1.0}},
        "12": {"class_type": "VAEEncode", "inputs": {"pixels": ["10i", 0], "vae": ["39", 0]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": 24, "cfg": 2.8, "sampler_name": "euler", "scheduler": "simple",
                         "denoise": denoise, "model": ["66", 0], "positive": ["85", 0], "negative": ["85", 1], "latent_image": ["12", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["8", 0]}},
    }

def free():
    try:
        urllib.request.urlopen(urllib.request.Request(f"{COMFY_URL}/free",
            json.dumps({"unload_models": True, "free_memory": True}).encode(), {"Content-Type": "application/json"}), timeout=30).read()
    except Exception: pass

def submit(g, dst):
    pid = json.loads(urllib.request.urlopen(urllib.request.Request(f"{COMFY_URL}/prompt",
        json.dumps({"prompt": g, "client_id": uuid.uuid4().hex}).encode(), {"Content-Type": "application/json"}), timeout=120).read())["prompt_id"]
    for _ in range(config.SUBMIT_TIMEOUT_S):
        hist = json.loads(urllib.request.urlopen(f"{COMFY_URL}/history/{pid}", timeout=30).read())
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error": raise RuntimeError(f"ComfyUI error: {st.get('messages')}")
            if hist[pid].get("outputs"):
                img = hist[pid]["outputs"]["9"]["images"][0]; src = COMFY_OUT / img["subfolder"] / img["filename"]
                for _w in range(120):
                    if src.exists(): Image.open(src).convert("RGB").save(dst); return dst
                    time.sleep(0.5)
        time.sleep(0.5)
    raise RuntimeError("timed out")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None); ap.add_argument("--denoise", type=float, default=0.7)
    ap.add_argument("--ctrl", type=float, default=0.9); ap.add_argument("--seed", type=int, default=770700)
    a = ap.parse_args()
    try:
        roster = {c["slug"]: c["subject"] for c in json.loads(ROSTER.read_text())}
    except FileNotFoundError:
        raise SystemExit(f"ERROR: roster file not found: {ROSTER} (set SF_ROSTER to override)")
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"ERROR: roster file malformed or unreadable ({ROSTER}): {e}")
    slugs = [a.only] if a.only else list(roster.keys())
    free()
    failed = []
    for s in slugs:
        subj = roster.get(s, "a fantasy pirate"); sdir = PACK / f"{s}_sprite"
        if not sdir.exists(): print(f"  SKIP {s} (no sprite dir)"); continue
        out = sdir / "_styled"; out.mkdir(exist_ok=True)
        try:
            for i in range(8):
                ren = sdir / f"dir_{i}.png"
                if not ren.exists(): continue
                pos = (f"sfhd style, {subj}, {DIRHINT[i]}, full body, standing, both feet on the ground, single figure, "
                       f"hand-painted painterly concept art, matte illustration, soft warm light, plain pale background")
                init_name, ctrl_name = prep(ren, f"{s}_{i}")
                submit(graph(init_name, ctrl_name, pos, a.seed, a.denoise, a.ctrl, f"pk_{s}_{i}"), out / f"styled_{i}.png")
                print(f"  {s} dir_{i} -> styled", flush=True)
        except Exception as e:
            print(f"  FAILED {s}: {e}", flush=True)
            failed.append(s)
            continue
        # styled sheet
        ims = [Image.open(out / f"styled_{i}.png").convert("RGB") for i in range(8) if (out / f"styled_{i}.png").exists()]
        if ims:
            g = 8; w = sum(im.width for im in ims) + g*(len(ims)+1); h = max(im.height for im in ims) + 2*g
            M = Image.new("RGB", (w, h), (40, 40, 46)); x = g
            for im in ims: M.paste(im, (x, g)); x += im.width + g
            M.save(out / "_styled_sheet.png")
        print(f"DONE {s}", flush=True)
    if failed:
        print(f"FAILED SLUGS ({len(failed)}): {', '.join(failed)}", flush=True)
    print("RESTYLIZE COMPLETE", flush=True)

if __name__ == "__main__":
    main()

"""Regenerate the harpooner concept with the harpoon held UPRIGHT AT HIS SIDE (so TRELLIS sees one
clean weapon, not a diagonal one it splits into a back-strapped offset). Qwen + sfhd LoRA, 4 seeds.
Run: <COMFY_PY> _harpooner_concept.py
"""
import json, time, uuid, urllib.request
from pathlib import Path
from PIL import Image
COMFY_URL = "http://127.0.0.1:8188"
COMFY_OUT = Path("E:/AI-Models/ComfyUI_windows_portable/ComfyUI/output")
OUT = Path("E:/AI/training/_p0_packs_modernize/pirate_raiders_hd/concepts")
UNET = "qwen_image_fp8_e4m3fn.safetensors"; LORA = "sfhd_style_v1_1250.safetensors"
CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"; VAE = "qwen_image_vae.safetensors"

POS = ("sfhd style, a hulking green-skinned orc harpooner with tusks and big ears, bare muscular arms with "
       "fur-trimmed leather bracers, a leather chest harness, a coil of rope, ragged trousers, "
       "holding a single tall barbed harpoon UPRIGHT AND VERTICAL at his right side, the harpoon shaft straight "
       "up and down close alongside his body with the butt resting on the ground, "
       "full body, standing, both feet on the ground, front view facing the viewer, single figure, "
       "hand-painted painterly concept art, matte illustration, soft warm light, plain pale grey background")
NEG = ("harpoon across the body, harpoon over the shoulder, harpoon on the back, diagonal weapon, weapon strapped "
       "to the back, two weapons, dual wield, second weapon, raised weapon, weapon held overhead, "
       "anime, manga, cel shaded, 3d render, cgi, photorealistic, multiple characters, blurry, deformed, "
       "extra limbs, text, watermark, cropped")

def graph(seed):
    return {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "80": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["37", 0], "lora_name": LORA, "strength_model": 1.75}},
        "66": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.1, "model": ["80", 0]}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "qwen_image", "device": "cpu"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": POS}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": NEG}},
        "5": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 24, "cfg": 3.5, "sampler_name": "euler",
              "scheduler": "simple", "denoise": 1.0, "model": ["66", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "harp_side", "images": ["8", 0]}},
    }

def submit(g, dst):
    pid = json.loads(urllib.request.urlopen(urllib.request.Request(f"{COMFY_URL}/prompt",
        json.dumps({"prompt": g, "client_id": uuid.uuid4().hex}).encode(), {"Content-Type": "application/json"}), timeout=120).read())["prompt_id"]
    for _ in range(2400):
        hist = json.loads(urllib.request.urlopen(f"{COMFY_URL}/history/{pid}", timeout=30).read())
        if pid in hist and hist[pid].get("outputs"):
            img = hist[pid]["outputs"]["9"]["images"][0]; src = COMFY_OUT / img["subfolder"] / img["filename"]
            for _w in range(120):
                if src.exists(): Image.open(src).convert("RGB").save(dst); return dst
                time.sleep(0.5)
        time.sleep(0.5)
    raise RuntimeError("timed out")

for i, seed in enumerate([770701, 880812, 113344, 556677]):
    dst = OUT / f"harpooner_side_{i}.png"
    submit(graph(seed), dst); print(f"  harpooner_side_{i} -> {dst}", flush=True)
print("HARPOONER CONCEPTS DONE", flush=True)

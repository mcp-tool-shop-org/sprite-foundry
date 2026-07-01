"""Shared rig configuration for every script in 3d-prerender/.

Every script in this directory (sprite_render.py, turntable.py, pack_restylize.py, pack_jury.py,
sprite_jury.py, harpooner_concept.py, mesh_character.py, retexture_character.py,
texture_patch_region.py) should `import config` and read rig paths/model names/tunables from
here instead of hardcoding them locally. This eliminates the drift where the same constant
(e.g. JURY models, ROSTER path, SUBMIT_TIMEOUT_S) was previously copy-pasted and could silently
diverge between scripts.

Every value below is overridable via an `SF_*` environment variable, with the current
rig-observed value (RTX 5090 / Omen 45L, this rig) as the default. This is deliberately a
single stdlib-only Python module, NOT a TOML/.env file with a parser — promoting this to a real
config file format is a deliberate non-goal until a second rig is in play. This is a
single-operator local-GPU tool, not a multi-tenant service; env-var overrides on top of
sane rig defaults are sufficient.
"""
import os
from pathlib import Path

# --- ComfyUI ---
COMFY_URL = os.environ.get("SF_COMFY_URL", "http://127.0.0.1:8188")
COMFY_ROOT = Path(os.environ.get("SF_COMFY_ROOT", "E:/AI-Models/ComfyUI_windows_portable/ComfyUI"))
COMFY_OUT = Path(os.environ.get("SF_COMFY_OUT", str(COMFY_ROOT / "output")))

# --- Concept output dir (harpooner_concept.py) ---
OUT = Path(os.environ.get("SF_OUT", "E:/AI/training/_p0_packs_modernize/pirate_raiders_hd/concepts"))

# --- Model root + TRELLIS ---
MODEL_ROOT = Path(os.environ.get("SF_MODEL_ROOT", "E:/AI-Models"))
TRELLIS_MODEL_ID = os.environ.get("SF_TRELLIS_MODEL_ID", "microsoft/TRELLIS.2-4B")

# --- Blender ---
BLENDER_EXE = Path(os.environ.get("SF_BLENDER_EXE", "E:/AI-Models/blender-5.0.1-windows-x64/blender.exe"))

# --- ComfyUI model filenames ---
UNET = os.environ.get("SF_UNET", "qwen_image_fp8_e4m3fn.safetensors")
LORA = os.environ.get("SF_LORA", "sfhd_style_v1_1250.safetensors")
CLIP = os.environ.get("SF_CLIP", "qwen_2.5_vl_7b_fp8_scaled.safetensors")
VAE = os.environ.get("SF_VAE", "qwen_image_vae.safetensors")
CTRL = os.environ.get("SF_CTRL", "Qwen-Image-InstantX-ControlNet-Union.safetensors")

# --- Pack + roster ---
PACK = Path(os.environ.get("SF_PACK", "E:/AI/training/_p0_packs_modernize/_mesh_line/_pirate_pack"))
ROSTER = Path(os.environ.get("SF_ROSTER", "E:/AI/sprite-foundry-2p5d/roster_pirate-raiders.json"))

# --- House style ---
BG = tuple(int(x) for x in os.environ.get("SF_BG", "216,210,192").split(","))

# --- Ollama / jury ---
OLLAMA = os.environ.get("SF_OLLAMA", "http://127.0.0.1:11434/api/chat")
JURY = os.environ.get("SF_JURY", "minimax-m3:cloud,kimi-k2.6:cloud,gemini-3-flash-preview:cloud").split(",")
CANARY = os.environ.get("SF_CANARY", "gemini-3-flash-preview:cloud")

# --- Submit/poll timeout (unified) ---
# pack_restylize.py previously used range(3000)*0.5s = 1500s; harpooner_concept.py used
# range(2400)*0.5s = 1200s. Unified on the larger/safer 3000 (= 1500s at the 0.5s poll interval
# each script already uses).
SUBMIT_TIMEOUT_S = int(os.environ.get("SF_SUBMIT_TIMEOUT_S", "3000"))

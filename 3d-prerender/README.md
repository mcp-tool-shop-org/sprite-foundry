# 3D Pre-Render Sprite Pipeline (the golden path)

The studio's **proven** way to turn a character concept into a high-fidelity 2.5D sprite: generate a
3D mesh, **render it from 8 directions** (no rigging), then **restylize** into the painterly house
style. Proven end-to-end on the whole **pirate-raiders-hd pack (26 characters)** on 2026-06-26.

> **Why pre-render, not rigging?** Making a 3D *sprite* does not require a rig — you render the mesh
> from N angles (the Octopath / HD-2D method). Auto-rigging (UniRig) **shreds** faced characters on
> rotation (a published structural limitation, not a tuning problem), so it is abandoned for sprites.

## The pipeline

```
concept (Qwen + sfhd LoRA)  →  TRELLIS.2 mesh  →  8-dir pre-render  →  restylize  →  jury-gate
        weapon to the SIDE        1024_cascade      = DELIVERABLE A      = DELIVERABLE B
                                                     (raw, shippable)     (painterly house style)
```

1. **Concept** — Qwen-Image + the `sfhd_style_v1_1250` house LoRA. Characterful pose; **hold any weapon
   upright AT THE SIDE** (see lessons). The roster `subject` string is the identity prompt.
   - Re-gen a fixed concept: `harpooner_concept.py` (pattern: Qwen txt2img + sfhd LoRA @1.75, EmptySD3Latent
     1024², KSampler euler/simple 24 / cfg 3.5 / denoise 1.0; negatives for the failure mode).
2. **Mesh — TRELLIS.2-4B** (MIT): `ATTN_BACKEND=sdpa SPARSE_ATTN_BACKEND=sdpa <trellis2-py> -u
   _mesh_character.py --image <concept>.png --out <mesh>.glb --ptype 1024_cascade` (~2 min, ~3.4 GB peak).
   One textured mesh, weapon baked in. **TRELLIS is deterministic** — same concept → same mesh.
3. **Pre-render 8-dir sprite — `sprite_render.py`** (DELIVERABLE A, raw, shippable):
   `blender -b --python sprite_render.py -- --glb <mesh>.glb --out <dir> --dirs 8 --size 768 --samples 256 --elev 18`
   - Turntable-orbit camera (telephoto ≈ orthographic), gentle ~18° downward (face reads), `track_to` centered.
   - Cycles + **OptiX** render, `render.use_persistent_data=True`, adaptive 0.01, transparent **RGBA PNG**,
     View Transform **Standard**, **OIDN denoiser** (OptiX denoise eats transparent-alpha edges).
   - Framing = **post alpha-bbox** (union over all directions → consistent scale + centered, no projection math).
   - Outputs `dir_N.png` (raw) + `sprite_N.png` (auto-fit) + `_sheet.png`.
4. **Restylize — `pack_restylize.py`** (DELIVERABLE B, painterly house style):
   `<comfy-py> pack_restylize.py [--only <slug>] [--denoise 0.7]`
   - Per frame: composite render on the house pale bg (216,210,192) → canny → base-Qwen
     (`qwen_image_fp8`) + **InstantX `Qwen-Image-ControlNet-Union`** (canny @0.9) + `sfhd` LoRA @1.75 img2img,
     KSampler 24 / cfg 2.8 / euler-simple / **denoise 0.7**, per-direction hint (stops view-flipping).
   - Per-character prompt = the roster `subject` (carries species + identity + weapon).
   - Outputs `<slug>_sprite/_styled/styled_N.png` + `_styled_sheet.png`.
5. **Gate** — cross-family Ollama-cloud vision jury: `pack_jury.py <pack-dir>` (whole pack) or
   `sprite_jury.py <dir>` (one char). Refute-by-default, 2-of-3, gemini = strict canary. **Always look
   full-res, ZOOMED** — judge defects on the zoomed single frame, never off a montage.

## Hard-won lessons (do not relearn)

- **No rigging for sprites.** UniRig auto-skin shreds faced characters on rotation. Render, don't rig.
- **Hold weapons to the SIDE** (vertical, alongside the body). A weapon crossing diagonally / over the
  shoulder confuses TRELLIS — it reads the far half as a *separate weapon strapped to the back* and offsets
  it. (The harpooner: long harpoon held diagonally → split/offset; held at the side → one clean weapon.)
- **A weapon baked into the concept → one mesh is FINE.** What always fails is *socketing a separate weapon
  onto the hand* — don't. TRELLIS the concept weapon-and-all.
- **TRELLIS is deterministic** — to fix a mesh defect, regenerate the **concept** (re-pose / re-gen), not re-roll.
- **Face softness is concept-side** — no downstream tool fixes it (Step1X-3D, StableNormal, MV-Adapter all
  ruled out on-rig). Crisper faces = better concept generation, upstream.
- **Don't overclaim.** Judge zoomed + jury-gated before calling anything done.

## Rig dependencies (this rig: RTX 5090 / Omen 45L)

- TRELLIS.2-4B env `E:/AI-Models/trellis2-env` + repo `E:/AI-Models/TRELLIS.2-repo/_mesh_character.py`.
- ComfyUI `E:/AI-Models/ComfyUI_windows_portable` + Qwen-Image (`qwen_image_fp8`) + `sfhd_style_v1_1250.safetensors`
  + `Qwen-Image-InstantX-ControlNet-Union.safetensors`.
- Blender 5.0 `E:/AI-Models/blender-5.0.1-windows-x64/blender.exe`.
- Cross-family jury: Ollama daemon + cloud vision models (re-confirm roster at run time).

> **Note:** these scripts carry rig-specific absolute paths and are committed as working tooling so the
> pipeline isn't lost. Productizing (de-hardcoded config, packaged CLI) is a follow-up — see the kickoff.

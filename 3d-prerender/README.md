# 3D Pre-Render Sprite Pipeline (the golden path)

The studio's **proven** way to turn a character concept into a high-fidelity 2.5D sprite: generate a
3D mesh, **bake a consistent texture onto it**, then **render it from 8 directions** (no rigging).
Proven end-to-end on **pirate-raiders-hd** (26 characters, 2026-06-26) and carried through the v2
retexture upgrade on the full **pirate-raiders-3d** roster (26/26, 2026-07-01).

> **Why pre-render, not rigging?** Making a 3D *sprite* does not require a rig — you render the mesh
> from N angles (the Octopath / HD-2D method). Auto-rigging (UniRig) **shreds** faced characters on
> rotation (a published structural limitation, not a tuning problem), so it is abandoned for sprites.

## The pipeline (v2 — retexture replaces restylize-for-consistency)

```
concept (Qwen + house LoRA)  →  TRELLIS.2 mesh  →  TRELLIS.2 retexture  →  8-dir render  →  jury-gate
        weapon to the SIDE        1024_cascade      shape-conditioned      = THE DELIVERABLE
                                                      texture bake
```

1. **Concept** — Qwen-Image + the house style LoRA (`config.LORA`). Characterful pose; **hold any
   weapon upright AT THE SIDE** (see Pipeline Gotchas). The roster `subject` string is the identity
   prompt.
   - Re-gen a fixed concept: `harpooner_concept.py` (pattern: Qwen txt2img + LoRA img2img, KSampler
     euler/simple 24 / cfg 3.5 / denoise 1.0; negatives tuned per failure mode).
2. **Mesh — TRELLIS.2-4B** (MIT), `Trellis2ImageTo3DPipeline`:
   `python cli.py mesh --image <concept>.png --out <mesh>.glb --ptype 1024_cascade` (~2 min, ~3.4 GB
   peak). One textured mesh, weapon baked in. **TRELLIS is deterministic** — same concept → same mesh.
3. **Retexture — TRELLIS.2-4B**, `Trellis2TexturingPipeline` (replaces the old cross-angle-consistency
   job that `pack_restylize.py` used to do — see "Why retexture, not restylize" below):
   `python cli.py retexture --mesh <mesh>.glb --image <concept>.png --out <retextured>.glb --seed <n>`
   (~80-90s: ~40s model load, ~40s bake). Bakes ONE texture from the mesh + reference image, guaranteeing
   cross-angle consistency by construction — there's only one bake, not 8 independent per-direction ones.
4. **Render — `sprite_render.py`** (THE deliverable, raw, shippable), run against the **retextured**
   glb: `python cli.py render --glb <retextured>.glb --out <dir> --dirs 8 --size 1024 --samples 512`.
   - Turntable-orbit camera (telephoto ≈ orthographic), gentle ~18° downward (face reads), `track_to`
     centered.
   - Cycles + **OptiX** render, `render.use_persistent_data=True`, adaptive 0.01, transparent **RGBA
     PNG**, View Transform **Standard**, **OIDN denoiser** (OptiX denoise eats transparent-alpha edges).
   - Framing = **post alpha-bbox** (union over all directions → consistent scale + centered, no
     projection math).
   - Outputs `dir_N.png` (raw) + `sprite_N.png` (auto-fit) + `_sheet.png`.
5. **Patch fallback (when a reroll won't fix it)** — `python cli.py patch --mesh <retextured>.glb --out
   <patched>.glb --y-min <f> --y-max <f>`: a direct texture-space patch for coverage defects (a garment
   gap exposing skin, etc.) that survive 2-3 reroll attempts at the concept/retexture stage. See
   "When a reroll fails 3+ times" below — this edits texture pixels only, geometry untouched.
6. **Gate** — cross-family Ollama-cloud vision jury: `python cli.py jury <pack-dir>` (whole pack, front
   sprite only — `--target pack`, the default) or `python cli.py jury --target sprite <dir>` (one
   character, front/side/back). Refute-by-default, 2-of-3, gemini = strict canary. **Always look
   full-res, ZOOMED** — judge defects on the zoomed single frame, never off a montage (see LAW #0
   below).
7. **Restylize (optional, painterly finishing pass)** — `pack_restylize.py` is still here and still
   works; it is no longer *required* for cross-angle consistency (retexture solves that by construction
   now), but it remains available as an optional painterly-house-style finishing pass over the raw
   render if a project wants that look. Not proven broken — just no longer load-bearing for consistency.

## CLI

`3d-prerender/cli.py` is a thin argparse wrapper — it builds a subprocess invocation of the real script
per stage and forwards unrecognized flags straight through, so it never drifts out of sync with each
script's own argument surface. Subcommands: `mesh`, `retexture`, `patch`, `render`, `jury`, `doctor`,
`pipeline`.

- Every stage command accepts `--probe`/`--dry-run`: prints the resolved subprocess command line and
  exits without spending GPU time — check before committing 1-5 minutes to a run.
- `python cli.py doctor` validates your config (model root, ComfyUI root, roster path, Blender
  executable, ComfyUI reachability) and reports pass/fail per check — run this first on a new rig.
- `python cli.py pipeline --image <concept>.png --out <dir>` chains mesh → retexture → render for one
  character in sequence.

## Config

`3d-prerender/config.py` is a single environment-overridable constants module — every script in this
folder imports rig-specific paths, model filenames, and generation constants (ComfyUI URL, model root,
Blender executable, LoRA/checkpoint filenames, the pale background color, the Ollama jury models) from
it instead of hardcoding them. Every constant is overridable via an `SF_*` environment variable of the
same name (e.g. `SF_COMFY_URL`, `SF_MODEL_ROOT`, `SF_BLENDER_EXE`, `SF_LORA`) to run this pipeline on a
different rig; see the module itself for the full list and current defaults. Promoting this to a config
*file* (TOML/.env) is a deliberate non-goal until a second rig is actually in play — see the module
docstring.

## Pipeline Gotchas

Dated, falsifiable lessons from running this pipeline in production. Each entry: symptom, root cause,
fix, and how to reproduce/verify — not just a "watch out for X." Entries are updated in place as
understanding deepens rather than left to go stale.

### 2026-06-30 — Independent per-direction restyle drifted identity across angles (root cause: Janus problem)
- **Symptom:** the old restylize-for-consistency approach (cloud two-stage Qwen+ControlNet-canny →
  distilled FLUX.2-klein, no ControlNet on stage 2) produced visible cross-angle identity drift — a
  captain's hat shape and beard color/texture changed between directions.
- **Root cause:** independently sampling each of the 8 views with a diffusion model is a named failure
  mode in the literature — the Janus problem (MVDream, arXiv:2308.16512) and Zero123++
  (arXiv:2310.15110, which explicitly attributes cross-view breakdown to "the sampling nature of
  diffusion models"). Per-view parameter tuning (canny strength, denoise) only partially mitigates it;
  it doesn't fix the underlying cause.
- **Fix:** bake ONE texture from mesh + reference image instead of 8 independent per-view samples.
  `Trellis2TexturingPipeline` (this pipeline's retexture stage) is exactly that fix — the field's
  convergent answer (SyncMVD, Paint3D, TEXTure, MVPaint, CharacterGen all use shared/joint multi-view
  generation or single-texture-bake for the same reason).
- **Reproduce/verify:** compare any pre-2026-06-30 restylized pack against its retextured re-run —
  cross-angle beard/hat/color consistency should visibly improve with zero per-character tuning.

### 2026-06-30 — Hallucinated face tattoos misdiagnosed as a lighting/geometry bug
- **Symptom:** a character's eyes rendered as shadowed/hidden across every angle. First hypothesis
  (lighting or brow geometry) was wrong.
- **Root cause:** the texture bake hallucinated a pair of face tattoos with zero textual cause anywhere
  in the roster prompt — a pure diffusion hallucination, not a rendering artifact.
- **Fix:** rewrite the ROSTER `identity` text to **positively describe** the wanted trait rather than
  just negating the defect. "dark sunken cold eyes" biased generation toward exactly that; rewriting to
  "cold hard pale grey eyes clearly visible and open under a heavy brow... not shadowed or hidden" plus
  explicit anti-tattoo negatives (`"face tattoos, facial tattoos, tattoos around the eyes, ink markings
  on the face, tribal face paint, dark markings under the eyes, war paint on the face"`) fixed it.
  Negating alone is weaker than describing the positive target.
- **Reproduce/verify:** re-mesh + re-retexture + re-render after any ROSTER text edit before calling a
  face/eye fix confirmed — a fix can look clean in the 2D concept but not fully carry through meshing.

### 2026-06-30 — Coverage defect (coat-front gap) survived 3 concept-stage rerolls
- **Symptom:** a coat-front gap exposing bare thigh/hip persisted across 3 separate reroll attempts at
  the 2D concept stage (new seed, strengthened negatives, lower denoise) — the concept image looked
  fine each time, but the actual 3D render still showed the gap.
- **Root cause:** TRELLIS's image→3D step has to infer depth/side geometry from a single front view and
  defaulted to an open-front topology biased by the coat's lapels/belt. The defect is introduced
  **downstream of the prompt entirely**, at meshing — no amount of 2D-stage text engineering fixes a
  meshing-stage defect.
- **Fix:** `texture_patch_region.py` (the `patch` CLI subcommand) — classifies vertices as skin-vs-garment
  by sampling baked texture color, restricts to a height band you supply, rasterizes the affected
  triangles' texel footprint (not just point-samples — a naive per-vertex disc-paint leaves a mottled
  look), dilates for full coverage, and recolors those texels from same-height garment texels. Edits
  texture pixels only, geometry untouched — low-risk, fully deterministic.
- **When to reach for this instead of another reroll:** after 2-3 failed reroll attempts on a
  coverage/modesty defect specifically (not every defect — grip/weapon issues are usually a concept-side
  fix, see below). Always patch the **retextured** glb (after the retexture stage), never before — an
  earlier patch would just get overwritten by the fresh bake.
- **Reproduce/verify:** `python cli.py patch --mesh <retextured>.glb --out <patched>.glb --y-min <f>
  --y-max <f>` — find `--y-min`/`--y-max` empirically (raw glTF Y-up axis; print the mesh's Y range
  first to calibrate). Verify clean across all 8 rendered angles, hands/face untouched.

### 2026-06-30 — Color desaturation on dyed fabric/wounds (root cause still open)
- **Symptom:** small pigmented details (wound scars, dyed fabric) lose saturation between the source
  concept and the final render — confirmed on 5+ characters, with several clean counter-examples on the
  same run (not universal).
- **Root cause investigation:** hypothesized as a Blender lighting/rendering artifact — **ruled out**.
  Re-rendered an existing mesh with world background strength 0.7→0.25 and fill light 2.5→1.5; wound-scar
  color was completely unchanged. Confirmed unchanged across the original mesh pipeline, the retexture
  re-bake, and significantly different Blender lighting — the desaturation is baked into the texture
  pixel data itself, most likely during TRELLIS's texture-generation/sampling step, not the render.
- **Status:** NOT fixed. Any real fix would need to target the 2D concept generation or TRELLIS's
  texture step, not the render pipeline. Treated as a known/cosmetic issue for now — flag as a candidate
  investigation if it blocks a future character.
- **Reproduce/verify:** compare a wound-scar or dyed-fabric region's color in the source concept vs. the
  final render at full res, zoomed.

### Weapon grips — fix the concept, not the mesh (recurring, proven multiple times)
- **Symptom:** a weapon's grip looks disconnected, offset, or duplicated after meshing.
- **Root cause:** TRELLIS can't build a 3D grip from an ambiguous 2D held-weapon pose. A weapon crossing
  diagonally / over the shoulder reads as a *separate weapon strapped to the back* and gets offset. A
  weapon held in both hands diagonally across the body dominates the prompt at any ControlNet strength
  tested down to 0.15 — text alone can't out-argue a canny-locked two-handed grip.
- **Fix, in order of preference:** (1) remove the weapon from the concept entirely — cleanest, proven
  repeatedly; (2) extend the hilt/haft up into the hand if the weapon must stay; (3) reposition via a
  low-ControlNet-strength reroll while keeping the weapon — this repeatedly failed when the source shows
  a two-handed diagonal grip, so don't bother if that's the starting pose.
- **Reproduce/verify:** check grip contact from at least two angles (front + one profile) — a weapon
  that looks fine head-on can still show a floating/disconnected grip in profile.

## Hard-won lessons (do not relearn)

- **No rigging for sprites.** UniRig auto-skin shreds faced characters on rotation. Render, don't rig.
- **A weapon baked into the concept → one mesh is FINE.** What always fails is *socketing a separate
  weapon onto the hand* — don't. TRELLIS the concept weapon-and-all.
- **TRELLIS is deterministic** — to fix a mesh defect, regenerate the **concept** (re-pose / re-gen), not
  re-roll blindly.
- **Face softness is concept-side** — no downstream tool fixes it (Step1X-3D, StableNormal, MV-Adapter
  all ruled out on-rig). Crisper faces = better concept generation, upstream.
- **A "done" list is a claim about disk state at write-time, not a fact.** Verify the actual mesh/render
  files exist before building on top of a status line — especially after any stale-data mix-up has
  already happened once.
- **Don't overclaim.** Judge zoomed + jury-gated before calling anything done — never approve an output
  without opening it at full resolution and zooming the specific region in question first (grip, weapon
  join, face). This is LAW #0 for this pipeline.

## Rig dependencies (this rig: RTX 5090 / Omen 45L)

All paths below are `3d-prerender/config.py` defaults, overridable per-rig via environment variables —
see that file for the full list.

- TRELLIS.2-4B env + repo (`microsoft/TRELLIS.2-4B`, MIT license).
- ComfyUI + the house style LoRA + Qwen-Image checkpoint + ControlNet-Union (only needed for the
  concept-generation and optional restylize steps — the mesh/retexture/render steps don't touch Comfy).
- Blender 5.0+.
- Cross-family jury: Ollama daemon + cloud vision models (re-confirm roster at run time).

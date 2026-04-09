# Option A: Multi-View Zero123 via Attention Fusion

## Goal

Extend Zero123 (Stable Diffusion fine-tuned for 3D view synthesis) to accept multiple reference images (front, side, back) instead of one. The model generates novel views that consistently integrate details from all seed images.

## Why This Matters

Current sprite generation has two broken paths:
1. **Per-direction txt2img** — 8 independent generations, no visual connection, characters don't actually rotate
2. **Turnaround LoRA (CharTurn)** — generates a sheet with front/side/back but in-between angles are mush, not true rotation
3. **Zero123 single-seed** — hallucinates unseen angles from one image, loses details that exist in other views

Option A solves this: feed front + side + back as seeds, generate any angle with real information from the closest reference.

## Architecture

### How Zero123 Works (Single Image)
1. Encode reference image via CLIP Vision → embedding
2. Concatenate embedding with target camera pose (azimuth, elevation)
3. Cross-attention in UNet conditions on this combined representation
4. Diffuse from noise → output image at target angle

### How Multi-View Fusion Works (Option A)
1. Encode each reference image via CLIP Vision → N embeddings
2. Associate each embedding with its source camera pose
3. **Key change**: modify UNet cross-attention to attend to all N reference embeddings simultaneously
4. Weight each reference's contribution by angular proximity to target pose
5. Diffuse from noise → output image at target angle

### IP-Adapter Pattern
IP-Adapter already solves "add image conditioning to cross-attention without retraining":
- Adds a parallel cross-attention branch per image input
- Uses decoupled attention (separate key/value projections for text vs image)
- Proven to work with SDXL and SD 1.5

We adapt this pattern for Zero123:
- Instead of one image input, we have N reference images
- Instead of one CLIP embedding, we have N embeddings + N source poses
- The cross-attention weights each reference by angular distance to target

## Implementation Plan

### Phase 1: Single-Reference Baseline (Verify Pipeline)

**Goal**: Get Zero123 running correctly from Python without ComfyUI.

The ComfyUI built-in `StableZero123_Conditioning` node has a compatibility bug with the 8GB checkpoint (cc_projection weights get stripped during CLIP vision loading). A standalone Python pipeline bypasses this.

**Tasks**:
1. Load `stable_zero123.ckpt` manually via torch, stashing `cc_projection` weights before any processing
2. Initialize `Stable_Zero123` model with stashed weights
3. Load CLIP Vision and VAE separately
4. Build the conditioning pipeline: CLIP encode → camera embed → cross-attn
5. Run KSampler → VAEDecode → save image
6. Verify: single front image → 90° rotation produces a real side view

**Files**: `pipeline/zero123_standalone.py`

**Estimated effort**: 1 session

### Phase 2: Multi-Reference Attention Fusion

**Goal**: Modify the cross-attention to accept N reference images.

**Approach**:
```
For each reference image (front, side, back):
  1. CLIP Vision encode → embedding_i
  2. Associate with source_pose_i (azimuth, elevation)

For target pose:
  1. Compute angular_distance(target_pose, source_pose_i) for each reference
  2. Compute attention_weight_i = softmax(-angular_distance / temperature)
  3. Weighted combination in cross-attention:
     - key_combined = sum(weight_i * project_key(embedding_i))
     - value_combined = sum(weight_i * project_value(embedding_i))
  4. Or: concatenate all embeddings, let attention learn to weight them
```

**Two sub-approaches**:

**2A: Weighted embedding blend (simpler)**
- Before cross-attention, blend the N CLIP embeddings using angular weights
- Feed the blended embedding to the unmodified Zero123 cross-attention
- Pros: No model modification needed
- Cons: Loses per-reference detail, just averages

**2B: Parallel cross-attention branches (IP-Adapter style)**
- Add N cross-attention branches, one per reference
- Each branch has its own key/value projection
- Output is weighted sum of all branches
- Pros: Preserves per-reference detail
- Cons: More complex, higher VRAM

**Start with 2A** (can be done in one session), **graduate to 2B** if quality insufficient.

**Files**: `pipeline/zero123_multiview.py`, `pipeline/attention_fusion.py`

**Estimated effort**: 2A = 1 session, 2B = 2-3 sessions

### Phase 3: Integration with Sprite Foundry

**Goal**: Wire the multi-view pipeline into sprite-foundry's generation flow.

**Flow**:
1. Generate turnaround sheet via CharTurn LoRA (existing `foundry_gen_turnaround.py`)
2. Extract front, side, back from sheet (existing cropping code)
3. Feed 3 views into multi-view Zero123 → generate 8 directions
4. Process to 48px sprites (existing BG removal + downscale)
5. Run mechanical gates (existing `foundry/mechanical.py`)
6. Register in foundry DB

**Files**: Update `foundry_gen_turnaround.py` or new `foundry_gen_multiview.py`

**Estimated effort**: 1 session

### Phase 4: Quality Gates (Doctrine Integration)

**Goal**: Wire the render doctrine checks into the pipeline.

Game Foundry OS v1.9.0 has:
- `render_doctrine_get` — project render thresholds
- `proof_run_board_composite` — board survivability proof
- `proof_run_visual_suite` — occupancy, perimeter, direction consistency

These should gate sprite promotion in sprite-foundry.

**Estimated effort**: 1 session

## Known Issues / Blockers

### ComfyUI Zero123 Bug
`stable_zero123.ckpt` fails to load in ComfyUI 0.18.0. The `cc_projection.weight` and `cc_projection.bias` keys get removed from the state dict during CLIP Vision loading (`clip_vision.load_clipvision_from_sd` calls `convert_to_transformers` which pops keys). By the time `get_model` is called, the keys are gone.

**Workaround**: Load the model manually in standalone Python, stashing cc_projection weights before CLIP Vision processing.

**Patches applied** (in ComfyUI runtime, may be overwritten on update):
- `comfy/supported_models.py:392` — fallback to stashed weights
- `comfy/sd.py:1570` — stash cc_projection in `load_checkpoint_guess_config`

### Model Licensing
Zero123++ weights are CC-BY-NC (non-commercial). Stable Zero123 has a more permissive community license. If this becomes a shipped tool, use Stable Zero123 or train from scratch.

### Hardware
- RTX 5080 Laptop, 16GB VRAM
- Zero123 checkpoint: 8GB (fp32) — fits but tight with other models
- For multi-reference (3 CLIP encodes + UNet): estimate ~10-12GB VRAM needed

## What Exists Today

### Sprite Foundry Pipeline (`F:\AI\sprite-foundry\pipeline\`)
- `foundry_gen.py` — original 8-direction independent txt2img (proven, 92 packs)
- `foundry_gen_iterative.py` — txt2img hero + img2img refine + IPAdapter rotate (IPAdapter locks pose, doesn't work)
- `foundry_gen_turnaround.py` — CharTurn LoRA turnaround sheet + crop (WORKS — good front/side/back)
- `foundry_gen_zero123.py` — Zero123 via ComfyUI API (BLOCKED by cc_projection bug)
- `zero123_direct.py` — standalone Zero123 loader (INCOMPLETE — skeleton only)
- `blender_rotate.py` — Blender billboard rotation (WORKS but billboard approach too simple)

### Models Installed (`F:\AI-Models\ComfyUI\models\`)
- `checkpoints/stable_zero123.ckpt` — 8GB, valid, cc_projection keys present
- `checkpoints/juggernautXL_ragnarokBy.safetensors` — base SDXL checkpoint
- `loras/charturn-xl.safetensors` — 436MB, CharTurn turnaround LoRA
- `loras/pixel-art-xl.safetensors` — pixel art style LoRA
- `loras/pixelArtDiffusionXL_spriteShaper.safetensors` — 218MB sprite LoRA
- `controlnet/controlnet-union-sdxl-promax.safetensors` — 2.4GB union ControlNet
- `ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors` — IP-Adapter
- `ipadapter/ip-adapter-faceid-plusv2_sdxl.bin` — FaceID Plus v2

### Game Foundry OS (`F:\AI\mcp-tool-shop-org\game-foundry-os\`)
- v1.9.0 shipped this session
- Schema v13 with render_doctrines table
- 138 MCP tools, 1270 tests
- Render doctrine, board composite proof, doctrine-aware visual proof all working

## References

- [Zero123++ Paper](https://arxiv.org/abs/2310.15110)
- [IP-Adapter Documentation](https://github.com/cubiq/ComfyUI_IPAdapter_plus)
- [Stable Virtual Camera](https://stability.ai/) — multi-view diffusion with N inputs
- [CharTurn XL LoRA](https://civitai.com/models/694887/xl-charturn-multi-view-turnaround-model-sheet-character-design)
- [Multi-View Extension Analysis](C:\Users\mikey\Downloads\Multi-View Extension of Zero123.txt)

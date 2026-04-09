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

### Phase 2: Attention-Level Fusion (Option A from Multi-View Extension doc)

**Goal**: Modify the UNet's cross-attention to attend to multiple reference embeddings simultaneously, following the IP-Adapter pattern.

**Architecture**:

Encode each seed image separately via CLIP Vision, then modify the UNet so its cross-attention layers attend to ALL reference embeddings at once. Each view contributes features through dedicated cross-attention branches — "decoupled" attention that lets each view inform the generation without retraining the backbone.

This is the IP-Adapter pattern applied to Zero123:
- IP-Adapter adds parallel cross-attention branches for image conditioning
- Each branch has its own key/value projections (decoupled from text cross-attn)
- We add one branch per reference image, each associated with its source camera pose
- The UNet attends to all references simultaneously during denoising

**Implementation**:
1. Project each reference image through CLIP-ViT encoder → N embeddings
2. Associate each embedding with its source pose (azimuth, elevation)
3. Add extra cross-attention branches to UNet (one per reference, or a joint key-value bank)
4. At each attention block, the UNet queries against all reference key/values
5. Angular proximity to target pose can weight each reference's contribution

**Two sub-approaches** (try in order):

**2A: Concatenated embedding (simpler)**
- Concatenate all N CLIP embeddings into one long token sequence
- Feed to unmodified cross-attention (treats multi-view as one long "prompt")
- Pros: Minimal code change, no new attention layers
- Cons: No explicit pose-awareness, model must figure out which tokens matter

**2B: Parallel cross-attention branches (full IP-Adapter style)**
- Add N dedicated cross-attention branches to the UNet
- Each branch projects its reference embedding with its own key/value weights
- Output is combined (sum/weighted average) based on angular distance to target
- Pros: Preserves per-reference detail, pose-aware weighting
- Cons: More complex, higher VRAM, requires modifying model definition

**Start with 2A** to prove multi-reference conditioning helps at all. **Graduate to 2B** if 2A produces mush from averaging.

**Key reference**: IP-Adapter uses separate cross-attn layers so the model learns image-specific cues without interfering with text conditioning. Apply the same principle here — separate branches let each view contribute independently.

**Files**: `pipeline/attention_fusion.py`, `pipeline/zero123_multiview.py`

**Estimated effort**: 2A = 1 session, 2B = 2-3 sessions

**Tradeoffs**: Architecturally complex but avoids retraining. Quality gain uncertain — if seeds are harmonious (different angles of same character), this should enrich detail. The model's prior may override conflicting cues, but for our use case (front/side/back of same character), the seeds should be highly compatible.

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

### Hardware / VRAM Strategy
- RTX 5080 Laptop, 16GB VRAM
- Zero123 checkpoint: 8GB (fp32) — fits but tight with other models
- For multi-reference (3 CLIP encodes + UNet): estimate ~10-12GB VRAM needed
- **Critical**: Run CLIP encodes in fp16 or encode sequentially (encode → cache embedding → free → next). Plan this before Phase 2 starts.
- UNet inference should be fp16 minimum. The 8GB fp32 checkpoint should be converted to fp16 at load time to halve VRAM usage.

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

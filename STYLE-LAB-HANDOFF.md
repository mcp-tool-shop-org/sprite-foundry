# Hunyuan3D Style Lab — Session Handoff

> Session: 2026-04-09 | Operator: Claude Opus 4.6

## What Was Done

### 1. Forge Vault: `hunyuan3d-lab` Test Game

Created a structured experiment harness in the Obsidian vault at `forge-vault/games/hunyuan3d-lab/` with:

- **Game index** (`_index.md`) — Dataview queries, scoring rubric, key paths
- **2 experiment axes** with hypotheses, run order, and scoring templates:
  - `experiments/body-type-variety.md` — armored knight, winged demon, dire wolf
  - `experiments/thin-feature-survival.md` — spear lancer, scorpion beast, moth shaman
- **6 test subject character pages** — each with CharTurn config, hypotheses, empty results tables
- **6 weapon variant turnaround sheets** — greatsword, battleaxe, sword & shield, longbow, warhammer, dual daggers
- **Pipeline reference** (`experiments/pipeline-reference.md`) — quick-ref to HUNYUAN3D-HANDOFF.md
- **Model candidates** (`experiments/model-candidates.md`) — research on alternative multi-view models
- **Weapon comparison** (`experiments/weapon-variants.md`) — side-by-side weapon loadout results

All images copied to `games/hunyuan3d-lab/assets/` and embedded in vault pages via `![[image]]` syntax.

### 2. CharTurn Pipeline Improvements

**File:** `pipeline/foundry_gen_turnaround.py`

| Change | Before | After | Why |
|--------|--------|-------|-----|
| Default canvas | 1536x1024 | 2048x1024 | SDXL practical wide limit; panoramic beyond ~2M pixels degrades quality |
| Per-char canvas override | Not supported | `gen_width`/`gen_height` in config JSON | Wide creatures need more room |
| CharTurn LoRA strength | 0.70 | 0.55 | Looser figure packing, less bunching |
| Spacing prompts | None | "evenly spaced, wide gaps between figures, figures far apart, each figure clearly separated" | Encourage figure separation |
| Anti-bunching negatives | None | "overlapping figures, figures touching, cramped, bunched together" | Penalize tight packing |

**New char configs:** 12 files in `pipeline/chars/h3d_*.json` (6 body/feature subjects + 6 weapon variants).

### 3. MV-Adapter Installation

**Purpose:** Multi-view generation for non-humanoid creatures that defeat CharTurn's figure separation (winged demons, spread-silhouette creatures).

| Component | Location | Status |
|-----------|----------|--------|
| ComfyUI nodes | `ComfyUI-runtime/custom_nodes/ComfyUI-MVAdapter/` | Installed, 13 nodes verified |
| Model weights | `F:/AI-Models/HuggingFaceHub/models--huanngzh--mv-adapter/` | `mvadapter_i2mv_sdxl.safetensors` (3.4 GB) downloaded |
| Dependencies | scikit-image, opencv-python | Installed |
| xformers fix | `diffusers/models/attention_processor.py` | Patched try/except for cu130/Python 3.14 DLL load failure |

**Not yet tested end-to-end.** Nodes import correctly but no workflow has been run yet.

### 4. Obsidian Fix

Disabled the `homepage` plugin which was crashing the vault on load (`TypeError: Cannot read properties of undefined (reading 'data')`). Removed from `community-plugins.json`. Vault loads clean.

---

## Key Findings

### Body Type Viability (CharTurn + figure separation)

| Body Type | 1536x1024 | 2048x1024 | Verdict |
|-----------|:---------:|:---------:|---------|
| Humanoid (knight, lancer, mage) | 5 figures | 5 figures | **Works** at any canvas |
| Humanoid-insectoid (moth shaman) | 5 figures | — | **Works** — robed body carries it |
| Quadruped (dire wolf) | 2 figures | **4 figures** | **Works** with wider canvas |
| Arthropod (scorpion) | 1 figure | **5 figures** | **Works** with wider canvas |
| Winged spread (demon) | 1 figure | 1 figure | **Broken** — wings fill all gaps |

**Conclusion:** CharTurn handles everything except spread-wing characters. Wider canvas fixes quadrupeds and arthropods. MV-Adapter is the path forward for winged creatures.

### Weapon Variant Results (2560x1024, LoRA 0.7)

| Weapon | Figures | Notes |
|--------|:-------:|-------|
| Greatsword | 6 | Large weapon reads clearly |
| Battleaxe | 7 | Best separation |
| Sword & Shield | 3 | Shield merges views |
| Longbow | 5 | Bow visible as thin feature |
| Warhammer | 7 | Excellent |
| Dual Daggers | 6 | Daggers small but present |

### Known Issues in Generated Sheets

1. **Floating weapons** — weapons detach from hands in some views
2. **Overlapping figures** — adjacent figures sometimes bleed into each other
3. **Back view artifacts** — "back" crop is often 1-4px (crop artifact, not a real figure)
4. **Inconsistent occupancy** — figure sizes vary wildly across views (7% to 52%)
5. **LoRA density bias** — CharTurn packs figures at trained density regardless of canvas width

---

## Next Session: Priority Work

### P0: Hard Gates for Sheet Quality (30 min)

Add automated quality checks to `crop_figures_from_sheet()` that reject bad sheets before they enter the 3D pipeline.

**Gate 1 — Minimum figure count:**
```python
if len(figures) < 3:
    return QualityResult(passed=False, reason=f"Only {len(figures)} figures, need 3+")
```

**Gate 2 — Bounding box overlap:**
```python
# For each pair of figures, compute IoU of bounding boxes
# Reject if any pair overlaps > 15%
for i, j in combinations(range(len(figures)), 2):
    iou = bbox_iou(figures[i].bbox, figures[j].bbox)
    if iou > 0.15:
        return QualityResult(passed=False, reason=f"Figures {i},{j} overlap {iou:.0%}")
```

**Gate 3 — Size consistency:**
```python
# Reject if tallest figure is > 2x shortest
heights = [bbox[3] - bbox[1] for bbox in bboxes]
if max(heights) / min(heights) > 2.0:
    return QualityResult(passed=False, reason="Figure height variance too large")
```

**Gate 4 — Occupancy floor:**
```python
# Reject any figure under 5% occupancy (crop artifact)
for i, (bbox, img) in enumerate(figures):
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if w < 10 or h < 10:
        figures.pop(i)  # Silently discard artifacts
```

### P1: Multi-Candidate Generation (30 min)

Add `--candidates N` flag to `foundry_gen_turnaround`:

```bash
python -m pipeline.foundry_gen_turnaround \
  --config pipeline/chars/h3d_armored_knight.json \
  --candidates 3
```

Behavior:
1. Generate N turnaround sheets with seeds `[base_seed, base_seed+1, ..., base_seed+N-1]`
2. Run hard gates on each
3. Auto-score passing candidates (figure count, occupancy consistency, separation quality)
4. Pick the best, discard the rest
5. If none pass, flag for manual review

Cost: ~30s per candidate on RTX 5080. 3 candidates = ~90 seconds total.

This mirrors the existing Foundry pattern: `start_concept_batch` → `record_concept_candidates` → `lock_concept_pick`.

### P2: MV-Adapter Workflow for Winged Creatures

Build `pipeline/foundry_gen_mv_adapter.py`:
1. Generate single concept image with creature LoRA
2. Feed to MV-Adapter for 6-angle orbit views
3. Extract individual views for Hunyuan3D input
4. Test on winged demon (the one body type that still fails)

### P3: Push Through 3D Pipeline

Take the best turnaround sheets from this session and run them through Hunyuan3D shape → texture → 8-angle render. The real weapon/feature survival test happens in the 3D reconstruction, not the 2D turnaround.

---

## File Inventory

### New files in `sprite-foundry/`

```
pipeline/chars/h3d_armored_knight.json
pipeline/chars/h3d_dire_wolf.json
pipeline/chars/h3d_winged_demon.json
pipeline/chars/h3d_spear_lancer.json
pipeline/chars/h3d_scorpion_beast.json
pipeline/chars/h3d_moth_shaman.json
pipeline/chars/h3d_knight_greatsword.json
pipeline/chars/h3d_knight_battleaxe.json
pipeline/chars/h3d_knight_sword_shield.json
pipeline/chars/h3d_knight_bow.json
pipeline/chars/h3d_knight_hammer.json
pipeline/chars/h3d_knight_dual_daggers.json
STYLE-LAB-HANDOFF.md (this file)
```

### Modified files in `sprite-foundry/`

```
pipeline/foundry_gen_turnaround.py  — canvas, LoRA strength, prompts, per-char override
```

### New files in `forge-vault/`

```
games/hunyuan3d-lab/_index.md
games/hunyuan3d-lab/characters/armored-knight.md
games/hunyuan3d-lab/characters/dire-wolf.md
games/hunyuan3d-lab/characters/winged-demon.md
games/hunyuan3d-lab/characters/spear-lancer.md
games/hunyuan3d-lab/characters/scorpion-beast.md
games/hunyuan3d-lab/characters/moth-shaman.md
games/hunyuan3d-lab/experiments/body-type-variety.md
games/hunyuan3d-lab/experiments/thin-feature-survival.md
games/hunyuan3d-lab/experiments/pipeline-reference.md
games/hunyuan3d-lab/experiments/model-candidates.md
games/hunyuan3d-lab/experiments/weapon-variants.md
games/hunyuan3d-lab/assets/*.png  (turnaround sheets, contact sheets, sprite crops)
```

### System changes

```
C:\Users\mikey\AppData\Roaming\Python\Python314\site-packages\
  diffusers/models/attention_processor.py  — xformers try/except patch

F:\AI-Models\ComfyUI-runtime\custom_nodes\
  ComfyUI-MVAdapter/  — git cloned from huanngzh/ComfyUI-MVAdapter

F:\AI-Models\HuggingFaceHub\models--huanngzh--mv-adapter\
  mvadapter_i2mv_sdxl.safetensors  — 3.4 GB
```

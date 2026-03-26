---
title: Getting Started
description: Prerequisites and first run for Sprite Foundry.
---

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.11+ | CLI and pipeline scripts |
| ComfyUI | Latest | Sprite generation (runs locally) |
| Godot | 4.6 | Finish lab lighting verification |
| GPU | NVIDIA recommended | SDXL generation (RTX 5080 / 16 GB VRAM tested) |

## Clone and initialize

```bash
git clone https://github.com/mcp-tool-shop-org/sprite-foundry.git
cd sprite-foundry

# Initialize the SQLite registry
python -m foundry init
```

## Register your first subject

Each character starts as a **subject** — a named entity with a role and consumer tag.

```bash
python -m foundry subject-add sera_vale "Sera Vale" \
  --role crew \
  --consumer star-freight \
  --sheet preflight/subject-sheet.md
```

## Check pipeline status

```bash
python -m foundry status
```

This shows all subjects, their current lifecycle state, and any pending reviews.

## Generation

Generation runs through the `pipeline/` scripts, which call ComfyUI's local API:

1. `foundry_gen.py` — standard bipedal generation
2. `foundry_gen_morph.py` — morphology variants (arthropod, quadruped, winged)
3. `foundry_maps.py` — normal + depth map derivation
4. `foundry_finish.py` — Godot finish lab captures

## Review and export

```bash
# Review pending attempts
python -m foundry review-show <run_id>

# Accept all in a run
python -m foundry batch-accept <run_id>

# Export to deterministic pack
python -m foundry export <run_id>
```

## Verify

Run the full verification suite:

```bash
bash verify.sh
```

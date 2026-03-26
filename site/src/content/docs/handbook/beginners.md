---
title: For Beginners
description: New to Sprite Foundry? Start here for a gentle introduction.
sidebar:
  order: 99
---

## What is this tool?

Sprite Foundry is a local pipeline that turns character descriptions into game-ready sprite packs. You describe a character (name, role, visual notes), and Sprite Foundry drives an AI image generator (ComfyUI) to produce 8-direction pixel sprites — the kind of character art used in top-down RPGs. It then derives normal maps and depth maps from those sprites, verifies lighting quality in a Godot scene, and packages everything into a deterministic export with checksums and provenance metadata.

In plain terms: you go from "I need a crew member named Sera Vale" to a folder of 24 validated PNGs (8 albedo + 8 normal + 8 depth) that a game engine can load directly.

## Who is this for?

Sprite Foundry is built for:

- **Game developers** who need consistent 8-direction character sprites with lighting data
- **Solo devs and small teams** who want AI-assisted sprite generation with human review gates
- **Asset pipeline engineers** who care about reproducibility, checksums, and provenance tracking
- **Star Freight contributors** — Sprite Foundry is the canonical asset pipeline for the Star Freight game

You should be comfortable working in a terminal and running Python scripts. This is a developer tool, not a GUI application.

## Prerequisites

Before you start, make sure you have:

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| **Python** | 3.11+ | Used for the CLI and all pipeline scripts |
| **ComfyUI** | Latest | Must be running locally on `localhost:8188`. This is the AI image generator that produces the sprites |
| **Godot** | 4.6 | Used for the finish lab — a lighting verification scene that renders sprites under 4 lighting states |
| **NVIDIA GPU** | Recommended | SDXL generation is GPU-intensive. Tested on RTX 5080 (16 GB VRAM). CPU-only is technically possible but extremely slow |
| **Terminal skills** | Basic | You need to be comfortable with `cd`, `python`, and reading terminal output |
| **Git** | Any recent | For cloning the repository |

Optional but helpful:
- **Pillow** (Python library) — used for dimension checks during mechanical gates
- Familiarity with pixel art concepts (sprite sheets, normal maps, transparency)

## Your First 5 Minutes

**Step 1: Clone and initialize**

```bash
git clone https://github.com/mcp-tool-shop-org/sprite-foundry.git
cd sprite-foundry
python -m foundry init
```

This creates a SQLite database (`foundry.db`) that tracks every subject, run, attempt, and decision.

**Step 2: Register a subject**

A subject is a character that you want to generate sprites for. Each subject has an ID, display name, role, and consumer tag.

```bash
python -m foundry subject-add sera_vale "Sera Vale" \
  --role crew \
  --consumer star-freight
```

**Step 3: Check pipeline status**

```bash
python -m foundry status
```

This shows all registered subjects, their current lifecycle state, and any pending reviews. At this point you will see your new subject with no runs yet.

**Step 4: Understand the workflow**

The full pipeline runs in this order:

1. **Generate** — ComfyUI produces 8-direction sprites (requires ComfyUI running)
2. **Check** — Mechanical gates validate transparency, dimensions, direction count
3. **Review** — You accept or reject each attempt at three stages (raw, pixel, finish)
4. **Produce** — Derive normal + depth maps, then run Godot finish lab captures
5. **Export** — Package everything into a checksummed asset pack

Generation requires ComfyUI to be running. If you are just exploring the CLI and registry, steps 1-3 above are enough to get familiar with the tool.

**Step 5: Explore existing data**

If the repo already has export packs in the `exports/` directory, you can inspect them:

```bash
python -m foundry story sera_vale
python -m foundry drift
python -m foundry metrics
```

## Common Mistakes

**1. Running generation without ComfyUI**

The `pipeline/foundry_gen.py` script calls ComfyUI's local HTTP API on `localhost:8188`. If ComfyUI is not running, the generation will fail immediately. Start ComfyUI first, then run generation.

**2. Skipping the mechanical check**

After registering attempts, always run `python -m foundry check <run_id>` before reviewing. The mechanical gates catch dimension errors and transparency issues that are easy to miss visually. Attempting to review an unchecked run will leave it in an inconsistent state.

**3. Confusing runs and attempts**

A **run** is a generation batch for one subject. An **attempt** is a single direction (e.g., `front_left`) within that run. Commands like `batch-accept` operate on all attempts in a run, while `review-accept` targets a specific direction. Make sure you are passing the right ID to each command.

**4. Exporting before finish-lab acceptance**

The `export` command requires attempts to be in the `finish_accepted` state. If you try to export a run that has only been raw-accepted or pixel-accepted, the export will fail or produce incomplete packs. Use `python -m foundry status` to verify the lifecycle state before exporting.

**5. Editing the SQLite database directly**

The registry is append-only by design. Every decision (accept, reject, regen) is tracked with timestamps and provenance. Do not modify `foundry.db` with external SQL tools — use the CLI commands instead to maintain audit integrity.

## Next Steps

- [Getting Started](/sprite-foundry/handbook/getting-started/) — detailed prerequisites and setup walkthrough
- [Pipeline](/sprite-foundry/handbook/pipeline/) — how each of the 7 pipeline stages works
- [CLI Reference](/sprite-foundry/handbook/reference/) — full list of all 20+ commands with arguments and exit codes
- [Security](/sprite-foundry/handbook/security/) — threat model and what the tool does and does not touch

## Glossary

| Term | Definition |
|------|------------|
| **Subject** | A named character registered in the foundry (e.g., "Sera Vale"). Has an ID, display name, role, and consumer tag |
| **Run** | A generation batch for one subject. Produces 8 direction attempts |
| **Attempt** | One direction within a run (e.g., `front_left`). Goes through a 13-state lifecycle |
| **Mechanical gate** | Automated validation — checks transparency, dimensions (48x48), and direction count (8) |
| **Review stage** | Human decision point. Three stages: raw (shape/silhouette), pixel (clean pixel art), finish (lit renders) |
| **Normal map** | A texture encoding surface orientation, used by game engines for 2D lighting effects |
| **Depth map** | A texture encoding distance from camera, used for parallax and shadow effects |
| **Finish lab** | A Godot 4.6 scene that renders sprites under 4 lighting states to verify normal map quality |
| **Export pack** | The final output: albedo + normal + depth PNGs, a contact sheet, and a manifest.json with checksums |
| **Manifest** | A JSON file (`manifest.json`) in each export pack containing schema version, SHA-256 checksums, and full provenance |
| **Reject code** | A classification tag applied when rejecting an attempt (e.g., shape error, artifact, wrong pose) |
| **Regen** | Re-generation of a rejected attempt. The original is preserved; the new attempt links back via lineage |
| **Consumer** | The game or project that will use the exported sprites (e.g., `star-freight`) |
| **ControlNet** | An AI technique that guides image generation using reference images (depth maps, edge maps) for pose consistency |
| **LoRA** | A lightweight model adapter. Sprite Foundry uses `pixel-art-xl` LoRA to produce pixel art style output from SDXL |
| **Morphology** | Body plan classification for non-humanoid subjects: arthropod, quadruped, or winged |

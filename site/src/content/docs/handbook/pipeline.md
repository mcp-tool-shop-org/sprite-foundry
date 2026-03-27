---
title: Pipeline
description: How each stage of the Sprite Foundry pipeline works.
sidebar:
  order: 2
---

## Stage overview

```
Subject Sheet ──► Generation ──► Mechanical Gates ──► Review ──► Maps ──► Finish Lab ──► Export
```

## 1. Subject registration

Every character starts as a subject in the SQLite registry. Subjects have:

- **ID** — slug identifier (e.g., `sera_vale`)
- **Display name** — human-readable (e.g., "Sera Vale")
- **Role** — lane classification (crew, creature, hostile, authority, civilian)
- **Consumer** — which game consumes the output (e.g., `star-freight`)
- **Subject sheet** — design spec with pose, palette, and morphology notes

## 2. ComfyUI generation

The pipeline drives ComfyUI headlessly:

- **Model:** SDXL with pixel-art-xl LoRA
- **Control:** ControlNet Depth + Canny for pose consistency
- **Output:** 8 directions × 48px transparent PNGs
- **Morphology:** Body-class-specific ControlNet depth guides enforce non-humanoid body plans (see below)

Each generation creates a **run** — a batch of 8-direction **attempts**.

### Body class system

The `body_class` field in character configs auto-selects depth references and ControlNet parameters. Depth guides are joint-free primitives that lock in mass and orientation without dictating skeleton or limb placement.

| Body Class | Depth Strength | End % | Shape | Example Creatures |
|------------|---------------|-------|-------|-------------------|
| Humanoid | 0.60 | 85% | Upright bipedal | Sera Vale, Scav Raider |
| Arthropod | 0.55 | 80% | Flat wide, 6 legs | Skitter Drone |
| Quadruped | 0.65 | 90% | Horizontal, 4 legs | Cargo Beast, Drift Maw |
| Crouching Predator | 0.55 | 80% | Low-slung, ground-hugging | Drift Lurker |
| Winged | 0.55 | 90% | Digitigrade + wings (dual Depth+Canny) | Void Raptor |
| Amorphous | 0.35 | 65% | Irregular blob, no limbs | Rat King, Spore Mother |
| Wide/Squat | 0.40 | 70% | Short wide pillar | Grinning Idol |
| Tall/Thin | 0.40 | 70% | Narrow vertical column | Lantern Angler, Root Puppet |

Lower strength values give the model more creative freedom. Earlier end percentages release the guide sooner, allowing more detail variation in the final denoising steps. Monster body classes use lower values than humanoid because exotic shapes benefit from looseness.

## 3. Mechanical gates

Automated validation checks each attempt:

- **Dimension** — must be exactly 48x48
- **Alpha** — must have RGBA transparency
- **Corner transparency** — at least 3 of 4 corners must be transparent
- **Foreground content** — must contain visible subject (not empty)
- **Single subject** — foreground mass must be center-dominant (body-class-aware thresholds for wide creatures)

Failed attempts are tagged `mechanical_fail` and excluded from review. Wide body classes (amorphous, wide/squat, quadruped, arthropod) use relaxed single-subject thresholds because their mass naturally spreads across the frame.

## 4. Review workflow

Three review stages, each with accept/reject decisions:

| Stage | What's reviewed | Criteria |
|-------|----------------|----------|
| Raw | Source sprites | Shape, silhouette, pose correctness |
| Pixel | Pixelated output | Clean pixel art, no artifacts |
| Finish | Lit renders | Normal maps work under all 4 lighting states |

Rejected attempts get a **reject code** and optional regen. All decisions are append-only — nothing is ever deleted from the registry.

## 5. Normal + depth maps

For each accepted attempt, ComfyUI derives:

- **Normal maps** — surface orientation for 2D lighting
- **Depth maps** — z-distance for parallax and shadow effects

## 6. Godot finish lab

A Godot 4.6 scene renders each direction under 4 lighting states:

1. **Baseline** — flat ambient
2. **Moonlight** — directional blue
3. **Torch** — point warm light
4. **Moon + particles + depth** — full composite

This produces 32 captures per subject (4 states × 8 directions).

## 7. Export

`foundry export <run_id>` creates a deterministic asset pack:

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json
```

The manifest includes:
- `schema_version: "1.0.0"` (frozen contract)
- SHA-256 checksums for every file
- Full provenance (subject, run, review decisions)
- Pivot point (`center_bottom`)

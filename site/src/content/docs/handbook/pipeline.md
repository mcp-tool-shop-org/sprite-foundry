---
title: Pipeline
description: How each stage of the Sprite Foundry pipeline works.
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
- **Morphology:** For non-humanoid subjects, depth/edge reference images guide body shape (arthropod, quadruped, winged)

Each generation creates a **run** — a batch of 8-direction **attempts**.

## 3. Mechanical gates

Automated validation checks each attempt:

- Transparency check (must have alpha channel)
- Direction count (must be exactly 8)
- Dimension check (must be 48×48)
- Duplicate detection

Failed attempts are tagged `mechanical_fail` and excluded from review.

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

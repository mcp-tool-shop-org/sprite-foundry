# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-03-26

### Added

- **Foundry CLI** — 20 commands for subject registration, run tracking, review workflow, export, and analytics
- **SQLite Registry** — append-only lifecycle tracking with 13 states, reject codes, regen lineage, schema v2
- **ComfyUI Generation Pipeline** — SDXL + pixel-art-xl LoRA + ControlNet (Depth + Canny), 8-direction 48px sprites
- **Morphology System** — arthropod, quadruped, and winged body families via depth/edge reference images
- **Mechanical Gates** — automated validation (transparency, direction count, dimension checks)
- **Normal + Depth Map Generation** — ComfyUI-derived maps for each accepted direction
- **Godot Finish Lab** — 4 lighting states × 8 directions = 32 captures per subject
- **Deterministic Export** — `foundry export <run_id>` emits packs with SHA-256 checksums and manifest.json
- **Export Contract v1.0.0** — frozen: 8 dirs, 48×48 transparent PNG, albedo/normal/depth layers, center_bottom pivot
- **Roster Index** — `exports/roster_index.json` with lane breakdown and file counts
- **20 Production Export Packs** — 7 crew, 6 creature, 3 hostile, 2 authority, 2 civilian
- **Bakeoff System** — comparative evaluation of generation stacks (A/B/C)
- **Batch Review** — `batch-accept` and `batch-reject` for high-throughput review
- **Drift Analysis** — failure pattern detection and pass rates across runs
- **Story + Lineage** — full provenance trail from subject registration through export
- **Subject Sheets** — per-character design specs with pose, palette, and morphology notes

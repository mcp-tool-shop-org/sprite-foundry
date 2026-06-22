# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-06-22

Dogfood-swarm health pass (Stage A) + the Trellis ingest feature, plus a
5080 → 5090 retune. 62 findings audited; first test suite stood up (0 → 61).

### Added

- **Trellis ingest bridge** — `python -m pipeline.foundry_ingest --dir <render_dir> --subject <id>` registers an externally-rendered 8-direction sprite set (the `trellis-sprite-pipeline` output) into the foundry lifecycle, so `check` / review / `produce` / `export` work on it like a generated run
- **Test suite** — 61 tests (`tests/`): mechanical gate boundaries, atomic state transitions, real schema migration, lineage cycle guard, winner ranking, checksum determinism, CLI parity, and ingest integration
- **RTX 5090 retune** — `SPRITE_FOUNDRY_GEN_WIDTH` / `_GEN_HEIGHT` / `_BATCH_SIZE` env overrides (defaults unchanged); Godot resolved from `SPRITE_FOUNDRY_GODOT` / `GODOT4_BIN` / discovery

### Fixed

- Export now resolves the albedo from the gated registry artifact (not the bakeoff/ filesystem path) — an ungated/stale sprite can no longer ship under a valid checksum; manifest dimensions verified across all 8 directions (no silent 0,0)
- Real schema-migration dispatch (version no longer advances without its migration running); lineage cycle guard; atomic compare-and-set state transitions; transaction/rollback boundaries; closed leaked PIL file handles
- ComfyUI execution-status + reachability checks with timeouts (server errors no longer masquerade as extract failures); content-bbox crop replaces fixed truncation; morph lane uses deterministic green-screen chroma key
- Removed hardcoded `F:/` paths (Godot binary, Godot finish-lab exports dir) that broke on non-`F:` rigs
- CI now actually runs `verify.sh`; `exports/` + `.polyglot-cache.json` gitignored

### Changed

- Renamed internally from "Star Freight Foundry" to **Sprite Foundry**; docs reframed from Star-Freight-specific to a general 2.5D-RPG sprite factory; sprite packs published to npm under `@sprite-foundry`

## [1.1.0] - 2026-03-27

### Added

- **Monster Lane** — pipeline extension for non-humanoid sprites with 3 new body classes (amorphous, wide/squat, tall/thin)
- **Body Class Presets** — `body_class` field in character configs auto-selects depth refs, ControlNet strength, and timing
- **3 New Depth Ref Generators** — `gen_amorphous_depth.py`, `gen_wide_squat_depth.py`, `gen_tall_thin_depth.py`
- **Body-Class-Aware Gates** — `single_subject` gate uses relaxed thresholds for wide body classes
- **6 Beast Export Packs** — Rat King, Lantern Angler, Grinning Idol, Spore Mother, Root Puppet, Mud Revenant
- **`--body-class` CLI Flag** — override body class from command line for `foundry_gen_morph`

### Changed

- Roster expanded to 82 production packs (added townsfolk, goblin, hero, pirate, villain, zombie, and beast lanes)
- Background removal uses dual-corner sampling to handle ground planes
- Scene setting stripped from beast prompts for clean bg removal
- `run_all_gates` and `gate_single_subject` accept optional `body_class` parameter
- `cmd_check` auto-resolves body class from character config JSON

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

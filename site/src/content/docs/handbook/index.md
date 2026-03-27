---
title: Sprite Foundry Handbook
description: Complete reference for the Sprite Foundry asset pipeline.
sidebar:
  order: 0
---

Sprite Foundry is a headless sprite generation pipeline that produces game-ready 8-direction pixel sprites with normal and depth maps for [Star Freight](https://github.com/mcp-tool-shop-org/star-freight).

## What it does

1. **Generates** sprites via ComfyUI (SDXL + pixel-art-xl LoRA + ControlNet)
2. **Tracks** every generation through a 13-state lifecycle in SQLite
3. **Derives** normal and depth maps for accepted sprites
4. **Verifies** lighting quality in a Godot 4.6 finish lab
5. **Exports** deterministic asset packs with SHA-256 checksums

## Current roster

26 production export packs across 6 lanes:

| Lane | Count | Subjects |
|------|-------|----------|
| Crew | 7 | Sera Vale, Ilen Marr, Thal, Thal (Hazard Suit), Varek, Kael Morrow, Hull Diver |
| Creature | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Hostile | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Authority | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civilian | 2 | Nera Quill, Orryn Broker |
| Beast | 6 | Rat King, Lantern Angler, Grinning Idol, Spore Mother, Root Puppet, Mud Revenant |

## Next steps

- [Getting Started](/sprite-foundry/handbook/getting-started/) — prerequisites and first run
- [Pipeline](/sprite-foundry/handbook/pipeline/) — how each stage works
- [CLI Reference](/sprite-foundry/handbook/reference/) — all 20 commands
- [Security](/sprite-foundry/handbook/security/) — threat model and scope

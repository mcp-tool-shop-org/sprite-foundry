# Phase 7 Handoff — Star Freight Graphical Client

## What Was Built (Phases 1–6C)

Sprite Foundry is a complete character asset pipeline:

**Generation** → ComfyUI (SDXL + pixel-art-xl LoRA + ControlNet Depth/Canny) generates 8-direction pixel sprites at 48px with morphology control for non-humanoid body plans.

**Registry** → SQLite-backed lifecycle: generated → mechanical gates → raw review → pixel review → maps → finish review → finish_accepted. Append-only decisions, regen lineage, reject codes.

**Maps** → Normal maps + depth maps derived via ComfyUI for each accepted direction.

**Finish** → Godot 4.6 lighting lab renders 4 states (baseline, moonlight, torch, moon+particles+depth) per direction. 32 captures per subject.

**Export** → `foundry export <run_id>` emits deterministic packs:
```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, checksums, full provenance)
```

**Consumer** → Godot pack viewer loads packs unchanged, validates manifest, renders with CanvasTexture (albedo + normal), direction switching via keyboard, subject cycling.

**Roster** → 20 export packs, zero failures, zero contract edits:

| Lane | Count | Subjects |
|---|---|---|
| Crew | 7 | Sera Vale, Ilen Marr, Thal, Thal (Hazard Suit), Varek, Kael Morrow, Hull Diver |
| Creature | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Hostile | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Authority | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civilian | 2 | Nera Quill, Orryn Broker |

Roster index: `exports/roster_index.json`

---

## What Needs To Happen Next

### The Problem

Star Freight is currently a **Python TUI game** (Textual + Rich). All rendering is ASCII/Unicode text. There is no graphical rendering path. The 20 exported sprite packs have no consumer inside the actual game.

The foundry proved generation, export, and consumption in a Godot viewer. But the game itself cannot display sprites.

### The Solution: Build a Graphical Star Freight Client

This is not a rewrite. Star Freight's engine is clean — pure functions, dataclasses, separated logic from rendering. The engine (2168 tests) stays. The TUI stays as a mode. A graphical client consumes the same engine but renders sprites, maps, and visual UI instead of text panels.

### Phase 7A — Graphical Client Seed

**Goal:** A Godot 4.6 application that runs the Star Freight engine and renders characters using exported sprite packs.

**Architecture:**

```
star-freight/              (existing Python game)
├── src/portlight/engine/  ← game logic stays here, unchanged
├── src/portlight/content/ ← world data stays here
└── src/portlight/app/     ← TUI rendering stays here

star-freight-client/       (NEW Godot 4.6 project)
├── project.godot
├── assets/characters/     ← import from foundry exports
├── scripts/
│   ├── pack_loader.gd     ← reads manifest.json, loads albedo/normal/depth
│   ├── character_node.gd  ← Sprite2D + CanvasTexture, direction switching
│   └── engine_bridge.gd   ← calls Python engine (JSON-RPC, subprocess, or GDExtension)
└── scenes/
    ├── main.tscn
    ├── crew_screen.tscn   ← crew display with character sprites
    ├── combat_grid.tscn   ← 8×6 grid with sprite combatants
    └── encounter.tscn     ← multi-phase encounter with character portraits
```

**The hard problem is the engine bridge.** Star Freight's logic is Python. The graphical client is Godot (GDScript). Options:

1. **JSON-RPC subprocess** — Godot spawns Python process, sends commands, receives state as JSON. Cleanest separation. Latency acceptable for turn-based.
2. **Shared state file** — Python writes game state to JSON, Godot reads and renders. Simplest but crude.
3. **Port engine to GDScript** — Full rewrite. Loses 2168 tests. Not recommended unless going all-in on Godot.
4. **GDExtension (Rust/C++)** — Bridge layer. Over-engineered for this stage.

**Recommended: JSON-RPC subprocess.** The game is turn-based. Latency doesn't matter. Python engine stays authoritative. Godot is a rendering client.

**Minimum viable scope for 7A:**

- Godot project with pack loader (already proven in viewer)
- Engine bridge that can: start new game, get campaign state, advance turn
- One screen showing crew members with their sprites
- One screen showing combat grid with sprite combatants instead of ASCII letters
- Direction switching from movement on the grid

**What the pack loader already proves:**
- `pack_viewer.gd` and `pack_viewer_launcher.gd` in the foundry repo show exactly how to discover packs, read manifests, load textures, build CanvasTextures, and display directions. Copy this pattern.

### Phase 7B — Character Placement Slice

Once 7A works:

- Crew in a ship/station interior context (not just a list — a spatial scene)
- Hostile in an encounter approach context (captain portrait + faction identity)
- Creature in environmental context (drift lane hazard)

This proves the sprites work in actual game contexts, not just isolated display.

### Phase 7C — Full Visual Surface Pass

Map every TUI surface to a graphical equivalent:

| TUI Surface | Graphical Version |
|---|---|
| Dashboard (text stats) | Visual dashboard with character portraits, ship render |
| Crew tab (text grid) | Crew quarters scene with positioned sprites |
| Combat grid (ASCII) | Isometric or top-down grid with animated sprites |
| Market (text lists) | Market scene with NPC merchants |
| Station (text events) | Station arrival scene with port visuals |
| Encounter (text journal) | Visual encounter with character sprites + effects |

---

## Key Files and Locations

### Foundry (F:/AI/star-freight-foundry/)

| File | Purpose |
|---|---|
| `foundry/cli.py` | CLI including `export` command |
| `foundry/db.py` | Schema, lifecycle states, directions |
| `exports/` | 20 deterministic asset packs |
| `exports/roster_index.json` | Machine-readable roster inventory |
| `game/godot/render-lab/scripts/pack_viewer.gd` | **Reference implementation** for pack loading |
| `game/godot/render-lab/scripts/pack_viewer_launcher.gd` | Auto-discovery of export packs |
| `pipeline/foundry_gen.py` | Bipedal generation |
| `pipeline/foundry_gen_morph.py` | Morphology-controlled generation |
| `pipeline/foundry_maps.py` | Normal + depth map derivation |
| `pipeline/foundry_finish.py` | Godot finish capture pipeline |

### Star Freight Engine (F:/AI/star-freight/src/portlight/)

| File | Purpose |
|---|---|
| `engine/models.py` | Core data models (Officer, Ship, Combatant) |
| `engine/crew.py` | Crew binding spine |
| `engine/grid_combat.py` | 8×6 tactical grid combat |
| `engine/sf_campaign.py` | Campaign integration layer |
| `content/star_freight.py` | All world content |
| `app/sf_views.py` | Current TUI rendering (10 view functions) |
| `app/tui/screens/encounter.py` | Multi-phase encounter screen (712 lines) |
| `app/tui/screens/dashboard.py` | Root dashboard screen |

### Subject ↔ Game Entity Mapping

The 20 exported subjects map to Star Freight's world:

| Export Slug | Game Entity | Where It Appears |
|---|---|---|
| sera_vale | Compact Broker (crew) | Crew screen, station encounters |
| ilen_marr | Orryn Tech (crew) | Crew screen, tech events |
| thal | Keth Engineer (crew) | Crew screen, repair events |
| varek | Veshan Gunner (crew) | Crew screen, combat |
| kael_morrow | Human crew | Crew screen |
| hull_diver | EVA Specialist (crew) | Salvage events, hull repair |
| nera_quill | Compact Bureaucrat | Station authority encounters |
| compact_patrol | Patrol Officer | Security encounters, inspections |
| veshan_envoy | Diplomatic Authority | Faction encounters |
| orryn_broker | Civilian Merchant | Market, trade encounters |
| scav_raider | Hostile pirate | Combat encounters |
| reach_pirate | Hostile pirate (different faction) | Combat encounters |
| interdiction_agent | Elite hostile (institutional) | Inspection/interdiction encounters |
| cargo_beast | Pack animal | Cargo events, creature encounters |
| drift_maw | Predator | Lane hazard encounters |
| drift_lurker | Ambush predator | Lane hazard encounters |
| skitter_drone | Arthropod | Environmental encounters |
| void_raptor | Winged predator | Lane hazard encounters |
| keth_healer_drone | Medical drone | Medical events, Keth encounters |
| thal_hazard | Thal in EVA suit (variant) | Hazardous duty events |

---

## Export Contract (Frozen)

Do not modify unless runtime pain proves the contract is wrong.

- **Schema:** v1.0.0
- **Direction tokens:** front, front_left, left, back_left, back, back_right, right, front_right
- **Direction order:** canonical, same in every manifest
- **Pivot:** center_bottom
- **Transparency:** required (transparent PNG)
- **Sprite size:** 48×48 pixels
- **Layers:** albedo (required), normal (required), depth (required)
- **Checksums:** SHA-256 per file in manifest
- **Immutability:** exports/{slug}/{run_id}/ is append-only, never modified after creation

---

## What NOT To Do

- Do not rewrite the Python engine in GDScript
- Do not redesign the export contract
- Do not add animation systems before static character display works
- Do not build a "universal asset manager" — just read manifests
- Do not couple the graphical client to ComfyUI or the foundry pipeline
- Do not break the TUI — it stays as an alternate interface
- Do not touch the foundry unless the export contract is provably insufficient

---

## Prerequisites

- Godot 4.6.1 at `F:\AI\Godot\Godot_v4.6.1-stable_win64.exe`
- Python 3.14 (Star Freight engine)
- RTX 5080 16GB VRAM (ComfyUI for any new generation)
- ComfyUI runtime at `F:\AI-Models\ComfyUI-runtime`

## Strongest First Move

Create `F:/AI/star-freight-client/` as a new Godot 4.6 project. Copy the pack loader pattern from the foundry viewer. Build the JSON-RPC engine bridge. Get one screen showing crew members with their actual sprites. That proves the full chain: Python engine → bridge → Godot renderer → foundry export packs.

# Canon Batch 03 — Mixed Production

**Baseline:** Batch 02 complete (15 subjects, 128 finish-accepted, 512 captures, 84% yield)
**Date:** 2026-03-26
**Purpose:** Prove routine production breadth — no frontier R&D

## Batch Design

4 new subjects + 1 controlled variant. Tests:
- Identity-preserving outfit variant (Thal Hazard Suit)
- Command/hierarchy silhouette without gear crutches (Veshan House Envoy)
- Equipment-heavy occlusion (Hull Diver)
- Hostile class differentiation (Compact Interdiction Agent)
- Routine creature production (Drift Lurker — proven quadruped lane)

## Batch Order

| # | Subject | Config | Stack | Lane | Pressure Test |
|---|---------|--------|-------|------|---------------|
| 1 | Thal (Hazard Suit) | `thal_hazard.json` | A_v2 | Variant | Identity preservation through costume change |
| 2 | Veshan House Envoy | `veshan_envoy.json` | A_v2 | Bipedal command | Hierarchy via tailoring, no gear |
| 3 | Hull Diver | `hull_diver.json` | A_v2 | Bipedal EVA/utility | Helmet + backpack occlusion |
| 4 | Compact Interdiction Agent | `interdiction_agent.json` | A_v2 | Bipedal hostile | Must not collapse into patrol or pirate |
| 5 | Drift Lurker | `drift_lurker.json` | A_v2_morph (Depth) | Quadruped creature | Routine morph, lean predator vs pack animal |

## Commands — bipedal subjects (1-4)

```bash
# Register
python -m foundry.cli subject-add <id> --name "<Display Name>"

# Generate (ComfyUI must be running)
python -m pipeline.foundry_gen --config pipeline/chars/<config>.json

# Review + accept
python -m foundry.cli batch-accept <run_id> --stage raw
python -m foundry.cli batch-accept <run_id> --stage pixel

# Produce (maps + Godot finish)
python -m foundry.cli produce <run_id>

# Finish review
python -m foundry.cli finish-board <run_id>
python -m foundry.cli batch-accept <run_id> --stage finish
```

## Commands — creature subject (5: Drift Lurker)

```bash
# Depth refs already generated: pipeline/morph_refs/drift_lurker_depth/
# Register
python -m foundry.cli subject-add drift_lurker --name "Drift Lurker"

# Generate with morphology control
python -m pipeline.foundry_gen_morph \
  --config pipeline/chars/drift_lurker.json \
  --depth-refs pipeline/morph_refs/drift_lurker_depth

# Then same review/produce/finish flow as bipedal
```

## Anti-Drift Watch List

| Subject | Watch For | Ban |
|---------|-----------|-----|
| Thal (Hazard Suit) | Antennae + compound eyes must survive suit bulk | Fully sealed helmet hiding face |
| Veshan House Envoy | Must read as diplomatic, not military | ANY visible weapon, armor, patrol gear |
| Hull Diver | Backpack + helmet must hold as shape anchors | Sleek sci-fi armor, exposed face |
| Interdiction Agent | Must not collapse into patrol OR pirate | Duster coat, gorget trophy, rank bar, comm unit |
| Drift Lurker | Must read predator, not pack animal | Saddle, harness, barrel body mass, upright stance |

## Acceptance Targets

- 100% or near-first-pass on Thal variant
- High first-pass on Veshan Envoy and Hull Diver
- Clear visual separation between Interdiction Agent and Patrol/Pirate
- Drift Lurker produced with no special R&D handling
- Zero regens is the goal; 1-2 acceptable if justified

## Review Verdict — 2026-03-26

All 5 subjects **FINISH-ACCEPTED**. 1 full-run regen (Drift Lurker v1).

| # | Subject | Verdict | Regens | Run ID | Notes |
|---|---------|---------|--------|--------|-------|
| 1 | Thal (Hazard Suit) | Accept | 0 | thal_hazard_p3_20260326_151723 | Variant proof: identity survived costume change. Forward hunch, antennae, compound eyes all held through suit bulk. |
| 2 | Veshan House Envoy | Accept | 0 | veshan_envoy_p3_20260326_152433 | Command presence test passed. Slight naval-officer drift in shoulder detail, but remained non-military and on-brief. |
| 3 | Hull Diver | Accept | 0 | hull_diver_p3_20260326_152916 | Occlusion test passed. Helmet, welding pack, boots, gauntlets all survived rotation without collapsing. |
| 4 | Compact Interdiction Agent | Accept | 0 | interdiction_agent_p3_20260326_153314 | Hostile differentiation passed. Did not collapse into patrol, pirate, or envoy lanes. |
| 5 | Drift Lurker | Accept (v2) | 1 | drift_lurker_p5a_20260326_154405 | v1 rejected: body_plan_drift (bipedal collapse in 4-5 directions). v2 at CN strength 0.65/end 0.9 held quadruped. Right/front_left still weaker but family holds. |

**Batch totals:** 40/48 attempts accepted (83% yield), 1 full-run regen, 160 finish captures.

**Lessons:**
- Variant production works: Thal identity survived major costume change on first pass
- Command/authority silhouettes produce cleanly without gear crutches
- Equipment-heavy subjects (helmet + backpack) survive rotation — occlusion is not a blocker
- Hostile differentiation holds when subject sheets explicitly ban collapse lanes
- Quadruped morph lane needs CN strength ≥ 0.65 / end ≥ 0.9 for lean predators (0.55/0.8 was insufficient)
- Morph pipeline gradient backgrounds require gradient-aware bg removal (tolerance ~42)
- Multi-subject composition gate false-positives on wide horizontal creatures — needs creature-aware override

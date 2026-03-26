---
title: CLI Reference
description: All Sprite Foundry CLI commands.
---

All commands are invoked as `python -m foundry <command>`.

## Registry

| Command | Arguments | Description |
|---------|-----------|-------------|
| `init` | — | Initialize the SQLite registry |
| `subject-add` | `id name --role --consumer [--sheet]` | Register a new character subject |
| `register-run` | `run_id --subject` | Record a generation run |
| `register-attempt` | `run_id --direction --path` | Record an attempt within a run |

## Review

| Command | Arguments | Description |
|---------|-----------|-------------|
| `review-show` | `run_id` | Display the review queue |
| `review-accept` | `run_id --direction [--stage --note]` | Accept one attempt |
| `review-reject` | `run_id --direction --code [--stage --note]` | Reject one attempt |
| `batch-accept` | `run_id [--stage --note --reviewer]` | Accept all pending in a run |
| `batch-reject` | `run_id --code [--stage --note --reviewer]` | Reject all pending with one code |
| `regen` | `run_id --direction` | Queue regeneration for rejected attempts |
| `check` | `run_id` | Run mechanical validation gates |

## Analysis

| Command | Arguments | Description |
|---------|-----------|-------------|
| `status` | — | Pipeline status summary |
| `story` | `subject_id` | Full provenance narrative |
| `lineage` | `attempt_id` | Regen chain for one attempt |
| `winner` | `run_id [-v]` | Canonical winner per direction |
| `drift` | `[run_id]` | Failure patterns and pass rates |
| `metrics` | `[run_id]` | Throughput metrics |
| `attempt-detail` | `attempt_id` | Full lifecycle for one attempt |

## Production

| Command | Arguments | Description |
|---------|-----------|-------------|
| `produce` | `run_id` | One-command: maps + finish captures |
| `export` | `run_id [--overwrite]` | Export as deterministic asset pack |
| `finish-board` | `run_id` | Generate finish-lab comparison board |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | User error (bad arguments, missing subject) |
| 2 | Runtime error (ComfyUI unreachable, file I/O) |

## Lifecycle states

```
generated → mechanical_fail
          → mechanical_pass → raw_review_pending → raw_rejected
                                                 → raw_accepted → pixel_review_pending → rejected
                                                                                       → accepted → finish_review_pending → finish_rejected
                                                                                                                          → finish_accepted
                                                                                                  → superseded (by regen)
```

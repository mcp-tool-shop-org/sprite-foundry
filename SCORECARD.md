# Scorecard

> Score a repo before remediation. Fill this out first, then use SHIP_GATE.md to fix.

**Repo:** <!-- repo name -->
**Date:** <!-- YYYY-MM-DD -->
**Type tags:** <!-- [npm] [mcp] [cli] etc. -->

## Pre-Remediation Assessment

| Category | Score | Notes |
|----------|-------|-------|
| A. Security | /10 | |
| B. Error Handling | /10 | |
| C. Operator Docs | /10 | |
| D. Shipping Hygiene | /10 | |
| E. Identity (soft) | /10 | |
| **Overall** | **/50** | |

## Key Gaps

<!-- List the 3-5 most critical gaps that need fixing. Be specific. -->

1.
2.
3.

## Remediation Priority

<!-- What to fix first, second, third. Informed by the gaps above. -->

| Priority | Item | Estimated effort |
|----------|------|-----------------|
| 1 | | |
| 2 | | |
| 3 | | |

## Post-Remediation

<!-- Fill this out after applying SHIP_GATE.md -->

| Category | Before | After |
|----------|--------|-------|
| A. Security | /10 | /10 |
| B. Error Handling | /10 | /10 |
| C. Operator Docs | /10 | /10 |
| D. Shipping Hygiene | /10 | /10 |
| E. Identity (soft) | /10 | /10 |
| **Overall** | /50 | /50 |

---

## Addendum: `3d-prerender/` subsystem (2026-07-01)

> The scores above were filled in for `foundry/` (the SQLite lifecycle-tracking CLI) on 2026-03-26.
> `3d-prerender/` (the mesh → retexture → render sprite pipeline) is a separate subsystem within this
> repo that had never been through a health pass — its scorecard was blank until this dogfood swarm.
> Scored as its own addendum rather than overwriting the `foundry/` scores above, since the two
> subsystems have unrelated code, unrelated test suites, and unrelated risk surfaces.

**Repo:** mcp-tool-shop-org/sprite-foundry, `3d-prerender/` folder only
**Date:** 2026-07-01
**Type tags:** `[cli]` (thin argparse wrapper over GPU pipeline scripts)

### Pre/Post-Remediation Assessment (this swarm scored and remediated in one pass)

| Category | Before | After | Notes |
|----------|--------|-------|-------|
| A. Security | 5/10 | 8/10 | Before: repo-root threat model claimed "does not access the network," which was false for this subsystem (jury scripts send images to cloud vision APIs) — undocumented, not exploitable, but inaccurate. After: threat model corrected to name the cloud jury calls and the intentionally-broad (rig-wide, `SF_*`-overridable) file-write scope. Not 10/10 because broad file-write scope is by design for a local generation tool, not eliminated. |
| B. Error Handling | 3/10 | 8/10 | Before: 2 scripts used bare `sys.argv[1]` indexing with no `--help`; 3 GPU scripts had zero input validation before an expensive model load, and no CUDA-OOM handling/cleanup; one batch script aborted entirely on a single item's failure. After: argparse + real `--help` everywhere, path validation before GPU loads, OOM try/except with `torch.cuda.empty_cache()` cleanup, per-item batch resilience (one bad slug/seed no longer aborts the whole run). Not 10/10 — no formal structured error shape (code/message/hint), just clear print statements + exit codes. |
| C. Operator Docs | 2/10 | 9/10 | Before: README described a pipeline shape one generation stale (no retexture step at all); no CLI existed to document; hard-won production lessons lived only in a private Claude memory file. After: README rewritten around the current golden path, `cli.py --help` is accurate, and a dated "Pipeline Gotchas" section (symptom/root-cause/fix/reproduce) now carries the lessons in-repo. Not 10/10 — first pass, not yet battle-tested across multiple future characters/packs. |
| D. Shipping Hygiene | 1/10 | 8/10 | Before: `3d-prerender/**` wasn't even in `ci.yml`'s paths filter — zero automated checks ran on this folder, ever. 3 of the pipeline's own scripts weren't version-controlled at all (lived only in a third-party upstream clone). After: CI wired in and green (verified on `main`), `verify.sh` covers syntax, 73/73 tests pass (11 new pure-logic tests for the texture-patch math). Not 10/10 — the GPU-dependent stages (mesh/retexture/render) can never run in CI by nature (no GPU runner); that's an accepted, permanent gap, not a to-do. |
| E. Identity (soft) | 3/10 | 6/10 | Before: shared the repo's logo/translations/landing page but the shared logo URL itself was broken (missing `-org`). After: URL fixed. Deliberately NOT given its own translation set or landing page — `3d-prerender/README.md` is a subsystem engineering runbook, not the repo's public front door, and this folder isn't a separately-shipped product; applying the full product-identity gate here would be scope creep onto an internal pipeline doc. |
| **Overall** | **14/50** | **39/50** | |

### Key Gaps (addressed this swarm)
1. 3 of 9 pipeline scripts had no version control at all (lived only in a third-party upstream clone) — highest-priority gap, fixed.
2. CI never ran on this folder — fixed (`3d-prerender/**` + `tests/**` added to `ci.yml`'s paths filter).
3. Rig-specific paths hardcoded across 2 scripts, with 2 more constants (Ollama jury roster, submit-timeout) silently duplicated and able to drift — fixed via `config.py`.

### Remaining known gaps (not addressed this swarm, intentionally scoped out)
- No structured error shape (code/message/hint) — informal print+exit-code style throughout, consistent with the existing `foundry/` convention, not a regression.
- Color-desaturation root cause still open (see README Pipeline Gotchas) — a generation-quality investigation, not a shipping blocker.
- No dedicated translations/landing page for this subsystem — see Identity note above; deliberate scope call, revisit only if `3d-prerender/` ever becomes its own separately-shipped product.

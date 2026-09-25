# sprite-foundry: how it works

Mapped at 2026-09-25 from commit 347c92f.

## What this is

10 parts, mostly Python (65 files), GDScript (4), TypeScript (2) and JavaScript (1). Work enters through 3 doors; the busiest is CI, which reaches 4 parts. People run the game.

## What changed since the last map

This is the first map.

## What comes in

1. **CI.** On a pull request touching 11 paths; on a push touching 11 paths; or by hand. Runs 3d-prerender/test_texture_patch_region.py, foundry/__init__.py, foundry/cli.py and 2 more; checks CHANGELOG.md, LICENSE, README.md and 1 more.
2. **Deploy site to GitHub Pages.** On a push to main touching 2 paths; or by hand. Runs site/astro.config.mjs and site/src/.
3. **the game** (what Godot runs). Starts game/godot/render-lab/scenes/render_lab.tscn.

## What happens through CI

1. The workflow runs 3d-prerender/test_texture_patch_region.py in 3d-prerender, foundry/__init__.py, foundry/cli.py and foundry/db.py in foundry, and verify.sh in the repository root; it checks 4 files in the repository root.
2. That reaches pipeline (2 files).
3. It writes to game/godot/render-lab/scripts/auto_lab.gd.
4. It also writes to bakeoff/ and game/godot/render-lab/assets/, which are not tracked.

## Who reads the results

- **game/godot/render-lab/scripts/auto_lab.gd** is read by game/godot/render-lab/scenes/render_lab.tscn.

## The other doors

**Deploy site to GitHub Pages** runs site/astro.config.mjs and site/src/, and deploys the site.

**the game** (what Godot runs) starts game/godot/render-lab/scenes/render_lab.tscn.

## What breaks what

- **foundry** is imported by 2 parts (pipeline, the repository root), and by 1 more only from tests; it sits on the path of 1 door.
- **pipeline** is run as a child process by 1 part (foundry) and sits on the path of 1 door.

## What tends to change together

No two source files changed together often enough to name.

Window: 180 days; a pair counts from 3 shared commits, since 0 source files reach 10 revisions; the floor rises to 10 when 25 do.

## What no test touches

- **render-lab** is imported by no test.

11 test files run in no workflow: pipeline/test_hunyuan3d_shape.py, pipeline/test_hunyuan3d_texture.py, tests/test_cli_parser.py and 8 mores.

## Written but never read

Every written place has a reader.

## Helpers that look duplicated

These are candidates from names and call order, not a judgement.

- **build_parser** is exported by 3d-prerender/cli.py (3d-prerender) and foundry/cli.py (foundry); the two look alike.
- **main** is exported by 3d-prerender/cli.py (3d-prerender) and foundry/cli.py (foundry); the two look alike.

## Generated, never hand-edited

- **game/godot/render-lab/scripts/auto_lab.gd** is written by pipeline/foundry_finish.py.

## Hand-authored

People write .github/, pipeline/chars/, preflight/, the repository root and site/; 31 writes with paths built at run time may land here.

## Where to start

.github/workflows/ci.yml → foundry/cli.py → foundry/__init__.py

Read those in order to follow one pull request end to end.

## What this map cannot see

- 1 import could not be resolved: `tests/test_ingest.py` imports `pipeline`, which is no module on its import path and no declared dependency.
- 31 writes and 22 reads use paths built at run time and are not named here.
- 25 writes go to places this repository does not track, so they are not listed as generated.
- 14 writes and 6 reads go to a path their caller passes, not to this repository.
- Statistics confidence is low: fewer than 20 source files reach 10 revisions in the window.

Regenerate with `npx --yes @dogfood-lab/atlas map`.

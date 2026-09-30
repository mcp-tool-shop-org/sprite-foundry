# sprite-foundry: how it works

Mapped at 2026-09-30 from commit 45a5555 by Atlas 1.24.0.

## What this is

10 parts, mostly Python (65 files), GDScript (4), CSS (2), TypeScript (2), Astro (1), JavaScript (1) and shell (1). Work enters through 3 doors; the busiest is CI, which reaches 4 parts. It deploys a site to GitHub Pages. People run the Godot project.

## What changed since 2026-09-25 (347c92f)

- The Godot project (game/godot/render-lab/project.godot) is a new Godot project. It starts game/godot/render-lab/scenes/render_lab.tscn.
- the game (game/godot/render-lab/project.godot) is no longer a game.
- pipeline/morph_refs/* is now written by pipeline/morph_refs/gen_amorphous_depth.py, pipeline/morph_refs/gen_morph_matrix.py, pipeline/morph_refs/gen_tall_thin_depth.py and pipeline/morph_refs/gen_wide_squat_depth.py.
- pipeline/morph_refs/keth_healer_drone_depth/depth_ref_sheet.png is now written by pipeline/morph_refs/gen_keth_healer_drone.py.
- preflight/contact-sheet-placeholder.png is now written by preflight/gen_contact_sheet.py.
- preflight was authored and is now mixed.
- 1 file changed content, across 1 part.

## What comes in

1. **CI.** On a pull request touching 11 paths; on a push touching 11 paths; or by hand. Runs 3d-prerender/test_texture_patch_region.py, foundry/__init__.py, foundry/cli.py and 2 more; checks CHANGELOG.md, LICENSE, README.md and 1 more.
2. **Deploy site to GitHub Pages.** On a push to main touching 2 paths; or by hand. Runs site/astro.config.mjs and site/src/.
3. **the Godot project** (what Godot runs). Starts game/godot/render-lab/scenes/render_lab.tscn.

## What happens through CI

1. The workflow runs 3d-prerender/test_texture_patch_region.py in 3d-prerender, foundry/__init__.py, foundry/cli.py and foundry/db.py in foundry, and verify.sh in the repository root; it checks 4 files in the repository root.
2. That reaches pipeline (2 files).
3. It writes to game/godot/render-lab/scripts/auto_lab.gd.
4. It also writes to bakeoff/ and game/godot/render-lab/assets/, which are not tracked.

## Who reads the results

- **game/godot/render-lab/scripts/auto_lab.gd** is read by game/godot/render-lab/scenes/render_lab.tscn.

## The other doors

**Deploy site to GitHub Pages** runs site/astro.config.mjs and site/src/, and deploys the site.

**the Godot project** (what Godot runs) starts game/godot/render-lab/scenes/render_lab.tscn.

## What breaks what

- **foundry** is imported by 2 parts (pipeline, the repository root), and by 1 more only from tests; it sits on the path of 1 door.
- **pipeline** is run as a child process by 1 part (foundry) and sits on the path of 1 door.

## What tends to change together

No two source files changed together often enough to name.

Window: 180 days; a pair counts from 3 shared commits, since the window holds fewer than 30 qualifying commits.

## What no test touches

- **render-lab** is imported by no test.

9 test files run in no workflow: tests/test_cli_parser.py, tests/test_db_helpers.py, tests/test_db_lineage.py and 6 more.

## Written but never read

- **preflight/contact-sheet-placeholder.png** is written by preflight/gen_contact_sheet.py and read by nothing else in this repository.

## Helpers that look duplicated

These are candidates from names and call order, not a judgement.

- **build_parser** is exported by 3d-prerender/cli.py (3d-prerender) and foundry/cli.py (foundry); the two look alike.
- **main** is exported by 3d-prerender/cli.py (3d-prerender) and foundry/cli.py (foundry); the two look alike.

## Generated, never hand-edited

- **game/godot/render-lab/scripts/auto_lab.gd** is written by pipeline/foundry_finish.py.
- **preflight/contact-sheet-placeholder.png** is written by preflight/gen_contact_sheet.py.

## Hand-authored

People write .github/, pipeline/chars/, the repository root and site/; 15 writes with paths built at run time may land here.

## Where to start

.github/workflows/ci.yml → foundry/cli.py → foundry/mechanical.py → foundry/db.py

Read those in order to follow one pull request end to end.

## What this map cannot see

- 15 writes and 19 reads use paths built at run time and are not named here.
- 26 writes go to places this repository does not track, so they are not listed as generated.
- 16 writes and 9 reads go to a path their caller passes, not to this repository.
- 7 writes go to the directory the command is run in (bakeoff/) or a path their caller passes, not to this repository.
- Statistics confidence is low: fewer than 30 qualifying commits in the window, and fewer than 25 source files reach 10 revisions.

Regenerate with `npx --yes @dogfood-lab/atlas map`.

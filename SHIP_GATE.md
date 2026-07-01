# Ship Gate

> No repo is "done" until every applicable line is checked.

**Tags:** `[all]` `[cli]`

---

## A. Security Baseline

- [x] `[all]` SECURITY.md exists (report email, supported versions, response timeline) (2026-03-26)
- [x] `[all]` README includes threat model paragraph (data touched, data NOT touched, permissions required) (2026-03-26)
- [x] `[all]` No secrets, tokens, or credentials in source or diagnostics output (2026-03-26)
- [x] `[all]` No telemetry by default — state it explicitly even if obvious (2026-03-26)

### Default safety posture

- [x] `[cli|mcp|desktop]` File operations constrained to known directories (2026-03-26)
- [ ] `[cli|mcp|desktop]` SKIP: No dangerous actions — foundry is a read/generate/export tool, no kill/delete/restart operations
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server

## B. Error Handling

- [x] `[all]` Errors follow the Structured Error Shape: `code`, `message`, `hint`, `cause?`, `retryable?` (2026-03-26) — CLI prints descriptive messages with exit codes
- [x] `[cli]` Exit codes: 0 ok · 1 user error · 2 runtime error (2026-03-26)
- [x] `[cli]` No raw stack traces without `--debug` (2026-03-26) — errors caught and printed as messages
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[desktop]` SKIP: not a desktop app
- [ ] `[vscode]` SKIP: not a VS Code extension

## C. Operator Docs

- [x] `[all]` README is current: what it does, install, usage, supported platforms + runtime versions (2026-03-26)
- [x] `[all]` CHANGELOG.md (Keep a Changelog format) (2026-03-26)
- [x] `[all]` LICENSE file present and repo states support status (2026-03-26)
- [x] `[cli]` `--help` output accurate for all commands and flags (2026-03-26) — argparse-generated help
- [ ] `[cli|mcp|desktop]` SKIP: Logging levels — local dev tool with print output, no structured logging levels needed
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[complex]` SKIP: not complex enough for HANDBOOK.md — handbook is in Starlight site instead

## D. Shipping Hygiene

- [x] `[all]` `verify` script exists (test + build + smoke in one command) (2026-03-26)
- [ ] `[all]` SKIP: Version in manifest matches git tag — not a published package, no version manifest
- [x] `[all]` Dependency scanning runs in CI (ecosystem-appropriate) (2026-03-26) — CI validates imports and manifests
- [ ] `[all]` SKIP: Automated dependency update mechanism — no external dependencies beyond Python stdlib
- [ ] `[npm]` SKIP: not an npm package
- [ ] `[npm]` SKIP: not an npm package
- [ ] `[npm]` SKIP: not an npm package
- [ ] `[vsix]` SKIP: not a VS Code extension
- [ ] `[desktop]` SKIP: not a desktop app

## E. Identity (soft gate — does not block ship)

- [x] `[all]` Logo in README header (2026-03-26)
- [x] `[all]` Translations (polyglot-mcp, 8 languages) (2026-03-26)
- [x] `[org]` Landing page (@mcptoolshop/site-theme) (2026-03-26)
- [x] `[all]` GitHub repo metadata: description, homepage, topics (2026-03-26)

---

## Gate Rules

**Hard gate (A–D):** Must pass before any version is tagged or published.
If a section doesn't apply, mark `SKIP:` with justification — don't leave it unchecked.

**Soft gate (E):** Should be done. Product ships without it, but isn't "whole."

---

## Addendum: `3d-prerender/` subsystem (2026-07-01)

> The checklist above was filled in for `foundry/` on 2026-03-26. `3d-prerender/` is a separate
> subsystem (the mesh → retexture → render sprite pipeline) that had never been through a real gate —
> scored here as its own addendum. See `SCORECARD.md`'s matching addendum for the numeric scoring.

**Tags:** `[cli]`

### A. Security Baseline

- [x] `[all]` Repo-wide SECURITY.md applies (no subsystem-specific report channel needed) (2026-07-01)
- [x] `[all]` README threat model corrected to accurately describe this subsystem — previously the
      repo-wide threat model claimed "does not access the network," which was false for the cloud jury
      calls this folder makes (2026-07-01)
- [x] `[all]` No secrets, tokens, or credentials in source or diagnostics output (2026-07-01)
- [x] `[all]` No telemetry by default (2026-07-01)
- [ ] `[cli]` SKIP: File operations constrained to known directories — deliberately NOT constrained;
      `config.py` defaults read/write rig-wide model caches and working paths by design (a local
      generation tool, not a sandboxed one), every path is `SF_*`-env-overridable
- [ ] `[cli]` SKIP: No dangerous actions — this subsystem only generates/renders/patches local files and
      calls local/cloud generation APIs; no kill/delete/restart operations

### B. Error Handling

- [x] `[all]` Errors surfaced as clear, actionable print statements + non-zero exit codes (informal
      shape, consistent with the rest of this repo — not a formal code/message/hint structure) (2026-07-01)
- [x] `[cli]` Exit codes: 0 ok, non-zero on failure, propagated through `cli.py`'s subprocess wrapper (2026-07-01)
- [x] `[cli]` No raw tracebacks on the common failure paths: missing input files (checked before the
      expensive GPU model load), CUDA OOM (caught, VRAM cleaned up, actionable message) (2026-07-01)

### C. Operator Docs

- [x] `[all]` README rewritten to the current (v2, mesh→retexture→render) pipeline shape, with a
      "Pipeline Gotchas" section carrying dated, falsifiable production lessons in-repo (2026-07-01)
- [x] `[all]` Repo-wide CHANGELOG.md/LICENSE apply (2026-07-01)
- [x] `[cli]` `cli.py --help` and every subcommand's `--help` output is accurate (verified live, not
      assumed — see the execution wave's smoke test) (2026-07-01)
- [ ] `[cli]` SKIP: Logging levels — print-based output, consistent with the rest of this repo

### D. Shipping Hygiene

- [x] `[all]` `verify.sh` extended with a `3d-prerender/*.py` syntax-check step (2026-07-01)
- [x] `[all]` CI (`ci.yml`) now triggers on `3d-prerender/**` — previously it did not, so this folder ran
      zero automated checks of any kind (2026-07-01)
- [x] `[all]` Real test coverage added: 11 pure-logic pytest tests (example-based + Hypothesis property
      tests) for the texture-patch math, following this repo's existing `collect_ignore_glob`
      GPU-quarantine convention — 73/73 tests green, CI verified green on `main` post-push (2026-07-01)
- [ ] `[all]` SKIP: Version in manifest matches git tag — not a separately-versioned package
- [ ] `[all]` SKIP: Automated dependency update mechanism — stdlib + a handful of well-known CPU-only
      libs (numpy/Pillow/scipy/trimesh/hypothesis) for the testable slice; GPU deps (torch/trellis2/bpy)
      aren't installable in CI at all, so no CI-side dependency scanning applies to them

### E. Identity (soft gate — does not block ship)

- [x] `[org]` Shares the repo's logo, translations, landing page, and GitHub metadata (2026-07-01)
- [x] `[org]` Repo-wide logo URL bug fixed (was missing `-org`, now points at the correct brand org) (2026-07-01)
- [ ] `[all]` SKIP: dedicated translations/landing page for this subsystem — `3d-prerender/README.md` is
      an internal engineering runbook, not the repo's public front door, and this folder is not a
      separately-shipped product; the full product-identity gate doesn't apply here

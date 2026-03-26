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
- [ ] `[all]` Translations (polyglot-mcp, 8 languages)
- [ ] `[org]` Landing page (@mcptoolshop/site-theme)
- [ ] `[all]` GitHub repo metadata: description, homepage, topics

---

## Gate Rules

**Hard gate (A–D):** Must pass before any version is tagged or published.
If a section doesn't apply, mark `SKIP:` with justification — don't leave it unchecked.

**Soft gate (E):** Should be done. Product ships without it, but isn't "whole."

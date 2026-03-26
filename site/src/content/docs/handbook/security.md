---
title: Security
description: Threat model and security scope for Sprite Foundry.
sidebar:
  order: 5
---

## Scope

Sprite Foundry is a **local developer tool** — it runs entirely on the developer's machine and never communicates with external services.

## What it touches

| Resource | Access | Purpose |
|----------|--------|---------|
| Local PNG files | Read/Write | Sprite generation, map derivation, export |
| SQLite database | Read/Write | Lifecycle registry (foundry.db) |
| ComfyUI API | Localhost only | Headless sprite generation |
| Godot headless | Subprocess | Finish lab lighting verification |
| Filesystem | Constrained dirs | `exports/`, `bakeoff/`, `boards/`, `derived/` |

## What it does NOT touch

- No network egress (ComfyUI runs on localhost)
- No secrets, tokens, or credentials
- No telemetry — nothing is collected or sent
- No user data beyond the sprites themselves
- No cloud services or external APIs

## Subprocess safety

The only subprocesses spawned are:

1. **ComfyUI** — called via HTTP to `localhost:8188` (configurable)
2. **Godot headless** — spawned for finish lab captures with `--headless`

Both are local processes controlled by the developer.

## Reporting vulnerabilities

Email: **64996768+mcp-tool-shop@users.noreply.github.com**

| Action | Target |
|--------|--------|
| Acknowledge report | 48 hours |
| Assess severity | 7 days |
| Release fix | 30 days |

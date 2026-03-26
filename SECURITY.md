# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a Vulnerability

Email: **64996768+mcp-tool-shop@users.noreply.github.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Version affected
- Potential impact

### Response timeline

| Action | Target |
|--------|--------|
| Acknowledge report | 48 hours |
| Assess severity | 7 days |
| Release fix | 30 days |

## Scope

This tool operates **locally only** — it is a developer-facing asset pipeline, not a deployed service.

- **Data touched:** local PNG sprite files, SQLite registry (foundry.db), ComfyUI workflow JSON, Godot finish lab scenes
- **No network egress** — ComfyUI runs on localhost; no external API calls
- **No secrets handling** — does not read, store, or transmit credentials
- **No telemetry** is collected or sent
- **File operations** constrained to the foundry working directory (exports/, bakeoff/, boards/, derived/)
- **Subprocess calls** limited to ComfyUI local API and Godot headless rendering

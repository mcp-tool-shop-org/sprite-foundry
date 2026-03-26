<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.md">English</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop/brand/main/logos/sprite-foundry/readme.png" alt="Sprite Foundry" width="600">
</p>

<p align="center">
  <strong>Headless sprite generation pipeline for Star Freight</strong>
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/sprite-foundry/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/sprite-foundry/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://mcp-tool-shop.github.io/sprite-foundry/"><img src="https://img.shields.io/badge/docs-handbook-blue" alt="Handbook"></a>
</p>

---

Sprite Foundry es una herramienta de procesamiento de recursos que opera localmente y que genera, revisa y exporta sprites de píxeles de 8 direcciones, junto con mapas de normales y de profundidad. Utiliza ComfyUI para la generación, SQLite para el seguimiento del ciclo de vida y Godot 4.6 para la verificación de iluminación de finish-lab, todo controlado desde una única interfaz de línea de comandos (CLI).

## Arquitectura

```
Subject Sheet ──► ComfyUI Generation ──► Mechanical Gates
                  (SDXL + LoRA +          (transparency,
                   ControlNet)             dimensions, count)
                                                │
                                                ▼
                                        Raw/Pixel Review
                                                │
                                                ▼
                                    Normal + Depth Map Gen
                                                │
                                                ▼
                                     Godot Finish Lab
                                     (4 lighting states)
                                                │
                                                ▼
                                      Deterministic Export
                                      (manifest + checksums)
```

## Personajes

20 paquetes de exportación de producción, sin incumplimientos de contrato:

| Personaje | Número | Personajes |
|------|-------|----------|
| Tripulación | 7 | Sera Vale, Ilen Marr, Thal, Thal (Traje de Protección), Varek, Kael Morrow, Hull Diver |
| Criaturas | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Hostiles | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Autoridades | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civiles | 2 | Nera Quill, Orryn Broker |

## Contrato de exportación v1.0.0 (congelado)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 direcciones: frontal, frontal_izquierda, izquierda, trasero_izquierda, trasero, trasero_derecho, derecha, frontal_derecha
- PNG transparente de 48x48, punto de pivote en el centro_inferior
- Los consumidores validan `schema_version: "1.0.0"` antes de la carga

## Requisitos previos

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) ejecutándose localmente (para la generación)
- Godot 4.6 (para el renderizado de finish lab)
- GPU NVIDIA recomendada (RTX 5080 / 16 GB de VRAM probados)

## Inicio rápido

```bash
# Clone
git clone https://github.com/mcp-tool-shop-org/sprite-foundry.git
cd sprite-foundry

# Initialize the registry
python -m foundry init

# Register a subject
python -m foundry subject-add sera_vale "Sera Vale" --role crew --consumer star-freight

# Check the full pipeline status
python -m foundry status
```

## Comandos de la CLI

| Comando | Descripción |
|---------|-------------|
| `init` | Inicializa el registro SQLite de Sprite Foundry. |
| `subject-add` | Registra un nuevo personaje. |
| `register-run` | Registra una ejecución de generación de ComfyUI. |
| `register-attempt` | Registra un intento individual dentro de una ejecución. |
| `check` | Ejecuta las pruebas de validación mecánica. |
| `review-show` | Muestra la cola de revisión para una ejecución. |
| `review-accept` | Acepta un intento en la etapa de revisión actual. |
| `review-reject` | Rechaza un intento con un código de rechazo. |
| `batch-accept` | Acepta todos los intentos pendientes en una ejecución. |
| `batch-reject` | Rechaza todos los intentos pendientes en una ejecución con un código. |
| `regen` | Programa la regeneración de los intentos rechazados. |
| `attempt-detail` | Muestra el ciclo de vida completo de un intento. |
| `finish-board` | Genera una tabla de comparación de finish-lab. |
| `status` | Resumen del estado del proceso. |
| `story` | Narrativa completa del origen de un personaje. |
| `lineage` | Cadena de regeneración para un intento. |
| `winner` | Ganador canónico por dirección. |
| `drift` | Análisis de patrones de fallos y tasas de éxito. |
| `metrics` | Métricas de rendimiento (por ejecución o a nivel de Sprite Foundry). |
| `produce` | Un solo comando: mapas + capturas de finish para una ejecución aceptada. |
| `export` | Exporta una ejecución aceptada como un paquete de recursos determinista. |

## Modelo de amenazas

Sprite Foundry es una **herramienta para desarrolladores que opera localmente**. No:

- Accede a la red (ComfyUI se ejecuta en localhost).
- Maneja secretos, tokens o credenciales.
- Recopila o envía datos de telemetría.
- Escribe fuera de su propio directorio de trabajo.

Las operaciones de archivos están restringidas a `exports/`, `bakeoff/`, `boards/`, `derived/` y el registro SQLite. Las llamadas a subprocesos están limitadas a la API local de ComfyUI y al renderizado headless de Godot.

## Licencia

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://github.com/mcp-tool-shop-org">MCP Tool Shop</a>
</p>

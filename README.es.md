<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.md">English</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop/brand/main/logos/sprite-foundry/readme.png" alt="Sprite Foundry" width="600">
</p>

<p align="center">
  <strong>Headless, canon-bound sprite pipeline — 8-direction pixel-art packs for 2.5D RPGs</strong>
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/sprite-foundry/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/sprite-foundry/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://mcp-tool-shop-org.github.io/sprite-foundry/"><img src="https://img.shields.io/badge/docs-handbook-blue" alt="Handbook"></a>
</p>

---

Sprite Foundry es un sistema de procesamiento de recursos exclusivo para uso local que genera, revisa y exporta sprites de píxeles con 8 direcciones, junto con mapas de normales y de profundidad. Utiliza ComfyUI para la generación con control de morfología mediante ControlNet (8 clases de cuerpo), SQLite para el seguimiento del ciclo de vida y Godot 4.6 para la verificación final de la iluminación; todo esto se controla desde una única interfaz de línea de comandos (CLI).

> **Los paquetes de sprites que produce esta fábrica se publican en npm** bajo el ámbito `@sprite-foundry`, a partir del repositorio monorepo [sprite-foundry-packs](https://github.com/mcp-tool-shop-org/sprite-foundry-packs). Este repositorio es la fábrica; ese otro repositorio es la tienda.

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

## Listado

92 paquetes de exportación para producción, distribuidos en 12 categorías:

| Categoría | Cantidad | Sujetos |
|------|-------|----------|
| Bestia | 16 | Bell Warden, Bone Weaver, Clock Golem, Grinning Idol, Hive Keeper, Hollow Knight, Ink Shade, Lantern Angler, Mirror Stalker, Mud Revenant, Rat King, Root Puppet, Spore Mother, Teeth Collector, Throat Singer, Wyvern |
| Habitantes del pueblo | 16 | Barmaid, Beggar, Blacksmith, Child, Elder, Farmer, Fisherman, Guard, Herbalist, Innkeeper, Lamplighter, Merchant, Minstrel, Noble, Scribe, Stable Hand |
| Duende | 8 | Archer, Bomber, Brute, Grunt, Scout, Shaman, Warchief, Wolf Rider |
| Héroe | 8 | Barbarian, Cleric, Fighter, Mage, Monk, Paladin, Ranger, Rogue |
| Pirata | 8 | Captain, Cutthroat, Drowned, Governor, Navy Sailor, Pistoleer, Quartermaster, Sea Priest |
| Villano | 8 | Assassin, Blackguard, Cult Priest, Dark Monk, Dread Ranger, Necromancer, Reaver, Warlord |
| Zombi | 8 | Bloater, Elite, Hazmat, Riot, Runner, Shambler, Skeletal, Worker |
| Criatura | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Tripulación | 7 | Sera Vale, Ilen Marr, Thal, Thal (Hazard Suit), Varek, Kael Morrow, Hull Diver |
| Hostil | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Autoridad | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civil | 2 | Nera Quill, Orryn Broker |

## Categoría de monstruos

Las criaturas no humanoides utilizan guías de profundidad específicas para cada clase de cuerpo en lugar del esqueleto humanoide estándar. Cada clase de cuerpo tiene su propia silueta de referencia de profundidad, intensidad de ControlNet y parámetros de temporización.

| Clase de cuerpo | Intensidad de la profundidad | Porcentaje final | Criaturas |
|------------|---------------|-------|-----------|
| Amorfa | 0.35 | 65% | Rat King, Spore Mother, Mud Revenant |
| Ancha/Baja | 0.40 | 70% | Grinning Idol |
| Alta/Delgada | 0.40 | 70% | Lantern Angler, Root Puppet |

Las guías de profundidad son primitivas sin uniones (blobs, pilares, columnas) que fijan la masa y la orientación sin dictar la colocación del esqueleto o las extremidades. El campo `body_class` en las configuraciones de los personajes selecciona automáticamente el preajuste correcto:

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## Contrato de exportación v1.0.0 (estable)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 direcciones: frontal, frontal izquierda, izquierda, trasera izquierda, trasera, trasera derecha, derecha, frontal derecha
- PNG transparente de 48×48, pivote en la parte inferior central
- Los consumidores validan `schema_version: "1.0.0"` antes de cargar

## Requisitos previos

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) en ejecución localmente (para la generación)
- Godot 4.6 (para el renderizado final)
- Se recomienda una GPU NVIDIA (se probó RTX 5090 / 32 GB; mínimo de 16 GB)

## Inicio rápido

```bash
# Clone
git clone https://github.com/mcp-tool-shop-org/sprite-foundry.git
cd sprite-foundry

# Initialize the registry
python -m foundry init

# Register a subject
python -m foundry subject-add sera_vale "Sera Vale" --role crew --consumer my-game

# Check the full pipeline status
python -m foundry status
```

## Comandos de la CLI

| Comando | Descripción |
|---------|-------------|
| `init` | Inicializar el registro SQLite de la fábrica |
| `subject-add` | Registrar un nuevo sujeto de personaje |
| `register-run` | Registrar una ejecución de generación de ComfyUI |
| `register-attempt` | Registrar un intento individual dentro de una ejecución |
| `check` | Ejecutar las comprobaciones de validación mecánica |
| `review-show` | Mostrar la cola de revisión para una ejecución |
| `review-accept` | Aceptar un intento en la etapa actual de revisión |
| `review-reject` | Rechazar un intento con un código de rechazo |
| `batch-accept` | Aceptar todos los intentos pendientes en una ejecución |
| `batch-reject` | Rechazar todos los intentos pendientes en una ejecución con un solo código |
| `regen` | Poner en cola la regeneración para los intentos rechazados |
| `attempt-detail` | Mostrar el ciclo de vida completo de un intento |
| `finish-board` | Generar un panel de comparación final |
| `status` | Resumen del estado del proceso |
| `story` | Narrativa completa del origen para un sujeto |
| `lineage` | Regenerar la cadena para un intento |
| `winner` | Ganador canónico por dirección |
| `drift` | Análisis de patrones de fallos y tasas de éxito |
| `metrics` | Métricas de rendimiento (por ejecución o a nivel de toda la fábrica) |
| `produce` | Un solo comando: mapas + capturas finales para una ejecución aceptada |
| `export` | Exportar una ejecución aceptada en la etapa final como un paquete de recursos determinista |

## Modelo de amenazas

Sprite Foundry es una **herramienta de desarrollo local**. No:

- Accede a la red (ComfyUI se ejecuta en localhost)
- Gestiona secretos, tokens o credenciales
- Recopila o envía datos de telemetría
- Escribe fuera de su propio directorio de trabajo

Las operaciones de archivo se limitan a `exports/`, `bakeoff/`, `boards/`, `derived/` y el registro SQLite. Las llamadas a subprocesos se limitan a la API local de ComfyUI y al renderizado sin cabeza de Godot.

## Licencia

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

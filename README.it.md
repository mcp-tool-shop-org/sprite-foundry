<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.md">English</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Sprite Foundry è un sistema di gestione delle risorse locale che genera, revisiona ed esporta sprite pixelati a 8 direzioni, con mappe di normali e di profondità. Utilizza ComfyUI per la generazione, SQLite per il tracciamento del ciclo di vita e Godot 4.6 per la verifica dell'illuminazione tramite finish-lab, il tutto controllato da un'unica interfaccia a riga di comando (CLI).

## Architettura

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

## Elenco

20 pacchetti di esportazione per la produzione, zero violazioni contrattuali:

| Personaggio | Numero | Soggetti |
|------|-------|----------|
| Equipaggio | 7 | Sera Vale, Ilen Marr, Thal, Thal (Tuta Protettiva), Varek, Kael Morrow, Hull Diver |
| Creature | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Ostili | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Autorità | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civili | 2 | Nera Quill, Orryn Broker |

## Contratto di esportazione v1.0.0 (congelato)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 direzioni: fronte, fronte_sinistra, sinistra, retro_sinistra, retro, retro_destra, destra, fronte_destra
- PNG trasparente 48x48, punto di rotazione al centro-inferiore
- I client verificano `schema_version: "1.0.0"` prima del caricamento

## Prerequisiti

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) in esecuzione localmente (per la generazione)
- Godot 4.6 (per il rendering finish lab)
- GPU NVIDIA consigliata (RTX 5080 / 16 GB di VRAM testati)

## Guida rapida

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

## Comandi CLI

| Comando | Descrizione |
|---------|-------------|
| `init` | Inizializza il registro SQLite di Sprite Foundry |
| `subject-add` | Registra un nuovo soggetto personaggio |
| `register-run` | Registra un'esecuzione di generazione ComfyUI |
| `register-attempt` | Registra un tentativo singolo all'interno di un'esecuzione |
| `check` | Esegue i controlli di validazione meccanica |
| `review-show` | Mostra la coda di revisione per un'esecuzione |
| `review-accept` | Accetta un tentativo nella fase di revisione corrente |
| `review-reject` | Rifiuta un tentativo con un codice di rifiuto |
| `batch-accept` | Accetta tutti i tentativi in sospeso in un'esecuzione |
| `batch-reject` | Rifiuta tutti i tentativi in sospeso in un'esecuzione con un unico codice |
| `regen` | Avvia la rigenerazione per i tentativi rifiutati |
| `attempt-detail` | Mostra il ciclo di vita completo per un tentativo |
| `finish-board` | Genera una scheda di confronto finish-lab |
| `status` | Riepilogo dello stato della pipeline |
| `story` | Descrizione completa della provenienza per un soggetto |
| `lineage` | Catena di rigenerazione per un tentativo |
| `winner` | Vincitore canonico per direzione |
| `drift` | Analisi dei modelli di errore e tassi di successo |
| `metrics` | Metriche di produttività (per esecuzione o a livello di Sprite Foundry) |
| `produce` | Un unico comando: mappe + acquisizioni finish per un'esecuzione accettata |
| `export` | Esporta un'esecuzione accettata come pacchetto di risorse deterministico |

## Modello di minaccia

Sprite Foundry è uno **strumento per sviluppatori locale**. Non:

- Accede alla rete (ComfyUI viene eseguito su localhost)
- Gestisce segreti, token o credenziali
- Raccoglie o invia dati di telemetria
- Scrive al di fuori della propria directory di lavoro

Le operazioni sui file sono limitate a `exports/`, `bakeoff/`, `boards/`, `derived/` e al registro SQLite. Le chiamate a sottoprocessi sono limitate all'API locale di ComfyUI e al rendering headless di Godot.

## Licenza

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://github.com/mcp-tool-shop-org">MCP Tool Shop</a>
</p>

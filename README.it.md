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

Sprite Foundry è un sistema di gestione delle risorse locale che genera, revisiona ed esporta sprite pixelati a 8 direzioni, con normal map e depth map. Utilizza ComfyUI per la generazione, con il controllo morfologico di ControlNet (8 classi di corpi), SQLite per il tracciamento del ciclo di vita e Godot 4.6 per la verifica dell'illuminazione di finish-lab, il tutto controllato da un'unica interfaccia a riga di comando (CLI).

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

92 pacchetti di esportazione per la produzione, suddivisi in 12 categorie:

| Categoria | Numero | Soggetti |
|------|-------|----------|
| Bestie | 16 | Bell Warden, Bone Weaver, Clock Golem, Grinning Idol, Hive Keeper, Hollow Knight, Ink Shade, Lantern Angler, Mirror Stalker, Mud Revenant, Rat King, Root Puppet, Spore Mother, Teeth Collector, Throat Singer, Wyvern |
| Abitanti | 16 | Barmaid, Beggar, Blacksmith, Child, Elder, Farmer, Fisherman, Guard, Herbalist, Innkeeper, Lamplighter, Merchant, Minstrel, Noble, Scribe, Stable Hand |
| Goblin | 8 | Archer, Bomber, Brute, Grunt, Scout, Shaman, Warchief, Wolf Rider |
| Eroe | 8 | Barbarian, Cleric, Fighter, Mage, Monk, Paladin, Ranger, Rogue |
| Pirata | 8 | Captain, Cutthroat, Drowned, Governor, Navy Sailor, Pistoleer, Quartermaster, Sea Priest |
| Antagonista | 8 | Assassin, Blackguard, Cult Priest, Dark Monk, Dread Ranger, Necromancer, Reaver, Warlord |
| Zombie | 8 | Bloater, Elite, Hazmat, Riot, Runner, Shambler, Skeletal, Worker |
| Creatura | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Equipaggio | 7 | Sera Vale, Ilen Marr, Thal, Thal (Hazard Suit), Varek, Kael Morrow, Hull Diver |
| Ostile | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Autorità | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civile | 2 | Nera Quill, Orryn Broker |

## Creature Lane (Categoria Creature)

Le creature non umanoidi utilizzano guide di profondità specifiche per la classe di corpo invece dello scheletro umanoide standard. Ogni classe di corpo ha il proprio riferimento di profondità, la forza di ControlNet e i parametri di temporizzazione.

| Classe di Corpo | Forza di Profondità | Percentuale Finale | Creature |
|------------|---------------|-------|-----------|
| Amorphous (Senza forma definita) | 0.35 | 65% | Rat King, Spore Mother, Mud Revenant |
| Wide/Squat (Ampio/Accovacciato) | 0.40 | 70% | Grinning Idol |
| Tall/Thin (Alto/Sottile) | 0.40 | 70% | Lantern Angler, Root Puppet |

Le guide di profondità sono primitive prive di giunture (blob, pilastri, colonne) che fissano la massa e l'orientamento senza definire la posizione dello scheletro o degli arti. Il campo `body_class` nelle configurazioni dei personaggi seleziona automaticamente la configurazione corretta:

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## Contratto di Esportazione v1.0.0 (congelato)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 direzioni: fronte, fronte_sinistra, sinistra, retro_sinistra, retro, retro_destra, destra, fronte_destra
- Immagine PNG trasparente 48x48, pivot al centro-inferiore
- I programmi di consumo validano `schema_version: "1.0.0"` prima del caricamento

## Prerequisiti

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) in esecuzione localmente (per la generazione)
- Godot 4.6 (per il rendering di finish lab)
- GPU NVIDIA consigliata (RTX 5080 / 16 GB di VRAM testati)

## Guida Rapida

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
| `register-attempt` | Registra un tentativo individuale all'interno di un'esecuzione |
| `check` | Esegue controlli di validazione meccanici |
| `review-show` | Visualizza la coda di revisione per un'esecuzione |
| `review-accept` | Accetta un tentativo nella fase di revisione corrente |
| `review-reject` | Rifiuta un tentativo con un codice di rifiuto. |
| `batch-accept` | Accetta tutti i tentativi in sospeso in una singola esecuzione. |
| `batch-reject` | Rifiuta tutti i tentativi in sospeso in una singola esecuzione, utilizzando un unico codice. |
| `regen` | Rigenera la coda per i tentativi rifiutati. |
| `attempt-detail` | Mostra l'intero ciclo di vita di un singolo tentativo. |
| `finish-board` | Genera una tabella di confronto tra le fasi di completamento. |
| `status` | Riepilogo dello stato della pipeline. |
| `story` | Descrizione completa della provenienza per un determinato elemento. |
| `lineage` | Catena di rigenerazione per un tentativo. |
| `winner` | Vincitore canonico per ogni direzione. |
| `drift` | Analisi dei modelli di errore e tassi di successo. |
| `metrics` | Metriche di produttività (per esecuzione o a livello di tutta la fonderia). |
| `produce` | Un singolo comando: mappa e acquisizioni di immagini di completamento per un'esecuzione accettata. |
| `export` | Esporta un'esecuzione con completamento accettato come pacchetto di risorse deterministico. |

## Modello delle minacce

Sprite Foundry è uno **strumento per sviluppatori locale**. Non:

- Accede alla rete (ComfyUI funziona in locale).
- Gestisce segreti, token o credenziali.
- Raccoglie o invia dati di telemetria.
- Scrive al di fuori della propria directory di lavoro.

Le operazioni sui file sono limitate alle directory `exports/`, `bakeoff/`, `boards/`, `derived/` e al registro SQLite. Le chiamate a processi secondari sono limitate all'API locale di ComfyUI e al rendering headless di Godot.

## Licenza

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

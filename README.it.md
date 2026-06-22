<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.md">English</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Sprite Foundry è una pipeline di asset locale che genera, esamina ed esporta sprite pixelati a 8 direzioni con mappe di normali e profondità. Gestisce ComfyUI per la generazione con controllo della morfologia tramite ControlNet (8 classi di corpi), SQLite per il tracciamento del ciclo di vita e Godot 4.6 per la verifica dell'illuminazione nella fase finale, tutto controllato da un'unica interfaccia a riga di comando (CLI).

> **I pacchetti di sprite prodotti da questa fabbrica vengono pubblicati su npm** all'interno dello spazio `@sprite-foundry`, dal monorepository [sprite-foundry-packs](https://github.com/mcp-tool-shop-org/sprite-foundry-packs). Questo repository è la fabbrica; quell'altro repository è il negozio.

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

| Categoria | Conteggio | Soggetti |
|------|-------|----------|
| Bestia | 16 | Bell Warden, Bone Weaver, Clock Golem, Grinning Idol, Hive Keeper, Hollow Knight, Ink Shade, Lantern Angler, Mirror Stalker, Mud Revenant, Rat King, Root Puppet, Spore Mother, Teeth Collector, Throat Singer, Wyvern |
| Abitanti della città | 16 | Barmaid, Beggar, Blacksmith, Child, Elder, Farmer, Fisherman, Guard, Herbalist, Innkeeper, Lamplighter, Merchant, Minstrel, Noble, Scribe, Stable Hand |
| Goblin | 8 | Archer, Bomber, Brute, Grunt, Scout, Shaman, Warchief, Wolf Rider |
| Eroe | 8 | Barbarian, Cleric, Fighter, Mage, Monk, Paladin, Ranger, Rogue |
| Pirata | 8 | Captain, Cutthroat, Drowned, Governor, Navy Sailor, Pistoleer, Quartermaster, Sea Priest |
| Cattivo | 8 | Assassin, Blackguard, Cult Priest, Dark Monk, Dread Ranger, Necromancer, Reaver, Warlord |
| Zombie | 8 | Bloater, Elite, Hazmat, Riot, Runner, Shambler, Skeletal, Worker |
| Creatura | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Equipaggio | 7 | Sera Vale, Ilen Marr, Thal, Thal (Hazard Suit), Varek, Kael Morrow, Hull Diver |
| Ostile | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Autorità | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civile | 2 | Nera Quill, Orryn Broker |

## Categoria Mostro

Le creature non umanoidi utilizzano guide di profondità specifiche per la classe del corpo tramite ControlNet invece dello scheletro umanoide standard. Ogni classe di corpo ha il proprio riferimento di silhouette, l'intensità di ControlNet e i parametri temporali.

| Classe del Corpo | Intensità della Profondità | Percentuale Finale | Creature |
|------------|---------------|-------|-----------|
| Amorfa | 0.35 | 65% | Rat King, Spore Mother, Mud Revenant |
| Larga/Tozza | 0.40 | 70% | Grinning Idol |
| Alta/Sottile | 0.40 | 70% | Lantern Angler, Root Puppet |

Le guide di profondità sono primitive senza giunti (blob, pilastri, colonne) che fissano la massa e l'orientamento senza dettare il posizionamento dello scheletro o degli arti. Il campo `body_class` nelle configurazioni dei personaggi seleziona automaticamente il preset corretto:

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

- 8 direzioni: frontale, frontale sinistra, sinistra, posteriore sinistra, posteriore, posteriore destra, destra, frontale destra
- PNG trasparente 48×48, pivot in basso al centro
- I consumatori convalidano `schema_version: "1.0.0"` prima del caricamento

## Prerequisiti

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) in esecuzione localmente (per la generazione)
- Godot 4.6 (per il rendering nella fase finale)
- NVIDIA GPU consigliata (testato RTX 5090 / 32 GB; minimo 16 GB)

## Avvio Rapido

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

## Comandi CLI

| Comando | Descrizione |
|---------|-------------|
| `init` | Inizializza il registro SQLite della fabbrica |
| `subject-add` | Registra un nuovo soggetto personaggio |
| `register-run` | Registra una sessione di generazione ComfyUI |
| `register-attempt` | Registra un tentativo individuale all'interno di una sessione |
| `check` | Esegue i controlli di validazione meccanica |
| `review-show` | Visualizza la coda di revisione per una sessione |
| `review-accept` | Accetta un tentativo nella fase di revisione corrente |
| `review-reject` | Rifiuta un tentativo con un codice di rifiuto |
| `batch-accept` | Accetta tutti i tentativi in sospeso in una sessione |
| `batch-reject` | Rifiuta tutti i tentativi in sospeso in una sessione con un unico codice |
| `regen` | Metti in coda la rigenerazione per i tentativi rifiutati |
| `attempt-detail` | Mostra il ciclo di vita completo per un tentativo |
| `finish-board` | Genera una scheda di confronto per la fase finale |
| `status` | Riepilogo dello stato della pipeline |
| `story` | Racconto completo della provenienza per un soggetto |
| `lineage` | Rigenera la catena per un tentativo |
| `winner` | Vincitore canonico per direzione |
| `drift` | Analisi dei modelli di errore e tassi di successo |
| `metrics` | Metriche di produttività (per sessione o a livello di fabbrica) |
| `produce` | Comando singolo: mappe + acquisizioni della fase finale per una sessione accettata |
| `export` | Esporta una sessione accettata nella fase finale come pacchetto di asset deterministico |

## Modello di Minaccia

Sprite Foundry è uno **strumento di sviluppo locale**. Non:

- Accede alla rete (ComfyUI viene eseguito su localhost)
- Gestisce segreti, token o credenziali
- Raccoglie o invia dati di telemetria
- Scrive al di fuori della propria directory di lavoro

Le operazioni sui file sono limitate a `exports/`, `bakeoff/`, `boards/`, `derived/` e al registro SQLite. Le chiamate ai sottoprocessi sono limitate all'API locale di ComfyUI e al rendering headless di Godot.

## Licenza

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

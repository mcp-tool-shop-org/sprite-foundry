<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Sprite Foundry est un système de gestion d'actifs local qui génère, examine et exporte des sprites pixelisés 8 directions avec des cartes de normalisation et de profondeur. Il utilise ComfyUI pour la génération, avec le contrôle morphologique ControlNet (8 classes de corps), SQLite pour le suivi du cycle de vie, et Godot 4.6 pour la vérification de l'éclairage (finish-lab), le tout contrôlé à partir d'une seule interface en ligne de commande.

## Architecture

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

## Liste des personnages

92 ensembles d'exportation de production répartis en 12 catégories :

| Personnage | Nombre | Sujets |
|------|-------|----------|
| Bêtes | 16 | Bell Warden, Bone Weaver, Clock Golem, Grinning Idol, Hive Keeper, Hollow Knight, Ink Shade, Lantern Angler, Mirror Stalker, Mud Revenant, Rat King, Root Puppet, Spore Mother, Teeth Collector, Throat Singer, Wyvern |
| Habitants de la ville | 16 | Barmaid, Beggar, Blacksmith, Child, Elder, Farmer, Fisherman, Guard, Herbalist, Innkeeper, Lamplighter, Merchant, Minstrel, Noble, Scribe, Stable Hand |
| Gobelins | 8 | Archer, Bomber, Brute, Grunt, Scout, Shaman, Warchief, Wolf Rider |
| Héros | 8 | Barbarian, Cleric, Fighter, Mage, Monk, Paladin, Ranger, Rogue |
| Pirates | 8 | Captain, Cutthroat, Drowned, Governor, Navy Sailor, Pistoleer, Quartermaster, Sea Priest |
| Vilains | 8 | Assassin, Blackguard, Cult Priest, Dark Monk, Dread Ranger, Necromancer, Reaver, Warlord |
| Zombies | 8 | Bloater, Elite, Hazmat, Riot, Runner, Shambler, Skeletal, Worker |
| Créature | 6 | Bête de chargement, Gueule de dérive, Drone d'exploration, Prédateur de dérive, Raptor du vide, Drone guérisseur Keth |
| Équipage | 7 | Sera Vale, Ilen Marr, Thal, Thal (Combinaison de protection), Varek, Kael Morrow, Plongeur |
| Hostile | 3 | Pilleur, Pirate, Agent d'interdiction compact |
| Autorité | 2 | Agent de patrouille compact, Envoy de la Maison Veshan |
| Civil | 2 | Nera Quill, Courtier Orryn |

## Catégorie de monstres

Les créatures non humanoïdes utilisent des guides de profondeur spécifiques à la classe de corps au lieu du squelette humanoïde standard. Chaque classe de corps possède sa propre silhouette de référence de profondeur, sa force ControlNet et ses paramètres de synchronisation.

| Classe de corps | Force de profondeur | Pourcentage de fin | Créature |
|------------|---------------|-------|-----------|
| Amorphe | 0.35 | 65% | Rat King, Spore Mother, Mud Revenant |
| Large/Accroupi | 0.40 | 70% | Grinning Idol |
| Grand/Mince | 0.40 | 70% | Lantern Angler, Root Puppet |

Les guides de profondeur sont des primitives sans articulation (amas, piliers, colonnes) qui fixent la masse et l'orientation sans imposer la position du squelette ou des membres. Le champ `body_class` dans les configurations des personnages sélectionne automatiquement le préréglage correct :

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## Contrat d'exportation v1.0.0 (figé)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 directions : avant, avant_gauche, gauche, arrière_gauche, arrière, arrière_droite, droite, avant_droite
- PNG transparent 48x48, point de pivot au centre-bas
- Les consommateurs valident `schema_version: "1.0.0"` avant de charger

## Prérequis

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) en cours d'exécution localement (pour la génération)
- Godot 4.6 (pour le rendu finish lab)
- GPU NVIDIA recommandé (RTX 5080 / 16 Go de VRAM testés)

## Démarrage rapide

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

## Commandes de l'interface en ligne de commande

| Commande | Description |
|---------|-------------|
| `init` | Initialise le registre SQLite de la forge. |
| `subject-add` | Enregistre un nouveau sujet de personnage. |
| `register-run` | Enregistre une exécution de génération ComfyUI. |
| `register-attempt` | Enregistre une tentative individuelle au sein d'une exécution. |
| `check` | Exécute les contrôles de validation mécaniques. |
| `review-show` | Affiche la file d'attente de révision pour une exécution. |
| `review-accept` | Accepte une tentative à l'étape de révision actuelle. |
| `review-reject` | Rejette une tentative avec un code de rejet. |
| `batch-accept` | Accepte toutes les tentatives en attente dans une exécution. |
| `batch-reject` | Rejette toutes les tentatives en attente dans une exécution avec un seul code. |
| `regen` | Planifie la régénération des tentatives rejetées. |
| `attempt-detail` | Affiche le cycle de vie complet d'une tentative. |
| `finish-board` | Génère un tableau de comparaison finish-lab. |
| `status` | Résumé de l'état du pipeline. |
| `story` | Description complète de l'origine d'un sujet. |
| `lineage` | Chaîne de régénération pour une tentative. |
| `winner` | Gagnant canonique par direction. |
| `drift` | Analyse des schémas d'échec et taux de réussite. |
| `metrics` | Métriques de débit (par exécution ou à l'échelle de la forge). |
| `produce` | Commande unique : cartes + captures finish pour une exécution acceptée. |
| `export` | Exporte une exécution acceptée par finish en tant que paquet de ressources déterministe. |

## Modèle de menace

Sprite Foundry est un **outil de développement local**. Il ne :

- Accède au réseau (ComfyUI s'exécute sur localhost)
- Gère les secrets, les jetons ou les informations d'identification
- Collecte ou envoie des données télémétriques
- Écrit en dehors de son propre répertoire de travail

Les opérations de fichiers sont limitées à `exports/`, `bakeoff/`, `boards/`, `derived/` et le registre SQLite. Les appels de sous-processus sont limités à l'API locale de ComfyUI et au rendu headless de Godot.

## Licence

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

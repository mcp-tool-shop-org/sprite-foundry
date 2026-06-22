<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Sprite Foundry est un système de création d’éléments graphiques (assets) qui fonctionne uniquement en local. Il génère, examine et exporte des sprites pixelisés multidirectionnels (8 directions) avec des cartes de normales et de profondeur. Il alimente ComfyUI pour la génération à l’aide du contrôle morphologique de ControlNet (8 classes de corps), SQLite pour le suivi du cycle de vie, et Godot 4.6 pour la vérification de l’éclairage en phase finale — le tout contrôlé depuis une seule interface en ligne de commande (CLI).

> **Les ensembles de sprites produits par cette usine sont publiés sur npm** sous le nom de domaine `@sprite-foundry`, à partir du dépôt monolitique [sprite-foundry-packs](https://github.com/mcp-tool-shop-org/sprite-foundry-packs). Ce dépôt est l’usine ; ce dépôt est la boutique.

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

## Liste des éléments

92 ensembles d’exportation de production répartis en 12 catégories :

| Catégorie | Nombre | Sujets |
|------|-------|----------|
| Bête | 16 | Gardien de cloche, Tisseur d’os, Golem horloger, Idole grimaçante, Gardien de ruche, Chevalier creux, Ombre d’encre, Pêcheur-lanterne, Stalker miroir, Revenant boueux, Roi rat, Marionnette racinaire, Mère spore, Collecteur de dents, Chanteur de gorge, Wyverne |
| Habitants de la ville | 16 | Servante, Mendiant, Forgeron, Enfant, Ancien, Fermier, Pêcheur, Garde, Herboriste, Aubergiste, Allumeur de lampes, Marchand, Ménestrel, Noble, Écrivain, Palefrenier |
| Gobelin | 8 | Archer, Bombardier, Brute, Soldat, Éclaireur, Chaman, Chef de guerre, Cavalier loup |
| Héros | 8 | Barbare, Clerc, Guerrier, Mage, Moine, Paladin, Rôdeur, Voleur |
| Pirate | 8 | Capitaine, Coupe-gorge, Noyé, Gouverneur, Marin, Pistolero, Maître d’équipage, Prêtre de la mer |
| Méchant | 8 | Assassin, Garde noire, Prêtre du culte, Moine sombre, Rôdeur redoutable, Nécromancien, Pilleur, Seigneur de guerre |
| Zombie | 8 | Gonflé, Élite, Anti-hazard, Émeutier, Coureur, Vagabond, Squelettique, Ouvrier |
| Créature | 6 | Bête de cargaison, Gueule dérive, Drone agile, Prédateur dérive, Raptor du vide, Soigneur-drone Keth |
| Équipage | 7 | Sera Vale, Ilen Marr, Thal, Thal (combinaison anti-hazard), Varek, Kael Morrow, Plongeur de coque |
| Hostile | 3 | Pilleur, Pirate Reach, Agent d’interdiction compact |
| Autorité | 2 | Agent de patrouille compact, Envoyé de la maison Veshan |
| Civil | 2 | Nera Quill, Orryn Broker |

## Catégorie des monstres

Les créatures non humanoïdes utilisent des guides de profondeur spécifiques à leur classe corporelle au lieu du squelette humanoïde standard. Chaque classe corporelle a sa propre silhouette de référence de profondeur, sa force ControlNet et ses paramètres de synchronisation.

| Classe corporelle | Force de profondeur | Pourcentage final | Créatures |
|------------|---------------|-------|-----------|
| Amorphe | 0.35 | 65% | Roi rat, Mère spore, Revenant boueux |
| Large/Trapu | 0.40 | 70% | Idole grimaçante |
| Grand/Mince | 0.40 | 70% | Pêcheur-lanterne, Marionnette racinaire |

Les guides de profondeur sont des primitives sans articulations (amas, piliers, colonnes) qui fixent la masse et l’orientation sans dicter le placement du squelette ou des membres. Le champ `body_class` dans les configurations des personnages sélectionne automatiquement le préréglage correct :

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## Contrat d’exportation v1.0.0 (figé)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 directions : avant, avant gauche, gauche, arrière gauche, arrière, arrière droite, droite, avant droite
- PNG transparent de 48 x 48 pixels, pivot en bas au centre
- Les consommateurs valident `schema_version: "1.0.0"` avant le chargement

## Prérequis

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) en cours d’exécution localement (pour la génération)
- Godot 4.6 (pour le rendu en phase finale)
- GPU NVIDIA recommandé (RTX 5090 / 32 Go testé ; minimum 16 Go)

## Démarrage rapide

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

## Commandes CLI

| Commande | Description |
|---------|-------------|
| `init` | Initialiser le registre SQLite de l’usine |
| `subject-add` | Enregistrer un nouveau sujet de personnage |
| `register-run` | Enregistrer une exécution de génération ComfyUI |
| `register-attempt` | Enregistrer une tentative individuelle au sein d’une exécution |
| `check` | Exécuter les contrôles de validation mécaniques |
| `review-show` | Afficher la file d’attente des révisions pour une exécution |
| `review-accept` | Accepter une tentative à l’étape actuelle de la révision |
| `review-reject` | Rejeter une tentative avec un code de rejet |
| `batch-accept` | Accepter toutes les tentatives en attente dans une exécution |
| `batch-reject` | Rejeter toutes les tentatives en attente dans une exécution avec un seul code |
| `regen` | Mettre en file d’attente la régénération pour les tentatives rejetées |
| `attempt-detail` | Afficher l’intégralité du cycle de vie pour une tentative |
| `finish-board` | Générer un tableau comparatif en phase finale |
| `status` | Résumé de l’état du pipeline |
| `story` | Récit complet de la provenance pour un sujet |
| `lineage` | Chaîne de régénération pour une tentative |
| `winner` | Gagnant canonique par direction |
| `drift` | Analyse des schémas d’échec et taux de réussite |
| `metrics` | Indicateurs de débit (par exécution ou à l’échelle de l’usine) |
| `produce` | Commande unique : cartes + captures en phase finale pour une exécution acceptée |
| `export` | Exporter une exécution acceptée en phase finale sous forme d’ensemble d’éléments graphiques déterministe |

## Modèle de menace

Sprite Foundry est un **outil de développement local**. Il ne :

- Accède pas au réseau (ComfyUI s’exécute sur localhost)
- Gère pas les secrets, les jetons ou les informations d’identification
- Collecte ni n’envoie pas de données de télémétrie
- Écrit pas en dehors de son propre répertoire de travail

Les opérations sur les fichiers sont limitées à `exports/`, `bakeoff/`, `boards/`, `derived/` et au registre SQLite. Les appels aux sous-processus sont limités à l’API locale de ComfyUI et au rendu sans tête de Godot.

## Licence

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

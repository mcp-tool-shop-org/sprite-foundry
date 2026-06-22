<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.md">English</a>
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

Sprite Foundry é um sistema de produção de recursos local que gera, analisa e exporta sprites pixelizados com 8 direções, incluindo mapas de normal e profundidade. Ele utiliza o ComfyUI para a geração, com controle de morfologia do ControlNet (8 classes de corpo), SQLite para rastreamento do ciclo de vida e Godot 4.6 para verificação da iluminação na fase final — tudo controlado a partir de uma única interface de linha de comando (CLI).

> **Os pacotes de sprites produzidos por esta fábrica são publicados no npm** sob o escopo `@sprite-foundry`, a partir do monorepos [sprite-foundry-packs](https://github.com/mcp-tool-shop-org/sprite-foundry-packs). Este repositório é a fábrica; aquele repositório é a loja.

## Arquitetura

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

## Lista de personagens

92 pacotes de exportação em 12 categorias:

| Categoria | Contagem | Personagens |
|------|-------|----------|
| Monstro | 16 | Bell Warden, Bone Weaver, Clock Golem, Grinning Idol, Hive Keeper, Hollow Knight, Ink Shade, Lantern Angler, Mirror Stalker, Mud Revenant, Rat King, Root Puppet, Spore Mother, Teeth Collector, Throat Singer, Wyvern |
| Morador da cidade | 16 | Barmaid, Beggar, Blacksmith, Child, Elder, Farmer, Fisherman, Guard, Herbalist, Innkeeper, Lamplighter, Merchant, Minstrel, Noble, Scribe, Stable Hand |
| Goblin | 8 | Archer, Bomber, Brute, Grunt, Scout, Shaman, Warchief, Wolf Rider |
| Herói | 8 | Barbarian, Cleric, Fighter, Mage, Monk, Paladin, Ranger, Rogue |
| Pirata | 8 | Captain, Cutthroat, Drowned, Governor, Navy Sailor, Pistoleer, Quartermaster, Sea Priest |
| Vilão | 8 | Assassin, Blackguard, Cult Priest, Dark Monk, Dread Ranger, Necromancer, Reaver, Warlord |
| Zumbi | 8 | Bloater, Elite, Hazmat, Riot, Runner, Shambler, Skeletal, Worker |
| Criatura | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Tripulação | 7 | Sera Vale, Ilen Marr, Thal, Thal (Hazard Suit), Varek, Kael Morrow, Hull Diver |
| Hostil | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Autoridade | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civil | 2 | Nera Quill, Orryn Broker |

## Categoria de Monstro

Criaturas não humanoides usam guias de profundidade específicos da classe de corpo do ControlNet em vez do esqueleto humano padrão. Cada classe de corpo tem sua própria silhueta de referência de profundidade, força do ControlNet e parâmetros de tempo.

| Classe de Corpo | Força da Profundidade | Porcentagem Final | Criaturas |
|------------|---------------|-------|-----------|
| Amorfa | 0.35 | 65% | Rat King, Spore Mother, Mud Revenant |
| Larga/Baixa | 0.40 | 70% | Grinning Idol |
| Alta/Fina | 0.40 | 70% | Lantern Angler, Root Puppet |

Os guias de profundidade são primitivas sem articulações (blobs, pilares, colunas) que fixam a massa e a orientação sem ditar o posicionamento do esqueleto ou dos membros. O campo `body_class` nas configurações do personagem seleciona automaticamente a configuração correta:

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## Contrato de Exportação v1.0.0 (congelado)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 direções: frente, frente_esquerda, esquerda, trás_esquerda, trás, trás_direita, direita, frente_direita
- PNG transparente de 48×48, pivô centralizado na parte inferior
- Os consumidores validam `schema_version: "1.0.0"` antes de carregar

## Pré-requisitos

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) em execução localmente (para geração)
- Godot 4.6 (para renderização na fase final)
- GPU NVIDIA recomendada (RTX 5090 / 32 GB testada; mínimo de 16 GB)

## Início Rápido

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

## Comandos da CLI

| Comando | Descrição |
|---------|-------------|
| `init` | Inicializa o registro SQLite da fábrica |
| `subject-add` | Registra um novo personagem |
| `register-run` | Registra uma execução de geração do ComfyUI |
| `register-attempt` | Registra uma tentativa individual dentro de uma execução |
| `check` | Executa verificações mecânicas |
| `review-show` | Exibe a fila de revisão para uma execução |
| `review-accept` | Aceita uma tentativa na fase atual de revisão |
| `review-reject` | Rejeita uma tentativa com um código de rejeição |
| `batch-accept` | Aceita todas as tentativas pendentes em uma execução |
| `batch-reject` | Rejeita todas as tentativas pendentes em uma execução com um único código |
| `regen` | Coloca na fila a regeneração para tentativas rejeitadas |
| `attempt-detail` | Mostra o ciclo de vida completo de uma tentativa |
| `finish-board` | Gera um painel de comparação da fase final |
| `status` | Resumo do status do pipeline |
| `story` | Narrativa completa da origem para um personagem |
| `lineage` | Regenera a cadeia para uma tentativa |
| `winner` | Vencedor canônico por direção |
| `drift` | Análise de padrões de falha e taxas de sucesso |
| `metrics` | Métricas de produtividade (por execução ou em toda a fábrica) |
| `produce` | Com um único comando: mapas + capturas da fase final para uma execução aceita |
| `export` | Exporta uma execução aceita na fase final como um pacote de recursos determinístico |

## Modelo de Ameaças

Sprite Foundry é uma **ferramenta de desenvolvimento local**. Não:

- Acessa a rede (o ComfyUI é executado no localhost)
- Lida com segredos, tokens ou credenciais
- Coleta ou envia dados de telemetria
- Escreve fora de seu próprio diretório de trabalho

As operações de arquivo são restritas a `exports/`, `bakeoff/`, `boards/`, `derived/` e o registro SQLite. As chamadas de subprocesso são limitadas à API local do ComfyUI e à renderização sem interface gráfica do Godot.

## Licença

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

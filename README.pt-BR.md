<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.md">English</a>
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

Sprite Foundry é um sistema de gerenciamento de recursos local que gera, revisa e exporta sprites de pixels em 8 direções, com mapas de normal e profundidade. Ele utiliza o ComfyUI para geração, com controle de morfologia via ControlNet (8 classes de corpos), SQLite para rastreamento do ciclo de vida e Godot 4.6 para verificação de iluminação (finish-lab) — tudo controlado a partir de uma única interface de linha de comando (CLI).

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

## Lista de Personagens

92 pacotes de exportação para produção, divididos em 12 categorias:

| Personagem | Número | Tipos |
|------|-------|----------|
| Bestiário | 16 | Bell Warden, Bone Weaver, Clock Golem, Grinning Idol, Hive Keeper, Hollow Knight, Ink Shade, Lantern Angler, Mirror Stalker, Mud Revenant, Rat King, Root Puppet, Spore Mother, Teeth Collector, Throat Singer, Wyvern |
| Habitantes da Cidade | 16 | Barmaid, Beggar, Blacksmith, Child, Elder, Farmer, Fisherman, Guard, Herbalist, Innkeeper, Lamplighter, Merchant, Minstrel, Noble, Scribe, Stable Hand |
| Goblin | 8 | Archer, Bomber, Brute, Grunt, Scout, Shaman, Warchief, Wolf Rider |
| Herói | 8 | Barbarian, Cleric, Fighter, Mage, Monk, Paladin, Ranger, Rogue |
| Pirata | 8 | Captain, Cutthroat, Drowned, Governor, Navy Sailor, Pistoleer, Quartermaster, Sea Priest |
| Vilão | 8 | Assassin, Blackguard, Cult Priest, Dark Monk, Dread Ranger, Necromancer, Reaver, Warlord |
| Zumbi | 8 | Bloater, Elite, Hazmat, Riot, Runner, Shambler, Skeletal, Worker |
| Criaturas | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Equipe | 7 | Sera Vale, Ilen Marr, Thal, Thal (Traje de Proteção), Varek, Kael Morrow, Hull Diver |
| Hostis | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Autoridade | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civis | 2 | Nera Quill, Orryn Broker |

## Monstros

Criaturas não humanoides utilizam guias de profundidade específicos para cada classe de corpo, em vez do esqueleto humanoide padrão. Cada classe de corpo possui seu próprio perfil de referência de profundidade, intensidade do ControlNet e parâmetros de tempo.

| Classe de Corpo | Intensidade da Profundidade | Porcentagem Final | Criaturas |
|------------|---------------|-------|-----------|
| Amórfico | 0.35 | 65% | Rat King, Spore Mother, Mud Revenant |
| Largo/Abaixado | 0.40 | 70% | Grinning Idol |
| Alto/Fino | 0.40 | 70% | Lantern Angler, Root Puppet |

Os guias de profundidade são primitivos sem articulações (massas, pilares, colunas) que definem a massa e a orientação, sem determinar o posicionamento do esqueleto ou dos membros. O campo `body_class` nas configurações dos personagens seleciona automaticamente a configuração correta:

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## Contrato de Exportação v1.0.0 (fixo)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 direções: frente, frente_esquerda, esquerda, trás_esquerda, trás, trás_direita, direita, frente_direita
- PNG transparente de 48x48, ponto de pivô no centro_inferior
- Os sistemas validam `schema_version: "1.0.0"` antes de carregar

## Pré-requisitos

- Python 3.11+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) instalado localmente (para geração)
- Godot 4.6 (para renderização finish lab)
- GPU NVIDIA recomendada (RTX 5080 / 16 GB de VRAM testados)

## Início Rápido

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

## Comandos da CLI

| Comando | Descrição |
|---------|-------------|
| `init` | Inicializa o registro SQLite do Sprite Foundry |
| `subject-add` | Registra um novo personagem |
| `register-run` | Registra uma execução de geração do ComfyUI |
| `register-attempt` | Registra uma tentativa individual dentro de uma execução |
| `check` | Executa verificações mecânicas |
| `review-show` | Exibe a fila de revisão para uma execução |
| `review-accept` | Aceita uma tentativa na fase de revisão atual |
| `review-reject` | Rejeita uma tentativa com um código de rejeição |
| `batch-accept` | Aceita todas as tentativas pendentes em uma execução |
| `batch-reject` | Rejeita todas as tentativas pendentes em uma execução com um único código |
| `regen` | Agenda a regeneração para tentativas rejeitadas |
| `attempt-detail` | Mostra o ciclo de vida completo de uma tentativa |
| `finish-board` | Gera um painel de comparação finish-lab |
| `status` | Resumo do status do pipeline |
| `story` | Histórico completo de uma personagem |
| `lineage` | Cadeia de regeneração para uma tentativa |
| `winner` | Vencedor canônico por direção |
| `drift` | Análise de padrões de falha e taxas de aprovação |
| `metrics` | Métricas de desempenho (por execução ou em todo o Sprite Foundry) |
| `produce` | Um único comando: mapas + capturas finish para uma execução aceita |
| `export` | Exporta uma execução aceita como um pacote de recursos determinístico |

## Modelo de Ameaças

O Sprite Foundry é uma **ferramenta para desenvolvedores que opera localmente**. Ele não:

- Acessa a rede (o ComfyUI é executado no localhost)
- Lida com segredos, tokens ou credenciais
- Coleta ou envia dados de telemetria
- Escreve fora de seu próprio diretório de trabalho

As operações de arquivo são restritas aos diretórios `exports/`, `bakeoff/`, `boards/`, `derived/` e ao registro SQLite. As chamadas de subprocessos são limitadas à API local do ComfyUI e à renderização headless do Godot.

## Licença

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

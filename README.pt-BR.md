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

Sprite Foundry é um sistema de gerenciamento de recursos que opera localmente e que gera, revisa e exporta sprites de pixels em 8 direções, com mapas de normal e profundidade. Ele utiliza o ComfyUI para geração, o SQLite para rastreamento do ciclo de vida e o Godot 4.6 para verificação de iluminação (finish-lab), tudo controlado a partir de uma única interface de linha de comando (CLI).

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

20 pacotes de exportação de produção, sem violações de contrato:

| Personagem | Número | Tipos |
|------|-------|----------|
| Equipe | 7 | Sera Vale, Ilen Marr, Thal, Thal (Traje de Proteção), Varek, Kael Morrow, Hull Diver |
| Criaturas | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| Hostis | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| Autoridade | 2 | Compact Patrol Officer, Veshan House Envoy |
| Civis | 2 | Nera Quill, Orryn Broker |

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
  Built by <a href="https://github.com/mcp-tool-shop-org">MCP Tool Shop</a>
</p>

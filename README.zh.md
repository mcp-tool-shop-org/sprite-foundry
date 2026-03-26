<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.md">English</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Sprite Foundry 是一个仅在本地运行的资源流水线，用于生成、审查和导出具有法线和深度贴图的 8 个方向像素精灵图。它使用 ComfyUI 进行生成，使用 SQLite 进行生命周期跟踪，并使用 Godot 4.6 进行 finish-lab 光照验证——所有操作都通过单个命令行界面控制。

## 架构

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

## 角色列表

20 个生产导出包，无任何合同违规：

| 类别 | 数量 | 角色 |
|------|-------|----------|
| 船员 | 7 | Sera Vale, Ilen Marr, Thal, Thal (防护服), Varek, Kael Morrow, Hull Diver |
| 生物 | 6 | Cargo Beast, Drift Maw, Skitter Drone, Drift Lurker, Void Raptor, Keth Healer-Drone |
| 敌对 | 3 | Scav Raider, Reach Pirate, Compact Interdiction Agent |
| 执法 | 2 | Compact Patrol Officer, Veshan House Envoy |
| 平民 | 2 | Nera Quill, Orryn Broker |

## 导出合同 v1.0.0 (已冻结)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 个方向：正面、左前、左侧、左后、背面、右后、右侧、右前
- 48x48 透明 PNG 格式，中心底部作为旋转中心
- 客户端在加载之前验证 `schema_version: "1.0.0"`

## 先决条件

- Python 3.11+
- 运行在本地的 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) (用于生成)
- Godot 4.6 (用于 finish lab 渲染)
- 推荐使用 NVIDIA GPU (已测试 RTX 5080 / 16 GB 显存)

## 快速开始

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

## 命令行指令

| 指令 | 描述 |
|---------|-------------|
| `init` | 初始化 SQLite 注册表 |
| `subject-add` | 注册新的角色 |
| `register-run` | 记录 ComfyUI 生成过程 |
| `register-attempt` | 记录一次生成尝试 |
| `check` | 运行机械验证 |
| `review-show` | 显示当前生成过程的审查队列 |
| `review-accept` | 接受当前审查阶段的一次尝试 |
| `review-reject` | 拒绝一次尝试，并提供拒绝代码 |
| `batch-accept` | 接受当前生成过程中的所有待处理尝试 |
| `batch-reject` | 使用一个代码拒绝当前生成过程中的所有待处理尝试 |
| `regen` | 为被拒绝的尝试重新生成 |
| `attempt-detail` | 显示一次尝试的完整生命周期 |
| `finish-board` | 生成 finish-lab 比较图 |
| `status` | 流水线状态摘要 |
| `story` | 角色的完整溯源信息 |
| `lineage` | 一次尝试的生成链 |
| `winner` | 每个方向的最佳结果 |
| `drift` | 失败模式分析和通过率 |
| `metrics` | 吞吐量指标 (按生成过程或整个流水线) |
| `produce` | 一键命令：为已接受的生成过程生成贴图和 finish 捕捉 |
| `export` | 将已接受的生成过程导出为确定性的资源包 |

## 安全模型

Sprite Foundry 是一个**本地开发工具**。它不：

- 访问网络 (ComfyUI 运行在本地)
- 处理密钥、令牌或凭据
- 收集或发送遥测数据
- 在其工作目录之外写入文件

文件操作仅限于 `exports/`、`bakeoff/`、`boards/`、`derived/` 以及 SQLite 注册表。子进程调用仅限于 ComfyUI 的本地 API 和 Godot 的无头渲染。

## 许可证

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://github.com/mcp-tool-shop-org">MCP Tool Shop</a>
</p>

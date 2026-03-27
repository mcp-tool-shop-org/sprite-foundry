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

Sprite Foundry 是一个本地资源流水线，用于生成、审查和导出 8 个方向的像素精灵图，并带有法线和深度贴图。它使用 ComfyUI 进行图像生成，利用 ControlNet 技术进行身体姿态控制（8 种身体类型），使用 SQLite 跟踪生命周期，并使用 Godot 4.6 进行 finish-lab 渲染验证，所有操作都通过单个命令行界面进行控制。

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

共有 92 个生产导出包，分布在 12 个类别中：

| 类别 | 数量 | 角色 |
|------|-------|----------|
| 野兽 | 16 | 钟楼守卫、骨骼编织者、机械傀儡、咧嘴偶像、蜂巢守护者、空洞骑士、墨水幽灵、灯笼钓鱼者、镜像潜伏者、泥土复生者、鼠王、根系傀儡、孢子之母、牙齿收集者、喉咙吟唱者、飞龙 |
| 城镇居民 | 16 | 酒馆女招待、乞丐、铁匠、儿童、老人、农民、渔夫、卫兵、草药师、客栈老板、点灯人、商人、吟游诗人、贵族、书记员、马厩工人 |
| 哥布林 | 8 | 弓箭手、炸弹兵、蛮汉、喽啰、侦察兵、萨满、战争首领、狼骑兵 |
| 英雄 | 8 | 野蛮人、牧师、战士、法师、武僧、圣骑士、游侠、盗贼 |
| 海盗 | 8 | 船长、杀人犯、溺水者、总督、海军水手、枪手、副船长、海神 |
| 反派 | 8 | 刺客、黑骑士、邪教祭司、黑暗武僧、黑暗游侠、死灵法师、掠夺者、军阀 |
| 僵尸 | 8 | 肿胀者、精英、防护服、暴动者、奔跑者、蹒跚者、骷髅、工人 |
| 生物 | 6 | 货物野兽、漂浮巨口、小型无人机、漂浮潜伏者、虚空掠夺者、治疗无人机 |
| 船员 | 7 | 塞拉·维尔、伊伦·马尔、塔尔、塔尔（防护服）、瓦雷克、凯尔·莫罗、深海潜水员 |
| 敌对生物 | 3 | 拾荒者、海盗、紧凑型拦截特工 |
| 执法者 | 2 | 紧凑型巡逻官、维沙之家使节 |
| 平民 | 2 | 内拉·奎尔、奥林·经纪人 |

## 怪物类别

非人形生物使用特定于身体类型的 ControlNet 深度引导，而不是标准的人形骨骼。每个身体类型都有其自己的深度参考轮廓、ControlNet 强度和时间参数。

| 身体类型 | 深度强度 | 结束百分比 | 生物 |
|------------|---------------|-------|-----------|
| 非人形 | 0.35 | 65% | 鼠王、孢子之母、泥土复生者 |
| 宽/矮 | 0.40 | 70% | 咧嘴偶像 |
| 高/瘦 | 0.40 | 70% | 灯笼钓鱼者、根系傀儡 |

深度引导是无关节的原始图形（块状、柱状、圆柱状），它们锁定质量和方向，而不会规定骨骼或肢体的放置。角色配置中的 `body_class` 字段会自动选择正确的预设：

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## 导出合约 v1.0.0 (已冻结)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8 个方向：正面、正面左侧、左侧、背面左侧、背面、背面右侧、右侧、正面右侧
- 48x48 透明 PNG，中心底部作为旋转中心
- 消费者在加载之前验证 `schema_version: "1.0.0"`

## 先决条件

- Python 3.11+
- 运行中的本地 [ComfyUI](https://github.com/comfyanonymous/ComfyUI)（用于生成）
- Godot 4.6（用于 finish lab 渲染）
- 推荐使用 NVIDIA GPU（已测试 RTX 5080 / 16 GB VRAM）

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

## 命令行界面命令

| 命令 | 描述 |
|---------|-------------|
| `init` | 初始化 Foundry 的 SQLite 注册表 |
| `subject-add` | 注册新的角色 |
| `register-run` | 记录 ComfyUI 生成过程 |
| `register-attempt` | 记录单个尝试 |
| `check` | 运行机械验证 |
| `review-show` | 显示运行的审查队列 |
| `review-accept` | 接受当前审查阶段的尝试 |
| `review-reject` | 拒绝带有拒绝代码的尝试。 |
| `batch-accept` | 接受一个运行中的所有待处理的尝试。 |
| `batch-reject` | 使用一个代码拒绝一个运行中的所有待处理的尝试。 |
| `regen` | 为被拒绝的尝试重新生成队列。 |
| `attempt-detail` | 显示一个尝试的完整生命周期。 |
| `finish-board` | 生成一个比较板，用于比较最终结果。 |
| `status` | 流水线状态摘要。 |
| `story` | 一个对象的完整溯源信息。 |
| `lineage` | 一个尝试的重新生成链。 |
| `winner` | 每个方向的规范胜者。 |
| `drift` | 故障模式分析和通过率。 |
| `metrics` | 吞吐量指标（按运行或整个工厂）。 |
| `produce` | 一个命令：将已接受的运行的地图和最终结果导出。 |
| `export` | 将已接受的运行导出为可确定性的资源包。 |

## 威胁模型

Sprite Foundry 是一个**本地开发工具**。它不：

- 访问网络（ComfyUI 在本地运行）。
- 处理密钥、令牌或凭据。
- 收集或发送遥测数据。
- 在其自身的工作目录之外写入文件。

文件操作仅限于 `exports/`、`bakeoff/`、`boards/`、`derived/` 以及 SQLite 注册表。子进程调用仅限于 ComfyUI 的本地 API 和 Godot 的无头渲染。

## 许可证

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

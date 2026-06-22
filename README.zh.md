<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.md">English</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

精灵工厂是一个本地资源流水线，用于生成、审查和导出带有法线贴图和深度贴图的八方向像素精灵。它通过ControlNet形态控制（8种身体类别）驱动ComfyUI进行生成，使用SQLite进行生命周期跟踪，并使用Godot 4.6进行最终渲染验证——所有操作均来自单个命令行界面。

> **该工厂生产的精灵包发布到npm上**，命名空间为`@sprite-foundry`，源自[sprite-foundry-packs](https://github.com/mcp-tool-shop-org/sprite-foundry-packs)这个单仓库。这个仓库是工厂；那个仓库是商店。

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

## 列表

共有12个类别，包含92个用于导出的资源包：

| 类别 | 数量 | 主题 |
|------|-------|----------|
| 野兽 | 16 | 钟楼守卫、骨骼编织者、时钟傀儡、咧嘴的偶像、蜂巢守护者、空心骑士、墨影、灯笼垂钓者、镜子潜伏者、泥土复仇者、鼠王、根部木偶、孢子之母、牙齿收集者、喉歌歌手、飞龙 |
| 城镇居民 | 16 | 女招待、乞丐、铁匠、孩子、长老、农民、渔夫、守卫、草药师、旅店老板、点灯人、商人、吟游诗人、贵族、抄写员、马厩工人 |
| 地精 | 8 | 弓箭手、炸弹手、蛮兵、普通士兵、侦察兵、萨满祭司、战争首领、狼骑士 |
| 英雄 | 8 | 野蛮人、牧师、战士、法师、武僧、圣骑士、游侠、盗贼 |
| 海盗 | 8 | 船长、冷酷之徒、溺水者、总督、海军水手、枪手、大副、海洋祭司 |
| 反派 | 8 | 刺客、黑卫士、邪教祭司、黑暗武僧、可怕的游侠、死灵法师、掠夺者、军阀 |
| 僵尸 | 8 | 肿胀者、精英、防护服怪、暴动者、奔跑者、蹒跚者、骨骼生物、工人 |
| 生物 | 6 | 货运野兽、漂流颚、滑行无人机、漂流潜伏者、虚空猛禽、凯斯治疗无人机 |
| 船员 | 7 | 塞拉·维尔、伊伦·马尔、塔尔、塔尔（防护服）、瓦雷克、凯尔·莫罗、水下潜行者 |
| 敌对生物 | 3 | 拾荒掠夺者、边境海盗、紧凑拦截特工 |
| 当局 | 2 | 紧凑巡逻警官、维尚家族使者 |
| 平民 | 2 | 内拉·奎尔、奥林·经纪人 |

## 怪物类别

非人形生物使用特定于身体类别的ControlNet深度引导，而不是标准的人形骨骼。每个身体类别都有自己的深度参考轮廓、ControlNet强度和时间参数。

| 身体类别 | 深度强度 | 结束百分比 | 生物 |
|------------|---------------|-------|-----------|
| 无定形 | 0.35 | 65% | 鼠王、孢子之母、泥土复仇者 |
| 宽/矮胖 | 0.40 | 70% | 咧嘴的偶像 |
| 高/瘦长 | 0.40 | 70% | 灯笼垂钓者、根部木偶 |

深度引导是无关节的基本体（块状物、柱子），可以固定质量和方向，而不会限制骨骼或肢体的放置。角色配置中的`body_class`字段会自动选择正确的预设：

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## 导出协议 v1.0.0（已冻结）

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8个方向：正面、前左、左侧、后左、背面、后右、右侧、前右
- 48×48透明PNG，中心底部为支点
- 消费者在加载之前会验证`schema_version: "1.0.0"`

## 先决条件

- Python 3.11+
- 本地运行的[ComfyUI](https://github.com/comfyanonymous/ComfyUI)（用于生成）
- Godot 4.6（用于最终渲染）
- 建议使用NVIDIA GPU（已测试RTX 5090 / 32 GB；最低16 GB）

## 快速入门

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

## 命令行命令

| 命令 | 描述 |
|---------|-------------|
| `init` | 初始化工厂SQLite注册表 |
| `subject-add` | 注册一个新的角色主题 |
| `register-run` | 记录ComfyUI生成过程 |
| `register-attempt` | 记录一次运行中的单个尝试 |
| `check` | 运行机械验证门控 |
| `review-show` | 显示一次运行的审查队列 |
| `review-accept` | 接受当前审查阶段的一次尝试 |
| `review-reject` | 使用拒绝代码拒绝一次尝试 |
| `batch-accept` | 接受一次运行中所有待处理的尝试 |
| `batch-reject` | 使用一个代码拒绝一次运行中的所有待处理尝试 |
| `regen` | 排队重新生成被拒绝的尝试 |
| `attempt-detail` | 显示一次尝试的完整生命周期 |
| `finish-board` | 生成最终渲染比较图 |
| `status` | 流水线状态摘要 |
| `story` | 某个主题的完整来源叙述 |
| `lineage` | 重新生成一次尝试的链条 |
| `winner` | 每个方向的最佳结果 |
| `drift` | 失败模式分析和通过率 |
| `metrics` | 吞吐量指标（每次运行或整个工厂） |
| `produce` | 一键：生成已接受的一次运行的贴图+最终渲染图像 |
| `export` | 将最终渲染批准的一次运行导出为确定性资源包 |

## 威胁模型

精灵工厂是一个**本地开发工具**。它不：

- 访问网络（ComfyUI在localhost上运行）
- 处理敏感信息、令牌或凭据
- 收集或发送遥测数据
- 将数据写入其工作目录之外的位置

文件操作仅限于`exports/`、`bakeoff/`、`boards/`、`derived/`和SQLite注册表。子进程调用仅限于ComfyUI的本地API和Godot无头渲染。

## 许可证

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

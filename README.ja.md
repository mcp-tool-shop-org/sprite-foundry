<p align="center">
  <a href="README.md">English</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Sprite Foundryは、ローカル環境でのみ動作するアセット生成パイプラインで、8方向のピクセルスプライトを生成、レビューし、ノーマルマップと深度マップとともにエクスポートします。生成にはComfyUI、ライフサイクル管理にはSQLite、レンダリング検証にはGodot 4.6を使用し、これらはすべて単一のCLIから制御されます。

## アーキテクチャ

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

## 登場人物リスト

20件のプロダクションエクスポートパッケージ、契約違反ゼロ：

| キャラクター | 数 | 対象 |
|------|-------|----------|
| クルー | 7 | セラ・ヴェール、イレン・マール、タル、タル（ハザードスーツ）、ヴァレク、カエル・モロウ、ハルダイバー |
| クリーチャー | 6 | カーゴビースト、ドリフトマウ、スキッタードローン、ドリフトラーカー、ボイドラプター、ケス・ヒーラー・ドローン |
| 敵 | 3 | スカベンジャー・レイダー、リーチ・パイレート、コンパクト・インターディクション・エージェント |
| 権力者 | 2 | コンパクト・パトロール・オフィサー、ヴェシャン・ハウス・エ Envoy |
| 一般市民 | 2 | ネラ・クイル、オリーン・ブローカー |

## エクスポート契約 v1.0.0 (固定)

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8方向：正面、左正面、左、左背面、背面、右背面、右、右正面
- 48x48ピクセルの透過PNG、中心下を原点
- 読み込み前に、クライアントは`schema_version: "1.0.0"`を検証します。

## 前提条件

- Python 3.11以上
- ローカルで動作している[ComfyUI](https://github.com/comfyanonymous/ComfyUI) (生成用)
- Godot 4.6 (finish labレンダリング用)
- NVIDIA GPU推奨 (RTX 5080 / 16 GB VRAMで検証済み)

## クイックスタート

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

## CLIコマンド

| コマンド | 説明 |
|---------|-------------|
| `init` | SQLiteレジストリを初期化します。 |
| `subject-add` | 新しいキャラクターを登録します。 |
| `register-run` | ComfyUIによる生成ジョブを記録します。 |
| `register-attempt` | ジョブ内の一連の試行を記録します。 |
| `check` | 機械的な検証を実行します。 |
| `review-show` | ジョブのレビューキューを表示します。 |
| `review-accept` | 現在のレビュー段階での試行を承認します。 |
| `review-reject` | 拒否コードを使用して試行を拒否します。 |
| `batch-accept` | ジョブ内の保留中のすべての試行を承認します。 |
| `batch-reject` | ジョブ内の保留中のすべての試行を、1つのコードで拒否します。 |
| `regen` | 拒否された試行の再生成をキューに入れます。 |
| `attempt-detail` | 特定の試行のライフサイクル全体を表示します。 |
| `finish-board` | finish-labの比較ボードを生成します。 |
| `status` | パイプラインの状態の概要を表示します。 |
| `story` | 特定の対象に関する完全なトレーサビリティ情報を表示します。 |
| `lineage` | 試行の再生成チェーンを表示します。 |
| `winner` | 各方向の最適な結果を表示します。 |
| `drift` | 失敗パターン分析と合格率を表示します。 |
| `metrics` | スループットの指標 (ジョブごとまたは全体) を表示します。 |
| `produce` | 1つのコマンドで、承認されたジョブのマップとfinishキャプチャを取得します。 |
| `export` | 承認されたジョブを、決定論的なアセットパックとしてエクスポートします。 |

## 脅威モデル

Sprite Foundryは、**ローカル開発ツール**です。以下の機能はありません。

- ネットワークへのアクセス (ComfyUIはlocalhostで動作)
- シークレット、トークン、または認証情報の処理
- テレメトリーの収集または送信
- 自身の作業ディレクトリ以外の場所に書き込み

ファイル操作は、`exports/`、`bakeoff/`、`boards/`、`derived/`、およびSQLiteレジストリに限定されます。サブプロセス呼び出しは、ComfyUIのローカルAPIとGodotのヘッドレスレンダリングに限定されます。

## ライセンス

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://github.com/mcp-tool-shop-org">MCP Tool Shop</a>
</p>

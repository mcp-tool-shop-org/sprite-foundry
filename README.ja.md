<p align="center">
  <a href="README.md">English</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Sprite Foundryは、ローカル環境でのみ動作するアセットパイプラインであり、ノーマルマップと深度マップを持つ8方向のピクセルスプライトを生成、レビュー、エクスポートします。ControlNetによる形態制御（8種類のボディクラス）、ライフサイクル追跡のためのSQLite、最終的なレンダリング検証のためのGodot 4.6を利用し、これらはすべて単一のCLIから制御されます。

このファクトリーで生成されるスプライトパックは、[sprite-foundry-packs](https://github.com/mcp-tool-shop-org/sprite-foundry-packs)というモノリポジトリを通じて、`@sprite-foundry`のスコープの下でnpmに公開されます。このリポジトリがファクトリーであり、別のリポジトリがストアフロントです。

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

## ロースター

12のレーンにまたがる92個のエクスポートパック：

| レーン | 数 | 対象 |
|------|-------|----------|
| 獣 | 16 | ベルワーデン、ボーンウィーバー、クロックゴーレム、グリニングアイドル、ハイブキーパー、ホローナイト、インクシェード、ランタンアングラー、ミラーストーカー、マッドレヴェナント、ラットキング、ルートパペット、スポア・マザー、ティースコレクター、スロートシンガー、ワイバーン |
| 町人 | 16 | バーメイド、物乞い、鍛冶屋、子供、長老、農民、漁師、警備兵、薬草医、宿屋の主人、灯台守、商人、吟遊詩人、貴族、書記、馬丁 |
| ゴブリン | 8 | アーチャー、ボンバー、ブルート、グルント、スカウト、シャーマン、ウォーチーフ、ウルフライダー |
| ヒーロー | 8 | バーバリアン、クレリック、ファイター、メイジ、モンク、パラディン、レンジャー、ローグ |
| 海賊 | 8 | キャプテン、カットスロート、ドラウンド、ガバナー、ネイビーセーラー、ピストラー、クォーターマスター、シー・プリースト |
| 悪役 | 8 | アサシン、ブラックガード、カルトプリースト、ダークモンク、ドレッドレンジャー、ネクロマンサー、リーバー、ウォーロード |
| ゾンビ | 8 | ブロウター、エリート、ハズマット、ライオット、ランナー、シャンブラー、スケレタル、ワーカー |
| クリーチャー | 6 | カーゴビースト、ドリフトモウ、スキッター・ドローン、ドリフト・ラーカー、ボイドラプター、ケス・ヒーラー・ドローン |
| クルー | 7 | セーラ・ヴェール、イレン・マー、サール、サール（ハザードスーツ）、ヴァレク、ケイル・モロー、ハルダイバー |
| 敵対者 | 3 | スカブレイダー、リーチパイレート、コンパクトインターディクションエージェント |
| 権威 | 2 | コンパクトパトロールオフィサー、ヴェシャンハウスエンヴォイ |
| 民間人 | 2 | ネラ・クイル、オーリン・ブローカー |

## モンスターレーン

非人間型のクリーチャーは、標準の人間型スケルトンの代わりに、ボディクラス固有のControlNet深度ガイドを使用します。各ボディクラスには、独自の深度参照シルエット、ControlNetの強度、およびタイミングパラメータがあります。

| ボディクラス | 深度強度 | 終了% | クリーチャー |
|------------|---------------|-------|-----------|
| 不定形 | 0.35 | 65% | ラットキング、スポア・マザー、マッドレヴェナント |
| 幅広/低い | 0.40 | 70% | グリニングアイドル |
| 背が高い/細い | 0.40 | 70% | ランタンアングラー、ルートパペット |

深度ガイドは、関節を持たないプリミティブ（塊、柱）であり、スケルトンや四肢の配置を決定することなく、質量と方向を固定します。キャラクター設定内の`body_class`フィールドは、適切なプリセットを自動的に選択します。

```bash
# Body class auto-resolved from config
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json

# CLI override
python -m pipeline.foundry_gen_morph --config pipeline/chars/beast_rat_king.json --body-class tall_thin
```

## エクスポート契約 v1.0.0（固定）

```
exports/{subject_slug}/{run_id}/
├── albedo/    8 × 48px transparent PNGs
├── normal/    8 × matching normal maps
├── depth/     8 × matching depth maps
├── preview/   contact sheet
└── manifest.json  (schema v1.0.0, SHA-256 checksums, provenance)
```

- 8方向：正面、前方左、左、後方左、後方、後方右、右、前方右
- 48×48の透明PNG、中心下をピボットとする
- コンシューマーは、読み込み前に`schema_version: "1.0.0"`を検証する

## 前提条件

- Python 3.11+
- ローカルで実行されている[ComfyUI](https://github.com/comfyanonymous/ComfyUI)（生成用）
- Godot 4.6（最終レンダリング用）
- NVIDIA GPUを推奨（RTX 5090 / 32 GB でテスト済み。最低16 GB）

## クイックスタート

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

## CLIコマンド

| コマンド | 説明 |
|---------|-------------|
| `init` | ファクトリーのSQLiteレジストリを初期化する |
| `subject-add` | 新しいキャラクターの対象を登録する |
| `register-run` | ComfyUIの生成実行を記録する |
| `register-attempt` | 実行内の個々の試行を記録する |
| `check` | 機械的な検証ゲートを実行する |
| `review-show` | 実行のレビューキューを表示する |
| `review-accept` | 現在のレビュー段階での試行を受け入れる |
| `review-reject` | 拒否コードを使用して試行を拒否する |
| `batch-accept` | 実行内の保留中のすべての試行を受け入れる |
| `batch-reject` | 1つのコードで実行内の保留中のすべてを拒否する |
| `regen` | 拒否された試行の再生成をキューに入れる |
| `attempt-detail` | 1つの試行の完全なライフサイクルを表示する |
| `finish-board` | 最終レンダリング比較ボードを生成する |
| `status` | パイプラインステータスの概要 |
| `story` | 対象の完全な来歴 |
| `lineage` | 試行の再生成チェーン |
| `winner` | 方向ごとの正準的な勝者 |
| `drift` | 失敗パターン分析と合格率 |
| `metrics` | スループットメトリック（実行ごとまたはファクトリー全体） |
| `produce` | 1つのコマンド：受け入れられた実行のマップと最終レンダリングキャプチャ |
| `export` | 最終的に受け入れられた実行を、決定的なアセットパックとしてエクスポートする |

## 脅威モデル

Sprite Foundryは**ローカル開発ツール**です。以下の機能はありません。

- ネットワークにアクセスする（ComfyUIはlocalhostで実行される）
- シークレット、トークン、または認証情報を処理する
- テレメトリーを収集または送信する
- 独自の作業ディレクトリ外に書き込む

ファイル操作は、`exports/`、`bakeoff/`、`boards/`、`derived/`、およびSQLiteレジストリに限定されます。サブプロセス呼び出しは、ComfyUIのローカルAPIとGodotヘッドレスレンダリングに制限されます。

## ライセンス

[MIT](LICENSE)

---

<p align="center">
  Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
</p>

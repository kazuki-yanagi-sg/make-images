# プロジェクト解析レポート

---

## Gitブランチ切り替え不可問題の分析（2026-04-16）

### 症状

`feature/initial-design`から`main`への切り替えは成功するが、`main`から`feature/initial-design`への切り替えが失敗する。

```
error: Your local changes to the following files would be overwritten by checkout:
	.gitignore
	CLAUDE.md
	Planning/TDD_PLAN.md
Please commit your changes or stash them before you switch branches.
Aborting
```

### 専門家パネル分析

#### 数学者の視点
- **状態の非対称性**: `main`ブランチには1コミット（7b8fea4）が存在
- `feature/initial-design`ブランチには「No commits yet」（orphan状態）
- ステージングされたファイルはどちらのブランチにもコミットされていない「浮遊状態」
- これは集合論的に「∅（空集合）と非空集合の間の遷移問題」と類似

#### 物理学者の視点
- **エネルギー保存則の類推**: Gitはデータ損失を防ぐために切り替えを拒否
- 3つのファイルが「競合状態」にある：両ブランチで異なるバージョンが存在
- 作業ツリーの変更をコミットせずに切り替えると「情報のエントロピー増大」（データ損失）が発生
- システムは平衡状態を保つために操作を拒否

#### 計算機科学者の視点
- **根本原因**: Orphan branchとステージング領域の状態不整合
- `feature/initial-design`でファイルをステージングしたが、コミットせずに`main`へ切り替えた
- Gitのステージング領域はブランチ間で共有されるが、コミットは各ブランチに固有
- 解決策: 現在の状態をコミットしてから切り替える

### 技術的詳細

| 項目 | main | feature/initial-design |
|------|------|------------------------|
| コミット数 | 1 | 0 (orphan) |
| ステージングファイル | あり（持ち越し） | あり（元の場所） |
| 競合ファイル | 3つ | 3つ |

### 解決手順

1. mainブランチで未コミット変更をstash
2. feature/initial-designに切り替え
3. stashをpop
4. 全変更をコミット
5. （必要に応じて）mainにマージ

---

## 目的到達可能性解析（2026-04-09）

### 目的

CANVAで作成されたテンプレートを基に、Instagram用のHTML/CSSを生成する。

### 要件と現在の実装状況

| 要件 | 実装状況 | 備考 |
|------|---------|------|
| 1. タグと画像を送信して構造抽出・DB保存 | ✅ 実装済み | `/api/templates` |
| 2. RAGでベクトル検索（タグ → 構造） | ✅ 実装済み | `TemplateSearchService` |
| 3. プロンプトで文言生成 → 構造に代入 | ✅ 実装済み | `CopyGenerationService` |
| 4. 後から細かな設定（img等）を調整 | ⚠️ 部分実装 | UIで編集機能が必要 |

### 結論: **目的到達可能**

現在の実装でコアフロー（登録→検索→生成→出力）は動作する状態にある。

---

### 詳細解析

#### 1. テンプレート登録フロー (`/api/templates`)

**パス**: `backend/app/main.py:47-108`

```
入力: 画像 + name + manual_tags
  ↓
OpenAI Vision API で構造JSON抽出 (llm.py:13-59)
  ↓
自動タグ生成（atmosphereから単語分割）
  ↓
検索用テキスト生成 → Embedding生成
  ↓
HTML/CSSプレビュー生成 (WholePostRenderer)
  ↓
DB保存（Template テーブル）+ Chroma登録
  ↓
出力: template_id, structure_json, preview_html/css
```

**評価**: ✅ 正常動作。CANVAの画像を適切に解析可能。

#### 2. テンプレート検索フロー

**パス**: `backend/app/services/template_search_service.py`

```
入力: tags (ユーザー指定)
  ↓
手動タグ完全一致 → 手動タグ部分一致 → 自動タグ一致 → ベクトル類似
  ↓
スコア計算: manual*100 + partial*40 + auto*10 + semantic*0.1
  ↓
出力: 上位候補テンプレートリスト
```

**評価**: ✅ タグ優先順位が明確で、ユーザーの意図に沿った検索が可能。

#### 3. 文言生成フロー

**パス**: `backend/app/services/copy_generation_service.py`

```
入力: structure_json + prompt + tags
  ↓
スロット（headline, subheadline, cta等）を抽出
  ↓
各スロットに対してLLMで文言生成
  ↓
max_chars制約に収まるよう短縮
  ↓
出力: 各スロットの文言辞書
```

**評価**: ✅ 文字数制約を守りながら文言生成。

#### 4. HTML/CSSレンダリング

**パス**: `backend/app/services/whole_post_renderer.py`

```
入力: filled_structure_json
  ↓
canvasサイズ反映 → 各要素をHTML/CSSに変換
  ↓
出力: output_html, output_css
```

**評価**: ✅ プレビュー可能なHTML/CSS出力。

---

### ギャップ分析（改善が必要な箇所）

| # | 項目 | 現状 | 必要な対応 | 優先度 |
|---|------|------|-----------|--------|
| 1 | 画像要素（imgタグ）の後編集 | 未実装 | フロントエンドで編集UI追加 | 高 |
| 2 | テンプレート登録APIのユニットテスト | 未実装 | TDD_PLAN.mdに記載済み | 中 |
| 3 | LangChain統合 | スケルトンのみ | CLAUDE.mdの方針では必須 | 低 |
| 4 | PostgreSQL + pgvector | SQLite + Chroma | 本番移行時に対応 | 低 |

---

### テスト状況

**TDD_PLAN.md チェックリストより**:

- [x] 受け入れテスト
- [ ] テンプレート登録APIのユニットテスト ← **未実装**
- [x] テンプレート検索ロジックのユニットテスト
- [x] 文言生成ロジックのユニットテスト
- [x] HTML/CSSレンダラのユニットテスト
- [x] 生成APIの統合テスト

---

### 次のアクション

1. **高優先度**: 画像要素の後編集機能をフロントエンドに追加
2. **中優先度**: テンプレート登録APIのユニットテスト追加（TDD遵守）
3. **低優先度**: LangChain統合、PostgreSQL移行

---

# エラー分析レポート

---

## Git変更件数10000件超の問題（2026-04-07 更新）

### 症状

VS CodeのGit変更履歴に約10000件以上のファイルが表示される。再起動しても直らない。

### 発生箇所

- 場所: `/Users/kazukiyanagi/Desktop/3_学習/一般学習/make-images/.gitignore`
- 問題: `.gitignore`が不完全で、`venv/`や`node_modules/`が除外されていない

### 技術的な解析

1. **make-imagesの.gitignoreの内容（修正前）**
   ```
   *.jpg
   *.png
   *.gif
   ```

2. **問題点**
   - `venv/`が除外されていない → backend/venv/配下の約10000件のファイルが未追跡
   - `node_modules/`が除外されていない → frontend/node_modules/配下のファイルが未追跡
   - `__pycache__/`が除外されていない → Pythonキャッシュファイルが未追跡
   - `.env`が除外されていない → 環境変数ファイルが未追跡

3. **実際の未追跡ファイル数の内訳**
   ```
   backend/venv/    → 約10000件以上（site-packages含む）
   frontend/node_modules/ → 多数
   __pycache__/     → 複数
   .env             → 1件
   ```

### 根本原因

**make-imagesプロジェクトの`.gitignore`が不完全**

- Python仮想環境（venv）が除外されていなかった
- Node.jsの依存関係（node_modules）が除外されていなかった
- 一般的な開発ファイル（__pycache__、.env等）が除外されていなかった

### 解決策

`.gitignore`に以下を追加:
- `venv/`
- `node_modules/`
- `__pycache__/`
- `*.pyc`
- `.env`
- `.DS_Store`

---

## Git変更件数10000件超の問題（2026-04-07 旧分析）

### 症状

VS CodeのGit変更履歴に約10000件以上のファイルが表示される。

### 発生箇所

- 場所: `/Users/kazukiyanagi/Desktop/3_学習/一般学習/`（親ディレクトリ）
- 関連ファイル: `.gitignore`

### 技術的な解析

1. **リポジトリ構造**
   ```
   /Users/kazukiyanagi/Desktop/3_学習/一般学習/  ← 親Gitリポジトリ
   └── make-images/                              ← ネストした子Gitリポジトリ（本プロジェクト）
   ```

2. **大規模ディレクトリの内訳**

   | ディレクトリ | ファイル数 | サイズ |
   |-------------|-----------|--------|
   | CNN_SVM_test/ | 29,299 | 842MB |
   | test_YOLO26/ | 多数 | 1.9GB |
   | 車両判定/ | 多数 | 1.7GB |
   | Haystak/ | 多数 | 1.4GB |

3. **現在の.gitignore（不十分）**
   ```
   CNN_SVM_test/data/  ← dataディレクトリのみ除外
   test_YOLO26/        ← 除外済み
   make-images/        ← 除外済み
   ```

   `CNN_SVM_test/`全体や`車両判定/`、`Haystak/`が除外されていない。

### 根本原因

**親ディレクトリの`.gitignore`が不完全**

- `CNN_SVM_test/data/`のみ除外しているが、他のサブディレクトリ（29,299ファイル）が未除外
- `車両判定/`、`Haystak/`などの大規模ディレクトリが未除外
- VS Codeが親リポジトリの変更も表示するため、合算で10000件超に見える

### make-imagesプロジェクトの実際の変更

```
$ cd make-images && git status --porcelain | wc -l
9
```

本プロジェクトの変更は**わずか9件**のみ。

---

## zsh シェル警告（2026-04-07）

### 症状

```
npm:unset: no such hash table element: npm
```

フロントエンド起動時（`npm run dev`）にこの警告が表示される。

### 発生箇所

- ファイル: zshの設定ファイル（`.zshrc`など）
- 行番号: 不明（シェル初期化時）
- 関数: npm関連のハッシュテーブル操作

### 技術的な解析

1. **zshのハッシュテーブル**
   - zshはコマンドパスをハッシュテーブルにキャッシュする
   - `unhash npm`または類似のコマンドが存在しない`npm`エントリを削除しようとしている

2. **原因の可能性**
   - `.zshrc`でnpmのパスを`unhash`しようとしているが、まだハッシュされていない
   - nvm（Node Version Manager）の設定が不完全
   - シェルプラグイン（oh-my-zsh等）の設定問題

### 根本原因

**シェル設定の問題であり、アプリケーションのエラーではない**

Viteは正常に起動しており、フロントエンドアプリケーションは動作している：
```
VITE v8.0.4  ready in 12174 ms
➜  Local:   http://localhost:5174/
```

### 影響

- **なし**: 警告のみでアプリケーションの動作に影響はない
- フロントエンドは正常に起動し、利用可能

---

# 500エラー分析レポート

## 調査日時

2026-04-07

## エラー概要

バックエンドAPIが500 Internal Server Errorを返し、アプリケーションが正常に動作しない状態。

## 根本原因

**Python 3.14の互換性問題**

仮想環境（venv）がPython 3.14で作成されていたが、以下のパッケージがPython 3.14をサポートしていなかった：

| パッケージ | 問題 |
|-----------|------|
| asyncpg | Python 3.14でのビルドに失敗 |
| pydantic-core | Python 3.14でのビルドに失敗 |
| tiktoken | PyO3のPython 3.14サポート未対応（最大3.12） |

## エラートレースバック

```
from pgvector.sqlalchemy import Vector
  → pgvector/utils/__init__.py
    → numpy/__init__.py
      → numpy/linalg/linalg.py
        → TimeoutError: [Errno 60] Operation timed out
```

numpyのインポート時にファイルI/Oでタイムアウトが発生。これはPython 3.14との互換性問題に起因する可能性が高い。

## 依存関係の問題

`requirements.txt`に記載されたバージョンはPython 3.12向けに指定されていたが、venvが誤ってシステムデフォルトのPython 3.14で作成されていた。

```
# pip install 実行時のエラー
error: the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.12)
```

## 解決策

### 実施した修正

1. **venvの再作成**（Python 3.12を使用）
   ```bash
   rm -rf venv
   /opt/homebrew/bin/python3.12 -m venv venv
   ```

2. **依存関係の再インストール**
   ```bash
   ./venv/bin/pip install --upgrade pip
   ./venv/bin/pip install -r requirements.txt
   ```

### 結果

- APIが正常に動作することを確認（HTTP 200 OK）
- `/api/generate`エンドポイントがHTML/CSSを正しく生成

## 再発防止策

1. **Python バージョンの明示的な指定**
   - `README.md`または`CONTRIBUTING.md`に必要なPythonバージョンを明記
   - `.python-version`ファイルの作成を推奨

2. **CI/CDでのバージョンチェック**
   - テスト実行前にPythonバージョンを確認するステップを追加

3. **pyproject.tomlの活用**
   - `python_requires`でサポートバージョンを明示

## 検証結果

```bash
# テストリクエスト
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"tags": ["採用", "ポップ"], "prompt": "新卒採用の画像を作成してください"}'

# レスポンス: HTTP 200 OK
# 正常にHTML/CSSが生成された
```

# Make Images - Generative Design System

## 【最新実装】TDDベース API の実行方法

今回作成した「設計レイアウト構造の抽出＆プロンプトからのデザイン生成バックエンドAPI」を正しく実行・検証するための手順です。

### 1. 単体テストの実行 (TDDの検証用)
「いかなる状況でもテストコードを変更しない」という条件のもとで構築したシステムが、正しくパスするかを検証します。
```bash
cd backend
source venv/bin/activate
# テスト時はダミーのキーを指定して実行します
export OPENAI_API_KEY="mock_key"
python -m pytest tests/test_api.py -v
```

### 2. バックエンドサーバーの起動 (本番連携用)
実際のOpenAI API（GPT-4o / Vector Embedding）を用いて稼働させるための起動コマンドです。
```bash
cd backend
source venv/bin/activate
# 実際のAPIキー環境変数をエクスポートしてください（必須）
export OPENAI_API_KEY="your_actual_openai_api_key_here"
uvicorn app.main:app --reload
```
起動後、ブラウザで **http://localhost:8000/docs** にアクセスすると、FastAPIが自動生成したSwagger UI（APIテスト画面）が表示され、ブラウザ上から画像のアップロードやJSONの生成をGUIでテスト可能です。

### 3. Curlを使用した動作確認例

**① 画像テンプレートのアップロード（レイアウト解析・ベクトル登録）**
```bash
curl -X 'POST' \
  'http://localhost:8000/api/templates' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@/パス/トゥ/あなたの画像.jpg' \
  -F 'name=サンプルテンプレート' \
  -F 'manual_tags=["採用","インタビュー"]'
```
-> 成功すると `template_id` が返却されます。

**② PPTXテンプレート + 正解PNG の同時アップロード**
```bash
curl -X 'POST' \
  'http://localhost:8000/api/templates' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@/パス/トゥ/テンプレート.pptx' \
  -F 'reference_image=@/パス/トゥ/正解画像.png' \
  -F 'name=サンプルテンプレート' \
  -F 'manual_tags=["採用","インタビュー"]'
```
-> `pptx` を構造の一次ソースにし、`reference_image` を見本としてLLMが差分補正します。

**③ デザインパラメータの生成（プロンプト送信）**
```bash
curl -X 'POST' \
  'http://localhost:8000/api/generate' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "tags": ["春", "セール", "ポップ"],
  "prompt": "春のセールのために、ピンクと桜を基調としたポップなデザイン"
}'
```
-> バックエンド処理でタグ検索と文言生成が行われ、HTML/CSSプレビューが出力されます。

---

## 過去の実装 / アーキテクチャ資料
（以下は以前のプロジェクト仕様等のバックアップです）
## クイックスタート

### 1. バックエンド起動

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

サーバーが http://localhost:8000 で起動します。

### 2. フロントエンド起動

```bash
cd frontend
npm run dev
```

ブラウザで http://localhost:5173 を開きます。

### 3. 使い方

1. タグを入力（例: `新卒採用` `ポップ`）してEnter
2. プロンプトを入力（例: `若者向けの明るい採用告知`）
3. 「生成する」ボタンをクリック
4. 生成されたHTML/CSSがプレビューされます

---

## セットアップ（初回のみ）

### バックエンド

```bash
cd backend

# Python 3.12推奨
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 環境変数設定（本番モードで使用）
cp .env.example .env
# .envにAPIキーを設定
```

### フロントエンド

```bash
cd frontend
npm install
```

---

## 開発コマンド

### テスト実行

```bash
cd backend
source venv/bin/activate
pytest                    # 全テスト
pytest tests/unit/        # ユニットテストのみ
pytest -v                 # 詳細表示
```

### ビルド

```bash
cd frontend
npm run build
```

---

## アーキテクチャ

### 3フェーズワークフロー

```
【入力】タグ + プロンプト

Phase 1: embeddingベクトル検索
  └─ タグをembeddingし、類似コンポーネントをDBから取得

Phase 2: LLM競合解決
  └─ 同一roleのコンポーネントが複数ある場合、LLMが文脈で選択

Phase 3: セクションテンプレート合成
  └─ 選択されたコンポーネントをrole順にHTML/CSSに合成

【出力】HTML/CSS
```

### 技術スタック

| Layer | Technology |
|-------|------------|
| Backend | Python + FastAPI |
| Workflow | LangChain |
| Database | PostgreSQL + pgvector |
| LLM | Claude API |
| Embedding | OpenAI Embeddings |
| Frontend | React + TypeScript + Vite |
| Testing | pytest (TDD) |

---

## ディレクトリ構成

```
make-images/
├── backend/
│   ├── app/
│   │   ├── api/           # APIエンドポイント
│   │   ├── models/        # SQLAlchemyモデル
│   │   ├── services/      # ビジネスロジック
│   │   ├── workflows/     # LangChainワークフロー
│   │   └── config.py      # 設定
│   ├── tests/
│   │   ├── unit/          # ユニットテスト
│   │   └── integration/   # 統合テスト
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/    # Reactコンポーネント
│       ├── api.ts         # API呼び出し
│       └── App.tsx        # メインアプリ
└── Planning/              # 設計書
```

---

## 現在の状態

- **デモモード**: DBなしでサンプルコンポーネントを使用
- **本番モード**: PostgreSQL + pgvector + APIキーが必要

本番モードを有効にするには、`.env`にAPIキーを設定し、DBをセットアップしてください。

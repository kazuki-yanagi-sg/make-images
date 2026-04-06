# Instagram PR Image Generator

## 開発ルール

### TDD絶対遵守

**必ずテストを先に書いてから実装すること**

```
1. RED:    失敗するテストを書く
2. GREEN:  テストが通る最小限のコードを書く
3. REFACTOR: コードを整理する（テストは通ったまま）
```

**理由**: リファクタリングを確実に進めるため。テストがあれば安心してコードを改善できる。

**禁止事項**:
- テストなしで実装コードを書くこと
- テストを後回しにすること
- テストが通らない状態でコミットすること
- コードを基準にしてテスト設計書を変更すること

### テスト設計書 = 正（Single Source of Truth）

```
テスト設計書 > 実装コード
```

- テスト設計書（TDD_PLAN.md）が仕様の真実
- 実装がテストと合わない → **実装を修正**
- テストを実装に合わせて変えるのは**禁止**

### ブランチ管理

- ローカル開発のみだがブランチ管理は意識する
- feature/xxx でブランチを切って作業
- mainへのマージはテストが通ってから

---

## プロジェクト方針

### スコープ
- **単一企業向けプロトタイプ**（マルチテナント不要）
- **認証なし**
- **ローカル環境のみ**（デプロイなし）
- **フロントエンド必須**（視覚的に動くものが必要）

### 実装するもの: LLMワークフロー

本プロジェクトは**ワークフロー**を実装する。
LangChainを使用してワークフローを構築する。

---

## 概要

Gammaスタイルの「ハイブリッド型デザインエンジン」

**ハイブリッド方式**:
- **セマンティックデザイン（トーン制御）**: ユーザープロンプトの意味を解析して競合解決
- **セクションテンプレート（構造制御）**: 固定のHTML構造にコンポーネントを合成

---

## コアコンセプト

### ベーステンプレート方式

- 事前にHTML/CSSテンプレートを用意
- 画像は「参考」として構造・タグの解析に使用
- 要件定義の揺らぎを防ぐため、この方式で固定

### コンポーネント粒度

**文字・画像を差し替えるだけで即使えるレベル**

---

## ワークフロー

### 登録フロー

```
画像 → LLMが構造・タグを解析 → 手動でHTML/CSSテンプレートを紐付け → DB保存
```

### 生成フロー（3 Phase）

```
【入力】
├─ タグ（複数）: ["recruitment", "playful", "minimal"]
└─ ユーザープロンプト: "新卒採用を開始しました！若い力を求めています"
```

#### Phase 1: embeddingベクトル検索

ユーザー入力タグをembeddingし、類似コンポーネントをDBから取得

**なぜembedding検索か？**
- ユーザーは決まったタグを入力してくれるとは限らない
- 例: 「#新入社員」と「#新卒社員」→ 同じ意味だが表記が違う
- → embedding類似検索で表記揺れに対応

```
入力タグ: ["新卒採用", "ポップ", "シンプル"]
    ↓ embedding
各タグに類似するコンポーネントを取得
    ↓
├─ 新卒採用 → [comp_A(header), comp_B(cta), comp_C(body)]
├─ ポップ   → [comp_D(color), comp_E(font)]
└─ シンプル → [comp_F(layout), comp_G(header)]

→ 全候補: [comp_A, comp_B, comp_C, comp_D, comp_E, comp_F, comp_G]
```

#### Phase 2: LLMで競合解決（セマンティックデザイン）

同一の役割を持つコンポーネントが複数候補に入った場合、LLMが文脈で選択

```
競合検出: comp_A(header) vs comp_G(header)
    ↓
ユーザープロンプトの文脈を解析
    ↓
文脈的にcomp_Aを採用
```

#### Phase 3: セクションテンプレートで合成

選択されたコンポーネントを役割ごとにセクションテンプレートに組み込み

```
セクションテンプレート:
├─ header: comp_A
├─ body:   comp_C
├─ cta:    comp_B
├─ color:  comp_D
├─ font:   comp_E
└─ layout: comp_F
    ↓
最終HTML/CSS生成
```

```
【出力】
HTML/CSS
```

---

## 技術スタック

| Layer | Technology |
|-------|------------|
| Backend | Python + FastAPI |
| Workflow | **LangChain** |
| Database | PostgreSQL + pgvector |
| LLM | Claude API |
| Embedding | OpenAI Embeddings |
| Frontend | React + TypeScript |
| Testing | pytest (TDD) + Docker PostgreSQL |

---

## 設計書

- [Planning/ARCHITECTURE.md](./Planning/ARCHITECTURE.md) - アーキテクチャ
- [Planning/DATABASE.md](./Planning/DATABASE.md) - DBスキーマ
- [Planning/API.md](./Planning/API.md) - API仕様
- [Planning/PROMPTS.md](./Planning/PROMPTS.md) - メタプロンプト
- [Planning/TDD_PLAN.md](./Planning/TDD_PLAN.md) - TDD計画

---

## 開発コマンド

```bash
# テスト実行
cd backend && pytest

# サーバー起動
cd backend && uvicorn app.main:app --reload

# フロントエンド起動
cd frontend && npm run dev
```

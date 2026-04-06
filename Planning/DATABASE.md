# データベース設計書

## 1. ER図

```
┌─────────────────────────────────────┐
│           components                 │
├─────────────────────────────────────┤
│ id (PK)                              │
│ name                                 │
│ role                                 │  ← header, body, cta, color, font, layout, etc.
│ description                          │  ← タグとしてembedding検索に使用
│ template_html                        │
│ template_css                         │
│ slots (JSONB)                        │
│ embedding (VECTOR)                   │  ← descriptionのembedding
│ source_image_url                     │
│ created_at                           │
│ updated_at                           │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│          generations                 │
├─────────────────────────────────────┤
│ id (PK)                              │
│ input_tags (TEXT[])                  │
│ input_prompt (TEXT)                  │
│ selected_components (UUID[])         │
│ output_html (TEXT)                   │
│ output_css (TEXT)                    │
│ slot_values (JSONB)                  │
│ aspect_ratio                         │
│ created_at                           │
│ updated_at                           │
└─────────────────────────────────────┘
```

## 2. テーブル定義

### 2.1 components（コンポーネント）

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| name | VARCHAR(255) | NOT NULL | コンポーネント名 |
| role | VARCHAR(50) | NOT NULL | 役割（header, body, cta, etc.） |
| description | TEXT | NOT NULL | タグ/説明（embedding検索用） |
| template_html | TEXT | | HTMLテンプレート |
| template_css | TEXT | | CSSテンプレート |
| slots | JSONB | DEFAULT '{}' | スロット定義 |
| embedding | VECTOR(1536) | | descriptionのembedding |
| source_image_url | VARCHAR(500) | | 元画像URL |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() | |

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE components (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    template_html TEXT,
    template_css TEXT,
    slots JSONB DEFAULT '{}',
    embedding VECTOR(1536),
    source_image_url VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- embeddingでの類似検索用インデックス
CREATE INDEX idx_components_embedding ON components
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- roleでの絞り込み用インデックス
CREATE INDEX idx_components_role ON components(role);
```

**description の例**:
```
"新卒採用 採用 リクルート フレッシュ 若手 ポップ 明るい"
```
→ このテキストをembeddingし、ユーザー入力タグとの類似検索に使用

**slots の構造例**:
```json
{
  "title": {
    "type": "text",
    "max_chars": 20,
    "placeholder": "タイトルを入力"
  },
  "bg_color": {
    "type": "color",
    "default": "#FF6B6B"
  },
  "image": {
    "type": "image",
    "aspect_ratio": "16:9"
  }
}
```

### 2.2 generations（生成履歴）

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | |
| input_tags | TEXT[] | NOT NULL | 入力タグ配列 |
| input_prompt | TEXT | NOT NULL | ユーザープロンプト |
| selected_components | UUID[] | | 使用したコンポーネントID |
| output_html | TEXT | | 生成されたHTML |
| output_css | TEXT | | 生成されたCSS |
| slot_values | JSONB | | 各スロットに入れた値 |
| aspect_ratio | VARCHAR(10) | DEFAULT '1:1' | 1:1, 4:5, 9:16 |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() | |

```sql
CREATE TABLE generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    input_tags TEXT[] NOT NULL,
    input_prompt TEXT NOT NULL,
    selected_components UUID[],
    output_html TEXT,
    output_css TEXT,
    slot_values JSONB,
    aspect_ratio VARCHAR(10) DEFAULT '1:1' CHECK (aspect_ratio IN ('1:1', '4:5', '9:16')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 3. クエリ例

### 3.1 Phase 1: embeddingベクトル検索

```sql
-- ユーザー入力タグをembeddingしたベクトル $1 で類似検索
SELECT
    c.*,
    1 - (c.embedding <=> $1) AS similarity
FROM components c
WHERE 1 - (c.embedding <=> $1) > 0.5  -- 類似度閾値
ORDER BY similarity DESC
LIMIT 20;
```

### 3.2 役割ごとの候補取得

```sql
-- 特定の役割のコンポーネントのみ取得
SELECT
    c.*,
    1 - (c.embedding <=> $1) AS similarity
FROM components c
WHERE c.role = 'header'
  AND 1 - (c.embedding <=> $1) > 0.5
ORDER BY similarity DESC
LIMIT 5;
```

## 4. サンプルデータ

```sql
INSERT INTO components (name, role, description, template_html, template_css, slots) VALUES
(
    '採用ヘッダー_ポップ',
    'header',
    '新卒採用 採用 リクルート ポップ 明るい 若手 フレッシュ',
    '<div class="header" style="background: {{bg_color}}"><h1>{{title}}</h1></div>',
    '.header { padding: 20px; text-align: center; }',
    '{"title": {"type": "text", "max_chars": 20}, "bg_color": {"type": "color", "default": "#FF6B6B"}}'
),
(
    '採用ヘッダー_フォーマル',
    'header',
    '新卒採用 採用 リクルート フォーマル 堅い ビジネス 企業',
    '<div class="header formal" style="background: {{bg_color}}"><h1>{{title}}</h1></div>',
    '.header.formal { padding: 30px; text-align: left; font-family: serif; }',
    '{"title": {"type": "text", "max_chars": 25}, "bg_color": {"type": "color", "default": "#1a1a2e"}}'
);
```

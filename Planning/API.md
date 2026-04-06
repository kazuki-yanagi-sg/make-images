# API設計書

## Base URL
```
http://localhost:8000/api/v1
```

## 1. コンポーネント管理 API

### 1.1 POST /components/analyze
コンポーネント（HTML/CSS or 画像）を解析してDBに登録

**Request:**
```json
{
  "name": "recruitment_header_01",
  "type": "html_css",
  "source_html": "<div class='header'>...</div>",
  "source_css": ".header { background: #1a1a2e; ... }",
  "manual_tags": ["recruitment", "formal"]  // optional
}
```

または画像の場合:
```json
{
  "name": "event_card_01",
  "type": "image",
  "source_image_url": "https://example.com/design.png",
  "manual_tags": ["event", "playful"]
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "recruitment_header_01",
  "analyzed_structure": {
    "layout": { "type": "vertical", "sections": ["header", "main"] },
    "colors": { "primary": "#1a1a2e", "accent": "#e94560" },
    "mood": ["professional", "modern"]
  },
  "auto_tags": [
    { "name": "recruitment", "confidence": 0.92 },
    { "name": "formal", "confidence": 0.88 },
    { "name": "minimal", "confidence": 0.75 }
  ],
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 1.2 GET /components
コンポーネント一覧取得

**Query Parameters:**
- `tags`: カンマ区切りのタグ（例: `recruitment,formal`）
- `type`: `html_css` or `image`
- `limit`: 件数（default: 20）
- `offset`: オフセット

**Response:**
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "recruitment_header_01",
      "type": "html_css",
      "tags": ["recruitment", "formal", "minimal"],
      "thumbnail_url": "https://..."
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### 1.3 GET /components/{id}
コンポーネント詳細取得

### 1.4 DELETE /components/{id}
コンポーネント削除

---

## 2. タグ管理 API

### 2.1 GET /tags
タグ一覧取得

**Response:**
```json
{
  "items": [
    { "id": "...", "name": "recruitment", "category": "usage", "count": 15 },
    { "id": "...", "name": "formal", "category": "tone", "count": 23 }
  ]
}
```

### 2.2 POST /tags
新規タグ作成

**Request:**
```json
{
  "name": "tech",
  "category": "usage",
  "description": "IT/テクノロジー関連の投稿"
}
```

---

## 3. 画像生成 API

### 3.1 POST /generate
タグとコンテンツから画像を生成

**Request:**
```json
{
  "tags": ["recruitment", "formal"],
  "content": {
    "title": "エンジニア募集中！",
    "body": "私たちと一緒に未来を作りませんか？\n新卒・中途どちらも歓迎です。",
    "cta": "詳細はプロフィールから",
    "hashtags": ["採用", "エンジニア", "新卒採用"]
  },
  "options": {
    "aspect_ratio": "1:1",
    "style_preference": "modern"
  }
}
```

**Response:**
```json
{
  "id": "gen_123456",
  "status": "completed",
  "matched_components": [
    {
      "id": "550e8400-...",
      "name": "recruitment_header_01",
      "match_score": 0.95
    }
  ],
  "output": {
    "image_url": "https://storage.example.com/generated/gen_123456.png",
    "html": "<div class='ig-post'>...</div>",
    "css": ".ig-post { ... }",
    "sections": {
      "header": { "text": "エンジニア募集中！", "char_count": 9 },
      "main": { "text": "私たちと一緒に...", "char_count": 35 },
      "footer": { "text": "#採用 #エンジニア", "cta": "詳細はプロフィールから" }
    }
  },
  "created_at": "2024-01-15T10:35:00Z"
}
```

### 3.2 GET /generate/{id}
生成結果取得

### 3.3 GET /generate/history
生成履歴一覧

---

## 4. 類似検索 API

### 4.1 POST /components/search
セマンティック検索でコンポーネントを検索

**Request:**
```json
{
  "query": "明るくポップな採用告知のデザイン",
  "limit": 5
}
```

**Response:**
```json
{
  "items": [
    {
      "id": "...",
      "name": "recruitment_pop_01",
      "similarity": 0.89,
      "tags": ["recruitment", "playful", "colorful"]
    }
  ]
}
```

---

## 5. エラーレスポンス

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "タグ 'unknown_tag' は存在しません",
    "details": {
      "field": "tags",
      "value": "unknown_tag"
    }
  }
}
```

**エラーコード:**
| Code | HTTP Status | Description |
|------|-------------|-------------|
| INVALID_INPUT | 400 | 入力値不正 |
| NOT_FOUND | 404 | リソース未発見 |
| ANALYSIS_FAILED | 500 | LLM解析失敗 |
| GENERATION_FAILED | 500 | 画像生成失敗 |

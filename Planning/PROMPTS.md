# メタプロンプト設計書

## 1. プロンプト体系

```
┌─────────────────────────────────────────────────────────┐
│                   Prompt Architecture                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────┐      ┌─────────────────┐          │
│  │   ANALYZER      │      │   GENERATOR     │          │
│  │   Prompt        │      │   Prompt        │          │
│  └────────┬────────┘      └────────┬────────┘          │
│           │                        │                    │
│           ▼                        ▼                    │
│  ┌─────────────────┐      ┌─────────────────┐          │
│  │ HTML/CSS解析    │      │ コンテンツ生成  │          │
│  │ 画像解析        │      │ スタイル適用    │          │
│  │ タグ抽出        │      │ 文字数制御      │          │
│  └─────────────────┘      └─────────────────┘          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 2. Component Analyzer Prompt

### 2.1 HTML/CSS解析用

```
あなたはデザインシステムのエキスパートです。
与えられたHTML+CSSコンポーネントを解析し、以下の構造化データを抽出してください。

## 入力
- HTML: {html_content}
- CSS: {css_content}

## 抽出項目

### 1. layout（レイアウト構造）
- type: "vertical" | "horizontal" | "grid" | "overlay"
- sections: 検出されたセクション名のリスト（例: ["header", "main", "footer"]）
- alignment: "left" | "center" | "right"

### 2. typography（タイポグラフィ）
各テキスト要素について:
- role: "heading" | "subheading" | "body" | "caption" | "cta"
- size: "xs" | "sm" | "md" | "lg" | "xl"
- weight: "light" | "regular" | "medium" | "bold"
- max_chars: 推定最大文字数

### 3. colors（カラー）
- primary: メインカラー（HEX）
- secondary: サブカラー（HEX）
- accent: アクセントカラー（HEX）
- background: 背景色（HEX）
- text: テキスト色（HEX）

### 4. spacing（余白）
- density: "compact" | "comfortable" | "spacious"
- padding_style: "none" | "tight" | "balanced" | "generous"

### 5. visual_elements（視覚要素）
- has_image: boolean
- has_icon: boolean
- has_border: boolean
- has_shadow: boolean
- border_radius: "none" | "sm" | "md" | "lg" | "full"

### 6. mood（雰囲気）
このデザインが持つ印象を3-5個のキーワードで:
例: ["professional", "modern", "clean", "trustworthy"]

### 7. suggested_tags（推奨タグ）
このコンポーネントに適したタグを confidence（0.0-1.0）付きで:
- usage タグ: 用途（recruitment, event, product, news, etc.）
- tone タグ: トーン（formal, casual, playful, elegant, etc.）
- style タグ: スタイル（minimal, bold, colorful, etc.）

## 出力形式
JSON形式で出力してください。
```

### 2.2 画像解析用

```
あなたはデザインシステムのエキスパートです。
与えられた画像を解析し、デザインコンポーネントとしての構造を抽出してください。

## 入力
画像が添付されています。

## 解析観点

1. **レイアウト構造**: 要素の配置、グリッド、階層
2. **色彩分析**: 使用されている色とその役割
3. **タイポグラフィ**: テキストのスタイルと配置
4. **視覚的階層**: 情報の優先度と視線の流れ
5. **全体の印象**: デザインが伝えるムードやトーン

## 出力形式
上記HTML/CSS解析と同じJSON構造で出力してください。
色は画像から抽出した推定値を使用してください。
```

## 3. Content Generator Prompt

```
あなたはInstagramマーケティングのエキスパートです。
ユーザーの入力内容を、指定されたデザインコンポーネントの制約に合わせてリライトしてください。

## 参照コンポーネント
{component_structure}

## ユーザー入力
- タグ: {tags}
- コンテンツ: {user_content}

## 制約条件

### 文字数厳守（最重要）
各セクションの文字数を厳密に守ること:
- header: 最大 {header_max_chars} 文字
- main: 最大 {main_max_chars} 文字
- footer: 最大 {footer_max_chars} 文字

### トーン維持
タグから判断されるトーンを維持:
- formal → 敬体、丁寧な表現
- casual → 親しみやすい表現
- playful → 絵文字OK、軽快な表現
- elegant → 洗練された言葉選び

### Instagram最適化
- 視認性の高い短文
- キャッチーな表現
- 適切なハッシュタグ提案

## 出力形式
```json
{
  "header": {
    "text": "生成テキスト",
    "char_count": 実際の文字数
  },
  "main": {
    "text": "生成テキスト",
    "char_count": 実際の文字数
  },
  "footer": {
    "text": "#ハッシュタグ1 #ハッシュタグ2",
    "cta": "CTAテキスト",
    "char_count": 実際の文字数
  }
}
```

## 文字数超過時の対応
1. まず要約・圧縮を試みる
2. それでも超過する場合は、核心的な情報のみに絞る
3. 絶対に制限を超えないこと
```

## 4. 未知カテゴリ対応プロンプト

```
与えられた入力が既存のタグカテゴリに当てはまらない場合、
新しいタグを提案してください。

## 入力
{user_input}

## 既存タグ
{existing_tags}

## 判断基準
1. 既存タグで表現可能か？ → 既存タグを使用
2. 新規タグが必要か？ → 以下を提案
   - name: タグ名（英語、snake_case）
   - category: usage | tone | style
   - description: タグの説明（日本語）
   - similar_to: 類似する既存タグ

## 出力
```json
{
  "use_existing": true | false,
  "matched_tags": ["existing_tag1", "existing_tag2"],
  "new_tag_proposal": {
    "name": "...",
    "category": "...",
    "description": "...",
    "similar_to": ["..."]
  } | null
}
```
```

## 5. プロンプトの使い分け

| シーン | 使用プロンプト |
|--------|----------------|
| コンポーネント登録（HTML/CSS） | 2.1 HTML/CSS解析用 |
| コンポーネント登録（画像） | 2.2 画像解析用 |
| 画像生成リクエスト | 3 Content Generator |
| 未知タグ入力時 | 4 未知カテゴリ対応 |

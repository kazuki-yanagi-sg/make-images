# TDD実装計画書

## 1. TDDルール（絶対遵守）

```
1. RED:    失敗するテストを書く
2. GREEN:  テストが通る最小限のコードを書く
3. REFACTOR: コードを整理する（テストは通ったまま）
```

**このドキュメントが正（Single Source of Truth）**
- 実装がテストと合わない → 実装を修正
- テストを実装に合わせて変えるのは禁止

---

## 2. ディレクトリ構成

```
make-images/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPIエントリーポイント
│   │   ├── config.py                  # 設定
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── component.py           # SQLAlchemyモデル
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── component.py           # Pydanticスキーマ
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── embedding_service.py   # OpenAI Embedding
│   │   │   ├── vector_search.py       # Phase 1: ベクトル検索
│   │   │   ├── conflict_resolver.py   # Phase 2: 競合解決
│   │   │   └── template_composer.py   # Phase 3: テンプレート合成
│   │   ├── workflows/
│   │   │   ├── __init__.py
│   │   │   └── generation_workflow.py # LangChainワークフロー
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── components.py
│   │       └── generate.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── unit/
│   │   │   ├── test_embedding_service.py
│   │   │   ├── test_vector_search.py
│   │   │   ├── test_conflict_resolver.py
│   │   │   └── test_template_composer.py
│   │   └── integration/
│   │       ├── test_generation_workflow.py
│   │       └── test_api.py
│   ├── requirements.txt
│   └── docker-compose.yml             # PostgreSQL + pgvector
├── frontend/
│   └── ...
└── Planning/
```

---

## 3. 実装順序

### Phase 0: 基盤セットアップ

#### 0.1 プロジェクト初期化

```python
# tests/unit/test_config.py

def test_config_loads_from_env():
    """環境変数から設定を読み込めること"""
    config = get_config()
    assert config.database_url is not None
    assert config.openai_api_key is not None
```

#### 0.2 DBモデル

```python
# tests/unit/test_models.py

def test_component_model_has_required_fields():
    """Componentモデルが必要なフィールドを持つこと"""
    component = Component(
        name="test",
        role="header",
        description="テスト用ヘッダー"
    )
    assert component.name == "test"
    assert component.role == "header"
    assert component.description == "テスト用ヘッダー"

def test_component_model_has_embedding_field():
    """Componentモデルがembeddingフィールドを持つこと"""
    component = Component(
        name="test",
        role="header",
        description="テスト"
    )
    assert hasattr(component, 'embedding')
```

---

### Phase 1: embeddingベクトル検索

#### 1.1 Embedding Service

```python
# tests/unit/test_embedding_service.py

@pytest.mark.asyncio
async def test_create_embedding_returns_vector():
    """テキストからembeddingベクトルを生成できること"""
    service = EmbeddingService()
    embedding = await service.create_embedding("新卒採用 ポップ")

    assert embedding is not None
    assert len(embedding) == 1536  # OpenAI embedding dimension

@pytest.mark.asyncio
async def test_similar_texts_have_high_similarity():
    """類似テキストは高い類似度を持つこと"""
    service = EmbeddingService()
    emb1 = await service.create_embedding("新卒採用")
    emb2 = await service.create_embedding("新入社員採用")
    emb3 = await service.create_embedding("料理レシピ")

    sim_similar = service.cosine_similarity(emb1, emb2)
    sim_different = service.cosine_similarity(emb1, emb3)

    assert sim_similar > sim_different
```

#### 1.2 Vector Search

```python
# tests/unit/test_vector_search.py

@pytest.mark.asyncio
async def test_search_returns_components_by_similarity(db_session, seed_components):
    """embeddingで類似コンポーネントを検索できること"""
    search = VectorSearchService(db_session)

    results = await search.search(
        query_tags=["新卒採用", "ポップ"],
        limit=10
    )

    assert len(results) > 0
    assert all(hasattr(r, 'similarity') for r in results)
    # 類似度順にソートされていること
    similarities = [r.similarity for r in results]
    assert similarities == sorted(similarities, reverse=True)

@pytest.mark.asyncio
async def test_search_handles_tag_variations(db_session, seed_components):
    """表記揺れに対応できること"""
    search = VectorSearchService(db_session)

    results1 = await search.search(query_tags=["新卒採用"])
    results2 = await search.search(query_tags=["新入社員採用"])

    # 同じ意味のタグで似たコンポーネントが取れること
    ids1 = {r.id for r in results1[:3]}
    ids2 = {r.id for r in results2[:3]}
    assert len(ids1 & ids2) > 0  # 共通のコンポーネントがある
```

---

### Phase 2: LLM競合解決

#### 2.1 Conflict Resolver

```python
# tests/unit/test_conflict_resolver.py

@pytest.mark.asyncio
async def test_detect_conflicts_by_role():
    """同一roleのコンポーネントを競合として検出すること"""
    resolver = ConflictResolver()

    components = [
        Component(id="1", name="header_pop", role="header"),
        Component(id="2", name="header_formal", role="header"),
        Component(id="3", name="body_1", role="body"),
    ]

    conflicts = resolver.detect_conflicts(components)

    assert "header" in conflicts
    assert len(conflicts["header"]) == 2
    assert "body" not in conflicts  # bodyは1つなので競合なし

@pytest.mark.asyncio
async def test_resolve_conflict_selects_one(mock_llm):
    """LLMが文脈に基づいて1つを選択すること"""
    mock_llm.return_value = {"selected_id": "1"}

    resolver = ConflictResolver(llm=mock_llm)

    conflicting = [
        Component(id="1", name="header_pop", role="header"),
        Component(id="2", name="header_formal", role="header"),
    ]

    selected = await resolver.resolve(
        conflicting_components=conflicting,
        user_prompt="若者向けの明るい採用告知",
        role="header"
    )

    assert selected.id == "1"  # ポップな方が選ばれる
```

---

### Phase 3: セクションテンプレート合成

#### 3.1 Template Composer

```python
# tests/unit/test_template_composer.py

def test_compose_merges_components_by_role():
    """役割ごとにコンポーネントを配置すること"""
    composer = TemplateComposer()

    components = [
        Component(role="header", template_html="<header>{{title}}</header>"),
        Component(role="body", template_html="<main>{{content}}</main>"),
        Component(role="cta", template_html="<button>{{cta_text}}</button>"),
    ]

    result = composer.compose(components)

    assert "<header>" in result.html
    assert "<main>" in result.html
    assert "<button>" in result.html

def test_compose_fills_slots():
    """スロットに値を埋め込むこと"""
    composer = TemplateComposer()

    component = Component(
        role="header",
        template_html="<h1>{{title}}</h1>",
        slots={"title": {"type": "text", "max_chars": 20}}
    )

    result = composer.fill_slots(
        component=component,
        values={"title": "新卒採用開始！"}
    )

    assert "<h1>新卒採用開始！</h1>" in result

def test_compose_respects_max_chars():
    """文字数制限を守ること"""
    composer = TemplateComposer()

    component = Component(
        role="header",
        template_html="<h1>{{title}}</h1>",
        slots={"title": {"type": "text", "max_chars": 10}}
    )

    result = composer.fill_slots(
        component=component,
        values={"title": "これは非常に長いタイトルです"}
    )

    # 10文字以内に切り詰められること
    assert len(result.slot_values["title"]) <= 10
```

---

### Phase 4: ワークフロー統合

#### 4.1 Generation Workflow (LangChain)

```python
# tests/integration/test_generation_workflow.py

@pytest.mark.asyncio
async def test_full_workflow(db_session, seed_components, mock_llm):
    """全フェーズを通したワークフローが動作すること"""
    workflow = GenerationWorkflow(db_session, mock_llm)

    result = await workflow.run(
        tags=["新卒採用", "ポップ"],
        user_prompt="若者向けの明るい採用告知を作りたい",
        aspect_ratio="1:1"
    )

    assert result.output_html is not None
    assert result.output_css is not None
    assert len(result.selected_components) > 0

@pytest.mark.asyncio
async def test_workflow_handles_no_conflicts(db_session, seed_components_no_conflict):
    """競合がない場合もワークフローが動作すること"""
    workflow = GenerationWorkflow(db_session)

    result = await workflow.run(
        tags=["ユニーク"],
        user_prompt="テスト"
    )

    assert result.output_html is not None
```

---

### Phase 5: API

```python
# tests/integration/test_api.py

@pytest.mark.asyncio
async def test_post_generate(client, seed_components):
    """POST /api/generate でHTML/CSSを生成できること"""
    response = await client.post("/api/generate", json={
        "tags": ["新卒採用", "ポップ"],
        "prompt": "若者向けの採用告知",
        "aspect_ratio": "1:1"
    })

    assert response.status_code == 200
    data = response.json()
    assert "output_html" in data
    assert "output_css" in data
    assert "selected_components" in data
```

---

## 4. Fixtures

```python
# tests/conftest.py

import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    """テスト用PostgreSQLコンテナ（pgvector付き）"""
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        yield postgres

@pytest.fixture
async def db_session(postgres_container):
    """DBセッション"""
    # ... セットアップ

@pytest.fixture
def mock_llm(mocker):
    """Claude APIモック"""
    return mocker.patch("app.services.conflict_resolver.call_claude")

@pytest.fixture
async def seed_components(db_session):
    """テスト用コンポーネント"""
    components = [
        Component(
            name="採用ヘッダー_ポップ",
            role="header",
            description="新卒採用 ポップ 明るい 若手",
            template_html="<header>{{title}}</header>"
        ),
        Component(
            name="採用ヘッダー_フォーマル",
            role="header",
            description="新卒採用 フォーマル 堅い ビジネス",
            template_html="<header class='formal'>{{title}}</header>"
        ),
        # ... 他のコンポーネント
    ]
    # DB投入 & embedding生成
```

---

## 5. 実行コマンド

```bash
# 全テスト
cd backend && pytest

# 特定フェーズのテスト
pytest tests/unit/test_vector_search.py

# カバレッジ
pytest --cov=app --cov-report=html

# 失敗時停止
pytest -x
```

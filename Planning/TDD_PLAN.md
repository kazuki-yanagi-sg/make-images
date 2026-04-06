# TDD実装計画書

## 1. TDDの進め方

```
RED → GREEN → REFACTOR のサイクル

1. RED:    失敗するテストを書く
2. GREEN:  テストが通る最小限のコードを書く
3. REFACTOR: コードを整理する（テストは通ったまま）
```

## 2. テスト環境

| 項目 | 技術 |
|------|------|
| テストフレームワーク | pytest |
| DB | Docker PostgreSQL (testcontainers的に使用) |
| モック | pytest-mock, unittest.mock |
| 非同期テスト | pytest-asyncio |
| カバレッジ | pytest-cov |

## 3. ディレクトリ構成

```
make-images/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── tag.py
│   │   │   ├── component.py
│   │   │   └── generation.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── tag.py
│   │   │   ├── component.py
│   │   │   └── generation.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── component_analyzer.py
│   │   │   ├── tag_matcher.py
│   │   │   ├── content_compositor.py
│   │   │   └── embedding_service.py
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── tag_repository.py
│   │   │   ├── component_repository.py
│   │   │   └── generation_repository.py
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── components.py
│   │       ├── tags.py
│   │       └── generate.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py           # pytest fixtures
│   │   ├── unit/
│   │   │   ├── test_component_analyzer.py
│   │   │   ├── test_tag_matcher.py
│   │   │   └── test_content_compositor.py
│   │   ├── integration/
│   │   │   ├── test_component_api.py
│   │   │   ├── test_generate_api.py
│   │   │   └── test_tag_api.py
│   │   └── fixtures/
│   │       ├── sample_html.py
│   │       └── sample_components.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pytest.ini
│   └── docker-compose.test.yml
└── Planning/
```

## 4. 実装順序（TDDサイクル）

### Phase 1: 基盤層

#### 1.1 DB接続 & モデル

```python
# tests/unit/test_models.py

def test_tag_model_creation():
    """タグモデルが正しく作成できること"""
    tag = Tag(name="recruitment", category="usage")
    assert tag.name == "recruitment"
    assert tag.category == "usage"

def test_component_model_with_slots():
    """コンポーネントモデルがslotsを持てること"""
    component = Component(
        name="header_01",
        type="header",
        slots={"title": {"type": "text", "max_chars": 20}}
    )
    assert component.slots["title"]["max_chars"] == 20
```

#### 1.2 Repository層

```python
# tests/integration/test_tag_repository.py

@pytest.mark.asyncio
async def test_create_tag(db_session):
    """タグをDBに保存できること"""
    repo = TagRepository(db_session)
    tag = await repo.create(name="recruitment", category="usage")
    assert tag.id is not None

@pytest.mark.asyncio
async def test_find_tags_by_names(db_session):
    """複数のタグ名で検索できること"""
    repo = TagRepository(db_session)
    tags = await repo.find_by_names(["recruitment", "formal"])
    assert len(tags) == 2
```

### Phase 2: コンポーネント解析

#### 2.1 HTML/CSS解析

```python
# tests/unit/test_component_analyzer.py

def test_extract_slots_from_html():
    """HTMLから{{slot}}形式のスロットを抽出できること"""
    html = '<div class="header">{{title}}</div>'
    analyzer = ComponentAnalyzer()
    slots = analyzer.extract_slots(html)
    assert "title" in slots

def test_analyze_css_colors():
    """CSSからカラーパレットを抽出できること"""
    css = ".header { background: #1a1a2e; color: #ffffff; }"
    analyzer = ComponentAnalyzer()
    colors = analyzer.extract_colors(css)
    assert "#1a1a2e" in colors

@pytest.mark.asyncio
async def test_llm_analyze_component(mock_claude):
    """LLMでコンポーネントを解析してタグを推定できること"""
    mock_claude.return_value = {
        "suggested_tags": [
            {"name": "recruitment", "confidence": 0.9}
        ]
    }
    analyzer = ComponentAnalyzer(llm_client=mock_claude)
    result = await analyzer.analyze(html="...", css="...")
    assert result.suggested_tags[0]["name"] == "recruitment"
```

### Phase 3: タグマッチング

#### 3.1 タグからコンポーネント取得

```python
# tests/unit/test_tag_matcher.py

@pytest.mark.asyncio
async def test_find_components_by_tags(db_session, seed_components):
    """タグに紐づくコンポーネントを取得できること"""
    matcher = TagMatcher(db_session)
    components = await matcher.find_by_tags(["recruitment", "formal"])
    assert len(components) > 0
    assert all(c.type in ["header", "body", "cta"] for c in components)

@pytest.mark.asyncio
async def test_prioritize_components_by_confidence(db_session, seed_components):
    """confidence順にソートされること"""
    matcher = TagMatcher(db_session)
    components = await matcher.find_by_tags(["recruitment"])
    confidences = [c.confidence for c in components]
    assert confidences == sorted(confidences, reverse=True)
```

### Phase 4: コンテンツ合成

#### 4.1 競合解決

```python
# tests/unit/test_content_compositor.py

@pytest.mark.asyncio
async def test_resolve_conflict_by_context(mock_claude):
    """文脈で競合するコンポーネントを解決できること"""
    components = [
        Component(name="blue_palette", type="color"),
        Component(name="red_palette", type="color"),
    ]
    mock_claude.return_value = {"selected": "blue_palette"}

    compositor = ContentCompositor(llm_client=mock_claude)
    selected = await compositor.resolve_conflict(
        components=components,
        context="落ち着いた企業イメージの採用告知"
    )
    assert selected.name == "blue_palette"

@pytest.mark.asyncio
async def test_fill_slots_with_content(mock_claude):
    """スロットにコンテンツを埋め込めること"""
    component = Component(
        template_html='<h1>{{title}}</h1>',
        slots={"title": {"type": "text", "max_chars": 20}}
    )
    mock_claude.return_value = {"title": "エンジニア募集中！"}

    compositor = ContentCompositor(llm_client=mock_claude)
    result = await compositor.fill_slots(
        component=component,
        user_text="当社ではエンジニアを募集しています"
    )
    assert "エンジニア募集中！" in result.html
    assert len("エンジニア募集中！") <= 20  # 文字数制限
```

### Phase 5: API統合

#### 5.1 コンポーネント登録API

```python
# tests/integration/test_component_api.py

@pytest.mark.asyncio
async def test_post_component_analyze(client, mock_claude):
    """POST /components/analyze でコンポーネントを登録できること"""
    response = await client.post("/api/v1/components/analyze", json={
        "name": "test_header",
        "type": "html_css",
        "source_html": "<div>{{title}}</div>",
        "source_css": ".header { color: #000; }"
    })
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "auto_tags" in data
```

#### 5.2 画像生成API

```python
# tests/integration/test_generate_api.py

@pytest.mark.asyncio
async def test_post_generate(client, seed_components, mock_claude):
    """POST /generate でHTML/CSSを生成できること"""
    response = await client.post("/api/v1/generate", json={
        "tags": ["recruitment", "formal"],
        "content": {
            "text": "エンジニア募集中です"
        },
        "options": {
            "aspect_ratio": "1:1"
        }
    })
    assert response.status_code == 200
    data = response.json()
    assert "output_html" in data
    assert "output_css" in data
    assert "slot_values" in data
```

## 5. Fixtures

```python
# tests/conftest.py

import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    """テスト用PostgreSQLコンテナ"""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres

@pytest.fixture
async def db_session(postgres_container):
    """DBセッション"""
    engine = create_async_engine(postgres_container.get_connection_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

@pytest.fixture
def mock_claude(mocker):
    """Claude APIのモック"""
    return mocker.patch("app.services.llm_client.call_claude")

@pytest.fixture
async def seed_components(db_session):
    """テスト用コンポーネントデータ"""
    # タグ作成
    tags = [
        Tag(name="recruitment", category="usage"),
        Tag(name="formal", category="tone"),
    ]
    db_session.add_all(tags)

    # コンポーネント作成
    component = Component(
        name="recruitment_header_01",
        type="header",
        template_html="<h1>{{title}}</h1>",
        slots={"title": {"type": "text", "max_chars": 20}}
    )
    db_session.add(component)
    await db_session.commit()

    yield
```

## 6. 実行コマンド

```bash
# 全テスト実行
pytest

# 特定のテスト実行
pytest tests/unit/test_component_analyzer.py

# カバレッジ付き
pytest --cov=app --cov-report=html

# 失敗時に即停止
pytest -x

# 詳細出力
pytest -v
```

## 7. CI/CD設定（GitHub Actions）

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install -r backend/requirements-dev.txt

      - name: Run tests
        run: pytest --cov=app
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres
```

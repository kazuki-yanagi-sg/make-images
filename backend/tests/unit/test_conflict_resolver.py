"""Conflict Resolver Serviceのテスト"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from app.services.conflict_resolver import ConflictResolver
from app.models.component import Component


@pytest.fixture
def sample_conflicting_components():
    """競合するコンポーネント（同じrole）"""
    return [
        Component(
            name="header_pop",
            role="header",
            description="ポップで明るいヘッダー",
            template_html="<header class='pop'>{{title}}</header>"
        ),
        Component(
            name="header_formal",
            role="header",
            description="フォーマルで堅いヘッダー",
            template_html="<header class='formal'>{{title}}</header>"
        ),
    ]


@pytest.fixture
def sample_non_conflicting_components():
    """競合しないコンポーネント（異なるrole）"""
    return [
        Component(
            name="header_1",
            role="header",
            description="ヘッダー",
            template_html="<header>{{title}}</header>"
        ),
        Component(
            name="body_1",
            role="body",
            description="ボディ",
            template_html="<main>{{content}}</main>"
        ),
        Component(
            name="cta_1",
            role="cta",
            description="CTA",
            template_html="<button>{{cta_text}}</button>"
        ),
    ]


@pytest.fixture
def mock_llm_client():
    """LLMクライアントモック"""
    client = AsyncMock()
    return client


def test_detect_conflicts_finds_same_role_components(sample_conflicting_components):
    """同一roleのコンポーネントを競合として検出すること"""
    resolver = ConflictResolver()

    components = sample_conflicting_components
    conflicts = resolver.detect_conflicts(components)

    assert "header" in conflicts
    assert len(conflicts["header"]) == 2


def test_detect_conflicts_returns_empty_for_unique_roles(sample_non_conflicting_components):
    """各roleが1つずつの場合は競合なしを返すこと"""
    resolver = ConflictResolver()

    conflicts = resolver.detect_conflicts(sample_non_conflicting_components)

    # 競合がないroleはconflictsに含まれない
    assert "header" not in conflicts
    assert "body" not in conflicts
    assert "cta" not in conflicts


def test_detect_conflicts_mixed_components():
    """一部のroleのみ競合がある場合"""
    resolver = ConflictResolver()

    components = [
        Component(name="h1", role="header", description="h1"),
        Component(name="h2", role="header", description="h2"),
        Component(name="b1", role="body", description="b1"),  # bodyは1つだけ
    ]

    conflicts = resolver.detect_conflicts(components)

    assert "header" in conflicts
    assert len(conflicts["header"]) == 2
    assert "body" not in conflicts


@pytest.mark.asyncio
async def test_resolve_selects_component_based_on_context(
    mock_llm_client, sample_conflicting_components
):
    """LLMが文脈に基づいて適切なコンポーネントを選択すること"""
    # LLMがポップなヘッダーを選ぶようにモック
    mock_llm_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"selected_index": 0, "reason": "若者向けにはポップなデザインが適切"}')]
    )

    resolver = ConflictResolver(llm_client=mock_llm_client)

    selected = await resolver.resolve(
        conflicting_components=sample_conflicting_components,
        user_prompt="若者向けの明るい採用告知",
        role="header"
    )

    assert selected is not None
    assert selected.name == "header_pop"


@pytest.mark.asyncio
async def test_resolve_returns_first_component_if_llm_fails(
    mock_llm_client, sample_conflicting_components
):
    """LLMがエラーの場合は最初のコンポーネントを返すこと"""
    mock_llm_client.messages.create.side_effect = Exception("LLM Error")

    resolver = ConflictResolver(llm_client=mock_llm_client)

    selected = await resolver.resolve(
        conflicting_components=sample_conflicting_components,
        user_prompt="テスト",
        role="header"
    )

    # フォールバックとして最初のコンポーネントを返す
    assert selected is not None
    assert selected.name == "header_pop"


@pytest.mark.asyncio
async def test_resolve_calls_llm_with_correct_prompt(
    mock_llm_client, sample_conflicting_components
):
    """LLMに適切なプロンプトで呼び出すこと"""
    mock_llm_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"selected_index": 0, "reason": "test"}')]
    )

    resolver = ConflictResolver(llm_client=mock_llm_client)

    await resolver.resolve(
        conflicting_components=sample_conflicting_components,
        user_prompt="若者向けの採用告知",
        role="header"
    )

    # LLMが呼ばれたことを確認
    mock_llm_client.messages.create.assert_called_once()
    call_args = mock_llm_client.messages.create.call_args

    # システムプロンプトまたはメッセージに必要な情報が含まれていることを確認
    messages = call_args.kwargs.get("messages", [])
    assert len(messages) > 0

    # ユーザープロンプトが含まれていることを確認
    message_content = str(messages)
    assert "若者向け" in message_content or "採用告知" in message_content


@pytest.mark.asyncio
async def test_resolve_all_resolves_multiple_conflicts():
    """複数の競合を一度に解決できること"""
    mock_llm_client = AsyncMock()
    mock_llm_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"selected_index": 0, "reason": "test"}')]
    )

    resolver = ConflictResolver(llm_client=mock_llm_client)

    conflicts = {
        "header": [
            Component(name="h1", role="header", description="h1"),
            Component(name="h2", role="header", description="h2"),
        ],
        "body": [
            Component(name="b1", role="body", description="b1"),
            Component(name="b2", role="body", description="b2"),
        ],
    }

    resolved = await resolver.resolve_all(
        conflicts=conflicts,
        user_prompt="テスト"
    )

    assert "header" in resolved
    assert "body" in resolved
    assert resolved["header"].name == "h1"
    assert resolved["body"].name == "b1"

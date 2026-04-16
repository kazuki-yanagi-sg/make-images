"""Generation Workflowの統合テスト"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.workflows.generation_workflow import GenerationWorkflow, GenerationResult
from app.models.component import Component
from app.services.vector_search import SearchResult


@pytest.fixture
def mock_db_session():
    """DBセッションモック"""
    return AsyncMock()


@pytest.fixture
def mock_embedding_service():
    """Embedding Serviceモック"""
    service = MagicMock()

    async def mock_create_embedding(text):
        return [0.1] * 1536

    service.create_embedding = mock_create_embedding
    service.cosine_similarity = MagicMock(return_value=0.9)
    return service


@pytest.fixture
def mock_llm_client():
    """LLMクライアントモック"""
    client = AsyncMock()
    client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"selected_index": 0, "reason": "test"}')]
    )
    return client


@pytest.fixture
def sample_components():
    """サンプルコンポーネント"""
    return [
        Component(
            name="採用ヘッダー_ポップ",
            role="header",
            description="新卒採用 ポップ 明るい",
            template_html="<header>{{title}}</header>",
            template_css=".header { background: yellow; }",
            slots={"title": {"type": "text", "max_chars": 20}},
            embedding=[0.1] * 1536
        ),
        Component(
            name="採用ヘッダー_フォーマル",
            role="header",
            description="新卒採用 フォーマル 堅い",
            template_html="<header class='formal'>{{title}}</header>",
            template_css=".header.formal { background: navy; }",
            slots={"title": {"type": "text", "max_chars": 20}},
            embedding=[0.15] * 1536
        ),
        Component(
            name="採用ボディ",
            role="body",
            description="採用情報 本文",
            template_html="<main>{{content}}</main>",
            template_css=".main { padding: 20px; }",
            slots={"content": {"type": "text", "max_chars": 100}},
            embedding=[0.2] * 1536
        ),
        Component(
            name="採用CTA",
            role="cta",
            description="応募ボタン",
            template_html="<button>{{cta_text}}</button>",
            template_css="button { color: white; }",
            slots={"cta_text": {"type": "text", "max_chars": 15}},
            embedding=[0.25] * 1536
        ),
    ]


@pytest.mark.asyncio
async def test_workflow_returns_generation_result(
    mock_db_session, mock_embedding_service, mock_llm_client, sample_components
):
    """ワークフローがGenerationResultを返すこと"""
    # DBモックの設定
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    workflow = GenerationWorkflow(
        db_session=mock_db_session,
        embedding_service=mock_embedding_service,
        llm_client=mock_llm_client
    )

    result = await workflow.run(
        tags=["新卒採用", "ポップ"],
        user_prompt="若者向けの明るい採用告知"
    )

    assert isinstance(result, GenerationResult)
    assert result.output_html is not None
    assert result.output_css is not None


@pytest.mark.asyncio
async def test_workflow_selects_components(
    mock_db_session, mock_embedding_service, mock_llm_client, sample_components
):
    """ワークフローがコンポーネントを選択すること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    workflow = GenerationWorkflow(
        db_session=mock_db_session,
        embedding_service=mock_embedding_service,
        llm_client=mock_llm_client
    )

    result = await workflow.run(
        tags=["新卒採用"],
        user_prompt="テスト"
    )

    assert len(result.selected_components) > 0


@pytest.mark.asyncio
async def test_workflow_resolves_conflicts(
    mock_db_session, mock_embedding_service, mock_llm_client, sample_components
):
    """ワークフローが競合を解決すること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    workflow = GenerationWorkflow(
        db_session=mock_db_session,
        embedding_service=mock_embedding_service,
        llm_client=mock_llm_client
    )

    result = await workflow.run(
        tags=["新卒採用", "ポップ"],
        user_prompt="若者向け"
    )

    # headerが2つあったが、1つに解決されているはず
    header_count = sum(
        1 for c in result.selected_components
        if c.role == "header"
    )
    assert header_count == 1


@pytest.mark.asyncio
async def test_workflow_composes_html(
    mock_db_session, mock_embedding_service, mock_llm_client, sample_components
):
    """ワークフローがHTMLを合成すること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    workflow = GenerationWorkflow(
        db_session=mock_db_session,
        embedding_service=mock_embedding_service,
        llm_client=mock_llm_client
    )

    result = await workflow.run(
        tags=["新卒採用"],
        user_prompt="テスト"
    )

    assert "<header>" in result.output_html or "<header class" in result.output_html
    assert "<main>" in result.output_html
    assert "<button>" in result.output_html


@pytest.mark.asyncio
async def test_workflow_handles_no_results(
    mock_db_session, mock_embedding_service, mock_llm_client
):
    """検索結果がない場合も正常に処理すること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    workflow = GenerationWorkflow(
        db_session=mock_db_session,
        embedding_service=mock_embedding_service,
        llm_client=mock_llm_client
    )

    result = await workflow.run(
        tags=["存在しないタグ"],
        user_prompt="テスト"
    )

    assert result.output_html == ""
    assert result.selected_components == []


@pytest.mark.asyncio
async def test_workflow_with_slot_values(
    mock_db_session, mock_embedding_service, mock_llm_client, sample_components
):
    """スロット値を埋め込んでHTMLを生成すること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    workflow = GenerationWorkflow(
        db_session=mock_db_session,
        embedding_service=mock_embedding_service,
        llm_client=mock_llm_client
    )

    slot_values = {
        "header": {"title": "新卒採用開始！"},
        "body": {"content": "詳細はこちら"},
        "cta": {"cta_text": "応募する"},
    }

    result = await workflow.run(
        tags=["新卒採用"],
        user_prompt="テスト",
        slot_values=slot_values
    )

    assert "新卒採用開始！" in result.output_html
    assert "詳細はこちら" in result.output_html
    assert "応募する" in result.output_html

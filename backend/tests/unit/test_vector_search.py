"""Vector Search Serviceのテスト"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from app.services.vector_search import VectorSearchService, SearchResult
from app.services.embedding_service import EmbeddingService
from app.models.component import Component


@pytest.fixture
def mock_embedding_service():
    """Embedding Serviceモック"""
    service = MagicMock(spec=EmbeddingService)
    # 非同期メソッドをAsyncMockで設定
    async def mock_create_embedding(text):
        return [0.1] * 1536

    service.create_embedding = mock_create_embedding
    service.cosine_similarity = EmbeddingService.cosine_similarity
    return service


@pytest.fixture
def mock_db_session():
    """DBセッションモック"""
    session = AsyncMock()
    return session


@pytest.fixture
def sample_components():
    """サンプルコンポーネント"""
    return [
        Component(
            name="採用ヘッダー_ポップ",
            role="header",
            description="新卒採用 ポップ 明るい 若手",
            template_html="<header>{{title}}</header>",
            embedding=[0.1] * 1536
        ),
        Component(
            name="採用ヘッダー_フォーマル",
            role="header",
            description="新卒採用 フォーマル 堅い ビジネス",
            template_html="<header class='formal'>{{title}}</header>",
            embedding=[0.15] * 1536
        ),
        Component(
            name="採用ボディ",
            role="body",
            description="採用情報 本文 詳細",
            template_html="<main>{{content}}</main>",
            embedding=[0.2] * 1536
        ),
    ]


@pytest.mark.asyncio
async def test_search_returns_search_results(
    mock_db_session, mock_embedding_service, sample_components
):
    """検索結果がSearchResult型で返されること"""
    # DBから返される結果をセットアップ
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    search = VectorSearchService(mock_db_session, mock_embedding_service)
    results = await search.search(query_tags=["新卒採用"], limit=10)

    assert len(results) > 0
    assert all(isinstance(r, SearchResult) for r in results)


@pytest.mark.asyncio
async def test_search_results_have_similarity(
    mock_db_session, mock_embedding_service, sample_components
):
    """検索結果に類似度スコアが含まれること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    search = VectorSearchService(mock_db_session, mock_embedding_service)
    results = await search.search(query_tags=["新卒採用"], limit=10)

    assert all(hasattr(r, "similarity") for r in results)
    assert all(isinstance(r.similarity, float) for r in results)


@pytest.mark.asyncio
async def test_search_returns_component_data(
    mock_db_session, mock_embedding_service, sample_components
):
    """検索結果にコンポーネント情報が含まれること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    search = VectorSearchService(mock_db_session, mock_embedding_service)
    results = await search.search(query_tags=["新卒採用"], limit=10)

    first_result = results[0]
    assert hasattr(first_result, "component")
    assert first_result.component.role in ["header", "body", "cta", "footer"]


@pytest.mark.asyncio
async def test_search_respects_limit(
    mock_db_session, mock_embedding_service, sample_components
):
    """limit指定が尊重されること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components[:2]
    mock_db_session.execute.return_value = mock_result

    search = VectorSearchService(mock_db_session, mock_embedding_service)
    results = await search.search(query_tags=["新卒採用"], limit=2)

    assert len(results) <= 2


@pytest.mark.asyncio
async def test_search_combines_multiple_tags(
    mock_db_session, mock_embedding_service, sample_components
):
    """複数タグを結合して検索すること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    # 呼び出し履歴をトラックするために修正
    call_history = []
    original_create_embedding = mock_embedding_service.create_embedding

    async def tracking_create_embedding(text):
        call_history.append(text)
        return await original_create_embedding(text)

    mock_embedding_service.create_embedding = tracking_create_embedding

    search = VectorSearchService(mock_db_session, mock_embedding_service)
    await search.search(query_tags=["新卒採用", "ポップ"], limit=10)

    # embeddingサービスが呼ばれたことを確認
    assert len(call_history) > 0
    assert "新卒採用" in call_history[0] and "ポップ" in call_history[0]


@pytest.mark.asyncio
async def test_search_returns_empty_for_no_match(
    mock_db_session, mock_embedding_service
):
    """マッチしない場合は空リストを返すこと"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    search = VectorSearchService(mock_db_session, mock_embedding_service)
    results = await search.search(query_tags=["存在しないタグ"], limit=10)

    assert results == []


@pytest.mark.asyncio
async def test_search_groups_by_role(
    mock_db_session, mock_embedding_service, sample_components
):
    """検索結果を役割ごとにグループ化できること"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_components
    mock_db_session.execute.return_value = mock_result

    search = VectorSearchService(mock_db_session, mock_embedding_service)
    results = await search.search(query_tags=["新卒採用"], limit=10)
    grouped = search.group_by_role(results)

    assert "header" in grouped
    assert "body" in grouped
    assert len(grouped["header"]) == 2  # 2つのheaderコンポーネント

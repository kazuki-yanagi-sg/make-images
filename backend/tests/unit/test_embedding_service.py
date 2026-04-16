"""Embedding Serviceのテスト"""
import pytest
from unittest.mock import AsyncMock, patch
import numpy as np
from app.services.embedding_service import EmbeddingService


@pytest.fixture
def mock_openai_client():
    """OpenAI APIモック"""
    with patch("app.services.embedding_service.AsyncOpenAI") as mock:
        client_instance = AsyncMock()
        # embeddingレスポンスをモック
        mock_embedding = [0.1] * 1536
        client_instance.embeddings.create.return_value = AsyncMock(
            data=[AsyncMock(embedding=mock_embedding)]
        )
        mock.return_value = client_instance
        yield client_instance


@pytest.mark.asyncio
async def test_create_embedding_returns_vector(mock_openai_client):
    """テキストからembeddingベクトルを生成できること"""
    service = EmbeddingService()
    embedding = await service.create_embedding("新卒採用 ポップ")

    assert embedding is not None
    assert len(embedding) == 1536  # OpenAI embedding dimension


@pytest.mark.asyncio
async def test_create_embedding_calls_openai(mock_openai_client):
    """OpenAI APIが正しく呼び出されること"""
    service = EmbeddingService()
    await service.create_embedding("テストテキスト")

    mock_openai_client.embeddings.create.assert_called_once()
    call_args = mock_openai_client.embeddings.create.call_args
    assert call_args.kwargs["input"] == "テストテキスト"
    assert "text-embedding" in call_args.kwargs["model"]


@pytest.mark.asyncio
async def test_create_embeddings_batch(mock_openai_client):
    """複数テキストのembeddingを一括生成できること"""
    mock_embedding1 = [0.1] * 1536
    mock_embedding2 = [0.2] * 1536
    mock_openai_client.embeddings.create.return_value = AsyncMock(
        data=[
            AsyncMock(embedding=mock_embedding1),
            AsyncMock(embedding=mock_embedding2)
        ]
    )

    service = EmbeddingService()
    embeddings = await service.create_embeddings(["テキスト1", "テキスト2"])

    assert len(embeddings) == 2
    assert all(len(emb) == 1536 for emb in embeddings)


def test_cosine_similarity_same_vectors():
    """同じベクトルの類似度は1.0であること"""
    vec = [1.0, 0.0, 0.0]

    similarity = EmbeddingService.cosine_similarity(vec, vec)

    assert similarity == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    """直交ベクトルの類似度は0であること"""
    vec1 = [1.0, 0.0]
    vec2 = [0.0, 1.0]

    similarity = EmbeddingService.cosine_similarity(vec1, vec2)

    assert similarity == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors():
    """反対ベクトルの類似度は-1.0であること"""
    vec1 = [1.0, 0.0]
    vec2 = [-1.0, 0.0]

    similarity = EmbeddingService.cosine_similarity(vec1, vec2)

    assert similarity == pytest.approx(-1.0)

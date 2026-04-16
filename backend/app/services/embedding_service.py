"""Embedding Service - OpenAI APIを使用したembedding生成"""
import numpy as np
from openai import AsyncOpenAI
from app.config import get_settings


class EmbeddingService:
    """OpenAI Embeddingを使用したテキストベクトル化サービス"""

    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "text-embedding-3-small"

    async def create_embedding(self, text: str) -> list[float]:
        """テキストからembeddingベクトルを生成

        Args:
            text: embeddingを生成するテキスト

        Returns:
            1536次元のembeddingベクトル
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding

    async def create_embeddings(self, texts: list[str]) -> list[list[float]]:
        """複数テキストから一括でembeddingを生成

        Args:
            texts: embeddingを生成するテキストのリスト

        Returns:
            embeddingベクトルのリスト
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]

    @staticmethod
    def cosine_similarity(
        vec1: list[float],
        vec2: list[float]
    ) -> float:
        """2つのベクトル間のコサイン類似度を計算

        Args:
            vec1: ベクトル1
            vec2: ベクトル2

        Returns:
            -1.0から1.0の類似度スコア
        """
        a = np.array(vec1)
        b = np.array(vec2)

        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

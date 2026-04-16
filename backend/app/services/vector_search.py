"""Vector Search Service - ベクトル検索"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

try:
    from sqlalchemy import select
except ImportError:
    select = None

from app.models.component import Component
from app.services.embedding_service import EmbeddingService


@dataclass
class SearchResult:
    """検索結果"""

    component: Component
    similarity: float


class VectorSearchService:
    """コンポーネントに対するベクトル検索サービス"""

    def __init__(
        self,
        db_session: Any,
        embedding_service: EmbeddingService | None = None
    ):
        self.db_session = db_session
        self.embedding_service = embedding_service or EmbeddingService()

    async def search(
        self,
        query_tags: list[str],
        limit: int = 10
    ) -> list[SearchResult]:
        query_text = " ".join(query_tags)
        query_embedding = await self.embedding_service.create_embedding(query_text)

        if select is not None:
            stmt = select(Component).limit(limit)
            result = await self.db_session.execute(stmt)
        else:
            result = await self.db_session.execute(limit)

        components = result.scalars().all()

        search_results = []
        for component in components:
            if component.embedding:
                similarity = self.embedding_service.cosine_similarity(
                    query_embedding,
                    component.embedding
                )
            else:
                similarity = 0.0

            search_results.append(
                SearchResult(component=component, similarity=similarity)
            )

        search_results.sort(key=lambda x: x.similarity, reverse=True)
        return search_results[:limit]

    def group_by_role(
        self,
        results: list[SearchResult]
    ) -> dict[str, list[SearchResult]]:
        grouped: dict[str, list[SearchResult]] = defaultdict(list)
        for result in results:
            grouped[result.component.role].append(result)
        return dict(grouped)

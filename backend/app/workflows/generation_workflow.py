"""Generation Workflow - 3フェーズを統合したデザイン生成ワークフロー"""
from dataclasses import dataclass, field
from typing import Any

from app.models.component import Component
from app.services.conflict_resolver import ConflictResolver
from app.services.embedding_service import EmbeddingService
from app.services.template_composer import TemplateComposer
from app.services.vector_search import VectorSearchService


@dataclass
class GenerationResult:
    """生成結果"""

    output_html: str
    output_css: str
    selected_components: list[Component] = field(default_factory=list)
    all_slots: dict[str, dict] = field(default_factory=dict)


class GenerationWorkflow:
    """既存のコンポーネント合成ワークフロー"""

    def __init__(
        self,
        db_session: Any,
        embedding_service: EmbeddingService | None = None,
        llm_client: Any | None = None
    ):
        self.db_session = db_session
        self.embedding_service = embedding_service
        self.llm_client = llm_client

        self.vector_search = VectorSearchService(
            db_session=db_session,
            embedding_service=embedding_service
        )
        self.conflict_resolver = ConflictResolver(llm_client=llm_client)
        self.template_composer = TemplateComposer()

    async def run(
        self,
        tags: list[str],
        user_prompt: str,
        slot_values: dict[str, dict[str, str]] | None = None,
        limit: int = 20
    ) -> GenerationResult:
        search_results = await self.vector_search.search(
            query_tags=tags,
            limit=limit
        )

        if not search_results:
            return GenerationResult(
                output_html="",
                output_css="",
                selected_components=[],
                all_slots={}
            )

        grouped = self.vector_search.group_by_role(search_results)
        components_list = [sr.component for sr in search_results]
        conflicts = self.conflict_resolver.detect_conflicts(components_list)

        resolved: dict[str, Component] = {}
        for role, results in grouped.items():
            if role in conflicts:
                conflicting = [r.component for r in results]
                selected = await self.conflict_resolver.resolve(
                    conflicting_components=conflicting,
                    user_prompt=user_prompt,
                    role=role
                )
                resolved[role] = selected
            else:
                resolved[role] = results[0].component

        selected_components = list(resolved.values())

        if slot_values:
            composed = self.template_composer.compose_with_slots(
                components=resolved,
                slot_values=slot_values
            )
        else:
            composed = self.template_composer.compose(resolved)

        return GenerationResult(
            output_html=composed.html,
            output_css=composed.css,
            selected_components=selected_components,
            all_slots=composed.all_slots
        )

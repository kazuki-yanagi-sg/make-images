"""Conflict Resolver Service - LLMを使用した競合解決"""
import json
from collections import defaultdict
from typing import Any

from app.models.component import Component


class ConflictResolver:
    """同一roleコンポーネントの競合をLLMで解決するサービス"""

    def __init__(self, llm_client: Any | None = None):
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = None
        self.model = "claude-3-5-sonnet-20241022"

    def detect_conflicts(
        self,
        components: list[Component]
    ) -> dict[str, list[Component]]:
        """同一roleのコンポーネントを検出"""
        by_role: dict[str, list[Component]] = defaultdict(list)
        for comp in components:
            by_role[comp.role].append(comp)

        return {
            role: comps
            for role, comps in by_role.items()
            if len(comps) > 1
        }

    async def resolve(
        self,
        conflicting_components: list[Component],
        user_prompt: str,
        role: str
    ) -> Component:
        """LLMを使って競合を解決し、最適なコンポーネントを選択"""
        if len(conflicting_components) == 0:
            raise ValueError("No components to resolve")

        if len(conflicting_components) == 1 or self.llm_client is None:
            return conflicting_components[0]

        try:
            options_text = "\n".join([
                f"{i}. {comp.name}: {comp.description}"
                for i, comp in enumerate(conflicting_components)
            ])

            prompt = f"""以下のユーザーリクエストに最も適したデザインコンポーネントを選んでください。

ユーザーリクエスト: {user_prompt}

役割: {role}

選択肢:
{options_text}

JSONフォーマットで回答してください:
{{"selected_index": <選択した番号>, "reason": "<選択理由>"}}"""

            response = await self.llm_client.messages.create(
                model=self.model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text
            result = json.loads(response_text)
            selected_index = result.get("selected_index", 0)

            if 0 <= selected_index < len(conflicting_components):
                return conflicting_components[selected_index]
            return conflicting_components[0]

        except Exception:
            return conflicting_components[0]

    async def resolve_all(
        self,
        conflicts: dict[str, list[Component]],
        user_prompt: str
    ) -> dict[str, Component]:
        """複数の競合を一度に解決"""
        resolved = {}
        for role, components in conflicts.items():
            resolved[role] = await self.resolve(
                conflicting_components=components,
                user_prompt=user_prompt,
                role=role
            )
        return resolved

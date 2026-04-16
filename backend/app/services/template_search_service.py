"""投稿全体テンプレート検索サービス"""
from dataclasses import dataclass
from typing import Any


@dataclass
class TemplateSearchResult:
    template: Any
    score: float
    matched_tags: list[str]


class TemplateSearchService:
    """手動タグ優先でテンプレートを選ぶ"""

    def search(
        self,
        templates: list[Any],
        input_tags: list[str],
        prompt: str = "",
    ) -> list[TemplateSearchResult]:
        normalized_input_tags = self._normalize_tags(input_tags)
        results: list[TemplateSearchResult] = []

        for template in templates:
            manual_tags = self._normalize_tags(getattr(template, "manual_tags_json", []) or [])
            auto_tags = self._normalize_tags(getattr(template, "auto_tags_json", []) or [])
            search_text = (getattr(template, "search_text", "") or "").lower()

            manual_matches = sorted(set(normalized_input_tags) & set(manual_tags))
            auto_matches = sorted(set(normalized_input_tags) & set(auto_tags))

            partial_matches = []
            for tag in normalized_input_tags:
                if tag in manual_matches:
                    continue
                if any(tag in manual or manual in tag for manual in manual_tags):
                    partial_matches.append(tag)

            semantic_score = 0.0
            if search_text:
                semantic_score = sum(1 for tag in normalized_input_tags if tag in search_text) * 0.1

            score = (
                len(manual_matches) * 100
                + len(partial_matches) * 40
                + len(auto_matches) * 10
                + semantic_score
            )

            if score <= 0:
                continue

            results.append(
                TemplateSearchResult(
                    template=template,
                    score=score,
                    matched_tags=manual_matches or partial_matches or auto_matches,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results

    def _normalize_tags(self, tags: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for tag in tags:
            if not isinstance(tag, str):
                continue
            value = tag.strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

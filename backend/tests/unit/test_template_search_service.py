"""Whole post template search service のテスト"""
from app.database import Template
from app.services.template_search_service import TemplateSearchService


def make_template(
    template_id: str,
    manual_tags: list[str],
    auto_tags: list[str] | None = None,
    search_text: str = "",
) -> Template:
    return Template(
        id=template_id,
        name=template_id,
        json_data='{"canvas": {"width": 1080, "height": 1080}, "elements": []}',
        vector_id=f"vec_{template_id}",
        manual_tags_json=manual_tags,
        auto_tags_json=auto_tags or [],
        search_text=search_text,
    )


def test_search_prioritizes_manual_tag_matches():
    service = TemplateSearchService()
    exact = make_template("tpl_exact", ["採用", "ポップ"], ["明るい"])
    auto_only = make_template("tpl_auto", ["イベント"], ["採用", "ポップ"])

    results = service.search(
        templates=[auto_only, exact],
        input_tags=["採用", "ポップ"],
        prompt="若者向けの採用告知",
    )

    assert results
    assert results[0].template.id == "tpl_exact"


def test_search_excludes_unrelated_templates():
    service = TemplateSearchService()
    unrelated = make_template("tpl_food", ["料理", "レシピ"], ["ごはん"])

    results = service.search(
        templates=[unrelated],
        input_tags=["採用", "ポップ"],
        prompt="新卒採用を明るく伝えたい",
    )

    assert results == []

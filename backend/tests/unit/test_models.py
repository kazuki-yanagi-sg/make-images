"""モデルのテスト"""
import pytest
from uuid import UUID
from app.models.component import Component


def test_component_model_has_required_fields():
    """Componentモデルが必要なフィールドを持つこと"""
    component = Component(
        name="test_header",
        role="header",
        description="テスト用ヘッダー 採用 ポップ"
    )
    assert component.name == "test_header"
    assert component.role == "header"
    assert component.description == "テスト用ヘッダー 採用 ポップ"


def test_component_model_has_optional_fields():
    """Componentモデルがオプショナルフィールドを持つこと"""
    component = Component(
        name="test",
        role="header",
        description="テスト",
        template_html="<header>{{title}}</header>",
        template_css=".header { color: red; }",
        slots={"title": {"type": "text", "max_chars": 20}}
    )
    assert component.template_html == "<header>{{title}}</header>"
    assert component.template_css == ".header { color: red; }"
    assert component.slots["title"]["max_chars"] == 20


def test_component_model_has_embedding_field():
    """Componentモデルがembeddingフィールドを持つこと"""
    component = Component(
        name="test",
        role="header",
        description="テスト"
    )
    assert hasattr(component, "embedding")


def test_component_model_has_id():
    """ComponentモデルがUUID idを持つこと"""
    component = Component(
        name="test",
        role="header",
        description="テスト"
    )
    assert hasattr(component, "id")

"""Template Composer Serviceのテスト"""
import pytest
from app.services.template_composer import TemplateComposer, ComposedTemplate
from app.models.component import Component


@pytest.fixture
def sample_components_by_role():
    """役割ごとのコンポーネント"""
    return {
        "header": Component(
            name="header_1",
            role="header",
            description="ヘッダー",
            template_html="<header>{{title}}</header>",
            template_css=".header { background: blue; }",
            slots={"title": {"type": "text", "max_chars": 20}}
        ),
        "body": Component(
            name="body_1",
            role="body",
            description="ボディ",
            template_html="<main>{{content}}</main>",
            template_css=".main { padding: 20px; }",
            slots={"content": {"type": "text", "max_chars": 100}}
        ),
        "cta": Component(
            name="cta_1",
            role="cta",
            description="CTA",
            template_html="<button>{{cta_text}}</button>",
            template_css="button { color: white; }",
            slots={"cta_text": {"type": "text", "max_chars": 15}}
        ),
    }


def test_compose_merges_components_by_role(sample_components_by_role):
    """役割ごとにコンポーネントを配置すること"""
    composer = TemplateComposer()

    result = composer.compose(sample_components_by_role)

    assert isinstance(result, ComposedTemplate)
    assert "<header>" in result.html
    assert "<main>" in result.html
    assert "<button>" in result.html


def test_compose_merges_css(sample_components_by_role):
    """CSSを結合すること"""
    composer = TemplateComposer()

    result = composer.compose(sample_components_by_role)

    assert "background: blue" in result.css
    assert "padding: 20px" in result.css
    assert "color: white" in result.css


def test_compose_orders_by_role():
    """役割の順序に従ってHTMLを配置すること"""
    composer = TemplateComposer()

    components = {
        "cta": Component(
            name="cta", role="cta", description="cta",
            template_html="<button>CTA</button>"
        ),
        "header": Component(
            name="header", role="header", description="header",
            template_html="<header>Header</header>"
        ),
        "body": Component(
            name="body", role="body", description="body",
            template_html="<main>Body</main>"
        ),
    }

    result = composer.compose(components)

    # headerがbodyより前、bodyがctaより前にあることを確認
    header_pos = result.html.find("<header>")
    body_pos = result.html.find("<main>")
    cta_pos = result.html.find("<button>")

    assert header_pos < body_pos < cta_pos


def test_fill_slots_replaces_placeholders():
    """プレースホルダーを値で置換すること"""
    composer = TemplateComposer()

    component = Component(
        name="header",
        role="header",
        description="header",
        template_html="<h1>{{title}}</h1>",
        slots={"title": {"type": "text", "max_chars": 20}}
    )

    result = composer.fill_slots(
        component=component,
        values={"title": "新卒採用開始！"}
    )

    assert "<h1>新卒採用開始！</h1>" in result.html


def test_fill_slots_handles_multiple_placeholders():
    """複数のプレースホルダーを処理すること"""
    composer = TemplateComposer()

    component = Component(
        name="card",
        role="body",
        description="card",
        template_html="<div><h2>{{title}}</h2><p>{{description}}</p></div>",
        slots={
            "title": {"type": "text", "max_chars": 20},
            "description": {"type": "text", "max_chars": 50}
        }
    )

    result = composer.fill_slots(
        component=component,
        values={
            "title": "タイトル",
            "description": "説明文です"
        }
    )

    assert "<h2>タイトル</h2>" in result.html
    assert "<p>説明文です</p>" in result.html


def test_fill_slots_respects_max_chars():
    """文字数制限を守ること"""
    composer = TemplateComposer()

    component = Component(
        name="header",
        role="header",
        description="header",
        template_html="<h1>{{title}}</h1>",
        slots={"title": {"type": "text", "max_chars": 10}}
    )

    result = composer.fill_slots(
        component=component,
        values={"title": "これは非常に長いタイトルです"}
    )

    # 10文字以内に切り詰められること
    assert len(result.slot_values["title"]) <= 10


def test_fill_slots_keeps_unfilled_placeholders():
    """値がないプレースホルダーはそのまま残すこと"""
    composer = TemplateComposer()

    component = Component(
        name="header",
        role="header",
        description="header",
        template_html="<h1>{{title}}</h1><p>{{subtitle}}</p>",
        slots={
            "title": {"type": "text", "max_chars": 20},
            "subtitle": {"type": "text", "max_chars": 30}
        }
    )

    result = composer.fill_slots(
        component=component,
        values={"title": "タイトルのみ"}
    )

    assert "<h1>タイトルのみ</h1>" in result.html
    assert "{{subtitle}}" in result.html


def test_compose_with_slots_filled(sample_components_by_role):
    """スロットを埋めた状態で合成すること"""
    composer = TemplateComposer()

    slot_values = {
        "header": {"title": "採用情報"},
        "body": {"content": "詳細はこちら"},
        "cta": {"cta_text": "応募する"},
    }

    result = composer.compose_with_slots(
        components=sample_components_by_role,
        slot_values=slot_values
    )

    assert "<header>採用情報</header>" in result.html
    assert "<main>詳細はこちら</main>" in result.html
    assert "<button>応募する</button>" in result.html


def test_composed_template_has_all_slots():
    """ComposedTemplateが全スロット情報を持つこと"""
    composer = TemplateComposer()

    components = {
        "header": Component(
            name="header", role="header", description="header",
            template_html="<h1>{{title}}</h1>",
            slots={"title": {"type": "text", "max_chars": 20}}
        ),
    }

    result = composer.compose(components)

    assert "title" in result.all_slots
    assert result.all_slots["title"]["max_chars"] == 20


def test_compose_handles_empty_components():
    """空のコンポーネントマップを処理できること"""
    composer = TemplateComposer()

    result = composer.compose({})

    assert result.html == ""
    assert result.css == ""


def test_compose_wraps_in_container():
    """コンテナでラップすること"""
    composer = TemplateComposer()

    components = {
        "header": Component(
            name="header", role="header", description="header",
            template_html="<header>Test</header>"
        ),
    }

    result = composer.compose(components, wrap_in_container=True)

    assert '<div class="design-container">' in result.html
    assert "</div>" in result.html

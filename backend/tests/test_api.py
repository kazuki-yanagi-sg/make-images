import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["OPENAI_API_KEY"] = "mock_key"

from app.database import Base, get_db
from app.main import app


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def sample_structure():
    return {
        "canvas": {"width": 1080, "height": 1080, "background_color": "#FFF8F2"},
        "elements": [
            {
                "id": "headline",
                "type": "text",
                "role": "headline",
                "x": 120,
                "y": 120,
                "width": 840,
                "height": 180,
                "content": "",
                "style": {
                    "font_size": 64,
                    "font_weight": 700,
                    "color": "#111111",
                    "align": "center",
                },
                "slot": {"name": "headline", "required": True, "max_chars": 18},
            }
        ],
    }


@patch("app.main.extract_template_structure")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_upload_template_success(mock_emb, mock_add_vec, mock_extract):
    mock_extract.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#テスト"])
    mock_emb.return_value = [0.1] * 8

    files = {"file": ("test.png", b"fake_image", "image/png")}
    data = {"name": "test_template", "manual_tags": '["採用", "ポップ"]'}
    response = client.post("/api/templates", files=files, data=data)

    assert response.status_code == 200
    assert response.json()["message"] == "success"
    assert "template_id" in response.json()


def test_upload_template_invalid_file():
    files = {"file": ("test.txt", b"plain text", "text/plain")}
    response = client.post("/api/templates", files=files)
    assert response.status_code == 400


def test_upload_template_requires_manual_tags():
    files = {"file": ("test.png", b"fake_image", "image/png")}
    data = {"name": "test_template"}
    response = client.post("/api/templates", files=files, data=data)
    assert response.status_code == 400


@patch("app.main._extract_from_pptx")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_upload_pptx_template_allows_without_reference_image(
    mock_emb, mock_add_vec, mock_extract_pptx
):
    mock_extract_pptx.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#インタビュー"])
    mock_emb.return_value = [0.1] * 8

    files = {
        "file": (
            "test.pptx",
            b"fake_pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    }
    data = {"name": "test_template", "manual_tags": '["採用", "ポップ"]'}

    response = client.post("/api/templates", files=files, data=data)

    assert response.status_code == 200
    assert response.json()["message"] == "success"
    mock_extract_pptx.assert_called_once()


def test_openapi_does_not_expose_reference_image_for_templates_endpoint():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    multipart_schema_ref = schema["paths"]["/api/templates"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    component_name = multipart_schema_ref.split("/")[-1]
    properties = schema["components"]["schemas"][component_name]["properties"]

    assert "reference_image" not in properties


@patch("app.main._extract_from_pptx")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_upload_pptx_template_with_reference_success(
    mock_emb, mock_add_vec, mock_extract_pptx
):
    mock_extract_pptx.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#インタビュー"])
    mock_emb.return_value = [0.1] * 8

    files = {
        "file": (
            "test.pptx",
            b"fake_pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
    }
    data = {"name": "test_pptx_template", "manual_tags": '["採用", "ポップ"]'}

    response = client.post("/api/templates", files=files, data=data)

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "success"
    assert "template_id" in payload
    assert payload["auto_tags"] == ["#採用", "#インタビュー"]
    mock_extract_pptx.assert_called_once()


@patch("app.main.extract_template_structure")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_generate_design_success(mock_emb, mock_add_vec, mock_extract):
    mock_extract.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#テスト"])
    mock_emb.return_value = [0.1] * 8

    register = client.post(
        "/api/templates",
        files={"file": ("test.png", b"fake_image", "image/png")},
        data={"name": "test_template", "manual_tags": json.dumps(["採用", "ポップ"])},
    )
    assert register.status_code == 200

    payload = {"tags": ["採用", "ポップ"], "prompt": "春のセール用のPOP"}
    response = client.post("/api/generate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "output_html" in data
    assert "output_css" in data
    assert "template_id" in data


def test_generate_design_requires_tags():
    payload = {"prompt": "無効なテスト"}
    response = client.post("/api/generate", json=payload)

    assert response.status_code == 422


def test_generate_design_not_found_without_saved_templates():
    payload = {"tags": ["採用"], "prompt": "無効なテスト"}
    response = client.post("/api/generate", json=payload)

    assert response.status_code == 404


@patch("app.main.extract_template_structure")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_get_template_detail_returns_structure_and_preview(mock_emb, mock_add_vec, mock_extract):
    mock_extract.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#テスト"])
    mock_emb.return_value = [0.1] * 8

    register = client.post(
        "/api/templates",
        files={"file": ("test.png", b"fake_image", "image/png")},
        data={"name": "test_template", "manual_tags": json.dumps(["採用", "ポップ"])},
    )
    assert register.status_code == 200
    template_id = register.json()["template_id"]

    response = client.get(f"/api/templates/{template_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == template_id
    assert "structure_json" in payload
    assert "preview_html" in payload
    assert "preview_css" in payload


@patch("app.main.extract_template_structure")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_list_templates_returns_summaries_sorted_by_newest(mock_emb, mock_add_vec, mock_extract):
    mock_extract.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#テスト"])
    mock_emb.return_value = [0.1] * 8

    first = client.post(
        "/api/templates",
        files={"file": ("first.png", b"fake_image", "image/png")},
        data={"name": "first_template", "manual_tags": json.dumps(["採用"])},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/templates",
        files={"file": ("second.png", b"fake_image", "image/png")},
        data={"name": "second_template", "manual_tags": json.dumps(["社員紹介"])},
    )
    assert second.status_code == 200

    response = client.get("/api/templates")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert [item["name"] for item in payload] == ["second_template", "first_template"]
    assert payload[0]["manual_tags"] == ["社員紹介"]
    assert payload[0]["auto_tags"] == ["#採用", "#テスト"]
    assert "created_at" in payload[0]


@patch("app.main.extract_template_structure")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_patch_template_element_style_updates_color_and_preview(mock_emb, mock_add_vec, mock_extract):
    mock_extract.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#テスト"])
    mock_emb.return_value = [0.1] * 8

    register = client.post(
        "/api/templates",
        files={"file": ("test.png", b"fake_image", "image/png")},
        data={"name": "test_template", "manual_tags": json.dumps(["採用", "ポップ"])},
    )
    assert register.status_code == 200
    template_id = register.json()["template_id"]

    response = client.patch(
        f"/api/templates/{template_id}/elements/headline/style",
        json={"color": "#ff0000"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["element"]["style"]["color"] == "#ff0000"
    assert "#ff0000" in payload["preview_css"]


@patch("app.main.extract_template_structure")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_template_editor_page_contains_preview_and_element_tools(mock_emb, mock_add_vec, mock_extract):
    mock_extract.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#テスト"])
    mock_emb.return_value = [0.1] * 8

    register = client.post(
        "/api/templates",
        files={"file": ("test.png", b"fake_image", "image/png")},
        data={"name": "test_template", "manual_tags": json.dumps(["採用", "ポップ"])},
    )
    assert register.status_code == 200
    template_id = register.json()["template_id"]

    response = client.get(f"/templates/{template_id}/editor")

    assert response.status_code == 200
    text = response.text
    assert "template-editor" in text
    assert "preview-frame" in text
    assert "elements-panel" in text
    assert "color-picker" in text


@patch("app.main.TemplateAnalyzer")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_upload_pdf_template_success(mock_emb, mock_add_vec, mock_analyzer_class):
    """PDFファイルのアップロードが成功する"""
    from app.services.template_analyzer import TemplateAnalysis

    mock_analyzer = mock_analyzer_class.return_value
    mock_analyzer.analyze.return_value = TemplateAnalysis(
        canvas={"width": 810, "height": 1012.5},
        text_elements=[{"content": "Test", "x": 10, "y": 20, "width": 30, "height": 5}],
        image_elements=[{"format": "png", "width": 100, "height": 100, "size_bytes": 1000}],
        auto_tags=["#採用", "#インタビュー"],
        atmosphere="プロフェッショナルな採用インタビュー",
        llm_elements=[],
    )
    mock_emb.return_value = [0.1] * 8

    files = {"file": ("test.pdf", b"fake_pdf_content", "application/pdf")}
    data = {"name": "test_pdf_template", "manual_tags": '["採用", "ポップ"]'}
    response = client.post("/api/templates", files=files, data=data)

    assert response.status_code == 200
    assert response.json()["message"] == "success"
    assert "template_id" in response.json()
    mock_analyzer.analyze.assert_called_once()


@patch("app.main.extract_template_structure")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_update_template_structure_json_success(mock_emb, mock_add_vec, mock_extract):
    """structure_jsonの更新が成功する"""
    mock_extract.return_value = (sample_structure(), "Mock atmosphere", ["#採用", "#テスト"])
    mock_emb.return_value = [0.1] * 8

    # テンプレートを作成
    register = client.post(
        "/api/templates",
        files={"file": ("test.png", b"fake_image", "image/png")},
        data={"name": "test_template", "manual_tags": json.dumps(["採用", "ポップ"])},
    )
    assert register.status_code == 200
    template_id = register.json()["template_id"]

    # 元のstructure_jsonを取得
    original = client.get(f"/api/templates/{template_id}")
    assert original.status_code == 200
    original_structure = original.json()["structure_json"]

    # structure_jsonを更新
    updated_structure = original_structure.copy()
    updated_structure["elements"][0]["x"] = 200  # 位置を変更
    updated_structure["elements"][0]["rotation"] = 180  # 回転を追加

    response = client.patch(
        f"/api/templates/{template_id}",
        json={"structure_json": updated_structure},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "success"

    # 更新後のテンプレートを取得して確認
    updated = client.get(f"/api/templates/{template_id}")
    assert updated.status_code == 200
    assert updated.json()["structure_json"]["elements"][0]["x"] == 200
    assert updated.json()["structure_json"]["elements"][0]["rotation"] == 180


@patch("app.main.extract_template_structure")
@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
def test_update_template_not_found(mock_emb, mock_add_vec, mock_extract):
    """存在しないテンプレートの更新は404を返す"""
    response = client.patch(
        "/api/templates/nonexistent-id",
        json={"structure_json": {"canvas": {"width": 100, "height": 100}, "elements": []}},
    )
    assert response.status_code == 404


def test_update_template_requires_structure_json():
    """structure_jsonが必須"""
    response = client.patch("/api/templates/some-id", json={})
    assert response.status_code == 422

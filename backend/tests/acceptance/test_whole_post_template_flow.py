"""投稿全体テンプレート方式の受け入れテスト"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, Generation, Template, get_db
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


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
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
            },
            {
                "id": "cta",
                "type": "text",
                "role": "cta",
                "x": 240,
                "y": 860,
                "width": 600,
                "height": 80,
                "content": "",
                "style": {"font_size": 32, "color": "#333333", "align": "center"},
                "slot": {"name": "cta", "required": True, "max_chars": 12},
            },
        ],
    }


@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
@patch("app.main.extract_template_structure")
def test_register_and_generate_whole_post_template(
    mock_extract, mock_embedding, mock_add_vector
):
    mock_extract.return_value = (sample_structure(), "採用 ポップ 明るい", ["#採用", "#ポップ"])
    mock_embedding.return_value = [0.1] * 8

    files = {"file": ("template.png", b"fake_image", "image/png")}
    data = {
        "name": "recruitment_post",
        "manual_tags": json.dumps(["採用", "ポップ"]),
    }
    register_response = client.post("/api/templates", files=files, data=data)

    assert register_response.status_code == 200
    register_payload = register_response.json()
    assert register_payload["template_id"]
    assert register_payload["manual_tags"] == ["採用", "ポップ"]
    assert "preview_html" in register_payload
    assert "preview_css" in register_payload

    generate_response = client.post(
        "/api/generate",
        json={"tags": ["採用", "ポップ"], "prompt": "新卒採用スタートを明るく伝えたい"},
    )

    assert generate_response.status_code == 200
    generate_payload = generate_response.json()
    assert generate_payload["template_id"] == register_payload["template_id"]
    assert "output_html" in generate_payload
    assert "output_css" in generate_payload
    assert "filled_structure" in generate_payload
    assert "新卒採用" in generate_payload["output_html"]

    db = TestingSessionLocal()
    try:
        generations = db.query(Generation).all()
        assert len(generations) == 1
        assert generations[0].selected_template_id == register_payload["template_id"]
    finally:
        db.close()


@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
@patch("app.main.extract_template_structure")
def test_register_rejects_empty_manual_tags(
    mock_extract, mock_embedding, mock_add_vector
):
    mock_extract.return_value = (sample_structure(), "採用 ポップ", ["#採用", "#ポップ"])
    mock_embedding.return_value = [0.1] * 8

    files = {"file": ("template.png", b"fake_image", "image/png")}
    data = {"name": "recruitment_post", "manual_tags": json.dumps([])}

    response = client.post("/api/templates", files=files, data=data)

    assert response.status_code == 400


@patch("app.main.add_template_vector")
@patch("app.main.get_embedding")
@patch("app.main.extract_template_structure")
def test_generate_returns_not_found_for_unrelated_tags(
    mock_extract, mock_embedding, mock_add_vector
):
    mock_extract.return_value = (sample_structure(), "採用 ポップ 明るい", ["#採用", "#ポップ"])
    mock_embedding.return_value = [0.1] * 8

    files = {"file": ("template.png", b"fake_image", "image/png")}
    data = {
        "name": "recruitment_post",
        "manual_tags": json.dumps(["採用", "ポップ"]),
    }
    register_response = client.post("/api/templates", files=files, data=data)
    assert register_response.status_code == 200

    response = client.post(
        "/api/generate",
        json={"tags": ["料理", "レシピ"], "prompt": "お弁当特集を作りたい"},
    )

    assert response.status_code == 404

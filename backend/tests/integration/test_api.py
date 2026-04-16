"""APIの統合テスト"""
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
            }
        ],
    }


async def register_template(client: AsyncClient):
    from unittest.mock import patch

    with patch("app.main.extract_template_structure") as mock_extract, patch(
        "app.main.get_embedding"
    ) as mock_embedding, patch("app.main.add_template_vector"):
        mock_extract.return_value = (sample_structure(), "採用 ポップ 明るい", ["#採用", "#ポップ"])
        mock_embedding.return_value = [0.1] * 8
        response = await client.post(
            "/api/templates",
            files={"file": ("template.png", b"fake_image", "image/png")},
            data={"name": "recruitment_post", "manual_tags": json.dumps(["新卒採用", "ポップ"])},
        )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_post_generate_returns_html_css():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_template(client)
        response = await client.post(
            "/api/generate",
            json={"tags": ["新卒採用", "ポップ"], "prompt": "若者向けの採用告知"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "output_html" in data
    assert "output_css" in data
    assert "template_id" in data


@pytest.mark.asyncio
async def test_post_generate_uses_saved_template():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        registered = await register_template(client)
        response = await client.post(
            "/api/generate",
            json={"tags": ["新卒採用"], "prompt": "テスト"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["template_id"] == registered["template_id"]
    assert "filled_structure" in data


@pytest.mark.asyncio
async def test_post_generate_rejects_internal_slot_values():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/generate",
            json={
                "tags": ["新卒採用"],
                "prompt": "テスト",
                "slot_values": {"header": {"title": "カスタムタイトル！"}},
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_generate_validates_request():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/generate",
            json={"tags": [], "prompt": "テスト"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_generate_returns_not_found_without_templates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/generate",
            json={"tags": ["新卒採用"], "prompt": "テスト"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_template_updates_structure_json():
    """PATCH /api/templates/{id} でstructure_jsonを更新できる"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # テンプレートを登録
        registered = await register_template(client)
        template_id = registered["template_id"]

        # 元のstructure_jsonを取得
        original = await client.get(f"/api/templates/{template_id}")
        assert original.status_code == 200
        original_structure = original.json()["structure_json"]

        # structure_jsonを更新（位置と回転を変更）
        updated_structure = original_structure.copy()
        updated_structure["elements"] = [
            {**el, "x": 200, "rotation": 180}
            for el in original_structure["elements"]
        ]

        response = await client.patch(
            f"/api/templates/{template_id}",
            json={"structure_json": updated_structure},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "success"

        # 更新後のテンプレートを取得して確認
        updated = await client.get(f"/api/templates/{template_id}")
        assert updated.status_code == 200
        assert updated.json()["structure_json"]["elements"][0]["x"] == 200
        assert updated.json()["structure_json"]["elements"][0]["rotation"] == 180


@pytest.mark.asyncio
async def test_patch_template_not_found():
    """存在しないテンプレートの更新は404を返す"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/api/templates/nonexistent-id",
            json={"structure_json": {"canvas": {"width": 100, "height": 100}, "elements": []}},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_template_requires_structure_json():
    """structure_jsonが必須"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch("/api/templates/some-id", json={})

    assert response.status_code == 422

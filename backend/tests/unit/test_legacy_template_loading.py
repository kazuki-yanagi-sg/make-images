"""旧スキーマテンプレート読み込みのテスト"""
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import _load_whole_post_templates


def test_load_whole_post_templates_reads_manual_tags_from_vector_metadata():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        db.execute(
            text(
                "CREATE TABLE templates ("
                "id VARCHAR PRIMARY KEY, "
                "json_data TEXT NOT NULL, "
                "vector_id VARCHAR)"
            )
        )
        db.execute(
            text(
                "INSERT INTO templates (id, json_data, vector_id) "
                "VALUES (:id, :json_data, :vector_id)"
            ),
            {
                "id": "tpl_legacy",
                "json_data": (
                    '{"elements": [{"type": "text", "role": "headline", "content": "INTERVIEW"}]}'
                ),
                "vector_id": "vec_legacy",
            },
        )
        db.commit()

        fake_collection = Mock()
        fake_collection.get.return_value = {
            "ids": ["tpl_legacy"],
            "metadatas": [
                {
                    "manual_tags": ["社員紹介"],
                    "auto_tags": ["Professional"],
                    "atmosphere": "Professional interview post",
                }
            ],
        }

        with patch("app.main.get_collection", return_value=fake_collection):
            templates = _load_whole_post_templates(db)

    assert len(templates) == 1
    assert templates[0].id == "tpl_legacy"
    assert templates[0].manual_tags_json == ["社員紹介"]
    assert "社員紹介" in templates[0].search_text

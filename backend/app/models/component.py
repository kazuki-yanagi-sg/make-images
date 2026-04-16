"""Componentモデル"""
from uuid import uuid4

from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import JSON

from app.models.base import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    class Vector(JSON):
        """pgvector がない環境向けのフォールバック"""

        cache_ok = True

        def __init__(self, dimensions: int | None = None):
            super().__init__()


class Component(Base):
    """デザインコンポーネントを表すSQLAlchemyモデル"""

    __tablename__ = "components"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    template_html = Column(Text, nullable=True)
    template_css = Column(Text, nullable=True)
    slots = Column(JSONB, default=dict)
    embedding = Column(Vector(1536), nullable=True)
    source_image_url = Column(String(500), nullable=True)

    def __init__(
        self,
        name: str,
        role: str,
        description: str,
        template_html: str | None = None,
        template_css: str | None = None,
        slots: dict | None = None,
        embedding: list[float] | None = None,
        source_image_url: str | None = None,
    ):
        self.id = uuid4()
        self.name = name
        self.role = role
        self.description = description
        self.template_html = template_html
        self.template_css = template_css
        self.slots = slots or {}
        self.embedding = embedding
        self.source_image_url = source_image_url

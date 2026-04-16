"""同期DB定義"""
from sqlalchemy import Column, DateTime, JSON, String, Text, create_engine as _create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone


def create_engine_patch(*args, **kwargs):
    if args and "sqlite://" in args[0] and "memory" in args[0]:
        kwargs["poolclass"] = StaticPool
    return _create_engine(*args, **kwargs)


SQLALCHEMY_DATABASE_URL = "sqlite:///./templates.db"

engine = create_engine_patch(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class Template(Base):
    __tablename__ = "templates"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=True)
    json_data = Column(Text, nullable=False)
    vector_id = Column(String, unique=True, index=True)
    source_image_path = Column(String, nullable=True)
    structure_json = Column(JSON, nullable=True)
    manual_tags_json = Column(JSON, nullable=False, default=list)
    auto_tags_json = Column(JSON, nullable=False, default=list)
    search_text = Column(Text, nullable=True)
    embedding_json = Column(JSON, nullable=True)
    preview_html = Column(Text, nullable=True)
    preview_css = Column(Text, nullable=True)
    atmosphere = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Generation(Base):
    __tablename__ = "generations"

    id = Column(String, primary_key=True, index=True)
    input_tags = Column(JSON, nullable=False, default=list)
    input_prompt = Column(Text, nullable=False)
    selected_template_id = Column(String, nullable=False, index=True)
    candidate_template_ids = Column(JSON, nullable=False, default=list)
    matched_tag_reasons = Column(JSON, nullable=False, default=dict)
    filled_structure_json = Column(JSON, nullable=False)
    output_html = Column(Text, nullable=False)
    output_css = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

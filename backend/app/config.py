"""アプリケーション設定"""
from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    """アプリケーション設定クラス"""

    database_url: str = "postgresql://postgres:postgres@localhost:5432/make_images"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """設定のシングルトンインスタンスを返す"""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/make_images",
        ),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

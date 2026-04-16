"""設定モジュールのテスト"""
import pytest
from app.config import get_settings, Settings


def test_settings_has_database_url():
    """設定にdatabase_urlが含まれること"""
    settings = get_settings()
    assert hasattr(settings, "database_url")
    assert settings.database_url is not None


def test_settings_has_openai_api_key():
    """設定にopenai_api_keyが含まれること"""
    settings = get_settings()
    assert hasattr(settings, "openai_api_key")


def test_settings_has_anthropic_api_key():
    """設定にanthropic_api_keyが含まれること"""
    settings = get_settings()
    assert hasattr(settings, "anthropic_api_key")


def test_settings_singleton():
    """get_settingsはシングルトンを返すこと"""
    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2

"""
config.py
─────────
Configuration classes for eltut-tours-platform.

Every value is sourced from environment variables (loaded by python-dotenv).
No secrets, URLs or credentials are hardcoded.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR: Path = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(key: str, default: int = 0) -> int:
    raw = os.getenv(key)
    try:
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


class BaseConfig:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    APP_NAME: str = os.getenv("APP_NAME", "ElTut Tours")
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:5000")

    SESSION_COOKIE_HTTPONLY: bool = _bool("SESSION_COOKIE_HTTPONLY", True)
    SESSION_COOKIE_SECURE: bool = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE: str = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME: timedelta = timedelta(
        seconds=_int("PERMANENT_SESSION_LIFETIME", 86400)
    )

    SQLALCHEMY_DATABASE_URI: str = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = _bool("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": _bool("SQLALCHEMY_ENGINE_OPTIONS_POOL_PRE_PING", True),
        "pool_recycle": _int("SQLALCHEMY_ENGINE_OPTIONS_POOL_RECYCLE", 300),
    }

    MONGO_URI: str = os.getenv("MONGO_URI", "")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "eltut_tours")

    MAIL_SERVER: str = os.getenv("MAIL_SERVER", "smtp.ionos.com")
    MAIL_PORT: int = _int("MAIL_PORT", 587)
    MAIL_USE_TLS: bool = _bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL: bool = _bool("MAIL_USE_SSL", False)
    MAIL_USERNAME: str = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER: str = os.getenv("MAIL_DEFAULT_SENDER", "")
    MAIL_ADMIN_RECIPIENT: str = os.getenv("MAIL_ADMIN_RECIPIENT", "")

    PAYPAL_MODE: str = os.getenv("PAYPAL_MODE", "sandbox")
    PAYPAL_CLIENT_ID: str = os.getenv("PAYPAL_CLIENT_ID", "")
    PAYPAL_CLIENT_SECRET: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    PAYPAL_CURRENCY: str = os.getenv("PAYPAL_CURRENCY", "USD")
    PAYPAL_RETURN_URL: str = os.getenv("PAYPAL_RETURN_URL", "")
    PAYPAL_CANCEL_URL: str = os.getenv("PAYPAL_CANCEL_URL", "")

    CLOUD_FUNCTION_URL: str = os.getenv("CLOUD_FUNCTION_URL", "")
    CLOUD_FUNCTION_SECRET: str = os.getenv("CLOUD_FUNCTION_SECRET", "")

    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_NAME: str = os.getenv("ADMIN_NAME", "ElTut Admin")

    UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", "static/images/uploads")
    MAX_CONTENT_LENGTH: int = _int("MAX_CONTENT_LENGTH", 64 * 1024 * 1024)
    ITEMS_PER_PAGE: int = _int("ITEMS_PER_PAGE", 12)


class DevelopmentConfig(BaseConfig):
    DEBUG: bool = True
    ENV: str = "development"
    SESSION_COOKIE_SECURE: bool = False


class ProductionConfig(BaseConfig):
    DEBUG: bool = False
    ENV: str = "production"
    SESSION_COOKIE_SECURE: bool = True


class TestingConfig(BaseConfig):
    TESTING: bool = True
    DEBUG: bool = True
    WTF_CSRF_ENABLED: bool = False
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    MAIL_SUPPRESS_SEND: bool = True


CONFIG_MAP: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}

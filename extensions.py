"""
extensions.py
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Uninitialised extension singletons for eltut-tours-platform.

Each extension is created here *without* an app attached. The factory in
app.py binds them via `init_app(app)` â€” this is the standard Flask
application-factory pattern and it keeps the app testable (same extension
objects, different configs per environment).

Nothing in this file reads config or touches a database at import time.
"""

from __future__ import annotations

from typing import Any

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from pymongo import MongoClient
from pymongo.database import Database


# â”€â”€â”€ SQL (Neon Postgres) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
db: SQLAlchemy = SQLAlchemy()
migrate: Migrate = Migrate()


# â”€â”€â”€ Auth & security â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
login_manager: LoginManager = LoginManager()
csrf: CSRFProtect = CSRFProtect()

# Rate limiter â€” storage URI can be overridden via init_app in the factory.
limiter: Limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


# â”€â”€â”€ Mail (IONOS SMTP) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
mail: Mail = Mail()


# â”€â”€â”€ NoSQL (MongoDB Atlas) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# The MongoClient is created lazily inside init_mongo() so that simply
# importing this module never opens a socket (important for tests).
_mongo_client: MongoClient[Any] | None = None
_mongo_db: Database[Any] | None = None


# Strings that indicate the .env file still holds a placeholder, not a
# real Atlas connection string. Used to skip Mongo init gracefully.
_MONGO_PLACEHOLDER_TOKENS: tuple[str, ...] = (
    "USER:PASSWORD",
    "cluster.mongodb.net",
    "your-cluster",
)


def _mongo_uri_is_placeholder(uri: str) -> bool:
    """Return True if the URI still contains obvious placeholder text."""
    if not uri:
        return True
    return any(token in uri for token in _MONGO_PLACEHOLDER_TOKENS)


def init_mongo(uri: str, db_name: str) -> Database[Any] | None:
    """
    Create (or reuse) the shared MongoDB client/database handle.

    Called once by the app factory after config is loaded. Idempotent â€”
    safe to call multiple times with the same URI (e.g. pytest re-imports).

    Returns None (and does not raise) if the URI is still a placeholder,
    so the app can boot before real Atlas credentials exist.

    Parameters
    ----------
    uri : str
        MongoDB Atlas connection string (mongodb+srv://...).
    db_name : str
        Target database name (e.g. "eltut_tours").

    Returns
    -------
    pymongo.database.Database | None
        The shared database handle, or None if not initialised.
    """
    global _mongo_client, _mongo_db

    if _mongo_uri_is_placeholder(uri):
        # Don't even attempt DNS â€” the URI is a template. Boot anyway.
        return None

    if _mongo_client is None:
        _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _mongo_db = _mongo_client[db_name]
    return _mongo_db


def get_mongo_db() -> Database[Any]:
    """
    Return the current MongoDB database handle.

    Raises
    ------
    RuntimeError
        If `init_mongo()` has not been called yet, or if it returned None
        because the URI was still a placeholder.
    """
    if _mongo_db is None:
        raise RuntimeError(
            "MongoDB has not been initialised. "
            "Set a real MONGO_URI in .env and let the app factory run, "
            "or call extensions.init_mongo(uri, db_name) manually."
        )
    return _mongo_db


# ─── UK date filters (registered from app.py via register_date_filters) ───
_UK_DATE_FMT = "%d %b %Y"
_UK_DATETIME_FMT = "%d %b %Y, %H:%M"
_UK_DATE_LONG_FMT = "%d %B %Y"
_UK_DATE_SHORT_FMT = "%d/%m/%Y"
_UK_DATE_WEEKDAY_FMT = "%a %d %b %Y"


def _safe_strftime(value: Any, fmt: str, default: str = "") -> str:
    """Format any date/datetime as a UK string; never raise."""
    if value is None:
        return default
    try:
        return value.strftime(fmt)
    except Exception:
        return default


def uk_date(value: Any, default: str = "") -> str:
    """10 Nov 2026"""
    return _safe_strftime(value, _UK_DATE_FMT, default)


def uk_datetime(value: Any, default: str = "") -> str:
    """10 Nov 2026, 14:30"""
    return _safe_strftime(value, _UK_DATETIME_FMT, default)


def uk_date_long(value: Any, default: str = "") -> str:
    """10 November 2026"""
    return _safe_strftime(value, _UK_DATE_LONG_FMT, default)


def uk_date_short(value: Any, default: str = "") -> str:
    """10/11/2026"""
    return _safe_strftime(value, _UK_DATE_SHORT_FMT, default)


def uk_date_weekday(value: Any, default: str = "") -> str:
    """Tue 10 Nov 2026"""
    return _safe_strftime(value, _UK_DATE_WEEKDAY_FMT, default)


def register_date_filters(app) -> None:
    """Register all UK date filters on the app's Jinja environment."""
    app.jinja_env.filters["uk_date"] = uk_date
    app.jinja_env.filters["uk_datetime"] = uk_datetime
    app.jinja_env.filters["uk_date_long"] = uk_date_long
    app.jinja_env.filters["uk_date_short"] = uk_date_short
    app.jinja_env.filters["uk_date_weekday"] = uk_date_weekday

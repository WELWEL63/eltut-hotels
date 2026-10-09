"""
extensions.py
─────────────
Uninitialised extension singletons for eltut-tours-platform.

Each extension is created here *without* an app attached. The factory in
app.py binds them via `init_app(app)` — this is the standard Flask
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


# ─── SQL (Neon Postgres) ───────────────────────────────────────────
db: SQLAlchemy = SQLAlchemy()
migrate: Migrate = Migrate()


# ─── Auth & security ───────────────────────────────────────────────
login_manager: LoginManager = LoginManager()
csrf: CSRFProtect = CSRFProtect()

# Rate limiter — storage URI can be overridden via init_app in the factory.
limiter: Limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


# ─── Mail (IONOS SMTP) ─────────────────────────────────────────────
mail: Mail = Mail()


# ─── NoSQL (MongoDB Atlas) ─────────────────────────────────────────
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

    Called once by the app factory after config is loaded. Idempotent —
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
        # Don't even attempt DNS — the URI is a template. Boot anyway.
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

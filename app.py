"""
app.py
──────
Application factory for eltut-tours-platform.

This is the *only* place the Flask app is created. It:
  1. Reads FLASK_ENV and picks the matching config class from config.py
  2. Binds every extension in extensions.py via init_app()
  3. Initialises the MongoDB client (lazily, once)
  4. Registers Jinja filters, error handlers and logging
  5. Registers all blueprints in a deterministic order
  6. Ensures runtime folders (instance/, uploads/) exist

Exposed module-level object:
    app  —  so `gunicorn app:app` works on Render without an entry script.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from flask import Flask, render_template

from config import CONFIG_MAP, BaseConfig
from utils import register_template_helpers, css_style
from extensions import (
    csrf,
    db,
    init_mongo,
    limiter,
    login_manager,
    mail,
    migrate,
    register_date_filters,
)


# ─── Paths ─────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent


# ─── Extension setup helpers ───────────────────────────────────────
def _configure_logging(app: Flask) -> None:
    """Attach a rotating file handler and a console handler."""
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_dir / "eltut.log", maxBytes=1_000_000, backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    if not app.debug:
        app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info("ElTut Tours startup")


def _ensure_runtime_folders(app: Flask) -> None:
    """Create folders the app writes to at runtime (uploads, instance)."""
    (BASE_DIR / "instance").mkdir(exist_ok=True)
    (BASE_DIR / app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)


def _register_jinja_filters(app: Flask) -> None:
    """Small, globally useful Jinja filters used across templates."""

    @app.template_filter("currency")
    def currency_filter(value: Any, symbol: str = "$") -> str:
        """Format a number as currency: 1234.5 -> '$1,234.50'."""
        try:
            return f"{symbol}{float(value):,.2f}"
        except (TypeError, ValueError):
            return f"{symbol}0.00"

    @app.template_filter("truncate_words")
    def truncate_words_filter(text: str | None, count: int = 20) -> str:
        """Truncate to N words with an ellipsis."""
        if not text:
            return ""
        words = text.split()
        return " ".join(words[:count]) + ("…" if len(words) > count else "")
    @app.template_filter("uk_date")
    def uk_date_filter(value: Any) -> str:
        """
        Format a date/datetime/ISO-string as '11 Oct 2026'.

        Returns '' for None, and falls back to str(value) for
        unparseable input (so templates never crash on bad data).
        """
        if value is None:
            return ""
        try:
            # datetime with time component
            from datetime import date, datetime
            if isinstance(value, datetime):
                return value.strftime("%d %b %Y")
            if isinstance(value, date):
                return value.strftime("%d %b %Y")
            # ISO string
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return ""
                # Try full ISO datetime first, then date-only
                for fmt in (None, "%Y-%m-%d"):
                    try:
                        if fmt is None:
                            dt = datetime.fromisoformat(s.replace("Z", ""))
                        else:
                            dt = datetime.strptime(s, fmt)
                        return dt.strftime("%d %b %Y")
                    except (ValueError, TypeError):
                        continue
        except Exception:
            pass
        return str(value)

    @app.template_filter("uk_range")
    def uk_range_filter(value: Any) -> str:
        """
        Format a (start, end) tuple/pair as '11 Oct 2026 → 18 Oct 2026'.

        Accepts a tuple, list, or dict with 'start'/'end' keys.
        """
        if value is None:
            return ""
        try:
            if isinstance(value, dict):
                start = value.get("start")
                end = value.get("end")
            else:
                start, end = value  # tuple/list of 2

            start_s = uk_date_filter(start)
            end_s = uk_date_filter(end)

            if start_s and end_s:
                return f"{start_s} → {end_s}"
            return start_s or end_s or ""
        except Exception:
            return ""

def _register_error_handlers(app: Flask) -> None:
    """Custom 404/500 handlers — fall back to plain text if templates missing."""

    @app.errorhandler(404)
    def not_found(_err: Exception) -> tuple[str, int]:
        try:
            return render_template("errors/404.html"), 404
        except Exception:  # noqa: BLE001 — template may not exist yet
            return "404 — Not Found", 404

    @app.errorhandler(500)
    def server_error(err: Exception) -> tuple[str, int]:
        app.logger.exception("Unhandled exception: %s", err)
        try:
            return render_template("errors/500.html"), 500
        except Exception:  # noqa: BLE001
            return "500 — Internal Server Error", 500


def _register_user_loader(app: Flask) -> None:
    """
    Wire Flask-Login's user loader.

    Tolerant of a missing models package — this is a no-op until Step 3
    creates models/user.py. Once the model exists, the loader wires up
    normally. The try/except is intentionally narrow: only ImportError
    is swallowed so genuine errors still surface.
    """
    try:
        from models.user import User  # noqa: PLC0415 — intentional late import
    except ImportError:
        app.logger.debug(
            "models.user not present yet — Flask-Login user loader skipped"
        )
        return

    @login_manager.user_loader
    def load_user(user_id: str) -> Any:  # noqa: ANN401 — User type arrives later
        return db.session.get(User, int(user_id))


def _register_blueprints(app: Flask) -> None:
    """
    Register blueprints in a deterministic order.

    Each import is inside the function so that blueprints can safely
    import `db`, `mail`, etc. without any circular-import dance at
    module load time. Until the blueprints exist (Steps 8-12), the
    imports are wrapped in try/except so the skeleton app still boots.
    """
    # Auth — must be earliest so /login, /register resolve before catch-alls
    try:
        from blueprints.auth import auth_bp  # type: ignore
        app.register_blueprint(auth_bp)
    except ImportError:
        app.logger.debug("auth blueprint not yet present — skipping")

    # Account — authenticated customer area
    try:
        from blueprints.account import account_bp  # type: ignore
        app.register_blueprint(account_bp)
    except ImportError:
        app.logger.debug("account blueprint not yet present — skipping")

    # Public — customer-facing site
    try:
        from blueprints.public import public_bp  # type: ignore
        app.register_blueprint(public_bp)
    except ImportError:
        app.logger.debug("public blueprint not yet present — skipping")

    # Admin
    try:
        from blueprints.admin import admin_bp  # type: ignore
        app.register_blueprint(admin_bp, url_prefix="/admin")
    except ImportError:
        app.logger.debug("admin blueprint not yet present — skipping")

    # REST API
    try:
        from blueprints.api import api_bp  # type: ignore
        app.register_blueprint(api_bp, url_prefix="/api/v1")
        # WHY: the API is stateless (no cookies, no session, no
        # login_required). CSRF protects cookie-authenticated browser
        # sessions against cross-site form submission. There is no
        # cookie to protect here, and a cross-origin form cannot set
        # Content-Type: application/json without triggering a CORS
        # preflight (which we do not enable). CSRF is therefore not
        # applicable to this blueprint.
        csrf.exempt(api_bp)
    except ImportError:
        app.logger.debug("api blueprint not yet present — skipping")


# ─── Factory ───────────────────────────────────────────────────────
def create_app(config_name: str | None = None) -> Flask:
    """
    Build and return a configured Flask application.

    Parameters
    ----------
    config_name : str | None
        One of "development", "production", "testing", "default".
        If None, FLASK_ENV from the environment decides (defaults to
        "development").

    Returns
    -------
    Flask
        Fully wired application instance.
    """
    env = (config_name or os.getenv("FLASK_ENV") or "development").lower()
    config_cls: type[BaseConfig] = CONFIG_MAP.get(env, CONFIG_MAP["default"])

    app = Flask(__name__, instance_relative_config=False)
    register_date_filters(app)
    app.config.from_object(config_cls)

    # ─── Bind extensions ───────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    # Sensible login defaults
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "warning"

    # ─── Mongo (lazy — do not connect in testing) ──────────────────
    if not app.config.get("TESTING"):
        mongo_db = init_mongo(
            app.config.get("MONGO_URI", ""),
            app.config.get("MONGO_DB_NAME", "eltut_tours"),
        )
        if mongo_db is None:
            app.logger.warning(
                "MONGO_URI is unset or still a placeholder — "
                "Mongo-backed features (reviews, enquiries, logs) will "
                "raise at request time until a real Atlas URI is provided."
            )

    # ─── Ensure Mongo indexes (no-op if Mongo not initialised) ─────
    if not app.config.get("TESTING"):
        try:
            from mongo.client import ensure_indexes  # noqa: PLC0415
            ensure_indexes(app)
        except Exception as _mongo_idx_exc:  # noqa: BLE001
            app.logger.warning(
                "ensure_indexes() failed at startup: %s", _mongo_idx_exc
            )

    # ─── Cross-cutting setup ───────────────────────────────────────
    _ensure_runtime_folders(app)
    _configure_logging(app)
    _register_jinja_filters(app)
    register_template_helpers(app)   # maybe_url() defensive helper
    app.jinja_env.filters["css_style"] = css_style
    _register_error_handlers(app)
    _register_user_loader(app)
    _register_blueprints(app)

    # ─── Security Headers ──────────────────────────────────────────
    @app.after_request
    def add_security_headers(response):
        """Add standard security headers to every response."""
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        # Basic Content Security Policy
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "img-src 'self' data: https: blob:; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://weather-website-client.tomorrow.io; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
                "https://www.tomorrow.io https://api.tomorrow.io https://widget.tomorrow.io https://cdn.tomorrow.io "
                "https://weather-website-client.tomorrow.io "
                "https://www.googletagmanager.com https://www.google-analytics.com "
                "https://connect.facebook.net "
                "https://static.klaviyo.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com "
                "https://weather-website-client.tomorrow.io https://cdn.tomorrow.io; "
            "connect-src 'self' https://cdn.jsdelivr.net "
                "https://api.tomorrow.io https://www.tomorrow.io https://widget.tomorrow.io "
                "https://weather-website-client.tomorrow.io "
                "https://api.wise.com https://wise.com https://www.wise.com "
                "https://www.google-analytics.com https://www.googletagmanager.com "
                "https://connect.facebook.net; "
            "frame-src 'self' https://maps.google.com https://www.google.com "
                "https://wise.com https://www.wise.com "
                "https://www.tomorrow.io; "
            "worker-src 'self' blob:; "
        )
        return response
    # ───────────────────────────────────────────────────────────────

    # ─── Jinja global: content() ─────────────────────────────────────
    # WHY a Jinja global rather than a context processor: this helper
    # is called from every template, needs to be fast, and doesn't
    # depend on request-scoped variables. The service caches per
    # request so N calls cost 1 query.
    from services import content_service as _content_service

    def _content(key: str, default: str | None = None) -> str:
        """Template helper: fetch admin-editable content or fallback."""
        try:
            return _content_service.get(key, default) or ""
        except Exception:
            return default or ""

    app.jinja_env.globals["content"] = _content

    # Small time helpers usable from any template.
    from datetime import date as _date, datetime as _datetime
    app.jinja_env.globals["today"] = lambda: _date.today()
    app.jinja_env.globals["now"] = lambda: _datetime.now()

    # Cached list of destinations for search widget dropdowns.
    # Uses a request-scoped cache so N widgets per page cost 1 query.
    def _search_destinations():
        try:
            from flask import g
            cached = getattr(g, "_search_destinations_cache", None)
            if cached is not None:
                return cached
            from services import search_service
            dests = search_service.destinations_for_widget()
            g._search_destinations_cache = dests
            return dests
        except Exception:
            return []

    app.jinja_env.globals["search_destinations"] = _search_destinations

    # Same idea, but only destinations that have at least one active
    # package. Used by the Packages tab of the search widget so
    # customers only see destinations they can actually book.
    def _search_package_destinations():
        try:
            from flask import g
            cached = getattr(g, "_search_pkg_destinations_cache", None)
            if cached is not None:
                return cached
            from services import search_service
            dests = search_service.destinations_for_package_widget()
            g._search_pkg_destinations_cache = dests
            return dests
        except Exception:
            return []

    app.jinja_env.globals["search_package_destinations"] = _search_package_destinations

    # Home page slideshow slides — cached per request.
    def _slideshow_slides():
        try:
            from flask import g
            cached = getattr(g, "_slideshow_slides_cache", None)
            if cached is not None:
                return cached
            from services import content_service
            slides = content_service.slideshow_slides()
            g._slideshow_slides_cache = slides
            return slides
        except Exception:
            return []

    app.jinja_env.globals["slideshow_slides"] = _slideshow_slides

    # ─── Tiny healthcheck route so we can test before blueprints land ─
    @app.route("/_health")
    def _health() -> dict[str, str]:
        return {"status": "ok", "app": app.config["APP_NAME"], "env": env}

    app.logger.info("App created — env=%s, config=%s", env, config_cls.__name__)
    return app


# ─── Module-level app (for `gunicorn app:app`) ─────────────────────
# Wrapped so a misconfigured .env never blocks importing app.py during
# development (e.g. before Atlas / Neon credentials exist). In production
# we WANT this to raise loudly, so the wrapper is DEBUG-only.
try:
    app: Flask | None = create_app()
except Exception as _exc:  # noqa: BLE001 — deliberately broad
    if os.getenv("FLASK_ENV", "development").lower() == "production":
        raise
    logging.getLogger(__name__).warning(
        "create_app() failed at import time in dev — continuing without "
        "module-level app. Reason: %s",
        _exc,
    )
    app = None


if __name__ == "__main__":
    # Local dev only; Render uses gunicorn.
    if app is None:
        app = create_app()
    app.run(debug=app.config.get("FLASK_DEBUG", False))
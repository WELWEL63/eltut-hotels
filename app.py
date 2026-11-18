"""
app.py
──────
Application factory for eltut-hotels.
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
    app.logger.info("ElTut Hotels startup")


def _ensure_runtime_folders(app: Flask) -> None:
    """Create folders the app writes to at runtime (uploads, instance)."""
    (BASE_DIR / "instance").mkdir(exist_ok=True)
    (BASE_DIR / app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)


def _register_jinja_filters(app: Flask) -> None:
    """Small, globally useful Jinja filters used across templates."""

    @app.template_filter("currency")
    def currency_filter(value: Any, symbol: str = "$") -> str:
        try:
            return f"{symbol}{float(value):,.2f}"
        except (TypeError, ValueError):
            return f"{symbol}0.00"

    @app.template_filter("truncate_words")
    def truncate_words_filter(text: str | None, count: int = 20) -> str:
        if not text:
            return ""
        words = text.split()
        return " ".join(words[:count]) + ("…" if len(words) > count else "")

    @app.template_filter("uk_date")
    def uk_date_filter(value: Any) -> str:
        if value is None:
            return ""
        try:
            from datetime import date, datetime
            if isinstance(value, datetime):
                return value.strftime("%d %b %Y")
            if isinstance(value, date):
                return value.strftime("%d %b %Y")
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return ""
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
        if value is None:
            return ""
        try:
            if isinstance(value, dict):
                start = value.get("start")
                end = value.get("end")
            else:
                start, end = value

            start_s = uk_date_filter(start)
            end_s = uk_date_filter(end)

            if start_s and end_s:
                return f"{start_s} → {end_s}"
            return start_s or end_s or ""
        except Exception:
            return ""


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_err: Exception) -> tuple[str, int]:
        try:
            return render_template("errors/404.html"), 404
        except Exception:
            return "404 — Not Found", 404

    @app.errorhandler(500)
    def server_error(err: Exception) -> tuple[str, int]:
        app.logger.exception("Unhandled exception: %s", err)
        try:
            return render_template("errors/500.html"), 500
        except Exception:
            return "500 — Internal Server Error", 500


def _register_user_loader(app: Flask) -> None:
    try:
        from models.user import User
    except ImportError:
        app.logger.debug("models.user not present yet — Flask-Login user loader skipped")
        return

    @login_manager.user_loader
    def load_user(user_id: str) -> Any:
        return db.session.get(User, int(user_id))


def _register_blueprints(app: Flask) -> None:
    # Auth
    try:
        from blueprints.auth import auth_bp
        app.register_blueprint(auth_bp)
    except Exception as e:
        print(f"AUTH BLUEPRINT FAILED: {e}")

    # Account
    try:
        from blueprints.account import account_bp
        app.register_blueprint(account_bp)
    except Exception as e:
        print(f"ACCOUNT BLUEPRINT FAILED: {e}")

    # Public
    try:
        from blueprints.public import public_bp
        app.register_blueprint(public_bp)
    except Exception as e:
        print(f"PUBLIC BLUEPRINT FAILED: {e}")

    # Admin
    try:
        from blueprints.admin import admin_bp
        app.register_blueprint(admin_bp, url_prefix="/admin")
    except Exception as e:
        print(f"ADMIN BLUEPRINT FAILED: {e}")

    # REST API
    try:
        from blueprints.api import api_bp
        app.register_blueprint(api_bp, url_prefix="/api/v1")
        csrf.exempt(api_bp)
    except Exception as e:
        print(f"API BLUEPRINT FAILED: {e}")


# ─── Factory ───────────────────────────────────────────────────────
def create_app(config_name: str | None = None) -> Flask:
    env = (config_name or os.getenv("FLASK_ENV") or "development").lower()
    config_cls: type[BaseConfig] = CONFIG_MAP.get(env, CONFIG_MAP["default"])

    app = Flask(__name__, instance_relative_config=False)
    register_date_filters(app)
    app.config.from_object(config_cls)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "warning"

    if not app.config.get("TESTING"):
        mongo_db = init_mongo(
            app.config.get("MONGO_URI", ""),
            app.config.get("MONGO_DB_NAME", "eltut_hotels"),
        )
        if mongo_db is None:
            app.logger.warning("MONGO_URI is unset or still a placeholder.")

    if not app.config.get("TESTING"):
        try:
            from mongo.client import ensure_indexes
            ensure_indexes(app)
        except Exception as _mongo_idx_exc:
            app.logger.warning("ensure_indexes() failed: %s", _mongo_idx_exc)

    _ensure_runtime_folders(app)
    _configure_logging(app)
    _register_jinja_filters(app)
    register_template_helpers(app)
    app.jinja_env.filters["css_style"] = css_style
    _register_error_handlers(app)
    _register_user_loader(app)
    _register_blueprints(app)

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "img-src 'self' data: https: blob:; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://weather-website-client.tomorrow.io; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.tomorrow.io https://api.tomorrow.io https://widget.tomorrow.io https://cdn.tomorrow.io https://weather-website-client.tomorrow.io https://www.googletagmanager.com https://www.google-analytics.com https://connect.facebook.net https://static.klaviyo.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com https://weather-website-client.tomorrow.io https://cdn.tomorrow.io; "
            "connect-src 'self' https://cdn.jsdelivr.net https://api.tomorrow.io https://www.tomorrow.io https://widget.tomorrow.io https://weather-website-client.tomorrow.io https://api.wise.com https://wise.com https://www.wise.com https://www.google-analytics.com https://www.googletagmanager.com https://connect.facebook.net; "
            "frame-src 'self' https://maps.google.com https://www.google.com https://wise.com https://www.wise.com https://www.tomorrow.io; "
            "worker-src 'self' blob:; "
        )
        return response

    from services import content_service as _content_service

    def _content(key: str, default: str | None = None) -> str:
        try:
            return _content_service.get(key, default) or ""
        except Exception:
            return default or ""

    app.jinja_env.globals["content"] = _content

    from datetime import date as _date, datetime as _datetime
    app.jinja_env.globals["today"] = lambda: _date.today()
    app.jinja_env.globals["now"] = lambda: _datetime.now()

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

    @app.route("/_health")
    def _health() -> dict[str, str]:
        return {"status": "ok", "app": app.config["APP_NAME"], "env": env}

    app.logger.info("App created — env=%s, config=%s", env, config_cls.__name__)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=app.config.get("FLASK_DEBUG", False))
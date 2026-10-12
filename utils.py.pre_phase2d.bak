"""
utils.py
────────
Small cross-cutting helpers used by templates and routes.

WHY THIS FILE EXISTS
    As the app is built incrementally, some templates reference url_for()
    endpoints that don't exist yet (e.g. base.html's nav links to
    routes we haven't built). Rather than crashing, we register a
    template global `maybe_url()` that returns "#" if the endpoint is
    missing.

    This keeps the app bootable at every step — a deliberate choice for
    a build-as-we-go project.
"""

from __future__ import annotations

from typing import Any

from flask import url_for
from werkzeug.routing.exceptions import BuildError


def maybe_url(endpoint: str, **values: Any) -> str:
    """
    Like url_for(), but returns '#' if the endpoint does not exist or
    cannot be built (e.g. missing required parameter).

    Usage in templates:
        <a href="{{ maybe_url('public.activity_list') }}">Activities</a>
    """
    try:
        return url_for(endpoint, **values)
    except BuildError:
        return "#"


def register_template_helpers(app) -> None:
    """Register every helper this module exposes on the given Flask app."""
    app.jinja_env.globals["maybe_url"] = maybe_url

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


def css_style(style: dict | None) -> str:
    """Turn a style dict from the CMS into a CSS style string.

    Handles the 9 style fields used by slideshow / hero content:
      font_family, font_size, font_weight, color, align,
      letter_spacing, line_height, text_shadow, text_transform.

    text_shadow is an enum string, not a raw CSS value:
      "soft" / "glow" / "gold-glow" / "none" / ""

    Returns a semicolon-joined CSS string, or "" if input is empty.
    Safe to use inline: style="{{ slide.title_style | css_style }}"
    """
    if not style:
        return ""

    parts: list[str] = []
    for css_prop, key in (
        ("font-family", "font_family"),
        ("font-size", "font_size"),
        ("font-weight", "font_weight"),
        ("color", "color"),
        ("text-align", "align"),
        ("letter-spacing", "letter_spacing"),
        ("line-height", "line_height"),
        ("text-transform", "text_transform"),
    ):
        v = (style.get(key) or "").strip()
        if v and v.lower() not in ("none", "normal"):
            parts.append(f"{css_prop}:{v}")

    shadow = (style.get("text_shadow") or "").strip().lower()
    shadow_css = {
        "soft":       "0 2px 12px rgba(0,0,0,0.35)",
        "glow":       "0 2px 24px rgba(0,0,0,0.6)",
        "gold-glow":  "0 0 20px rgba(212,160,23,0.6)",
    }.get(shadow)
    if shadow_css:
        parts.append(f"text-shadow:{shadow_css}")

    return ";".join(parts)

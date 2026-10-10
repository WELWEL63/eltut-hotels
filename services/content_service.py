"""
services/content_service.py
────────────────────────────
Admin-editable public page content — key/value store with in-request cache.

WHY THIS SERVICE EXISTS
    Admins need to change hero headlines, about-us paragraphs, footer
    text, hero images etc. without redeploying. Every such editable
    string lives in the `site_content` table under a dotted key like
    `home.hero.title`. Templates call `content("home.hero.title",
    "Default text")` and get either the admin's value or the default.

PUBLIC API
    registry() -> dict[str, ContentSpec]           all known keys
    defaults() -> dict[str, str]                   all default values
    get(key, default=None) -> str                  one value (cached)
    all_values() -> dict[str, str]                 every key -> value
    by_page(page=None) -> dict[str, list[SiteContent]]  admin listing
    set_value(key, value, user=None) -> SiteContent  admin write
    clear_cache() -> None                          bust the in-request cache
    seed_defaults(session) -> int                  insert any missing keys

DESIGN NOTES
    - Values are cached per-request in flask.g. Every template render
      therefore costs at most ONE query, no matter how many keys are
      referenced.
    - Registry is a static dict on this module — the single source of
      truth for which keys exist. Adding a key means adding one entry
      here; defaults() and seed_defaults() pick it up automatically.
    - Missing keys fall back to the registry default, then to the
      caller-supplied default. This means:
        * New deployments render fine before seed_defaults() has run.
        * Deleted keys gracefully revert to the code default.
        * Admin can clear a value and the page still works.
    - set_value() busts the in-request cache so a subsequent render
      in the same request sees the new value.
    - seed_defaults() is idempotent: only inserts keys that are missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from extensions import db
from models import SiteContent
from models import (
    CONTENT_TYPE_TEXT,
    CONTENT_TYPE_HTML,
    CONTENT_TYPE_IMAGE_URL,
    CONTENT_TYPE_MARKDOWN,
    PAGE_HOME,
    PAGE_ABOUT,
    PAGE_CONTACT,
    PAGE_FOOTER,
    PAGE_GLOBAL,
    PAGE_SLIDESHOW,
    SLIDESHOW_SLOT_COUNT,
)


log = logging.getLogger(__name__)


# ─── Registry ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ContentSpec:
    """Spec for one editable content key."""
    key: str
    page: str
    label: str
    default: str
    content_type: str = CONTENT_TYPE_TEXT
    notes: str = ""
    sort_order: int = 0


# Single source of truth. Add rows here to introduce new editable
# fields; seed_defaults() will backfill them on next run.
_REGISTRY: dict[str, ContentSpec] = {
    # ─── Home page ─────────────────────────────────────────────────────
    "home.hero.title": ContentSpec(
        key="home.hero.title",
        page=PAGE_HOME,
        label="Home — hero title",
        default="Discover Egypt with ElTut Tours",
        content_type=CONTENT_TYPE_HTML,
        notes="Main headline at the top of the homepage.",
        sort_order=10,
    ),
    "home.hero.subtitle": ContentSpec(
        key="home.hero.subtitle",
        page=PAGE_HOME,
        label="Home — hero subtitle",
        default="Curated hotels, unforgettable packages, and hand-picked activities across Egypt.",
        content_type=CONTENT_TYPE_HTML,
        notes="Supporting text below the hero title.",
        sort_order=20,
    ),
    "home.hero.image_url": ContentSpec(
        key="home.hero.image_url",
        page=PAGE_HOME,
        label="Home — hero background image",
        default="/static/images/hero-default.jpg",
        content_type=CONTENT_TYPE_IMAGE_URL,
        notes="Full URL or /static/... path. Recommended: 1920x1080.",
        sort_order=30,
    ),
    "home.hero.cta_text": ContentSpec(
        key="home.hero.cta_text",
        page=PAGE_HOME,
        label="Home — hero button text",
        default="Start exploring",
        content_type=CONTENT_TYPE_HTML,
        sort_order=40,
    ),

    # ─── About page ────────────────────────────────────────────────────
    "about.title": ContentSpec(
        key="about.title",
        page=PAGE_ABOUT,
        label="About — page title",
        default="About ElTut Tours",
        content_type=CONTENT_TYPE_HTML,
        sort_order=10,
    ),
    "about.intro": ContentSpec(
        key="about.intro",
        page=PAGE_ABOUT,
        label="About — intro paragraph",
        default=(
            "ElTut Tours is an Egypt-based travel company curating "
            "hotels, tours, and multi-day packages for international "
            "visitors. Since our founding we have helped thousands of "
            "travellers explore the Red Sea, the Nile, and the "
            "Pyramids."
        ),
        content_type=CONTENT_TYPE_HTML,
        sort_order=20,
    ),
    "about.mission": ContentSpec(
        key="about.mission",
        page=PAGE_ABOUT,
        label="About — mission statement",
        default="To make Egyptian travel effortless, transparent, and unforgettable.",
        content_type=CONTENT_TYPE_HTML,
        sort_order=30,
    ),

    # ─── Contact page ──────────────────────────────────────────────────
    "contact.title": ContentSpec(
        key="contact.title",
        page=PAGE_CONTACT,
        label="Contact — page title",
        default="Get in touch",
        content_type=CONTENT_TYPE_HTML,
        sort_order=10,
    ),
    "contact.intro": ContentSpec(
        key="contact.intro",
        page=PAGE_CONTACT,
        label="Contact — intro paragraph",
        default="Questions about a booking or a custom trip? We reply within 24 hours.",
        content_type=CONTENT_TYPE_HTML,
        sort_order=20,
    ),
    "contact.email": ContentSpec(
        key="contact.email",
        page=PAGE_CONTACT,
        label="Contact — email address",
        default="hello@tripsandtipseg.com",
        sort_order=30,
    ),
    "contact.phone": ContentSpec(
        key="contact.phone",
        page=PAGE_CONTACT,
        label="Contact — phone number",
        default="+20 100 000 0000",
        sort_order=40,
    ),
    "contact.address": ContentSpec(
        key="contact.address",
        page=PAGE_CONTACT,
        label="Contact — office address",
        default="Hurghada, Red Sea, Egypt",
        sort_order=50,
    ),

    # ─── Footer ────────────────────────────────────────────────────────
    "footer.tagline": ContentSpec(
        key="footer.tagline",
        page=PAGE_FOOTER,
        label="Footer — tagline",
        default="© ElTut Tours Egypt. All rights reserved.",
        content_type=CONTENT_TYPE_HTML,
        sort_order=10,
    ),
    "footer.social_instagram": ContentSpec(
        key="footer.social_instagram",
        page=PAGE_FOOTER,
        label="Footer — Instagram URL",
        default="",
        sort_order=20,
    ),
    "footer.social_facebook": ContentSpec(
        key="footer.social_facebook",
        page=PAGE_FOOTER,
        label="Footer — Facebook URL",
        default="",
        sort_order=30,
    ),

    # ─── Global ────────────────────────────────────────────────────────
    "global.site_name": ContentSpec(
        key="global.site_name",
        page=PAGE_GLOBAL,
        label="Global — site name",
        default="ElTut Tours",
        content_type=CONTENT_TYPE_HTML,
        sort_order=10,
    ),
    "global.support_email": ContentSpec(
        key="global.support_email",
        page=PAGE_GLOBAL,
        label="Global — support email",
        default="hello@tripsandtipseg.com",
        sort_order=20,
    ),
}

# ─── Home slideshow slots ──────────────────────────────────────────
# 6 slots, numbered. Each holds an image URL (or empty). The public
# home page reads them via slideshow_slides().
for _i in range(1, SLIDESHOW_SLOT_COUNT + 1):
    _key = f"home.slideshow.slide.{_i}"
    _REGISTRY[_key] = ContentSpec(
        key=_key,
        page=PAGE_SLIDESHOW,
        label=f"Slideshow — image {_i}",
        default="",
        content_type=CONTENT_TYPE_IMAGE_URL,
        notes="Upload from the slideshow editor or paste a URL.",
        sort_order=_i * 10,
    )


def registry() -> dict[str, ContentSpec]:
    """Return a copy of the content registry."""
    return dict(_REGISTRY)


def defaults() -> dict[str, str]:
    """Return {key: default} for every registered key."""
    return {k: spec.default for k, spec in _REGISTRY.items()}


# ─── In-request cache ─────────────────────────────────────────────────────
def _cache_key() -> str:
    return "_content_cache"


def _get_cache() -> dict[str, str] | None:
    """Fetch the in-request cache from flask.g if available, else None."""
    try:
        from flask import g  # noqa: PLC0415
    except Exception:  # pragma: no cover
        return None
    try:
        return getattr(g, _cache_key(), None)
    except RuntimeError:
        # Outside an app/request context — no cache
        return None


def _set_cache(values: dict[str, str]) -> None:
    try:
        from flask import g  # noqa: PLC0415
        setattr(g, _cache_key(), values)
    except Exception:  # pragma: no cover
        pass


def clear_cache() -> None:
    """Drop the in-request cache (call after writing)."""
    try:
        from flask import g  # noqa: PLC0415
        if hasattr(g, _cache_key()):
            delattr(g, _cache_key())
    except Exception:  # pragma: no cover
        pass


# ─── Read ─────────────────────────────────────────────────────────────────
def all_values() -> dict[str, str]:
    """Return every registered key mapped to its current value.

    Values are the DB row's `value` if set, otherwise the registry
    default. Cached per request.
    """
    cached = _get_cache()
    if cached is not None:
        return cached

    # Start from the defaults so every registered key has a value.
    values: dict[str, str] = defaults()

    try:
        rows = db.session.scalars(select(SiteContent)).all()
    except Exception as exc:  # noqa: BLE001
        # Never let a DB hiccup break page rendering. Log + use defaults.
        log.warning("content_service: could not load site_content: %s", exc)
        _set_cache(values)
        return values

    for row in rows:
        if row.value is not None:
            values[row.key] = row.value

    _set_cache(values)
    return values


def get(key: str, default: str | None = None) -> str | None:
    """Return the value for a single key.

    Resolution order:
        1. DB value (if the row exists and value is not NULL)
        2. Registry default (if the key is registered)
        3. The caller's `default` argument
        4. Empty string
    """
    values = all_values()
    if key in values:
        return values[key]
    if default is not None:
        return default
    return ""


# ─── Admin listing ────────────────────────────────────────────────────────
def by_page(page: str | None = None) -> dict[str, list[SiteContent]]:
    """Return content rows grouped by page for the admin editor.

    Missing rows are NOT materialised — the admin sees only keys that
    have a row. Use seed_defaults() first to ensure every registered
    key has a row.
    """
    stmt = select(SiteContent).order_by(
        SiteContent.page.asc(),
        SiteContent.sort_order.asc(),
        SiteContent.key.asc(),
    )
    if page:
        stmt = stmt.where(SiteContent.page == page)

    rows = db.session.scalars(stmt).all()
    grouped: dict[str, list[SiteContent]] = {}
    for row in rows:
        grouped.setdefault(row.page, []).append(row)
    return grouped


# ─── Write ────────────────────────────────────────────────────────────────
def set_value(key: str, value: str | None, user: Any = None) -> SiteContent:
    """Upsert the value for a key. Busts the in-request cache.

    If the key has no row yet, one is created using the registry spec
    (label, page, content_type, sort_order). Unknown keys are also
    allowed — they get sensible defaults from the key's leading segment.
    """
    row = db.session.scalars(
        select(SiteContent).where(SiteContent.key == key)
    ).first()

    if row is None:
        spec = _REGISTRY.get(key)
        if spec is not None:
            row = SiteContent(
                key=spec.key,
                value=value,
                content_type=spec.content_type,
                page=spec.page,
                label=spec.label,
                notes=spec.notes,
                sort_order=spec.sort_order,
            )
        else:
            # Unknown key — derive a page from the leading segment, or
            # fall back to "global".
            page = key.split(".", 1)[0] if "." in key else PAGE_GLOBAL
            row = SiteContent(
                key=key,
                value=value,
                page=page if page in (PAGE_HOME, PAGE_ABOUT, PAGE_CONTACT, PAGE_FOOTER) else PAGE_GLOBAL,
                label=key,
                content_type=CONTENT_TYPE_TEXT,
            )
        db.session.add(row)
    else:
        row.value = value

    if user is not None and getattr(user, "id", None):
        row.updated_by_user_id = user.id

    db.session.commit()
    clear_cache()
    return row


# ─── Slideshow helper ─────────────────────────────────────────────────────
def slideshow_slides() -> list[dict[str, Any]]:
    """Return the active slideshow slides as a list of dicts.

    A slide is "active" if its value (an image URL) is non-empty.
    Order matches slot number (1..N). Each dict contains:
        slot  (int)
        key   (str)   e.g. "home.slideshow.slide.1"
        url   (str)
    """
    values = all_values()
    out: list[dict[str, Any]] = []
    for i in range(1, SLIDESHOW_SLOT_COUNT + 1):
        key = f"home.slideshow.slide.{i}"
        url = (values.get(key) or "").strip()
        if not url:
            continue
        out.append({"slot": i, "key": key, "url": url})
    return out


# ─── Seeding ──────────────────────────────────────────────────────────────
def seed_defaults(session=None) -> int:
    """Insert any registered keys that don't have a row yet.

    Idempotent: safe to run on every startup. Returns the number of
    rows created. Use a session=... to control the transaction, or
    omit it to commit immediately.
    """
    session = session or db.session
    existing = set(session.scalars(select(SiteContent.key)).all())
    created = 0
    for key, spec in _REGISTRY.items():
        if key in existing:
            continue
        row = SiteContent(
            key=spec.key,
            value=None,             # NULL means "use the code default"
            content_type=spec.content_type,
            page=spec.page,
            label=spec.label,
            notes=spec.notes,
            sort_order=spec.sort_order,
        )
        session.add(row)
        created += 1

    if created:
        session.commit()
    log.info("content_service.seed_defaults: created %s row(s)", created)
    return created

"""
blueprints/public/activity_routes.py
────────────────────────────────────
Activity listing and detail pages.

ROUTES
    GET /activities              list with filters, sort, pagination
    GET /activities/<slug>       detail page
"""

from __future__ import annotations

from flask import abort, current_app, render_template, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from blueprints.public import public_bp
from extensions import db
from models import (
    Activity,
    ActivityExclusion,
    ActivityImage,
    ActivityInclusion,
    ActivityLanguage,
    ActivityPrice,
    Destination,
    Guide,
    VALID_ACTIVITY_CATEGORIES,
    VALID_ACTIVITY_DIFFICULTIES,
)


def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    raw = request.args.get(name, "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _get_first_price(activity_id: int):
    row = db.session.scalar(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.id)
        .limit(1)
    )
    if row is None:
        return (None, None)
    try:
        return (float(row.adult_price), row.currency)
    except Exception:
        return (None, None)


def _avg_rating(activity_id: int):
    try:
        from mongo.reviews import rating_summary
        summary = rating_summary("activity", activity_id)
        return (summary.get("average"), int(summary.get("count") or 0))
    except Exception:
        return (None, 0)


@public_bp.route("/activities")
def activity_list():
    """Browse activities with filters, sorting, and pagination."""
    page = _int_arg("page", 1, 1, 10_000)
    per_page = int(current_app.config.get("ITEMS_PER_PAGE", 12) or 12)
    per_page = max(6, min(per_page, 48))

    destination_slug = (request.args.get("destination") or "").strip().lower()
    category = (request.args.get("category") or "").strip().lower()
    difficulty = (request.args.get("difficulty") or "").strip().lower()
    query_text = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "newest").strip().lower()

    stmt = (
        select(Activity)
        .options(joinedload(Activity.images))
        .where(Activity.is_active.is_(True))
    )

    selected_destination = None
    if destination_slug:
        selected_destination = db.session.scalar(
            select(Destination).where(Destination.slug == destination_slug)
        )
        if selected_destination is not None:
            stmt = stmt.where(Activity.destination_id == selected_destination.id)

    if category and category in VALID_ACTIVITY_CATEGORIES:
        stmt = stmt.where(Activity.category == category)

    if difficulty and difficulty in VALID_ACTIVITY_DIFFICULTIES:
        stmt = stmt.where(Activity.difficulty == difficulty)

    if query_text:
        stmt = stmt.where(Activity.name.ilike(f"%{query_text}%"))

    if sort == "name":
        stmt = stmt.order_by(Activity.name.asc())
    elif sort == "price_asc":
        stmt = stmt.order_by(
            select(ActivityPrice.adult_price)
            .where(ActivityPrice.activity_id == Activity.id)
            .limit(1)
            .scalar_subquery()
            .asc()
        )
    elif sort == "price_desc":
        stmt = stmt.order_by(
            select(ActivityPrice.adult_price)
            .where(ActivityPrice.activity_id == Activity.id)
            .limit(1)
            .scalar_subquery()
            .desc()
        )
    else:
        stmt = stmt.order_by(Activity.id.desc())

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = list(db.session.scalars(stmt.limit(per_page).offset(offset)).unique())

    items = []
    for a in rows:
        price_adult, currency = _get_first_price(a.id)
        first_image = a.images[0].url if a.images else None
        items.append({
            "activity": a,
            "price_adult": price_adult,
            "currency": currency,
            "image_url": first_image,
        })

    destinations = list(db.session.scalars(
        select(Destination).order_by(Destination.name)
    ))

    return render_template(
        "public/activity_list.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        destinations=destinations,
        categories=VALID_ACTIVITY_CATEGORIES,
        difficulties=VALID_ACTIVITY_DIFFICULTIES,
        selected_destination=selected_destination,
        selected_category=category,
        selected_difficulty=difficulty,
        query_text=query_text,
        sort=sort,
    )


@public_bp.route("/activities/<slug>")
def activity_detail(slug: str):
    """Single activity detail page."""
    activity = db.session.scalars(
        select(Activity)
        .options(joinedload(Activity.images))
        .where(Activity.slug == slug, Activity.is_active.is_(True))
    ).unique().first()
    if activity is None:
        abort(404)

    inclusions = list(db.session.scalars(
        select(ActivityInclusion)
        .where(ActivityInclusion.activity_id == activity.id)
        .order_by(ActivityInclusion.sort_order)
    ))
    exclusions = list(db.session.scalars(
        select(ActivityExclusion)
        .where(ActivityExclusion.activity_id == activity.id)
        .order_by(ActivityExclusion.sort_order)
    ))
    languages = list(db.session.scalars(
        select(ActivityLanguage)
        .where(ActivityLanguage.activity_id == activity.id)
        .order_by(ActivityLanguage.language)
    ))
    images = list(db.session.scalars(
        select(ActivityImage)
        .where(ActivityImage.activity_id == activity.id)
        .order_by(ActivityImage.sort_order)
    ))

    destination = db.session.get(Destination, activity.destination_id)
    guide = db.session.get(Guide, activity.guide_id) if activity.guide_id else None

    price_adult, currency = _get_first_price(activity.id)
    price_child = None
    price_row = db.session.scalar(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity.id)
        .order_by(ActivityPrice.id)
        .limit(1)
    )
    if price_row is not None:
        try:
            price_child = float(price_row.child_price)
        except Exception:
            price_child = None

    avg_rating, review_count = _avg_rating(activity.id)

    remaining = None
    try:
        from services.availability_service import activity_availability
        from datetime import date as _date
        remaining = activity_availability(activity.id, _date.today())
    except Exception:
        remaining = None

    related = list(db.session.scalars(
        select(Activity)
        .where(
            Activity.destination_id == activity.destination_id,
            Activity.id != activity.id,
            Activity.is_active.is_(True),
        )
        .order_by(Activity.id)
        .limit(3)
    ))

    return render_template(
        "public/activity_detail.html",
        activity=activity,
        destination=destination,
        guide=guide,
        images=images,
        inclusions=inclusions,
        exclusions=exclusions,
        languages=languages,
        price_adult=price_adult,
        price_child=price_child,
        currency=currency,
        avg_rating=avg_rating,
        review_count=review_count,
        remaining=remaining,
        related=related,
    )

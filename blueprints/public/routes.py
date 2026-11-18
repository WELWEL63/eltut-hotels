"""
blueprints/public/routes.py
───────────────────────────
Home, About, and Contact pages for the public site.
"""

from __future__ import annotations

from flask import current_app, render_template
from sqlalchemy import func, select

from blueprints.public import public_bp
from extensions import db
from models import (
    Destination,
    HomeOffer,
    Hotel,
    Room,
    PRODUCT_HOTEL,
)

# Section keys
_SECTION_BEST_HOTEL = "best_hotel"


def _offers_for_section(section: str, limit: int = 6):
    rows = (
        db.session.query(HomeOffer)
        .filter(
            HomeOffer.section == section,
            HomeOffer.is_active.is_(True),
        )
        .order_by(HomeOffer.sort_order.asc(), HomeOffer.id.asc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []

    model_by_type = {PRODUCT_HOTEL: Hotel}
    ids_by_type: dict[str, list[int]] = {}
    for r in rows:
        ids_by_type.setdefault(r.product_type, []).append(r.product_id)

    products: dict[tuple[str, int], object] = {}
    for ptype, ids in ids_by_type.items():
        model = model_by_type.get(ptype)
        if model is None:
            continue
        for p in db.session.query(model).filter(model.id.in_(ids)).all():
            products[(ptype, p.id)] = p

    out = []
    for r in rows:
        obj = products.get((r.product_type, r.product_id))
        if obj is None:
            continue
        try:
            price = _section_price_for(section, obj.id)
        except Exception:
            price = None
        out.append({
            "obj": obj,
            "price": round(float(price), 2) if price is not None else None,
        })
    return out


def _section_price_for(section: str, product_id: int):
    if section == _SECTION_BEST_HOTEL:
        sub = (
            select(func.min(Room.base_price_per_night))
            .where(Room.hotel_id == product_id, Room.is_active.is_(True),
                   Room.base_price_per_night > 0)
        )
    else:
        return None
    return db.session.scalar(sub)


def _cheapest_per_destination(model, price_subquery, limit=6):
    inner = (
        select(model, price_subquery.label("cheapest_price"))
        .where(model.is_active.is_(True))
        .where(price_subquery.is_not(None))
        .where(price_subquery > 0)
        .distinct(model.destination_id)
        .order_by(model.destination_id, price_subquery.asc())
        .subquery()
    )
    rows = db.session.execute(
        select(inner).order_by(inner.c.cheapest_price.asc()).limit(limit)
    ).all()

    results = []
    for row in rows:
        obj_id = row[0]
        price = row[-1]
        results.append({
            "id": obj_id,
            "price": round(float(price), 2) if price is not None else None,
        })

    if results:
        ids = [r["id"] for r in results]
        objs = {
            m.id: m
            for m in db.session.scalars(
                select(model).where(model.id.in_(ids))
            ).unique().all()
        }
        for r in results:
            r["obj"] = objs.get(r["id"])

    return results


def _hotel_price_subquery():
    return (
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == Hotel.id, Room.is_active.is_(True),
               Room.base_price_per_night > 0)
        .correlate(Hotel)
        .scalar_subquery()
    )


@public_bp.route("/")
def index():
    try:
        featured_hotels = _offers_for_section(_SECTION_BEST_HOTEL, limit=6)
        if not featured_hotels:
            featured_hotels = _cheapest_per_destination(
                Hotel, _hotel_price_subquery(), limit=6
            )
    except Exception as exc:
        current_app.logger.warning("featured_hotels failed: %s", exc)
        featured_hotels = []

    top_destinations = list(
        db.session.scalars(
            select(Destination).order_by(Destination.name).limit(6)
        )
    )

    destination_images = {}
    try:
        from services import content_service
        destination_images = content_service.all_destination_images()
    except Exception as exc:
        current_app.logger.debug("destination images unavailable: %s", exc)

    counts = {
        "hotels": db.session.scalar(
            select(func.count(Hotel.id)).where(Hotel.is_active.is_(True))
        ) or 0,
        "destinations": db.session.scalar(
            select(func.count(Destination.id))
        ) or 0,
    }

    return render_template(
        "public/index.html",
        destination_images=destination_images,
        featured_hotels=featured_hotels,
        top_destinations=top_destinations,
        counts=counts,
    )


@public_bp.route("/about")
def about():
    return render_template("public/about.html")


@public_bp.route("/contact")
def contact():
    return render_template("public/contact.html")
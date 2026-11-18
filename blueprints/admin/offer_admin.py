"""
blueprints/admin/offer_admin.py — Hotels Only
Admin UI for curating home-page offers (best_hotel section only).
"""
from __future__ import annotations

from flask import (
    abort, current_app, flash, jsonify, redirect,
    render_template, request, url_for,
)

from blueprints.admin import admin_bp
from blueprints.admin.routes import admin_required
from extensions import db
from models import (
    HomeOffer, Hotel,
    PRODUCT_HOTEL,
    SECTION_BEST_HOTEL,
)

SECTIONS = {
    SECTION_BEST_HOTEL: {
        "product_type": PRODUCT_HOTEL,
        "model": Hotel,
        "icon": "building",
        "label": "Best hotels",
        "description": "Hotels featured on the home page.",
    },
}

SLOTS_PER_SECTION = 6


def _get_section_or_404(section: str) -> dict:
    cfg = SECTIONS.get(section)
    if cfg is None:
        abort(404)
    return cfg


def _resolve_products(cfg: dict, offers: list[HomeOffer]) -> list[dict]:
    model = cfg["model"]
    ids = [o.product_id for o in offers]
    if not ids:
        return []
    products = {p.id: p for p in db.session.query(model).filter(model.id.in_(ids)).all()}
    return [{"offer": o, "product": products.get(o.product_id)} for o in offers]


@admin_bp.route("/offers")
@admin_required
def offers_index():
    sections = []
    for key, cfg in SECTIONS.items():
        offers = (
            db.session.query(HomeOffer)
            .filter(HomeOffer.section == key)
            .order_by(HomeOffer.sort_order.asc(), HomeOffer.id.asc())
            .all()
        )
        rows = _resolve_products(cfg, offers)
        sections.append({
            "key": key, "cfg": cfg, "rows": rows,
            "count": len([r for r in rows if r["product"] is not None]),
            "slots": SLOTS_PER_SECTION,
        })
    return render_template("admin/offers.html", sections=sections, slots_per_section=SLOTS_PER_SECTION)


@admin_bp.route("/offers/<section>/search")
@admin_required
def offers_search(section: str):
    cfg = _get_section_or_404(section)
    model = cfg["model"]
    q = (request.args.get("q") or "").strip()
    stmt = db.session.query(model)
    if q:
        stmt = stmt.filter(model.name.ilike(f"%{q}%"))
    stmt = stmt.filter(model.is_active.is_(True)).order_by(model.name.asc()).limit(20)
    results = [{"id": p.id, "name": getattr(p, "name", f"#{p.id}")} for p in stmt.all()]
    return jsonify({"results": results})


@admin_bp.route("/offers/<section>/add", methods=["POST"])
@admin_required
def offers_add(section: str):
    cfg = _get_section_or_404(section)
    model = cfg["model"]
    try:
        product_id = int(request.form.get("product_id") or "")
    except (TypeError, ValueError):
        flash("Invalid product id.", "danger")
        return redirect(url_for("admin.offers_index"))
    product = db.session.get(model, product_id)
    if product is None:
        flash("That product doesn't exist.", "danger")
        return redirect(url_for("admin.offers_index"))
    existing = db.session.query(HomeOffer).filter_by(
        section=section, product_type=cfg["product_type"], product_id=product_id,
    ).first()
    if existing:
        flash(f"'{product.name}' is already in this section.", "warning")
        return redirect(url_for("admin.offers_index"))
    max_sort = db.session.query(db.func.max(HomeOffer.sort_order)).filter(HomeOffer.section == section).scalar() or 0
    db.session.add(HomeOffer(
        section=section, product_type=cfg["product_type"],
        product_id=product_id, sort_order=max_sort + 1, is_active=True,
    ))
    db.session.commit()
    flash(f"Added '{product.name}'.", "success")
    return redirect(url_for("admin.offers_index"))


@admin_bp.route("/offers/<int:offer_id>/remove", methods=["POST"])
@admin_required
def offers_remove(offer_id: int):
    offer = db.session.get(HomeOffer, offer_id)
    if offer is None:
        abort(404)
    db.session.delete(offer)
    db.session.commit()
    flash("Removed from the home page.", "success")
    return redirect(url_for("admin.offers_index"))


@admin_bp.route("/offers/<int:offer_id>/toggle", methods=["POST"])
@admin_required
def offers_toggle(offer_id: int):
    offer = db.session.get(HomeOffer, offer_id)
    if offer is None:
        abort(404)
    offer.is_active = not offer.is_active
    db.session.commit()
    flash(f"Offer {'shown' if offer.is_active else 'hidden'}.", "success")
    return redirect(url_for("admin.offers_index"))


@admin_bp.route("/offers/<int:offer_id>/move", methods=["POST"])
@admin_required
def offers_move(offer_id: int):
    offer = db.session.get(HomeOffer, offer_id)
    if offer is None:
        abort(404)
    direction = (request.form.get("direction") or "").lower()
    if direction not in ("up", "down"):
        flash("Invalid direction.", "danger")
        return redirect(url_for("admin.offers_index"))
    if direction == "up":
        sibling = db.session.query(HomeOffer).filter(
            HomeOffer.section == offer.section, HomeOffer.sort_order < offer.sort_order,
        ).order_by(HomeOffer.sort_order.desc()).first()
    else:
        sibling = db.session.query(HomeOffer).filter(
            HomeOffer.section == offer.section, HomeOffer.sort_order > offer.sort_order,
        ).order_by(HomeOffer.sort_order.asc()).first()
    if sibling is None:
        return redirect(url_for("admin.offers_index"))
    offer.sort_order, sibling.sort_order = sibling.sort_order, offer.sort_order
    db.session.commit()
    return redirect(url_for("admin.offers_index"))
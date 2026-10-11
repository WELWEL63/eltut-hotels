"""
blueprints/admin/offer_admin.py
───────────────────────────────
Admin UI for curating home-page "Offers".

Each section of the home page has a corresponding section key here:

    top_experience       -> activities
    best_hotel           -> hotels
    affordable_package   -> packages

Admins add/remove products to each section, reorder them, and toggle
them on/off without touching the database directly.

ROUTES
    GET  /admin/offers                                  -> sectioned list
    GET  /admin/offers/<section>/search?q=...           -> autocomplete (JSON)
    POST /admin/offers/<section>/add                    -> add by product_id
    POST /admin/offers/<offer_id>/remove                -> delete
    POST /admin/offers/<offer_id>/toggle                -> flip is_active
    POST /admin/offers/<offer_id>/move                  -> change sort_order

NOTES
    - All routes are @admin_required.
    - CSRF is enforced by the global CSRFProtect (form must include
      csrf_token hidden input — templates do this).
    - Products are looked up by id; a missing product is skipped at
      render time (defensive against deletions).
"""

from __future__ import annotations

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from blueprints.admin import admin_bp
from blueprints.admin.routes import admin_required
from extensions import db
from models import (
    Activity,
    HomeOffer,
    Hotel,
    Package,
    PRODUCT_ACTIVITY,
    PRODUCT_HOTEL,
    PRODUCT_PACKAGE,
    SECTION_TOP_EXPERIENCE,
    SECTION_BEST_HOTEL,
    SECTION_AFFORDABLE_PACKAGE,
)


# ─── Section config ────────────────────────────────────────────────
# Maps section key -> (product_type, model, icon, label, description)
SECTIONS = {
    SECTION_TOP_EXPERIENCE: {
        "product_type": PRODUCT_ACTIVITY,
        "model": Activity,
        "icon": "compass",
        "label": "Top experiences",
        "description": "Activities shown on the home page as 'Unmissable tours'.",
    },
    SECTION_BEST_HOTEL: {
        "product_type": PRODUCT_HOTEL,
        "model": Hotel,
        "icon": "building",
        "label": "Best hotels",
        "description": "Hotels featured on the home page.",
    },
    SECTION_AFFORDABLE_PACKAGE: {
        "product_type": PRODUCT_PACKAGE,
        "model": Package,
        "icon": "suitcase-lg",
        "label": "Affordable packages",
        "description": "Packages featured on the home page.",
    },
}

SLOTS_PER_SECTION = 6


# ─── Helpers ───────────────────────────────────────────────────────
def _get_section_or_404(section: str) -> dict:
    cfg = SECTIONS.get(section)
    if cfg is None:
        abort(404)
    return cfg


def _resolve_products(cfg: dict, offers: list[HomeOffer]) -> list[dict]:
    """Return render-ready rows: offer + the actual product (or None)."""
    model = cfg["model"]
    ids = [o.product_id for o in offers]
    if not ids:
        return []
    products = {
        p.id: p
        for p in db.session.query(model).filter(model.id.in_(ids)).all()
    }
    return [
        {"offer": o, "product": products.get(o.product_id)}
        for o in offers
    ]


# ─── Main page ─────────────────────────────────────────────────────
@admin_bp.route("/offers")
@admin_required
def offers_index():
    """Show all 3 sections with their current offers."""
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
            "key": key,
            "cfg": cfg,
            "rows": rows,
            "count": len([r for r in rows if r["product"] is not None]),
            "slots": SLOTS_PER_SECTION,
        })
    return render_template(
        "admin/offers.html",
        sections=sections,
        slots_per_section=SLOTS_PER_SECTION,
    )


# ─── Autocomplete (JSON) ───────────────────────────────────────────
@admin_bp.route("/offers/<section>/search")
@admin_required
def offers_search(section: str):
    """Search products for a given section. Returns JSON for the widget."""
    cfg = _get_section_or_404(section)
    model = cfg["model"]
    q = (request.args.get("q") or "").strip()

    stmt = db.session.query(model)
    if q:
        stmt = stmt.filter(model.name.ilike(f"%{q}%"))
    stmt = stmt.filter(model.is_active.is_(True))
    stmt = stmt.order_by(model.name.asc()).limit(20)

    results = [
        {
            "id": p.id,
            "name": getattr(p, "name", f"#{p.id}"),
            "code": getattr(p, "code", None),
            "destination_id": getattr(p, "destination_id", None),
        }
        for p in stmt.all()
    ]
    return jsonify({"results": results})


# ─── Add ───────────────────────────────────────────────────────────
@admin_bp.route("/offers/<section>/add", methods=["POST"])
@admin_required
def offers_add(section: str):
    """Add a product to a section by id."""
    cfg = _get_section_or_404(section)
    model = cfg["model"]

    raw = request.form.get("product_id") or ""
    try:
        product_id = int(raw)
    except (TypeError, ValueError):
        flash("Invalid product id.", "danger")
        return redirect(url_for("admin.offers_index"))

    product = db.session.get(model, product_id)
    if product is None:
        flash("That product doesn't exist.", "danger")
        return redirect(url_for("admin.offers_index"))

    # Enforce unique (section, product_type, product_id) — the DB does too,
    # but we check first for a friendly message.
    existing = (
        db.session.query(HomeOffer)
        .filter_by(
            section=section,
            product_type=cfg["product_type"],
            product_id=product_id,
        )
        .first()
    )
    if existing:
        flash(f"'{product.name}' is already in this section.", "warning")
        return redirect(url_for("admin.offers_index"))

    # Put it at the end of the current order
    max_sort = (
        db.session.query(db.func.max(HomeOffer.sort_order))
        .filter(HomeOffer.section == section)
        .scalar()
    ) or 0

    db.session.add(HomeOffer(
        section=section,
        product_type=cfg["product_type"],
        product_id=product_id,
        sort_order=max_sort + 1,
        is_active=True,
    ))
    db.session.commit()

    current_app.logger.info(
        "offer_admin: added %s#%s to section %s",
        cfg["product_type"], product_id, section,
    )
    flash(f"Added '{product.name}'.", "success")
    return redirect(url_for("admin.offers_index"))


# ─── Remove ────────────────────────────────────────────────────────
@admin_bp.route("/offers/<int:offer_id>/remove", methods=["POST"])
@admin_required
def offers_remove(offer_id: int):
    """Delete an offer row."""
    offer = db.session.get(HomeOffer, offer_id)
    if offer is None:
        abort(404)

    section = offer.section
    db.session.delete(offer)
    db.session.commit()

    flash("Removed from the home page.", "success")
    return redirect(url_for("admin.offers_index"))


# ─── Toggle active ─────────────────────────────────────────────────
@admin_bp.route("/offers/<int:offer_id>/toggle", methods=["POST"])
@admin_required
def offers_toggle(offer_id: int):
    """Flip is_active on an offer row."""
    offer = db.session.get(HomeOffer, offer_id)
    if offer is None:
        abort(404)

    offer.is_active = not offer.is_active
    db.session.commit()

    state = "shown" if offer.is_active else "hidden"
    flash(f"Offer {state}.", "success")
    return redirect(url_for("admin.offers_index"))


# ─── Reorder ───────────────────────────────────────────────────────
@admin_bp.route("/offers/<int:offer_id>/move", methods=["POST"])
@admin_required
def offers_move(offer_id: int):
    """Move an offer up or down within its section."""
    offer = db.session.get(HomeOffer, offer_id)
    if offer is None:
        abort(404)

    direction = (request.form.get("direction") or "").lower()
    if direction not in ("up", "down"):
        flash("Invalid direction.", "danger")
        return redirect(url_for("admin.offers_index"))

    # Find the sibling to swap with
    if direction == "up":
        sibling = (
            db.session.query(HomeOffer)
            .filter(
                HomeOffer.section == offer.section,
                HomeOffer.sort_order < offer.sort_order,
            )
            .order_by(HomeOffer.sort_order.desc())
            .first()
        )
    else:
        sibling = (
            db.session.query(HomeOffer)
            .filter(
                HomeOffer.section == offer.section,
                HomeOffer.sort_order > offer.sort_order,
            )
            .order_by(HomeOffer.sort_order.asc())
            .first()
        )

    if sibling is None:
        # Already at the top/bottom — nothing to do
        return redirect(url_for("admin.offers_index"))

    # Swap sort_order values (safe even if they're equal — use ids)
    offer.sort_order, sibling.sort_order = sibling.sort_order, offer.sort_order
    db.session.commit()

    return redirect(url_for("admin.offers_index"))
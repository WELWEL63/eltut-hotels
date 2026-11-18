"""
blueprints/public/search_routes.py — Hotels Only

ROUTES
    GET /search           redirects to /search/results with same query
    GET /search/results   renders hotel results
"""

from __future__ import annotations

from datetime import date, datetime

from flask import (
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from blueprints.public import public_bp
from services import search_service


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _int_arg(name: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = max(minimum, int(raw))
        if maximum is not None:
            value = min(value, maximum)
        return value
    except (TypeError, ValueError):
        return default


@public_bp.route("/search")
def search_shortcut():
    """Widget action URL. Redirects to /search/results preserving query."""
    qs = request.args.to_dict(flat=True)
    return redirect(url_for("public.search_results", **qs))


@public_bp.route("/search/results")
def search_results():
    """Render hotel search results."""
    destination = (request.args.get("destination") or "").strip() or None
    q = (request.args.get("q") or "").strip() or None
    sort = (request.args.get("sort") or "newest").strip().lower()

    check_in = _parse_date(request.args.get("check_in"))
    check_out = _parse_date(request.args.get("check_out"))

    adults = _int_arg("adults", 1, minimum=1, maximum=8)
    children = _int_arg("children", 0, minimum=0, maximum=8)
    page = _int_arg("page", 1, minimum=1)

    per_page = int(current_app.config.get("ITEMS_PER_PAGE", 12) or 12)
    per_page = max(6, min(per_page, 48))

    result = search_service.search(
        product_type="hotel",
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children=children,
        page=page,
        per_page=per_page,
        sort=sort,
        q=q,
    )

    destinations = search_service.destinations_for_widget()

    return render_template(
        "public/search_results.html",
        result=result,
        destinations=destinations,
        qs={
            "type": "hotel",
            "destination": result["filters"]["destination"] or "",
            "check_in": result["filters"]["check_in"] or "",
            "check_out": result["filters"]["check_out"] or "",
            "adults": result["filters"]["adults"],
            "children": result["filters"]["children"],
            "sort": result["filters"]["sort"],
            "q": result["filters"]["q"] or "",
        },
    )
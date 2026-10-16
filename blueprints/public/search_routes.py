"""
blueprints/public/search_routes.py
â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£
Public search widget handler + results page.

ROUTES
    GET /search           redirects to /search/results with same query
    GET /search/results   renders results (any product type)
                          + inline results within a set of filters

QUERY PARAMS
    type         hotel | package | activity   (default: hotel)
    destination  destination slug (optional)
    check_in     YYYY-MM-DD for hotel/package
    check_out    YYYY-MM-DD for hotel/package
    date         YYYY-MM-DD for activity
    adults       int >= 1   (default 1)
    children     int >= 0   (default 0)
    page         int >= 1
    sort         newest | name | price_asc | price_desc | stars_desc | duration_asc
    q            free-text

DESIGN NOTES
    - Reads are done via services.search_service. Route stays thin.
    - `/search` is the action URL from the home widget. It redirects to
      `/search/results` preserving the querystring, so the results page
      is bookmarkable.
    - Missing/blank filters fall back to sensible defaults (see
      search_service.search()).
    - The results page renders a shared `search_results.html` that
      adapts its card layout to whichever product_type is active.
"""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlencode

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


# â”£â”£â”£ /search â†’ redirect to results â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£
@public_bp.route("/search")
def search_shortcut():
    """Widget action URL. Redirects to /search/results preserving query."""
    qs = request.args.to_dict(flat=True)
    return redirect(url_for("public.search_results", **qs))


# â”£â”£â”£ /search/results â†’ actual render â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£
@public_bp.route("/search/results")
def search_results():
    """Render search results for the currently selected product type."""

    # â”£â”£â”£ Parse filters from the query string â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£
    product_type = (request.args.get("type") or "hotel").strip().lower()
    destination = (request.args.get("destination") or "").strip() or None
    q = (request.args.get("q") or "").strip() or None
    sort = (request.args.get("sort") or "newest").strip().lower()

    check_in = _parse_date(request.args.get("check_in"))
    check_out = _parse_date(request.args.get("check_out"))
    activity_date = _parse_date(request.args.get("date"))

    adults = _int_arg("adults", 1, minimum=1, maximum=8)
    children = _int_arg("children", 0, minimum=0, maximum=8)
    page = _int_arg("page", 1, minimum=1)

    per_page = int(current_app.config.get("ITEMS_PER_PAGE", 12) or 12)
    per_page = max(6, min(per_page, 48))

    # â”£â”£â”£ Run the search â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£â”£
    result = search_service.search(
        product_type=product_type,
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        activity_date=activity_date,
        adults=adults,
        children=children,
        page=page,
        per_page=per_page,
        sort=sort,
        q=q,
    )

    # â”£â”£â”£ Dropdown data for the persistent widget on the results page â”£
    destinations = search_service.destinations_for_widget()
    package_destinations = search_service.destinations_for_package_widget()

    return render_template(
        "public/search_results.html",
        result=result,
        destinations=destinations,
        package_destinations=package_destinations,
        # Query-string we can append to pagination links, minus page
        qs={
            "type": result["product_type"],
            "destination": result["filters"]["destination"] or "",
            "check_in": result["filters"]["check_in"] or "",
            "check_out": result["filters"]["check_out"] or "",
            "date": result["filters"]["activity_date"] or "",
            "adults": result["filters"]["adults"],
            "children": result["filters"]["children"],
            "sort": result["filters"]["sort"],
            "q": result["filters"]["q"] or "",
        },
    )

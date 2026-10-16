"""
services/package_options_service.py
────────────────────────────────────
Single entry point for customer-facing package options.

Loads PackageFlight cards for a package, computes each card's price
with the exact same formula the admin preview uses
(services.package_pricing_service.compute_package_flight_card), filters
to cards whose outbound date is within tolerance of the customer's
requested check_in, and returns a list of dicts ready for
templates/public/package_detail.html.

This replaces the old three paths:
    - PackageOption rows (legacy)
    - Flight rows (legacy synthetic)
    - flight_service.flight_options_for_package (invented return)

Design notes
────────────
* Read-only. No Flask imports.
* All money returned as float for template formatting; underlying math
  is Decimal via compute_package_flight_card.
* Card is skipped if compute_package_flight_card reports not ok or
  nights <= 0 or per_person <= 0 (protects against the card-17 style
  374-night data error from polluting the customer view).
* Default tolerance is 3 days, per the product spec (+/- 2/3 days).
* Deterministic ordering: closest departure first, then cheapest
  per_person.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from extensions import db
from models import Package, PackageFlight
from services.package_pricing_service import compute_package_flight_card


DEFAULT_TOLERANCE_DAYS = 3


def _normalise_dates(
    check_in: date | None,
    check_out: date | None,
    package: Package,
) -> tuple[date | None, date | None]:
    """If the customer supplied dates, use them. Otherwise fall back to
    the package's own check_in/check_out (if any)."""
    if check_in and check_out and check_out > check_in:
        return check_in, check_out
    return package.check_in, package.check_out


def options_for_package(
    package: Package,
    check_in: date | None,
    check_out: date | None,
    adults: int = 2,
    children: int = 0,
    tolerance_days: int = DEFAULT_TOLERANCE_DAYS,
) -> list[dict[str, Any]]:
    """
    Return the list of bookable options for a package.

    Each option is a dict carrying every key package_detail.html needs:
        id, card_id, label,
        departure_date, return_date, nights,
        flight_from, flight_to,
        airline_name, airline_logo, luggage_allowance,
        currency,
        price_adult, price_child,
        land_total, flight_total, markup_total, tax_total,
        transfer_total, grand_total,
        flexible_date_used, offset_days, return_estimated
    """
    if package is None:
        return []

    cards = list(db.session.scalars(
        select(PackageFlight)
        .where(PackageFlight.package_id == package.id)
        .where(PackageFlight.is_active.is_(True))
        .order_by(PackageFlight.sort_order.asc(), PackageFlight.id.asc())
    ))
    if not cards:
        return []

    req_in, req_out = _normalise_dates(check_in, check_out, package)

    pax = max(1, int(adults) + int(children))
    tol = max(0, int(tolerance_days))

    results: list[dict[str, Any]] = []

    for card in cards:
        calc = compute_package_flight_card(package, card)

        if not calc.get("ok"):
            continue
        nights = int(calc.get("nights") or 0)
        if nights <= 0 or nights > 60:   # guard against the 374-night data bug
            continue

        per_person = float(calc.get("per_person") or 0.0)
        if per_person <= 0:
            continue

        card_in = calc.get("check_in")
        card_out = calc.get("check_out")

        offset_days = 0
        flexible = False
        if req_in is not None and card_in is not None:
            offset_days = (card_in - req_in).days
            if abs(offset_days) > tol:
                continue
            flexible = offset_days != 0

        # Per-adult and per-child equivalents so the JS recompute still works.
        # The card's per_person already includes flight, transfer, markup,
        # tax apportioned per passenger. Children are charged the same
        # per-person rate as adults on this product (matches admin preview).
        price_adult = per_person
        price_child = per_person

        grand_total = per_person * pax

        results.append({
            "id": card.id,
            "card_id": card.id,
            "label": calc.get("label"),
            "departure_date": card_in,
            "return_date": card_out,
            "nights": nights,
            "flight_from": calc.get("flight_from"),
            "flight_to": calc.get("flight_to"),
            "airline_name": calc.get("airline_name"),
            "airline_logo": calc.get("airline_logo"),
            "luggage_allowance": calc.get("luggage_allowance"),
            "currency": calc.get("currency") or "GBP",
            "price_adult": round(price_adult, 2),
            "price_child": round(price_child, 2),
            "land_total": round(float(calc.get("hotel_total") or 0.0), 2),
            "flight_total": round(float(calc.get("flight_total") or 0.0), 2),
            "markup_total": round(float(calc.get("markup") or 0.0), 2),
            "tax_total": round(float(calc.get("tax") or 0.0), 2),
            "transfer_total": round(float(calc.get("transfer_fee") or 0.0), 2),
            "grand_total": round(grand_total, 2),
            "flexible_date_used": flexible,
            "offset_days": offset_days,
            "return_estimated": bool(calc.get("return_estimated", False)),
        })

    # Order: closest departure to requested check_in first, then cheapest.
    def _sort_key(o):
        off = abs(o.get("offset_days") or 0)
        return (off, o.get("grand_total") or 0.0)

    results.sort(key=_sort_key)
    return results


def cheapest_option_for_package(
    package: Package,
    check_in: date | None,
    check_out: date | None,
    adults: int = 2,
    children: int = 0,
    tolerance_days: int = DEFAULT_TOLERANCE_DAYS,
) -> dict[str, Any] | None:
    """Convenience: the cheapest matching option, or None."""
    opts = options_for_package(
        package=package,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        children=children,
        tolerance_days=tolerance_days,
    )
    if not opts:
        return None
    return min(opts, key=lambda o: o["grand_total"] or 0.0)


__all__ = [
    "options_for_package",
    "cheapest_option_for_package",
    "DEFAULT_TOLERANCE_DAYS",
]
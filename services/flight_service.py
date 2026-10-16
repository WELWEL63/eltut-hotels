"""
services/flight_service.py
──────────────────────────
Read-only queries against the flight_prices table.

Public API
──────────
    available_origins(destination_airport)
        -> list[dict] of airports that fly to this destination

    cheapest_flight(origin, destination, from_date, to_date)
        -> dict | None  (cheapest outbound within date range)

    flight_for_date(origin, destination, on_date)
        -> dict | None  (exact-date lookup)

    flight_with_fallback(origin, destination, on_date, tolerance_days=3)
        -> dict | None  (exact date, or closest within ±tolerance)

    round_trip_cost(origin, destination, check_in, check_out,
                    passengers=1, tolerance_days=3)
        -> dict  (outbound + return breakdown, with flexible-date metadata)

    flight_summary_for_package(package, origin, check_in, check_out,
                               passengers=1, tolerance_days=3)
        -> dict | None  (convenience wrapper for the package detail page)

    flight_options_for_package(package, check_in, check_out,
                               passengers=1, land_total=None, ...)
        -> list[dict]  (option cards for the package detail page, one per airline,
                        with land + flight + markup + transfer baked into grand_total)

Design notes
────────────
* No Flask imports — pure data layer.
* All money is Decimal.
* Returns None (not exception) when no flight matches — the caller
  decides how to display "no flight available".
* Return leg: currently estimated as outbound × 2 because we only have
  outbound data. When inbound data is available, swap in a real
  flight_for_date() call for the return date.
* Flexible-date fallback: when the exact check_in date has no flight,
  we look ±tolerance_days and use the closest. The response flags this
  via 'flexible_date_used' and 'offset_days' so the UI can say
  "no flight on X — showing Y instead".
* flight_options_for_package picks the CLOSEST date first, then
  cheapest as a tiebreaker — so a user asking for 1 Nov gets 1 Nov
  if it exists, even if a cheaper flight is available on 4 Nov.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from extensions import db
from models import Airport, Destination, FlightPrice


# ── Helpers ─────────────────────────────────────────────────────────
def _airport_display(iata: str) -> str:
    """'LGW' -> 'London Gatwick (LGW)'. Falls back to plain code."""
    if not iata:
        return ""
    ap = db.session.get(Airport, iata.upper())
    if ap is None:
        return iata
    return ap.display


def _flight_to_dict(row: FlightPrice) -> dict[str, Any]:
    return {
        "id": row.id,
        "airline": row.airline,
        "origin": row.origin,
        "origin_display": _airport_display(row.origin),
        "destination": row.destination,
        "destination_display": _airport_display(row.destination),
        "departure_date": row.departure_date,
        "direction": row.direction,
        "price_gbp": row.price_gbp,
        "currency": row.currency,
        "flight_number": row.flight_number,
        "departure_time": row.departure_time,
        "arrival_time": row.arrival_time,
    }


# ── Public API ──────────────────────────────────────────────────────
def available_origins(destination_airport: str) -> list[dict]:
    """
    Return the distinct origins that have at least one flight to
    `destination_airport` in flight_prices. Sorted by display name.

    Each item: {'iata_code', 'display', 'name', 'city', 'country'}
    """
    if not destination_airport:
        return []

    iatas = db.session.scalars(
        select(FlightPrice.origin)
        .where(FlightPrice.destination == destination_airport.upper())
        .distinct()
        .order_by(FlightPrice.origin)
    ).all()

    result = []
    for code in iatas:
        ap = db.session.get(Airport, code)
        result.append({
            "iata_code": code,
            "display": ap.display if ap else code,
            "name": ap.name if ap else code,
            "city": ap.city if ap else None,
            "country": ap.country if ap else None,
        })

    result.sort(key=lambda r: r["display"])
    return result


def cheapest_flight(
    origin: str,
    destination: str,
    from_date: date,
    to_date: date,
) -> dict | None:
    """
    Cheapest OUTBOUND flight from origin -> destination between two dates.
    Returns None if no rows match.
    """
    if not origin or not destination or not from_date or not to_date:
        return None

    row = db.session.scalars(
        select(FlightPrice)
        .where(
            FlightPrice.origin == origin.upper(),
            FlightPrice.destination == destination.upper(),
            FlightPrice.direction == "out",
            FlightPrice.departure_date >= from_date,
            FlightPrice.departure_date <= to_date,
        )
        .order_by(FlightPrice.price_gbp.asc(), FlightPrice.departure_date.asc())
        .limit(1)
    ).first()

    return _flight_to_dict(row) if row else None


def flight_for_date(
    origin: str,
    destination: str,
    on_date: date,
) -> dict | None:
    """
    Exact-date OUTBOUND lookup. Returns None if no row matches.
    """
    if not origin or not destination or not on_date:
        return None

    row = db.session.scalars(
        select(FlightPrice)
        .where(
            FlightPrice.origin == origin.upper(),
            FlightPrice.destination == destination.upper(),
            FlightPrice.direction == "out",
            FlightPrice.departure_date == on_date,
        )
        .order_by(FlightPrice.price_gbp.asc())
        .limit(1)
    ).first()

    return _flight_to_dict(row) if row else None


def flight_with_fallback(
    origin: str,
    destination: str,
    on_date: date,
    tolerance_days: int = 3,
) -> dict | None:
    """
    Try the exact date first. If no flight exists, look ±tolerance_days
    and return the CLOSEST one (ties broken by cheapest price).

    The returned dict has three extra keys:
        'flexible_date_used': bool   (True if we shifted from on_date)
        'offset_days':        int    (0 if exact, else delta in days)
        'requested_date':     date   (the original on_date)

    Returns None if no flight exists within the tolerance window.
    """
    if not origin or not destination or not on_date:
        return None

    # Exact match first
    exact = flight_for_date(origin, destination, on_date)
    if exact:
        exact["flexible_date_used"] = False
        exact["offset_days"] = 0
        exact["requested_date"] = on_date
        return exact

    if tolerance_days <= 0:
        return None

    window_start = on_date - timedelta(days=tolerance_days)
    window_end = on_date + timedelta(days=tolerance_days)

    # Fetch all candidates in window
    candidates = db.session.scalars(
        select(FlightPrice)
        .where(
            FlightPrice.origin == origin.upper(),
            FlightPrice.destination == destination.upper(),
            FlightPrice.direction == "out",
            FlightPrice.departure_date >= window_start,
            FlightPrice.departure_date <= window_end,
        )
    ).all()

    if not candidates:
        return None

    # Pick the CLOSEST to on_date; ties go to the earlier date.
    def distance(row):
        return abs((row.departure_date - on_date).days)

    closest = min(candidates, key=lambda r: (distance(r), r.departure_date))

    result = _flight_to_dict(closest)
    result["flexible_date_used"] = True
    result["offset_days"] = (closest.departure_date - on_date).days
    result["requested_date"] = on_date
    return result


def round_trip_cost(
    origin: str,
    destination: str,
    check_in: date,
    check_out: date,
    passengers: int = 1,
    tolerance_days: int = 3,
) -> dict[str, Any]:
    """
    Compute outbound + return cost.

    Outbound uses flight_with_fallback so a nearby date may be used
    if the exact check_in date has no flight — flagged in the response.

    Return leg is currently estimated as outbound × 2 because we only
    have outbound data. When inbound data is available, swap in a real
    lookup.

    Returns a dict with 'available', 'outbound', 'return', 'total_gbp',
    'flexible_date_used', 'offset_days', 'passengers'.
    """
    pax = max(int(passengers), 1)

    outbound = flight_with_fallback(
        origin, destination, check_in, tolerance_days=tolerance_days
    )

    if not outbound:
        return {
            "available": False,
            "reason": "no_outbound_in_window",
            "outbound": None,
            "return": None,
            "total_gbp": Decimal("0.00"),
            "passengers": pax,
            "flexible_date_used": False,
            "offset_days": 0,
            "requested_date": check_in,
        }

    outbound_price = Decimal(outbound["price_gbp"])

    # Return leg: try real lookup first, else estimate as 1× outbound.
    return_leg = flight_for_date(destination, origin, check_out)
    return_estimated = False
    if return_leg:
        return_price = Decimal(return_leg["price_gbp"])
    else:
        return_price = outbound_price
        return_estimated = True
        return_leg = {
            "estimated": True,
            "reason": "no_inbound_data",
            "origin": destination,
            "destination": origin,
            "departure_date": check_out,
            "price_gbp": outbound_price,
        }

    total_one_pax = outbound_price + return_price
    total = total_one_pax * pax

    return {
        "available": True,
        "outbound": outbound,
        "return": return_leg,
        "return_estimated": return_estimated,
        "one_pax_gbp": total_one_pax,
        "total_gbp": total,
        "passengers": pax,
        "currency": outbound.get("currency", "GBP"),
        "flexible_date_used": outbound.get("flexible_date_used", False),
        "offset_days": outbound.get("offset_days", 0),
        "requested_date": check_in,
    }


def flight_summary_for_package(
    package: Any,
    origin: str,
    check_in: date,
    check_out: date,
    passengers: int = 1,
    tolerance_days: int = 3,
) -> dict | None:
    """
    Convenience wrapper for the package detail page.

    Returns None if:
      * the package has no destination_id
      * the destination has no airport_code
      * no outbound flight exists within ±tolerance_days of check_in

    Otherwise returns the same dict shape as round_trip_cost().
    """
    if not package or not getattr(package, "destination_id", None):
        return None

    dest = db.session.get(Destination, package.destination_id)
    if not dest or not dest.airport_code:
        return None

    return round_trip_cost(
        origin=origin,
        destination=dest.airport_code,
        check_in=check_in,
        check_out=check_out,
        passengers=passengers,
        tolerance_days=tolerance_days,
    )


# ── Options builder for the package detail page ─────────────────────
# Default markup applied to the flight legs (percentage).
# Land cost already includes the hotel's own margin — markup here is
# only on the flights to mirror the tour-operator fee model.
DEFAULT_FLIGHT_MARKUP_PCT = Decimal("12.5")

# Transfer cost added per booking (covers airport ↔ hotel transfer).
DEFAULT_TRANSFER_GBP = Decimal("40.00")


def _transfer_cost(passengers: int) -> Decimal:
    """One-off transfer fee per booking. Scales mildly with party size."""
    pax = max(int(passengers), 1)
    return DEFAULT_TRANSFER_GBP + Decimal(pax - 1) * Decimal("10.00")


def flight_options_for_package(
    package: Any,
    check_in: date,
    check_out: date,
    passengers: int = 1,
    land_total: float | Decimal | None = None,
    *,
    currency: str = "GBP",
    tolerance_days: int = 3,
    markup_pct: Decimal | float | None = None,
    transfer_gbp: Decimal | None = None,
) -> list[dict]:
    """
    Build the option-card list for the package detail page.

    One card per airline: that airline's CLOSEST-date flight (cheapest
    as tiebreaker) within [check_in - tolerance_days,
    check_in + tolerance_days], combined with the land cost + a flight
    markup + a transfer fee, so the card shows the FULL total the
    customer will pay.

    Returns an empty list if:
      * the package has no destination_id
      * the destination has no airport_code
      * no flights exist within the tolerance window

    Each returned dict matches the existing option shape PLUS extra
    fields for the card display:

        id, label, departure_date, return_date,
        flight_from, flight_to,
        airline_name, airline_logo, luggage_allowance,
        price_adult, price_child, currency,
        grand_total, land_total, flight_total, markup_total,
        transfer_total, flexible_date_used, offset_days
    """
    if not package or not getattr(package, "destination_id", None):
        return []

    dest = db.session.get(Destination, package.destination_id)
    if not dest or not dest.airport_code:
        return []

    pax = max(int(passengers), 1)
    dest_airport = dest.airport_code.upper()
    window_start = check_in - timedelta(days=tolerance_days)
    window_end = check_in + timedelta(days=tolerance_days)

    # All outbound flights in the window
    candidates = db.session.scalars(
        select(FlightPrice)
        .where(
            FlightPrice.destination == dest_airport,
            FlightPrice.direction == "out",
            FlightPrice.departure_date >= window_start,
            FlightPrice.departure_date <= window_end,
        )
    ).all()

    if not candidates:
        return []

    # Group by airline
    by_airline: dict[str, list[FlightPrice]] = {}
    for row in candidates:
        key = (row.airline or "Unknown").strip()
        by_airline.setdefault(key, []).append(row)

    # Land total comes from the caller (sidebar_pricing.total).
    land = Decimal(str(land_total or 0)).quantize(Decimal("0.01"))

    markup_factor = Decimal(str(markup_pct)) if markup_pct is not None \
        else DEFAULT_FLIGHT_MARKUP_PCT

    transfer = transfer_gbp if transfer_gbp is not None else _transfer_cost(pax)

    options: list[dict] = []

    for airline, rows in by_airline.items():
        # CLOSEST date first, cheapest as tiebreaker — so a user asking
        # for 1 Nov gets 1 Nov if it exists, even if 4 Nov is cheaper.
        def sort_key(r: FlightPrice):
            offset = abs((r.departure_date - check_in).days)
            return (offset, r.price_gbp)

        chosen = sorted(rows, key=sort_key)[0]
        offset_days = (chosen.departure_date - check_in).days

        outbound_price = Decimal(chosen.price_gbp)

        # Try to find a matching inbound flight (same airline, closest return)
        # This is auto-pick mode — no pinned inbound, so we estimate.
        return_price = outbound_price
        return_estimated = True

        # Nights from the customer's chosen check_in/check_out
        # (this function is called for auto-pick packages that use
        #  package.check_in / package.check_out, not card-level dates)
        _nights = 0
        if check_in and check_out:
            _nights = (check_out - check_in).days

        flight_total_one_pax = outbound_price + return_price
        flight_total = flight_total_one_pax * pax

        # Markup on flights only
        markup_total = (
            flight_total * markup_factor / Decimal("100")
        ).quantize(Decimal("0.01"))

        # Card grand total = land + flights + markup + transfer
        grand = (
            land + flight_total + markup_total + transfer
        ).quantize(Decimal("0.01"))

        # price_adult is a per-passenger equivalent so the existing
        # JS recompute doesn't break. grand_total carries the truth.
        per_adult_equiv = (grand / Decimal(pax)).quantize(Decimal("0.01"))
        per_child_equiv = per_adult_equiv

        options.append({
            "id": chosen.id,
            "label": (
                f"{chosen.airline or 'Flight'} · "
                f"{_airport_display(chosen.origin)} → "
                f"{_airport_display(chosen.destination)}"
            ),
            "departure_date": chosen.departure_date,
            "return_date": check_out,
            "flight_from": _airport_display(chosen.origin),
            "flight_to": _airport_display(chosen.destination),
            "airline_name": chosen.airline,
            "airline_logo": None,
            "luggage_allowance": None,
            "price_adult": float(per_adult_equiv),
            "price_child": float(per_child_equiv),
            "currency": currency,
            # Extra fields used by the updated card + JS
            "grand_total": float(grand),
            "land_total": float(land),
            "flight_total": float(flight_total),
            "markup_total": float(markup_total),
            "transfer_total": float(transfer),
            "flexible_date_used": offset_days != 0,
            "offset_days": offset_days,
            "return_estimated": return_estimated,
        })

    # Cheapest first
    options.sort(key=lambda o: o["grand_total"])
    return options


__all__ = [
    "available_origins",
    "cheapest_flight",
    "flight_for_date",
    "flight_with_fallback",
    "round_trip_cost",
    "flight_summary_for_package",
    "flight_options_for_package",
]
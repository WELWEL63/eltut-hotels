"""
Standalone helper: compute per-person cost for a PackageFlight row.
Reusable from admin list page, admin edit page, and future preview.
"""
from decimal import Decimal


def _dec(v):
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def _airport_display(iata):
    """IATA -> 'City (CODE)' via airports table, fallback to raw code."""
    if not iata:
        return ""
    try:
        from models import Airport
        from extensions import db
        ap = db.session.get(Airport, iata.upper())
        if ap is not None:
            return getattr(ap, "display", None) or iata
    except Exception:
        pass
    return iata


def _rate_for_room(room_id, check_in, check_out):
    """Return (nightly, currency) for a room over a date range.
    Uses room_rates windows; falls back to rooms.base_price_per_night."""
    from models import RoomRate, Room
    from extensions import db
    from sqlalchemy import select

    if not check_in or not check_out:
        return (None, None)
    candidates = list(db.session.scalars(
        select(RoomRate)
        .where(
            RoomRate.room_id == room_id,
            RoomRate.valid_from <= check_in,
            RoomRate.valid_to >= check_in,
        )
    ))
    if candidates:
        chosen = min(
            candidates,
            key=lambda x: (x.valid_to - x.valid_from).days
            if (x.valid_from and x.valid_to) else 99999,
        )
        return (float(chosen.adult_price), chosen.currency)
    room = db.session.get(Room, room_id)
    if room and room.base_price_per_night:
        return (float(room.base_price_per_night), "GBP")
    return (None, None)


def _resolve_airline(flight):
    """Return {'name': str|None, 'logo_url': str|None} for a FlightPrice."""
    if flight is None:
        return {"name": None, "logo_url": None}
    name = getattr(flight, "airline", None)
    logo = None
    try:
        from models import Airline
        from extensions import db
        from sqlalchemy import select
        if name:
            norm = name.strip().lower().replace(" ", "")
            rows = list(db.session.scalars(select(Airline)))
            for al in rows:
                if al.name and al.name.strip().lower().replace(" ", "") == norm:
                    logo = al.logo_url
                    name = al.name
                    break
    except Exception:
        pass
    return {"name": name, "logo_url": logo}


def compute_package_flight_card(package, card):
    """Return dict with full breakdown for ONE PackageFlight card.

    Nights are derived from the card's own flight dates when BOTH
    outbound and inbound are set (flight-included package). If only
    outbound exists (land-only), nights fall back to package base dates.

    Keys (existing):
        ok, error, land_only,
        check_in, check_out, nights, room_nightly, currency,
        hotel_total, outbound_price, inbound_price, flight_total,
        subtotal, transfer_fee, markup, tax, per_person

    Keys (added for template binding — match package_detail.html):
        card_id, label,
        airline_name, airline_logo,
        flight_from, flight_to, luggage_allowance,
        departure_date, return_date,
        return_estimated
    """
    result = {
        "ok": False, "error": None, "land_only": False,
        "check_in": None, "check_out": None, "nights": 0,
        "room_nightly": None, "currency": "GBP",
        "hotel_total": 0.0, "outbound_price": 0.0, "inbound_price": 0.0,
        "flight_total": 0.0, "subtotal": 0.0, "transfer_fee": 0.0,
        "markup": 0.0, "tax": 0.0, "per_person": 0.0,
        # template-facing keys (populated below)
        "card_id": getattr(card, "id", None),
        "label": getattr(card, "label", None),
        "airline_name": None, "airline_logo": None,
        "flight_from": None, "flight_to": None,
        "luggage_allowance": None,
        "departure_date": None, "return_date": None,
        "return_estimated": True,
    }

    ob = card.outbound_flight
    ib = card.inbound_flight

    # Determine nights + effective dates
    if ob and ib and ob.departure_date and ib.departure_date:
        check_in = ob.departure_date
        check_out = ib.departure_date
        nights = (check_out - check_in).days
        result["land_only"] = False
        result["return_estimated"] = False
    elif ob and not ib and package.check_in and package.check_out:
        check_in = package.check_in
        check_out = package.check_out
        nights = (check_out - check_in).days
        result["land_only"] = True
    else:
        result["error"] = "Missing dates"
        return result

    if nights <= 0:
        result["error"] = "Invalid dates"
        return result

    result["check_in"] = check_in
    result["check_out"] = check_out
    result["nights"] = nights
    result["departure_date"] = check_in
    result["return_date"] = check_out

    # Flight display fields (from outbound; inbound for route end)
    if ob:
        al = _resolve_airline(ob)
        result["airline_name"] = al["name"]
        result["airline_logo"] = al["logo_url"]
        result["flight_from"] = _airport_display(ob.origin) or ob.origin
        dest_code = ob.destination
        result["flight_to"] = _airport_display(dest_code) or dest_code
        result["luggage_allowance"] = getattr(ob, "luggage_kg", None)

    # Room rate for those dates
    nightly, cur = _rate_for_room(package.room_id, check_in, check_out)
    if nightly is None:
        result["error"] = "No room rate"
        return result
    result["room_nightly"] = nightly
    if cur:
        result["currency"] = cur
    hotel_total = nightly * nights

    # Flights
    ob_price = float(ob.price_gbp) if ob else 0.0
    ib_price = float(ib.price_gbp) if ib else 0.0
    flight_total = ob_price + ib_price

    subtotal = hotel_total + flight_total
    transfer_fee = float(package.transfer_fee or 0)

    # Markup
    markup = 0.0
    if package.markup_value:
        mv = float(package.markup_value)
        if package.markup_kind == "percent":
            markup = (subtotal + transfer_fee) * (mv / 100.0)
        else:
            markup = mv

    # Tax
    tax = 0.0
    if package.tax_value:
        tv = float(package.tax_value)
        if package.tax_kind == "percent":
            tax = (subtotal + transfer_fee + markup) * (tv / 100.0)
        else:
            tax = tv

    per_person = subtotal + transfer_fee + markup + tax

    result.update({
        "ok": True,
        "outbound_price": ob_price,
        "inbound_price": ib_price,
        "flight_total": flight_total,
        "hotel_total": hotel_total,
        "transfer_fee": transfer_fee,
        "subtotal": subtotal,
        "markup": markup,
        "tax": tax,
        "per_person": per_person,
    })
    return result


def build_package_rows(packages):
    """For each package, return {pkg, cards:[{card, calc}], count}."""
    from models import PackageFlight
    from extensions import db
    from sqlalchemy import select

    out = []
    for pkg in packages:
        cards = list(db.session.scalars(
            select(PackageFlight)
            .where(PackageFlight.package_id == pkg.id)
            .order_by(PackageFlight.sort_order, PackageFlight.id)
        ))
        enriched = [{"card": c, "calc": compute_package_flight_card(pkg, c)} for c in cards]
        out.append({"pkg": pkg, "card": enriched, "count": len(cards)})
    return out
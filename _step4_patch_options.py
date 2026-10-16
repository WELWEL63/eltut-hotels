path = "services/package_options_service.py"
s = open(path, "r", encoding="utf-8").read()

# Insert a helper + land-only branch. Find the point where cards list is built.
old = '''    cards = list(db.session.scalars(
        select(PackageFlight)
        .where(PackageFlight.package_id == package.id)
        .where(PackageFlight.is_active.is_(True))
        .order_by(PackageFlight.sort_order.asc(), PackageFlight.id.asc())
    ))
    if not cards:
        return []'''

new = '''    cards = list(db.session.scalars(
        select(PackageFlight)
        .where(PackageFlight.package_id == package.id)
        .where(PackageFlight.is_active.is_(True))
        .order_by(PackageFlight.sort_order.asc(), PackageFlight.id.asc())
    ))

    # ── Land-only fallback ────────────────────────────────────────
    # Package has no PackageFlight cards at all → offer a land-only
    # option (hotel + transfer + markup + tax, no flights). This is
    # the path for destinations whose flight data hasn't been
    # imported yet (Sharm, Luxor, Nile Cruise).
    if not cards:
        return _land_only_option(
            package=package,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
        )'''

assert old in s, "cards block not found"
s = s.replace(old, new, 1)

# Add the helper before options_for_package definition
helper = '''def _land_only_option(
    *,
    package: Package,
    check_in: date | None,
    check_out: date | None,
    adults: int,
    children: int,
) -> list[dict[str, Any]]:
    """
    Build a single land-only option for a package that has no
    PackageFlight cards. Prices hotel + transfer + markup + tax.
    Returns [] if the package has no room rate at all.
    """
    from services.package_pricing_service import _rate_for_room
    from decimal import Decimal

    req_in, req_out = _normalise_dates(check_in, check_out, package)
    if not req_in or not req_out or req_out <= req_in:
        return []

    nights = (req_out - req_in).days
    if nights <= 0 or nights > 60:
        return []

    nightly, cur = _rate_for_room(package.room_id, req_in, req_out)
    if nightly is None or nightly <= 0:
        return []

    hotel_total = Decimal(str(nightly)) * nights
    transfer = Decimal(str(package.transfer_fee or 0))

    subtotal = hotel_total
    markup = Decimal("0")
    if package.markup_value:
        mv = Decimal(str(package.markup_value))
        if package.markup_kind == "percent":
            markup = (subtotal + transfer) * (mv / Decimal("100"))
        else:
            markup = mv
    tax = Decimal("0")
    if package.tax_value:
        tv = Decimal(str(package.tax_value))
        if package.tax_kind == "percent":
            tax = (subtotal + transfer + markup) * (tv / Decimal("100"))
        else:
            tax = tv

    per_person = float((subtotal + transfer + markup + tax).quantize(Decimal("0.01")))
    pax = max(1, int(adults) + int(children))
    grand_total = round(per_person * pax, 2)

    return [{
        "id": None,
        "card_id": None,
        "label": "Land only — no flights",
        "departure_date": req_in,
        "return_date": req_out,
        "nights": nights,
        "flight_from": None,
        "flight_to": None,
        "airline_name": None,
        "airline_logo": None,
        "luggage_allowance": None,
        "currency": cur or "GBP",
        "price_adult": round(per_person, 2),
        "price_child": round(per_person, 2),
        "land_total": round(float(hotel_total), 2),
        "flight_total": 0.0,
        "markup_total": round(float(markup), 2),
        "tax_total": round(float(tax), 2),
        "transfer_total": round(float(transfer), 2),
        "grand_total": grand_total,
        "flexible_date_used": False,
        "offset_days": 0,
        "return_estimated": False,
        "is_land_only": True,
    }]


'''

anchor = "def options_for_package("
assert anchor in s, "options_for_package anchor not found"
s = s.replace(anchor, helper + anchor, 1)

open(path, "w", encoding="utf-8").write(s)
print("package_options_service.py patched with land-only branch")
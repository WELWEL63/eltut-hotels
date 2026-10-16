path = "blueprints/public/booking_routes.py"
lines = open(path, "r", encoding="utf-8").read().splitlines(keepends=True)

# ── Build the three replacement blocks ─────────────────────────────
new_pricing = '''def _package_pricing(
    package: Package,
    adults: int,
    children: int,
    package_flight_id: int | None = None,
) -> dict:
    """Price a package booking from a selected PackageFlight card.

    Prices the card via services.package_pricing_service, the same
    function the admin preview uses. No card -> zeroed dict so the
    caller shows "select a departure" instead of a wrong number.
    """
    from services.package_pricing_service import compute_package_flight_card

    empty = {
        "adult_rate": None, "child_rate": None, "nights": package.duration_nights,
        "per_night": None, "per_person": None, "total": None, "currency": "GBP",
        "package_flight_id": None,
        "hotel_total": None, "flight_total": None, "markup": None, "tax": None,
        "transfer_fee": None,
        "departure_date": None, "return_date": None,
        "airline_name": None, "airline_logo": None,
        "flight_from": None, "flight_to": None,
    }
    if not package_flight_id:
        return empty

    from models import PackageFlight
    card = db.session.get(PackageFlight, package_flight_id)
    if card is None or card.package_id != package.id or not card.is_active:
        return empty

    calc = compute_package_flight_card(package, card)
    if not calc.get("ok"):
        return empty

    pax = max(1, int(adults) + int(children))
    per_person = float(calc.get("per_person") or 0.0)
    grand_total = per_person * pax

    return {
        "adult_rate": round(per_person, 2),
        "child_rate": round(per_person, 2),
        "nights": int(calc.get("nights") or package.duration_nights),
        "per_night": None,
        "per_person": round(per_person, 2),
        "total": round(grand_total, 2),
        "currency": calc.get("currency") or "GBP",
        "package_flight_id": card.id,
        "hotel_total": round(float(calc.get("hotel_total") or 0.0), 2),
        "flight_total": round(float(calc.get("flight_total") or 0.0), 2),
        "markup": round(float(calc.get("markup") or 0.0), 2),
        "tax": round(float(calc.get("tax") or 0.0), 2),
        "transfer_fee": round(float(calc.get("transfer_fee") or 0.0), 2),
        "departure_date": calc.get("check_in"),
        "return_date": calc.get("check_out"),
        "airline_name": calc.get("airline_name"),
        "airline_logo": calc.get("airline_logo"),
        "flight_from": calc.get("flight_from"),
        "flight_to": calc.get("flight_to"),
    }


'''

new_option_block = '''    # ─── Optional departure card (packages only) ───────────────────
    # The detail page sends ?package_flight_id=<PackageFlight.id>.
    # Legacy ?option_id=<PackageOption.id> is still accepted as a
    # fallback so old bookmarked URLs don't 404.
    package_flight_id: int | None = None
    raw_pfid = (request.args.get("package_flight_id") or "").strip()
    if product_type == "package" and raw_pfid:
        try:
            package_flight_id = int(raw_pfid)
        except ValueError:
            package_flight_id = None

    option = None  # kept for template backward-compat
    if product_type == "package":
        from models import PackageFlight
        if package_flight_id:
            card = db.session.get(PackageFlight, package_flight_id)
            if card and card.package_id == product.id and card.is_active:
                option = card
        if option is None:
            raw_option_id = (request.args.get("option_id") or "").strip()
            if raw_option_id:
                try:
                    legacy_opt_id = int(raw_option_id)
                except ValueError:
                    legacy_opt_id = None
                if legacy_opt_id:
                    candidate = db.session.get(PackageOption, legacy_opt_id)
                    if candidate and candidate.package_id == product.id and candidate.is_active:
                        option = candidate

    meta = _product_meta(product_type, product)

    # If a departure card was selected, seed meta's display fields.
    # The authoritative price comes from _package_pricing() below.
    if package_flight_id and option is not None:
        dep = getattr(option, "outbound_flight", None)
        if dep is not None and getattr(dep, "departure_date", None):
            meta["default_start"] = dep.departure_date.isoformat()

'''

new_pricing_call = '''        elif product_type == PRODUCT_TYPE_PACKAGE:
            pricing = _package_pricing(
                product, adults, children,
                package_flight_id=package_flight_id,
            )
'''

# ── Splice: work back-to-front so line numbers stay valid ──────────
# Region C (lines 345-361): the elif PACKAGE pricing block
# 345 is "        elif product_type == PRODUCT_TYPE_PACKAGE:"
# 361 is "                pricing = _package_pricing(product, adults, children)"
# region C is lines 345..361 inclusive
c_start, c_end = 345, 361
assert lines[c_start-1].strip().startswith("elif product_type == PRODUCT_TYPE_PACKAGE"), \
    f"C start mismatch: {lines[c_start-1]!r}"
assert "pricing = _package_pricing(product, adults, children)" in lines[c_end-1], \
    f"C end mismatch: {lines[c_end-1]!r}"
lines[c_start-1:c_end] = [new_pricing_call]

# Region B (lines 311-339): option block + meta override
# 311 "# ─── Optional departure option (packages only) ─────────────────"
# 339 '            meta["default_start"] = option.departure_date.isoformat()'
b_start, b_end = 311, 339
assert "Optional departure option" in lines[b_start-1], \
    f"B start mismatch: {lines[b_start-1]!r}"
assert "default_start" in lines[b_end-1], \
    f"B end mismatch: {lines[b_end-1]!r}"
lines[b_start-1:b_end] = [new_option_block]

# Region A (lines 228-250): _package_pricing body
# 228 "def _package_pricing(package: Package, adults: int, children: int) -> dict:"
# 250 "    }"
a_start, a_end = 228, 250
assert lines[a_start-1].startswith("def _package_pricing("), \
    f"A start mismatch: {lines[a_start-1]!r}"
assert lines[a_end-1].rstrip() == "    }", \
    f"A end mismatch: {lines[a_end-1]!r}"
lines[a_start-1:a_end] = [new_pricing]

open(path, "w", encoding="utf-8").writelines(lines)
print("booking_routes.py patched")
path = "services/package_options_service.py"
s = open(path, "r", encoding="utf-8").read()

old = '''    nightly, cur = _rate_for_room(package.room_id, req_in, req_out)
    if nightly is None or nightly <= 0:
        return []

    hotel_total = Decimal(str(nightly)) * nights
    transfer = Decimal(str(package.transfer_fee or 0))'''

new = '''    nightly, cur = _rate_for_room(package.room_id, req_in, req_out)
    if nightly is None or nightly <= 0:
        # Fallback to PackagePrice — the package's own land price,
        # used when room-level rate data hasn't been imported.
        nightly, cur = _land_rate_from_package_price(package, req_in, req_out)
    if nightly is None or nightly <= 0:
        return []

    hotel_total = Decimal(str(nightly)) * nights
    transfer = Decimal(str(package.transfer_fee or 0))'''

assert old in s, "land-only rate block not found"
s = s.replace(old, new, 1)

# Add the PackagePrice fallback helper before _land_only_option
helper = '''def _land_rate_from_package_price(
    package: Package,
    check_in: date,
    check_out: date,
):
    """
    Return (nightly_adult, currency) derived from the tightest
    PackagePrice window that contains check_in, divided by its
    duration. Falls back to any flexible PackagePrice row.
    Returns (None, None) if no row is usable.
    """
    from models import PackagePrice
    from sqlalchemy import select

    rows = list(db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package.id)
        .order_by(PackagePrice.adult_price.asc(), PackagePrice.id.asc())
    ))
    if not rows:
        return (None, None)

    candidates = [
        r for r in rows
        if (r.valid_from is not None and r.valid_to is not None
            and r.valid_from <= check_in <= r.valid_to)
    ]
    if candidates:
        chosen = min(
            candidates,
            key=lambda r: (r.valid_to - r.valid_from).days,
        )
    else:
        flexible = [
            r for r in rows
            if r.valid_from is None and r.valid_to is None
        ]
        chosen = flexible[0] if flexible else rows[0]

    if not chosen or chosen.adult_price is None:
        return (None, None)

    if chosen.valid_from and chosen.valid_to:
        window_nights = max(1, (chosen.valid_to - chosen.valid_from).days)
    else:
        window_nights = max(1, (check_out - check_in).days)

    try:
        nightly = float(chosen.adult_price) / window_nights
    except Exception:
        return (None, None)
    return (nightly, chosen.currency or "GBP")


'''

anchor = "def _land_only_option("
assert anchor in s, "land-only anchor not found"
s = s.replace(anchor, helper + anchor, 1)

open(path, "w", encoding="utf-8").write(s)
print("package_options_service.py patched with PackagePrice fallback")
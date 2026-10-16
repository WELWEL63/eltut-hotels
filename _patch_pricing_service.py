path = "services/pricing_service.py"
s = open(path, "r", encoding="utf-8").read()

old_price_pkg = '''def price_package(package_id: int, adults: int, children: int = 0) -> Decimal:
    """
    Return the total price for a package given party composition.

    Uses the first row in package_prices for the package.
    """
    _positive_int(adults, "adults")
    _positive_int(children, "children")
    if adults == 0 and children == 0:
        raise InvalidPricingInput("at least one adult or child is required")

    row = db.session.scalar(
        select(PackagePrice)
        .where(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.id)
        .limit(1)
    )
    if row is None:
        exists = db.session.scalar(
            select(Package.id).where(Package.id == package_id).limit(1)
        )
        if exists is None:
            raise PriceNotFound(f"package {package_id} not found")
        raise PriceNotFound(f"package {package_id} has no price row")

    total = (_dec(row.adult_price) * adults) + (_dec(row.child_price) * children)
    return _round(total)'''

new_price_pkg = '''def price_package(
    package_id: int,
    adults: int,
    children: int = 0,
    package_flight_id: int | None = None,
) -> Decimal:
    """
    Return the total price for a package given party composition.

    If package_flight_id is provided, price that PackageFlight card via
    services.package_pricing_service.compute_package_flight_card — the
    same function the admin preview uses, so customer and admin always
    agree to the penny.

    If package_flight_id is None, we still fall back to the FIRST
    PackagePrice row for backwards compatibility with old bookmarks or
    API clients, but callers should always prefer the card path.
    """
    _positive_int(adults, "adults")
    _positive_int(children, "children")
    if adults == 0 and children == 0:
        raise InvalidPricingInput("at least one adult or child is required")

    if package_flight_id:
        from models import Package, PackageFlight
        from services.package_pricing_service import compute_package_flight_card

        pkg = db.session.get(Package, package_id)
        if pkg is None:
            raise PriceNotFound(f"package {package_id} not found")

        card = db.session.get(PackageFlight, package_flight_id)
        if card is None or card.package_id != package_id or not card.is_active:
            raise PriceNotFound(
                f"package_flight {package_flight_id} not found for package {package_id}"
            )

        calc = compute_package_flight_card(pkg, card)
        if not calc.get("ok"):
            raise PriceNotFound(
                f"package_flight {package_flight_id} has no price "
                f"({calc.get('error') or 'unknown error'})"
            )

        per_person = _dec(calc.get("per_person") or 0)
        pax = max(1, int(adults) + int(children))
        return _round(per_person * pax)

    # Legacy fallback: first PackagePrice row
    row = db.session.scalar(
        select(PackagePrice)
        .where(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.id)
        .limit(1)
    )
    if row is None:
        exists = db.session.scalar(
            select(Package.id).where(Package.id == package_id).limit(1)
        )
        if exists is None:
            raise PriceNotFound(f"package {package_id} not found")
        raise PriceNotFound(f"package {package_id} has no price row")

    total = (_dec(row.adult_price) * adults) + (_dec(row.child_price) * children)
    return _round(total)'''

assert old_price_pkg in s, "price_package body not found"
s = s.replace(old_price_pkg, new_price_pkg, 1)

old_dispatch = '''    check_in: Optional[date] = None,
    check_out: Optional[date] = None,
    addons: Optional[Iterable[dict[str, Any]]] = None,
) -> Decimal:'''

new_dispatch = '''    check_in: Optional[date] = None,
    check_out: Optional[date] = None,
    addons: Optional[Iterable[dict[str, Any]]] = None,
    package_flight_id: Optional[int] = None,
) -> Decimal:'''

assert old_dispatch in s, "compute_booking_total signature not found"
s = s.replace(old_dispatch, new_dispatch, 1)

old_call = '''    elif product_type == PRODUCT_TYPE_PACKAGE:
        base = price_package(product_id, adults, children)'''

new_call = '''    elif product_type == PRODUCT_TYPE_PACKAGE:
        base = price_package(
            product_id, adults, children,
            package_flight_id=package_flight_id,
        )'''

assert old_call in s, "package dispatch not found"
s = s.replace(old_call, new_call, 1)

open(path, "w", encoding="utf-8").write(s)
print("pricing_service.py patched")
p = 'blueprints/public/package_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── Patch 1: enrich airline_lookup ───
old1 = '''    # Build a lookup of airline_name (lowercase) -> logo_url
    airline_lookup: dict[str, str] = {}
    try:
        for al in db.session.scalars(select(Airline)):
            if al.logo_url:
                airline_lookup[al.name.strip().lower()] = al.logo_url
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("airline lookup failed: %s", exc)'''

new1 = '''    # Build lookups for airline logo resolution:
    #   by_id   : {airline.id: {name, logo_url}}       ← preferred (FK-driven)
    #   by_name : {"normalized name": {name, logo_url}} ← fallback for legacy rows
    airlines_by_id: dict[int, dict] = {}
    airlines_by_name: dict[str, dict] = {}
    try:
        for al in db.session.scalars(select(Airline)):
            entry = {"name": al.name, "logo_url": al.logo_url}
            airlines_by_id[al.id] = entry
            if al.name:
                normalized = al.name.strip().lower().replace(" ", "")
                airlines_by_name[normalized] = entry
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("airline lookup failed: %s", exc)

    def _resolve_airline(flight) -> dict:
        """Return {name, logo_url} using FK first, then name fallback."""
        if flight is None:
            return {"name": None, "logo_url": None}
        # 1) FK lookup (preferred)
        if getattr(flight, "airline_id", None):
            entry = airlines_by_id.get(flight.airline_id)
            if entry:
                return {
                    "name": entry["name"] or flight.airline_name,
                    "logo_url": entry["logo_url"],
                }
        # 2) Fallback: normalized string match on airline_name
        if flight.airline_name:
            normalized = flight.airline_name.strip().lower().replace(" ", "")
            entry = airlines_by_name.get(normalized)
            if entry:
                return {
                    "name": flight.airline_name,
                    "logo_url": entry["logo_url"],
                }
        # 3) Nothing found
        return {"name": flight.airline_name, "logo_url": None}'''

if old1 in c:
    c = c.replace(old1, new1, 1)
    print("✅ Patch 1: airline lookups enriched")
else:
    print("❌ Patch 1 FAILED — see context below")
    idx = c.find("airline_lookup")
    print("Context:", repr(c[max(0,idx-100):idx+400]))
    raise SystemExit(1)

# ─── Patch 2: use FK-first resolution in options serialization ───
old2 = '''    options: list[dict] = []
    for opt in options_rows:
        flight = opt.flight
        price = opt.price
        airline_name = flight.airline_name if flight else None
        options.append({
            "id": opt.id,
            "label": opt.display_label,
            "departure_date": opt.departure_date,
            "return_date": opt.return_date,
            "flight_from": flight.flight_from if flight else None,
            "flight_to": flight.flight_to if flight else None,
            "airline_name": airline_name,
            "airline_logo": airline_lookup.get(
                (airline_name or "").strip().lower()
            ),
            "luggage_allowance": flight.luggage_allowance if flight else None,
            "price_adult": float(price.adult_price) if price else None,
            "price_child": float(price.child_price) if price else None,
            "currency": price.currency if price else None,
        })'''

new2 = '''    options: list[dict] = []
    for opt in options_rows:
        flight = opt.flight
        price = opt.price
        airline = _resolve_airline(flight)
        options.append({
            "id": opt.id,
            "label": opt.display_label,
            "departure_date": opt.departure_date,
            "return_date": opt.return_date,
            "flight_from": flight.flight_from if flight else None,
            "flight_to": flight.flight_to if flight else None,
            "airline_name": airline["name"],
            "airline_logo": airline["logo_url"],
            "luggage_allowance": flight.luggage_allowance if flight else None,
            "price_adult": float(price.adult_price) if price else None,
            "price_child": float(price.child_price) if price else None,
            "currency": price.currency if price else None,
        })'''

if old2 in c:
    c = c.replace(old2, new2, 1)
    print("✅ Patch 2: options resolve airline via FK first")
else:
    print("❌ Patch 2 FAILED — see context below")
    idx = c.find("for opt in options_rows")
    print("Context:", repr(c[max(0,idx-100):idx+600]))
    raise SystemExit(1)

# ─── Patch 3: keep render_template arg name for template compat ───
c = c.replace(
    "        airline_lookup=airline_lookup,",
    "        airline_lookup=airlines_by_name,"
)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print("✅ ALL PATCHES APPLIED — package_routes.py written")

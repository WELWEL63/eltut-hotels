p = 'blueprints/admin/package_admin.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ═══════════════════════════════════════════════════════
# PATCH 1: Add Airline to imports
# ═══════════════════════════════════════════════════════
old1 = '''from models import (
    BookingItem,
    Destination,
    Flight,'''
new1 = '''from models import (
    Airline,
    BookingItem,
    Destination,
    Flight,'''

if old1 in c:
    c = c.replace(old1, new1, 1)
    print("✅ Patch 1: Airline imported")
else:
    print("❌ Patch 1: anchor not found")
    raise SystemExit(1)

# ═══════════════════════════════════════════════════════
# PATCH 2: package_flight_new accepts airline_id
# ═══════════════════════════════════════════════════════
old2 = '''    flight = Flight(
        package_id=package.id,
        supplier_id=supplier_id,
        flight_from=flight_from,
        flight_to=flight_to,
        airline_name=(request.form.get("airline_name") or "").strip() or None,
        luggage_allowance=(request.form.get("luggage_allowance") or "").strip() or None,
        included=bool(request.form.get("included")),
        notes=(request.form.get("notes") or "").strip() or None,
    )'''

new2 = '''    # Airline: prefer FK, fall back to free-text airline_name
    airline_id = None
    raw_airline_id = (request.form.get("airline_id") or "").strip()
    if raw_airline_id:
        try:
            airline_id = int(raw_airline_id) or None
        except ValueError:
            airline_id = None

    airline_name = (request.form.get("airline_name") or "").strip() or None
    if airline_id:
        airline_obj = db.session.get(Airline, airline_id)
        if airline_obj:
            airline_name = airline_obj.name

    flight = Flight(
        package_id=package.id,
        supplier_id=supplier_id,
        airline_id=airline_id,
        flight_from=flight_from,
        flight_to=flight_to,
        airline_name=airline_name,
        luggage_allowance=(request.form.get("luggage_allowance") or "").strip() or None,
        included=bool(request.form.get("included")),
        notes=(request.form.get("notes") or "").strip() or None,
    )'''

if old2 in c:
    c = c.replace(old2, new2, 1)
    print("✅ Patch 2: flight_new accepts airline_id")
else:
    print("❌ Patch 2: anchor not found")
    idx = c.find("flight = Flight(")
    print("Context:", repr(c[max(0,idx-100):idx+400]))
    raise SystemExit(1)

# ═══════════════════════════════════════════════════════
# PATCH 3: package_edit passes airlines list to template
# ═══════════════════════════════════════════════════════
old3 = '''    options = list(db.session.scalars(
        select(PackageOption)
        .where(PackageOption.package_id == package.id)
        .order_by(PackageOption.sort_order.asc(), PackageOption.id.asc())
    ))'''

new3 = '''    options = list(db.session.scalars(
        select(PackageOption)
        .where(PackageOption.package_id == package.id)
        .order_by(PackageOption.sort_order.asc(), PackageOption.id.asc())
    ))

    # Airlines list for the flight form dropdown
    airlines = list(db.session.scalars(
        select(Airline).where(Airline.is_active.is_(True)).order_by(Airline.name)
    ))'''

if old3 in c:
    c = c.replace(old3, new3, 1)
    print("✅ Patch 3: airlines queried in package_edit")
else:
    print("❌ Patch 3: anchor not found")
    raise SystemExit(1)

# ═══════════════════════════════════════════════════════
# PATCH 4: pass airlines to render_template
# ═══════════════════════════════════════════════════════
old4 = '''    return render_template(
        "admin/package_form.html",
        package=package,
        options=options,'''

new4 = '''    return render_template(
        "admin/package_form.html",
        package=package,
        options=options,
        airlines=airlines,'''

if old4 in c:
    c = c.replace(old4, new4, 1)
    print("✅ Patch 4: airlines passed to template")
else:
    print("❌ Patch 4: anchor not found")
    raise SystemExit(1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print()
print("✅ ALL 4 PATCHES APPLIED — package_admin.py written")

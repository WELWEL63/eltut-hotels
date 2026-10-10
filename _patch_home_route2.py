p = 'blueprints/public/routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── Insert helper AFTER the import block, BEFORE @public_bp.route("/") ───
helper = '''

# ─── Home page helpers ────────────────────────────────────────────
def _cheapest_per_destination(model, price_getter, limit=6):
    """
    Return up to `limit` model instances - each from a DISTINCT destination,
    keeping the CHEAPEST one per destination.

    `price_getter` is a callable that takes the model instance and returns
    a float price (or None). Items with no price are skipped.
    """
    rows = list(db.session.scalars(
        select(model).where(model.is_active.is_(True))
    ))
    # Group by destination, keep the cheapest item per destination
    best: dict[int | None, tuple] = {}
    for obj in rows:
        try:
            price = price_getter(obj)
        except Exception:
            price = None
        if price is None:
            continue
        dest = getattr(obj, "destination_id", None)
        if dest not in best or price < best[dest][0]:
            best[dest] = (price, obj)
    # Sort by price ascending, take the top `limit`
    ordered = sorted(best.values(), key=lambda t: t[0])
    return [obj for _, obj in ordered[:limit]]


def _hotel_price(obj):
    """Cheapest active room price for a hotel, in float."""
    from sqlalchemy import func as _f
    row = db.session.scalar(
        select(_f.min(Room.base_price_per_night)).where(
            Room.hotel_id == obj.id,
            Room.is_active.is_(True),
            Room.base_price_per_night > 0,
        )
    )
    return float(row) if row else None


def _package_price(obj):
    """Cheapest PackagePrice for a package, in float."""
    from sqlalchemy import func as _f
    row = db.session.scalar(
        select(_f.min(PackagePrice.adult_price)).where(
            PackagePrice.package_id == obj.id
        )
    )
    return float(row) if row else None


def _activity_price(obj):
    """Cheapest ActivityPrice for an activity, in float."""
    from sqlalchemy import func as _f
    row = db.session.scalar(
        select(_f.min(ActivityPrice.adult_price)).where(
            ActivityPrice.activity_id == obj.id
        )
    )
    return float(row) if row else None

'''

# Insert helper BEFORE the "@public_bp.route(\"/\")" decorator
anchor = '@public_bp.route("/")'
if anchor not in c:
    print("ANCHOR NOT FOUND")
    raise SystemExit(1)

if "_cheapest_per_destination" in c:
    print("Helper already present - no change")
    raise SystemExit(0)

c = c.replace(anchor, helper.strip() + "\n\n\n" + anchor, 1)
print("Inserted helpers")

# ─── Replace the featured_* queries in index() ───
old_featured = '''    featured_activities = list(
        db.session.scalars(
            select(Activity)
            .where(Activity.is_active.is_(True))
            .order_by(Activity.id)
            .limit(6)
        )
    )
    featured_hotels = list(
        db.session.scalars(
            select(Hotel)
            .where(Hotel.is_active.is_(True))
            .order_by(Hotel.id)
            .limit(3)
        )
    )
    featured_packages = list(
        db.session.scalars(
            select(Package)
            .where(Package.is_active.is_(True))
            .order_by(Package.id)
            .limit(3)
        )
    )
    top_destinations = list(
        db.session.scalars(
            select(Destination).order_by(Destination.name).limit(8)
        )
    )'''

new_featured = '''    # ─── Featured content: cheapest per destination, 6 each ───
    try:
        featured_hotels = _cheapest_per_destination(Hotel, _hotel_price, limit=6)
    except Exception as exc:
        current_app.logger.warning("featured_hotels failed: %s", exc)
        featured_hotels = []

    try:
        featured_packages = _cheapest_per_destination(Package, _package_price, limit=6)
    except Exception as exc:
        current_app.logger.warning("featured_packages failed: %s", exc)
        featured_packages = []

    try:
        featured_activities = _cheapest_per_destination(Activity, _activity_price, limit=6)
    except Exception as exc:
        current_app.logger.warning("featured_activities failed: %s", exc)
        featured_activities = []

    top_destinations = list(
        db.session.scalars(
            select(Destination).order_by(Destination.name).limit(6)
        )
    )

    # ─── Destination images (admin-managed, best-effort) ───
    destination_images = {}
    try:
        from services import content_service
        destination_images = content_service.all_destination_images()
    except Exception as exc:
        current_app.logger.debug("destination images unavailable: %s", exc)'''

if old_featured in c:
    c = c.replace(old_featured, new_featured, 1)
    print("Replaced featured_* queries")
else:
    print("FEATURED ANCHOR NOT FOUND")
    idx = c.find("featured_activities = list(")
    print("Context:", repr(c[max(0,idx-100):idx+600]))
    raise SystemExit(1)

# ─── Pass destination_images to template ───
old_render = '''    return render_template(
        "public/index.html",'''
new_render = '''    return render_template(
        "public/index.html",
        destination_images=destination_images,'''

if old_render in c:
    c = c.replace(old_render, new_render, 1)
    print("Passed destination_images to template")
else:
    print("RENDER ANCHOR NOT FOUND")
    raise SystemExit(1)

# ─── Ensure needed model imports exist ───
needed = []
if "Room" not in c.split("from models import")[1].split(")")[0]:
    needed.append("Room")
if "PackagePrice" not in c.split("from models import")[1].split(")")[0]:
    needed.append("PackagePrice")
if "ActivityPrice" not in c.split("from models import")[1].split(")")[0]:
    needed.append("ActivityPrice")
if "Airline" not in c.split("from models import")[1].split(")")[0]:
    pass  # not needed here
if "current_app" not in c:
    needed.append("__FLASK_CURRENT_APP__")

if needed and "__FLASK_CURRENT_APP__" not in needed:
    # Add the missing imports inside the from models import (...) block
    old_imports = '''from models import (
    Activity,
    Destination,
    Hotel,
    Package,
)'''
    new_imports = '''from models import (
    Activity,
    ActivityPrice,
    Destination,
    Hotel,
    Package,
    PackagePrice,
    Room,
)'''
    if old_imports in c:
        c = c.replace(old_imports, new_imports, 1)
        print("Added model imports:", needed)
    else:
        print("WARN: could not auto-patch imports — check manually")

# Add current_app to flask import if missing
if "from flask import render_template" in c and "current_app" not in c.split("\n")[0:60].__str__():
    c = c.replace(
        "from flask import render_template",
        "from flask import current_app, render_template",
        1
    )
    print("Added current_app import")

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print("PATCHED - routes.py updated")

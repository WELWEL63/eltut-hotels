p = 'blueprints/public/routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── 1) Add cheapest-per-destination helper before def index() ───
helper = '''

def _cheapest_per_destination(model, price_subquery, limit=6):
    """
    Return the cheapest `limit` products where each one is in a distinct
    destination. Uses a window function via SQLAlchemy 2.x on Postgres.
    """
    from sqlalchemy import func as _func

    # Subquery: cheapest price per destination
    inner = (
        select(
            model,
            price_subquery.label("unit_price"),
            _func.row_number().over(
                partition_by=model.destination_id,
                order_by=price_subquery.asc(),
            ).label("rn"),
        )
        .where(model.is_active.is_(True))
        .where(price_subquery.is_not(None))
        .subquery()
    )
    # Postgres-safe: SELECT the first row per destination
    rows = db.session.execute(
        select(inner).where(inner.c.rn == 1)
    ).all()
    # Extract model instances — SQLAlchemy returns the mapped object
    # but our select() returns a Row; use ._mapping[model.__name__]
    results = []
    for r in rows:
        # r[0] is the model object
        results.append((r[0], r.unit_price))
    # Sort by price ascending, take top `limit`
    results.sort(key=lambda t: float(t[1] or 0))
    return [obj for obj, _ in results[:limit]]


def _hotel_price_subquery():
    return select(func.min(Room.base_price_per_night)).where(
        Room.hotel_id == Hotel.id,
        Room.is_active.is_(True),
    ).correlate(Hotel).scalar_subquery()


def _package_price_subquery():
    return select(func.min(PackagePrice.adult_price)).where(
        PackagePrice.package_id == Package.id,
    ).correlate(Package).scalar_subquery()


def _activity_price_subquery():
    return select(func.min(ActivityPrice.adult_price)).where(
        ActivityPrice.activity_id == Activity.id,
    ).correlate(Activity).scalar_subquery()
'''

anchor = "def index():"
if helper.strip() in c:
    print("Helper already present - no change")
elif anchor in c:
    c = c.replace(anchor, helper.strip() + "\n\n\n" + anchor, 1)
    print("Inserted _cheapest_per_destination helper")
else:
    print("Anchor 'def index():' not found")
    raise SystemExit(1)

# ─── 2) Replace the featured_* queries with cheapest-per-destination ───
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

new_featured = '''    # ─── Featured content: cheapest per destination, 6 cards each ───
    try:
        featured_hotels = _cheapest_per_destination(
            Hotel, _hotel_price_subquery(), limit=6
        )
    except Exception as exc:
        current_app.logger.warning("featured_hotels failed: %s", exc)
        featured_hotels = []

    try:
        featured_packages = _cheapest_per_destination(
            Package, _package_price_subquery(), limit=6
        )
    except Exception as exc:
        current_app.logger.warning("featured_packages failed: %s", exc)
        featured_packages = []

    try:
        featured_activities = _cheapest_per_destination(
            Activity, _activity_price_subquery(), limit=6
        )
    except Exception as exc:
        current_app.logger.warning("featured_activities failed: %s", exc)
        featured_activities = []

    top_destinations = list(
        db.session.scalars(
            select(Destination).order_by(Destination.name).limit(6)
        )
    )

    # ─── Destination images (admin-managed, best-effort) ───
    destination_images: dict[str, str] = {}
    try:
        from services import content_service  # noqa: PLC0415
        destination_images = content_service.all_destination_images()
    except Exception as exc:
        current_app.logger.debug("destination images unavailable: %s", exc)'''

if old_featured in c:
    c = c.replace(old_featured, new_featured, 1)
    print("Replaced featured_* queries")
else:
    print("FEATURED ANCHOR NOT FOUND")
    idx = c.find("featured_activities")
    print("Context:", repr(c[max(0,idx-200):idx+500]))
    raise SystemExit(1)

# ─── 3) Add destination_images to render_template ───
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

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print("PATCHED - routes.py updated")

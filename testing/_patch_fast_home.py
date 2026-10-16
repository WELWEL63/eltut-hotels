p = 'blueprints/public/routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── Replace the N+1 loop with a single-query version ───
old = '''def _cheapest_per_destination(model, price_getter, limit=6):
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
    # Return dicts with both the object and its cheapest price
    return [
        {"obj": obj, "price": round(float(price), 2)}
        for price, obj in ordered[:limit]
    ]'''

new = '''def _cheapest_per_destination(model, price_subquery, limit=6):
    """
    Single-query version — returns up to `limit` items, each from a
    DISTINCT destination, keeping the CHEAPEST one per destination.

    Uses PostgreSQL `DISTINCT ON (destination_id)` — 1 query, fast.
    """
    # Subquery: DISTINCT ON picks the row with the minimum price per destination
    inner = (
        select(model, price_subquery.label("cheapest_price"))
        .where(model.is_active.is_(True))
        .where(price_subquery.is_not(None))
        .where(price_subquery > 0)
        .distinct(model.destination_id)
        .order_by(model.destination_id, price_subquery.asc())
        .subquery()
    )
    # Wrap and re-sort by cheapest_price across all destinations
    rows = db.session.execute(
        select(inner).order_by(inner.c.cheapest_price.asc()).limit(limit)
    ).all()

    results = []
    for row in rows:
        # SQLAlchemy returns the model instance in row[0] when we
        # select(model, ...) inside the subquery
        obj = row[0]
        price = row[-1]
        results.append({
            "obj": obj,
            "price": round(float(price), 2) if price is not None else None,
        })
    return results


def _hotel_price_subquery():
    """Min active room price for a hotel — as SQL subquery."""
    return (
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == Hotel.id, Room.is_active.is_(True),
               Room.base_price_per_night > 0)
        .correlate(Hotel)
        .scalar_subquery()
    )


def _package_price_subquery():
    """Min PackagePrice.adult_price for a package — as SQL subquery."""
    return (
        select(func.min(PackagePrice.adult_price))
        .where(PackagePrice.package_id == Package.id)
        .correlate(Package)
        .scalar_subquery()
    )


def _activity_price_subquery():
    """Min ActivityPrice.adult_price for an activity — as SQL subquery."""
    return (
        select(func.min(ActivityPrice.adult_price))
        .where(ActivityPrice.activity_id == Activity.id)
        .correlate(Activity)
        .scalar_subquery()
    )'''

if old in c:
    c = c.replace(old, new, 1)
    print("✅ Replaced helper with single-query version")
else:
    print("❌ Anchor not found")
    raise SystemExit(1)

# ─── Update the calls in index() to pass subqueries ───
old_calls = '''        featured_hotels = _cheapest_per_destination(Hotel, _hotel_price, limit=6)'''
new_calls = '''        featured_hotels = _cheapest_per_destination(Hotel, _hotel_price_subquery(), limit=6)'''
if old_calls in c:
    c = c.replace(old_calls, new_calls, 1)
    print("✅ Updated hotels call")

old_calls = '''        featured_packages = _cheapest_per_destination(Package, _package_price, limit=6)'''
new_calls = '''        featured_packages = _cheapest_per_destination(Package, _package_price_subquery(), limit=6)'''
if old_calls in c:
    c = c.replace(old_calls, new_calls, 1)
    print("✅ Updated packages call")

old_calls = '''        featured_activities = _cheapest_per_destination(Activity, _activity_price, limit=6)'''
new_calls = '''        featured_activities = _cheapest_per_destination(Activity, _activity_price_subquery(), limit=6)'''
if old_calls in c:
    c = c.replace(old_calls, new_calls, 1)
    print("✅ Updated activities call")

# ─── Remove old price helpers that are no longer needed ───
for old_helper in [
    '''def _hotel_price(obj):
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


''',
    '''def _package_price(obj):
    """Cheapest PackagePrice for a package, in float."""
    from sqlalchemy import func as _f
    row = db.session.scalar(
        select(_f.min(PackagePrice.adult_price)).where(
            PackagePrice.package_id == obj.id
        )
    )
    return float(row) if row else None


''',
    '''def _activity_price(obj):
    """Cheapest ActivityPrice for an activity, in float."""
    from sqlalchemy import func as _f
    row = db.session.scalar(
        select(_f.min(ActivityPrice.adult_price)).where(
            ActivityPrice.activity_id == obj.id
        )
    )
    return float(row) if row else None


''',
]:
    c = c.replace(old_helper, "", 1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print("✅ routes.py patched — single-query per section")

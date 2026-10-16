path = "services/search_service.py"
s = open(path, "r", encoding="utf-8").read()

old = '''def destinations_for_widget() -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(Destination)
        .where(Destination.is_bookable.is_(True))
        .order_by(Destination.name.asc())
    ).all()
    return [
        {"id": d.id, "name": d.name, "slug": d.slug, "country": d.country}
        for d in rows
    ]'''

new = '''def destinations_for_widget() -> list[dict[str, Any]]:
    """
    Return destinations that are (a) bookable and (b) have at least one
    active package. Used by the search widget dropdown so customers
    only see destinations they can actually book.
    """
    has_pkg = (
        select(Package.id)
        .where(Package.destination_id == Destination.id)
        .where(Package.is_active.is_(True))
        .correlate(Destination)
        .exists()
    )
    rows = db.session.scalars(
        select(Destination)
        .where(Destination.is_bookable.is_(True))
        .where(has_pkg)
        .order_by(Destination.name.asc())
    ).all()
    return [
        {"id": d.id, "name": d.name, "slug": d.slug, "country": d.country}
        for d in rows
    ]'''

assert old in s, "destinations_for_widget not found"
s = s.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(s)
print("destinations_for_widget patched")
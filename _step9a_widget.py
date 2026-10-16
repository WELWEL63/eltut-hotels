path = "services/search_service.py"
s = open(path, "r", encoding="utf-8").read()

# Roll back the widget function to its original behaviour
current = '''def destinations_for_widget() -> list[dict[str, Any]]:
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

original = '''def destinations_for_widget() -> list[dict[str, Any]]:
    """Return the list of destinations used by the search widget dropdown."""
    rows = db.session.scalars(
        select(Destination)
        .where(Destination.is_bookable.is_(True))
        .order_by(Destination.name.asc())
    ).all()
    return [
        {"id": d.id, "name": d.name, "slug": d.slug, "country": d.country}
        for d in rows
    ]


def destinations_for_package_widget() -> list[dict[str, Any]]:
    """
    Return only destinations that have at least one active package.
    Used by the package tab of the search widget so customers only
    see destinations they can actually book a package for.
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

assert current in s, "widget function not found"
s = s.replace(current, original, 1)

# Update __all__
s = s.replace(
    '__all__ = [\n    "search",\n    "destinations_for_widget",\n]',
    '__all__ = [\n    "search",\n    "destinations_for_widget",\n    "destinations_for_package_widget",\n]'
)

open(path, "w", encoding="utf-8").write(s)
print("widget functions updated")
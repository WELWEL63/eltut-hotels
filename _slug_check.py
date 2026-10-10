from app import create_app
app = create_app()
with app.app_context():
    from extensions import db
    from models import Package
    from sqlalchemy import select

    p = db.session.get(Package, 527)
    print(f"package 527 slug: {p.slug!r}")
    print(f"package 527 name: {p.name!r}")
    print()

    by_slug = db.session.scalars(
        select(Package).where(Package.slug == "amzing-redsea-pkg-0527")
    ).first()
    if by_slug:
        print(f"slug lookup found: id={by_slug.id} name={by_slug.name!r}")
    else:
        print("slug lookup: NOT FOUND — this is a different/incorrect slug")

    # Find any package with similar slug
    similar = db.session.scalars(
        select(Package).where(Package.slug.like("amzing%")).limit(5)
    ).all()
    print(f"\npackages with slug starting 'amzing':")
    for row in similar:
        print(f"  id={row.id} slug={row.slug!r}")

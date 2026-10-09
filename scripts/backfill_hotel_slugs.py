"""One-shot backfill: assign slugs to hotels that were created without them.

Run from the project root:
    python -m scripts.backfill_hotel_slugs
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path so `from app import create_app` works
# whether this is run as `python -m scripts.backfill_hotel_slugs` or
# `python scripts/backfill_hotel_slugs.py`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app import create_app  # noqa: E402

def main() -> None:
    app = create_app()
    with app.app_context():
        from extensions import db
        from models import Hotel
        from sqlalchemy import select
        try:
            from slugify import slugify  # type: ignore
        except ImportError:
            # Minimal fallback: lowercase, hyphenate non-alnum, collapse dashes
            import re as _re
            def slugify(text: str) -> str:  # type: ignore
                s = text.lower().strip()
                s = _re.sub(r"[^a-z0-9]+", "-", s)
                return s.strip("-")

        nulls = db.session.scalars(
            select(Hotel).where(Hotel.slug.is_(None)).order_by(Hotel.id)
        ).all()
        print(f"found {len(nulls)} rows needing slugs")
        if not nulls:
            print("nothing to do")
            return

        existing = set(db.session.scalars(
            select(Hotel.slug).where(Hotel.slug.is_not(None))
        ).all())
        print(f"existing unique slugs in DB: {len(existing)}")

        def make_unique_slug(name: str, hotel_id: int) -> str:
            base = (slugify(name) or "")[:180] or f"hotel-{hotel_id}"
            candidate = base
            n = 2
            while candidate in existing:
                candidate = f"{base}-{n}"
                n += 1
            existing.add(candidate)
            return candidate

        for h in nulls:
            h.slug = make_unique_slug(h.name, h.id)
            print(f"  id={h.id:4d}  {h.name!r:55s} -> {h.slug!r}")

        db.session.commit()
        print(f"\ncommitted {len(nulls)} slug assignments")

if __name__ == "__main__":
    main()

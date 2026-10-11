"""Seed CMS key: package_flights_max = 4 (admin-editable)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402

app = create_app()
with app.app_context():
    from services import content_service
    existing = content_service.get("package_flights_max")
    if existing:
        print(f"Already set: package_flights_max = {existing}")
    else:
        try:
            content_service.set_value(
                "package_flights_max",
                "4",
                page="global",
                content_type="text",
            )
        except TypeError:
            # If content_service.set_value signature differs, try positional
            content_service.set_value("package_flights_max", "4")
        db.session.commit()
        print("Set package_flights_max = 4")
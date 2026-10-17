"""
Backfill standard Egypt-hotel facilities into every hotel in the DB.

Run:
    python backfill_standard_facilities.py --dry-run
    python backfill_standard_facilities.py --commit
"""
import argparse
from app import create_app
from extensions import db
from models import Hotel, HotelFacility
from sqlalchemy import select


# (name, type) — type drives the icon shown on cards
STANDARD_FACILITIES = [
    # ── GENERAL ─────────────────────────────────────────────────
    ("24-hour reception & concierge",  "general"),
    ("Free high-speed Wi-Fi",          "business"),
    ("Outdoor swimming pool",          "general"),
    ("Sun terrace & loungers",         "general"),
    ("Free parking",                   "general"),
    ("Free shuttle transfer",          "general"),
    ("Wake-up call service",           "general"),
    ("Laundry & dry-cleaning service", "general"),
    ("Airport transfers (paid)",       "general"),
    ("Multilingual staff",             "general"),
    ("24/7 security & CCTV",           "general"),
    ("Currency exchange desk",         "business"),

    # ── DINING ──────────────────────────────────────────────────
    ("Multiple restaurants & bars",    "dining"),
    ("Buffet breakfast included",      "dining"),
    ("Poolside snack bar",             "dining"),
    ("Room service (24 hours)",        "dining"),
    ("À la carte dining",              "dining"),
    ("Vegetarian & halal options",     "dining"),

    # ── WELLNESS ────────────────────────────────────────────────
    ("Spa & wellness centre",          "wellness"),
    ("Massage & beauty treatments",    "wellness"),
    ("Sauna & steam room",             "wellness"),
    ("Jacuzzi",                        "wellness"),

    # ── SPORT ──────────────────────────────────────────────────
    ("Fitness centre",                 "sport"),
    ("Tennis court",                   "sport"),
    ("Table tennis",                   "sport"),
    ("Water sports (on site)",         "sport"),
    ("Diving centre",                  "sport"),

    # ── FAMILY ─────────────────────────────────────────────────
    ("Kids' club (ages 4–12)",         "family"),
    ("Children's pool",                "family"),
    ("Babysitting service (on request)", "family"),
    ("Family rooms available",         "family"),

    # ── BUSINESS ───────────────────────────────────────────────
    ("Business centre",                "business"),
    ("Meeting & conference rooms",     "business"),
    ("ATM on site",                    "business"),
    ("Bank services available",        "business"),

    # ── OTHER / ACCESSIBILITY ──────────────────────────────────
    ("Wheelchair accessible",          "other"),
    ("Non-smoking rooms",              "other"),
    ("Pet-friendly (on request)",      "other"),
    ("Gift shop",                      "other"),
    ("Tour & excursion desk",          "other"),
    ("Free Wi-Fi in public areas",     "other"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    if not args.dry_run and not args.commit:
        print("Pass --dry-run or --commit")
        return 1

    app = create_app()
    ctx = app.app_context()
    ctx.push()

    try:
        hotels = list(db.session.scalars(select(Hotel)))
        print(f"Total hotels: {len(hotels)}")

        total_added = 0
        hotels_touched = 0
        batch = 0

        for hotel in hotels:
            existing = db.session.scalars(
                select(HotelFacility).where(HotelFacility.hotel_id == hotel.id)
            ).all()
            existing_names = {f.name.lower() for f in existing}

            added = 0
            for name, type_ in STANDARD_FACILITIES:
                if name.lower() in existing_names:
                    continue
                if not args.dry_run:
                    db.session.add(HotelFacility(
                        hotel_id=hotel.id,
                        name=name,
                        type=type_,
                    ))
                added += 1

            if added > 0:
                hotels_touched += 1
                total_added += added
                batch += 1

                # Batch commits every 50 hotels to keep session small
                if not args.dry_run and batch % 50 == 0:
                    db.session.commit()
                    print(f"  ...committed {batch} hotels ({total_added} facilities so far)")

        print(f"Would add / added: {total_added} facilities across {hotels_touched} hotels")

        if args.commit:
            db.session.commit()
            print("COMMITTED")
        else:
            db.session.rollback()
            print("DRY-RUN — no changes written")
    finally:
        ctx.pop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
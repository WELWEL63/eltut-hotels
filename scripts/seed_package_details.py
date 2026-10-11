"""
scripts/seed_package_details.py
───────────────────────────────
Regenerate package content for all 18 consolidated packages:

  1. Delete all NULL-dated (flexible) price rows
  2. Delete all PackageOption rows
  3. Generate weekly dated price windows for 7 / 10 / 14 nights
     - Range: 2026-10-11 → 2027-10-11 (52 weeks)
     - Season-adjusted: Dec-Feb +25%, Jun-Aug +40%, others base
     - Duration multipliers: 7 nights=1.0, 10 nights=1.45, 14 nights=1.80
     - Child = adult x 0.70
  4. Rewrite description, itinerary, inclusions, exclusions per destination
  5. Build one PackageOption per (flight x duration) with fixed-price
     surcharges by airline + origin

All data lands in admin-editable tables:
  - package_prices
  - package_options
  - packages.description
  - package_itineraries
  - package_inclusions / package_exclusions

USAGE
    python scripts/seed_package_details.py --dry-run
    python scripts/seed_package_details.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    Package,
    PackagePrice,
    PackageOption,
    PackageItinerary,
    PackageInclusion,
    PackageExclusion,
    Flight,
)


# ─── Config ────────────────────────────────────────────────────────
START_DATE = date(2026, 10, 11)
END_DATE = date(2027, 10, 11)
WEEK_STEP = 7  # generate one window per week

DURATIONS = [7, 10, 14]  # nights

DURATION_MULT = {
    7: Decimal("1.00"),
    10: Decimal("1.45"),
    14: Decimal("1.80"),
}

CHILD_FACTOR = Decimal("0.70")

# Season multiplier by calendar month
def season_multiplier(d: date) -> Decimal:
    m = d.month
    if m in (12, 1, 2):
        return Decimal("1.25")  # peak winter
    if m in (6, 7, 8):
        return Decimal("1.40")  # summer holidays
    return Decimal("1.00")      # shoulder

# Airline fixed surcharges (adult, child)
AIRLINE_SURCHARGE = {
    "wizz air":  (Decimal("-30"), Decimal("-20")),
    "wizzair":   (Decimal("-30"), Decimal("-20")),
    "wizz":      (Decimal("-30"), Decimal("-20")),
    "easy jet":  (Decimal("0"),   Decimal("0")),
    "easyjet":   (Decimal("0"),   Decimal("0")),
    "tui":       (Decimal("80"),  Decimal("50")),
    "egypt air": (Decimal("150"), Decimal("100")),
    "egyptair":  (Decimal("150"), Decimal("100")),
}

# Origin airport premiums (adult)
ORIGIN_PREMIUM = {
    "london gatwick":  Decimal("0"),
    "london luton":    Decimal("0"),
    "manchester":      Decimal("0"),
    "glasgow":         Decimal("-20"),
    "birmingham":      Decimal("10"),
    "bristol":         Decimal("15"),
    "leeds bradford":  Decimal("20"),
    "london heathrow": Decimal("80"),
}


def _airline_surcharge(name: str | None) -> tuple[Decimal, Decimal]:
    if not name:
        return (Decimal("0"), Decimal("0"))
    key = name.strip().lower()
    # try exact then contains
    if key in AIRLINE_SURCHARGE:
        return AIRLINE_SURCHARGE[key]
    for k, v in AIRLINE_SURCHARGE.items():
        if k in key:
            return v
    return (Decimal("0"), Decimal("0"))


def _origin_premium(origin: str | None) -> Decimal:
    if not origin:
        return Decimal("0")
    key = origin.strip().lower()
    for k, v in ORIGIN_PREMIUM.items():
        if k in key:
            return v
    return Decimal("0")


def _round_eur(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ─── Content templates by destination ──────────────────────────────
DESCRIPTIONS = {
    "Nile Cruise": (
        "Sail the legendary Nile between Luxor and Aswan aboard a premium cruise ship. "
        "Discover the temples of Karnak and Luxor, the tombs of the Valley of the Kings, "
        "the twin sanctuaries of Kom Ombo and Edfu, and the beautiful island temple of "
        "Philae. Evenings are spent on deck with sunset views, Egyptian cuisine, and "
        "traditional entertainment. All meals, guided excursions, and transfers included."
    ),
    "Luxor": (
        "Luxor is the world's greatest open-air museum — home to the temples of Karnak "
        "and Luxor, the Valley of the Kings and Queens, and the mortuary temple of "
        "Hatshepsut. Stay in a hand-picked resort on the Nile's east bank, with easy "
        "access to the West Bank's archaeological treasures. Optional hot-air balloon "
        "rides at dawn offer unforgettable views over the Theban Necropolis."
    ),
    "Hurghada": (
        "Hurghada is Egypt's original Red Sea resort — a lively strip of beaches, dive "
        "centres, and marina-side restaurants. Snorkel or dive among pristine coral "
        "gardens at Giftun Island, take a desert safari with Bedouin dinner, or simply "
        "relax by the pool with a cocktail in hand. Ideal for families and water-sports "
        "enthusiasts alike."
    ),
    "Sharm El Sheikh": (
        "Sharm El Sheikh sits at the tip of the Sinai Peninsula, where the Red Sea's "
        "richest coral reefs meet year-round sunshine. Snorkel Ras Mohammed National "
        "Park, dive the legendary Thistlegorm wreck, or quad-bike through the desert "
        "at sunset. Naama Bay offers buzzing nightlife, while quieter bays deliver "
        "peaceful family-friendly resorts."
    ),
}

ITINERARIES = {
    "Nile Cruise": [
        ("Arrival in Luxor", "Meet-and-greet at Luxor Airport, transfer to your cruise ship, welcome drink, and dinner on board. Evening at leisure."),
        ("Luxor East Bank", "Visit Karnak Temple and Luxor Temple with your Egyptologist guide. Lunch and dinner on board."),
        ("Luxor West Bank", "Cross to the West Bank: Valley of the Kings, Temple of Hatshepsut, and the Colossi of Memnon. Sail to Esna overnight."),
        ("Edfu & Kom Ombo", "Sail to Edfu, visit the Temple of Horus. Continue to Kom Ombo for the twin temple of Sobek and Haroeris. Sail to Aswan overnight."),
        ("Aswan", "Visit the High Dam, the Unfinished Obelisk, and the Temple of Philae. Optional Nubian village excursion in the afternoon."),
        ("Aswan → Kom Ombo → Edfu", "Sail back north. Visit Kom Ombo and Edfu temples. Dinner and overnight on board."),
        ("Return to Luxor", "Breakfast on board, disembarkation, transfer to Luxor Airport for your return flight."),
    ],
    "Luxor": [
        ("Arrival", "Transfer from Luxor Airport to your resort. Check-in, welcome drink, evening at leisure."),
        ("Karnak & Luxor Temples", "Guided tour of the vast Karnak complex and the illuminated Luxor Temple by night."),
        ("Valley of the Kings", "Cross to the West Bank: three royal tombs, Temple of Hatshepsut, and the Colossi of Memnon."),
        ("Optional: Hot-air balloon", "Dawn hot-air balloon flight over the Theban Necropolis (optional, at extra cost). Afternoon free at the resort."),
        ("Dendera day trip", "Full-day excursion to the beautifully preserved Temple of Hathor at Dendera."),
        ("Free day", "Relax by the pool, explore the corniche, or shop in Luxor's bustling souk."),
        ("Departure", "Transfer back to Luxor Airport for your flight home."),
    ],
    "Hurghada": [
        ("Arrival", "Airport transfer, check-in, welcome cocktail. Evening at leisure."),
        ("Beach & pool day", "Enjoy the resort's private beach, pools, and water sports. Optional spa treatments."),
        ("Giftun Island snorkeling", "Full-day boat trip to Giftun Island with snorkeling stops, lunch on board, and dolphin spotting."),
        ("Desert safari", "Afternoon quad-bike safari into the Eastern Desert with Bedouin tea and a sunset BBQ dinner."),
        ("Free day", "Optional dive course, parasailing, or a day trip to Luxor by road or air."),
        ("Marina & old town", "Explore Hurghada Marina and the traditional old town (El Dahar) with its bazaar and seafood restaurants."),
        ("Departure", "Transfer to Hurghada Airport for your return flight."),
    ],
    "Sharm El Sheikh": [
        ("Arrival", "Airport transfer, check-in, welcome drink. Evening at leisure."),
        ("Naama Bay", "Full day at Naama Bay — beach, water sports, and its famous promenade lined with restaurants."),
        ("Ras Mohammed National Park", "Snorkeling and diving day trip to one of the world's finest marine parks."),
        ("Tiran Island cruise", "Full-day boat trip to Tiran Island with three snorkeling stops and lunch on board."),
        ("Desert quad-bike safari", "Sunset quad-bike ride through the Sinai desert with Bedouin dinner and stargazing."),
        ("Free day", "Relax by the pool, book a massage, or take an optional day trip to St Catherine's Monastery."),
        ("Departure", "Transfer to Sharm El Sheikh Airport for your flight home."),
    ],
}

INCLUSIONS = {
    "Nile Cruise": [
        "Return flights from the UK",
        "Airport transfers in Egypt",
        "7 nights on board a 5-star Nile cruise ship",
        "Full board (breakfast, lunch, dinner)",
        "All guided excursions with Egyptologist",
        "Entrance fees to all listed sites",
        "English-speaking tour leader",
    ],
    "Luxor": [
        "Return flights from the UK",
        "Airport transfers in Egypt",
        "7 nights in a 5-star Nile-view resort",
        "Daily breakfast, half-board dinner",
        "Guided West Bank & East Bank tours",
        "Entrance fees to all listed sites",
    ],
    "Hurghada": [
        "Return flights from the UK",
        "Airport transfers in Egypt",
        "7 nights all-inclusive resort",
        "All meals, snacks, and local drinks",
        "One full-day boat trip with snorkeling",
        "One desert safari with BBQ dinner",
        "Use of all resort facilities",
    ],
    "Sharm El Sheikh": [
        "Return flights from the UK",
        "Airport transfers in Egypt",
        "7 nights all-inclusive resort",
        "All meals, snacks, and local drinks",
        "One Ras Mohammed snorkeling day trip",
        "One Tiran Island boat trip with lunch",
        "Use of all resort facilities",
    ],
}

EXCLUSIONS = {
    "Nile Cruise": [
        "Personal expenses and souvenirs",
        "Tips and gratuities",
        "Travel insurance",
        "Optional excursions (Nubian village, Abu Simbel)",
        "Beverages outside of meal times",
    ],
    "Luxor": [
        "Personal expenses and souvenirs",
        "Tips and gratuities",
        "Travel insurance",
        "Optional hot-air balloon flight",
        "Lunches and alcoholic drinks",
    ],
    "Hurghada": [
        "Personal expenses and souvenirs",
        "Tips and gratuities",
        "Travel insurance",
        "Optional dive courses",
        "Premium imported drinks",
    ],
    "Sharm El Sheikh": [
        "Personal expenses and souvenirs",
        "Tips and gratuities",
        "Travel insurance",
        "Optional day trips",
        "Premium imported drinks",
    ],
}


def _dest_key(name: str | None) -> str:
    if not name:
        return "Luxor"
    for k in DESCRIPTIONS:
        if k.lower() in name.lower():
            return k
    return "Luxor"


def _base_price(package: Package) -> Decimal:
    """Cheapest flexible price from current DB rows, or default €700."""
    row = db.session.query(PackagePrice).filter_by(package_id=package.id)\
        .filter(PackagePrice.valid_from.is_(None))\
        .order_by(PackagePrice.adult_price.asc()).first()
    if row and row.adult_price:
        return Decimal(str(row.adult_price))
    # fallback: cheapest dated
    row = db.session.query(PackagePrice).filter_by(package_id=package.id)\
        .order_by(PackagePrice.adult_price.asc()).first()
    if row and row.adult_price:
        return Decimal(str(row.adult_price))
    return Decimal("700")


def _weekly_dates():
    """Yield every 7th day from START_DATE to END_DATE (inclusive)."""
    d = START_DATE
    while d <= END_DATE:
        yield d
        d = d + timedelta(days=WEEK_STEP)


def seed(dry_run: bool) -> int:
    app = create_app()
    with app.app_context():
        packages = db.session.query(Package).order_by(Package.id).all()
        print(f"Packages to process: {len(packages)}")

        total_prices_added = 0
        total_options_added = 0

        for p in packages:
            base = _base_price(p)
            dest_key = _dest_key(p.name)

            print(f"\n--- Package {p.id}: {p.name[:60]} | base={base} | dest_key={dest_key}")

            if not dry_run:
                # 1) Delete all current prices + options for this package
                db.session.query(PackagePrice).filter_by(package_id=p.id).delete()
                db.session.query(PackageOption).filter_by(package_id=p.id).delete()
                # Clear itinerary + inclusions + exclusions to rewrite
                db.session.query(PackageItinerary).filter_by(package_id=p.id).delete()
                db.session.query(PackageInclusion).filter_by(package_id=p.id).delete()
                db.session.query(PackageExclusion).filter_by(package_id=p.id).delete()

                # 2) Description
                p.description = DESCRIPTIONS[dest_key]

                # 3) Itinerary
                for i, (title, desc) in enumerate(ITINERARIES[dest_key], start=1):
                    db.session.add(PackageItinerary(
                        package_id=p.id,
                        day_number=i,
                        title=title,
                        description=desc,
                    ))

                # 4) Inclusions
                for i, item in enumerate(INCLUSIONS[dest_key], start=1):
                    db.session.add(PackageInclusion(
                        package_id=p.id,
                        item=item,
                        sort_order=i,
                    ))

                # 5) Exclusions
                for i, item in enumerate(EXCLUSIONS[dest_key], start=1):
                    db.session.add(PackageExclusion(
                        package_id=p.id,
                        item=item,
                        sort_order=i,
                    ))

            # 6) Generate weekly price windows
            price_rows_created = 0
            for day in _weekly_dates():
                season = season_multiplier(day)
                for nights in DURATIONS:
                    adult = _round_eur(base * DURATION_MULT[nights] * season)
                    child = _round_eur(adult * CHILD_FACTOR)
                    if not dry_run:
                        db.session.add(PackagePrice(
                            package_id=p.id,
                            adult_price=adult,
                            child_price=child,
                            currency="EUR",
                            valid_from=day,
                            valid_to=day + timedelta(days=nights),
                        ))
                    price_rows_created += 1

            total_prices_added += price_rows_created
            print(f"  price windows: {price_rows_created}")

            # 7) Create one PackageOption per flight x duration
            #    (uses each flight's surcharge + origin premium on top of the cheapest 7n base)
            flights = db.session.query(Flight).filter_by(package_id=p.id).all()
            options_created = 0
            base_7n = _round_eur(base)
            for f in flights:
                airline_sur_adult, airline_sur_child = _airline_surcharge(f.airline_name)
                origin_prem = _origin_premium(f.flight_from)
                for nights in DURATIONS:
                    # Use a mid-window price for reference
                    ref_adult = _round_eur(
                        base * DURATION_MULT[nights] * Decimal("1.10")
                        + airline_sur_adult + origin_prem
                    )
                    ref_child = _round_eur(ref_adult * CHILD_FACTOR + airline_sur_child)
                    if not dry_run:
                        db.session.add(PackageOption(
                            package_id=p.id,
                            flight_id=f.id,
                            price_id=None,
                            room_id=p.room_id,
                            departure_date=None,
                            return_date=None,
                            label=f"{f.airline_name or 'Flight'} · {f.flight_from or '?'} → {f.flight_to or '?'} ({nights}n)",
                            is_active=True,
                            sort_order=options_created,
                        ))
                    options_created += 1
            total_options_added += options_created
            print(f"  flight options: {options_created}")

        if not dry_run:
            db.session.commit()
            print("\n=== COMMITTED ===")
        else:
            print("\n=== DRY RUN (nothing committed) ===")

        print(f"Total price windows created: {total_prices_added}")
        print(f"Total flight options created: {total_options_added}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return seed(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
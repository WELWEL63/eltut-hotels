"""
_enrich_261.py - Enrich hotel 261 with realistic full data.
v2: Uses only types allowed by the DB CHECK constraint:
    ('general', 'wellness', 'dining', 'sport', 'family', 'business', 'other')
Idempotent: safe to re-run.
"""
from decimal import Decimal

from sqlalchemy import select, func
from app import create_app
from extensions import db
from models.hotel import Hotel, HotelFacility, HotelImage
from models.room import Room


app = create_app()
HOTEL_ID = 261

HOTEL_DATA = {
    "address": "Corniche Road, Touristic Village, Hurghada 84511, Red Sea, Egypt",
    "latitude": Decimal("27.257900"),
    "longitude": Decimal("33.811600"),
    "check_in_time": "14:00",
    "check_out_time": "12:00",
    "description": (
        "A boutique tribute to classic Egyptian hospitality, 1001 Nights - "
        "Alf Leila Wa Leila blends Arabian-Nights charm with modern Red Sea "
        "comfort. Set along the Corniche with direct beach access, the resort "
        "offers three pools, four restaurants, a full-service spa, and an "
        "aqua park for families. Every room opens to either garden or sea "
        "views, and the resort's famous evening folklore show is included "
        "free for all guests."
    ),
    "useful_tips": (
        "- Beach towels are provided free at the pool desk.\n"
        "- The a la carte Egyptian restaurant fills up fast - book by 10 AM.\n"
        "- Shuttle to Hurghada Airport departs every 90 minutes (free).\n"
        "- Bring water shoes - the house reef has some coral."
    ),
    "house_rules": (
        "Check-in from 14:00 / Check-out before 12:00.\n"
        "Children under 6 stay free when sharing with two adults.\n"
        "Pets are not permitted.\n"
        "Quiet hours: 22:00 - 08:00.\n"
        "Smoking permitted only in designated outdoor areas."
    ),
    "check_in_details": (
        "Please present your passport and booking reference at reception. "
        "A pre-authorisation of USD 50 per night is taken on arrival for "
        "incidentals and released within 5 working days of departure."
    ),
    "cancellation_policy": (
        "Free cancellation up to 48 hours before check-in. "
        "Cancellations within 48 hours are charged the first night's stay. "
        "No-shows are charged the full booking amount."
    ),
    "neighborhood_info": (
        "The resort is on the Hurghada Corniche, 10 minutes from the marina "
        "and 15 minutes from Hurghada International Airport. The Old Town "
        "(El Dahar) with its bazaar is 20 minutes by taxi. Giftun Island "
        "ferries leave from the marina at 09:00 daily."
    ),
    "google_maps_url": (
        "https://www.google.com/maps/search/?api=1&query=27.257900,33.811600"
    ),
}

# v2: 'service' is NOT allowed -> used 'business' and 'other' instead
NEW_FACILITIES = [
    {"name": "Swimming Pool",   "type": "general",  "quantity": 3,    "notes": "Heated in winter"},
    {"name": "Restaurant",      "type": "dining",   "quantity": 4,    "notes": "Buffet + a la carte"},
    {"name": "Bar / Lounge",    "type": "dining",   "quantity": 2,    "notes": "Beach bar + lobby bar"},
    {"name": "Spa & Wellness",  "type": "wellness", "quantity": 1,    "notes": "Massage, hammam, sauna"},
    {"name": "Free WiFi",       "type": "business", "quantity": None, "notes": "All rooms + public areas"},
    {"name": "Airport Shuttle", "type": "other",    "quantity": None, "notes": "Free, every 90 minutes"},
]

NEW_IMAGES = [
    {"filename": "a4f4280305a7147abadea461bddc489c4b98e613.png", "type": "hero",       "sort_order": 10},
    {"filename": "7567d2c2b07d965e75a341728f9387ff532f6927.png", "type": "room",       "sort_order": 20},
    {"filename": "1e6bd8a0ae247585e7f40d614a43c900fd6de7ca.jpg", "type": "pool",       "sort_order": 30},
    {"filename": "c2b8d29d6109a4650ce3c84da518f34d80e2211a.jpg", "type": "beach",      "sort_order": 40},
    {"filename": "43fae623ff97ff4032ecad5bcfd645260cbaa5f1.jpg", "type": "restaurant", "sort_order": 50},
    {"filename": "485bdb809fcdb406ea7e45c00e7d97744901e62c.jpg", "type": "spa",        "sort_order": 60},
    {"filename": "20bc9b21096522350fe26d8c72bd39ec40404f6a.png", "type": "exterior",   "sort_order": 70},
]


with app.app_context():
    h = db.session.get(Hotel, HOTEL_ID)
    if not h:
        print(f"ERROR: Hotel {HOTEL_ID} not found")
        raise SystemExit(1)

    print(f"Enriching hotel {HOTEL_ID}: {h.name!r}")
    print()

    # 1. Update core fields
    changed = []
    for field, value in HOTEL_DATA.items():
        if getattr(h, field) != value:
            setattr(h, field, value)
            changed.append(field)

    # 2. Fix total_capacity to match real room count
    room_count = db.session.scalar(
        select(func.count(Room.id)).where(Room.hotel_id == h.id)
    ) or 1
    if h.total_capacity != room_count:
        h.total_capacity = room_count
        changed.append("total_capacity")

    print(f"[1] Core fields updated: {len(changed)}")
    for f in changed:
        print(f"     - {f}")

    # 3. Add facilities (skip if name exists)
    existing_names = {
        f.name for f in db.session.scalars(
            select(HotelFacility).where(HotelFacility.hotel_id == h.id)
        ).all()
    }
    added_fac = []
    for fdata in NEW_FACILITIES:
        if fdata["name"] in existing_names:
            continue
        fac = HotelFacility(
            hotel_id=h.id,
            name=fdata["name"],
            type=fdata["type"],
            quantity=fdata.get("quantity"),
            notes=fdata.get("notes"),
        )
        db.session.add(fac)
        added_fac.append(f"{fdata['name']} ({fdata['type']})")

    print()
    print(f"[2] Facilities added: {len(added_fac)}")
    for n in added_fac:
        print(f"     + {n}")

    # 4. Add images (skip if URL exists)
    existing_urls = {
        im.url for im in db.session.scalars(
            select(HotelImage).where(HotelImage.hotel_id == h.id)
        ).all()
    }
    added_img = []
    for imdata in NEW_IMAGES:
        url = f"/static/images/uploads/{imdata['filename']}"
        if url in existing_urls:
            continue
        img = HotelImage(
            hotel_id=h.id,
            url=url,
            type=imdata["type"],
            sort_order=imdata["sort_order"],
            media_type="image",
        )
        db.session.add(img)
        added_img.append(imdata["filename"][:20] + "...")

    print()
    print(f"[3] Images added: {len(added_img)}")
    for n in added_img:
        print(f"     + {n}")

    # 5. Commit
    db.session.commit()

    print()
    print("=" * 60)
    print("DONE. Hotel 261 is now fully enriched.")
    print("=" * 60)

"""
scripts/seed_from_csv.py
────────────────────────
Populate the SQL database from the three CSVs in data/.

Files consumed:
    data/egypttrips.csv         activities + prices + images + lists
    data/Egypt.csv              hotels + rooms + facilities + images
    data/Egypt-Packages.csv     packages + prices + flights + itineraries
                                + images + inclusions + exclusions

WHAT IS CREATED
    destinations    (derived from CSV strings, one per unique value)
    guides          (derived from "Tour Guide" strings)
    suppliers       (derived from "flights_name" strings)
    activities      + activity_prices, activity_images,
                      activity_inclusions, activity_exclusions,
                      activity_languages
    hotels          + hotel_facilities, hotel_images
    rooms           + room_images
    packages        + package_prices, package_images, package_inclusions,
                      package_exclusions, package_itineraries, flights

USAGE
    python -m scripts.seed_from_csv                 # seed all three
    python -m scripts.seed_from_csv --file trips    # only egypttrips.csv
    python -m scripts.seed_from_csv --file hotels   # only Egypt.csv
    python -m scripts.seed_from_csv --file packages # only Egypt-Packages.csv
    python -m scripts.seed_from_csv --dry-run       # parse but do not commit

IDEMPOTENCY
    Each CSV's rows are keyed by their natural business identifier
    (activity code, hotel_id, room_type_id, package code). Re-running
    the script will UPDATE existing rows rather than duplicate them.

UNIQUE-NAME STRATEGY
    Real CSVs contain duplicate marketing names across different
    business codes (e.g. two activities called "Cairo By Air"). Our
    `activities.name` and `packages.name` columns are UNIQUE, so the
    seeder disambiguates with _unique_activity_name() and
    _unique_package_name():

        1. Use the plain name if free or owned by the same code.
        2. Suffix with the destination:  "Cairo By Air — Hurghada".
        3. Suffix with the code:         "Cairo By Air (TRIP067)".
        4. Both as a last resort.

    Blank rows (empty Trip ID and empty Trip Name) are skipped entirely.
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import create_app
from extensions import db
from models import (
    Activity,
    ActivityExclusion,
    ActivityImage,
    ActivityInclusion,
    ActivityLanguage,
    ActivityPrice,
    Destination,
    Flight,
    Guide,
    Hotel,
    HotelFacility,
    HotelImage,
    Package,
    PackageExclusion,
    PackageImage,
    PackageInclusion,
    PackageItinerary,
    PackagePrice,
    Room,
    RoomImage,
    RoomRate,
    Supplier,
)


# ─── Paths & logging ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

TRIPS_CSV = DATA_DIR / "egypttrips.csv"
HOTELS_CSV = DATA_DIR / "Egypt.csv"
PACKAGES_CSV = DATA_DIR / "Egypt-Packages.csv"


log = logging.getLogger("seed")


def _configure_seed_logging() -> None:
    """
    Configure the seed logger exactly once, with a single handler.

    Called lazily after Flask's own logging is set up. Without this
    guard, both the root logger and Flask's handler would emit each
    message (visible as duplicated log lines).
    """
    if log.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


# ─── Generic parsing helpers ───────────────────────────────────────
PLACEHOLDER_TOKENS = {
    "", "picture", "url", "n/a", "na", "none", "null", "tbd",
}


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    v = value.strip().lower()
    if v in PLACEHOLDER_TOKENS:
        return True
    if re.fullmatch(r"url\d+", v):
        return True
    return False


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.replace("\r", " ").replace("\n", " ")
    v = re.sub(r"\s+", " ", v).strip()
    if not v or v.lower() in PLACEHOLDER_TOKENS:
        return None
    return v


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [p.strip(" .;") for p in re.split(r"[,\n]", value)]
    return [p for p in parts if p and p.lower() not in PLACEHOLDER_TOKENS]


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    v = str(value).strip().replace(",", "")
    v = re.sub(r"[^0-9.\-]", "", v)
    if not v:
        return None
    try:
        return Decimal(v)
    except (InvalidOperation, ValueError):
        return None


_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y")


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    v = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _duration_to_hours(value: str | None) -> Decimal:
    if not value:
        return Decimal("1.00")
    v = value.strip().lower()
    if "half" in v:
        return Decimal("4.00")
    if "full" in v:
        return Decimal("8.00")
    m = re.search(r"(\d+(?:\.\d+)?)", v)
    if m:
        return Decimal(m.group(1))
    return Decimal("1.00")


def _age_range(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return (None, None)
    m = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", value)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.search(r"(\d+)\s*\+", value)
    if m:
        return (int(m.group(1)), None)
    return (None, None)


# ─── Enum mapping helpers ──────────────────────────────────────────
_DIFFICULTY_MAP = {
    "easy": "easy",
    "moderate": "moderate",
    "challenging": "challenging",
    "hard": "challenging",
    "difficult": "challenging",
}

_CATEGORY_TOKENS = (
    ("history", "history"),
    ("adventure", "adventure"),
    ("cultural", "cultural"),
    ("water", "water"),
    ("desert", "desert"),
    ("food", "food"),
)

_TRANSPORT_TOKENS = ("bus", "car", "boat", "walking", "flight")

_MEAL_TOKENS = (
    ("all inclusive", "all_inclusive"),
    ("all-inclusive", "all_inclusive"),
    ("full board", "full_board"),
    ("half board", "half_board"),
    ("half-board", "half_board"),
    ("breakfast", "breakfast"),
    ("lunch", "half_board"),
    ("dinner", "half_board"),
    ("room only", "room_only"),
)

_MEAL_CODE_MAP = {
    "bb": "breakfast",
    "hb": "half_board",
    "fb": "full_board",
    "ai": "all_inclusive",
    "ro": "room_only",
}

_IMAGE_COLUMN = re.compile(r"hotelpicture\s*(\d+)", re.IGNORECASE)
_DAY_COLUMN = re.compile(r"^Day\s+(\d+)\s+Itinerary$", re.IGNORECASE)


def _pick_category(value: str | None) -> str:
    v = (value or "").lower()
    for token, mapped in _CATEGORY_TOKENS:
        if token in v:
            return mapped
    return "other"


def _pick_difficulty(value: str | None) -> str:
    return _DIFFICULTY_MAP.get((value or "").lower().strip(), "easy")


def _pick_transport(value: str | None) -> str:
    v = (value or "").lower()
    for token in _TRANSPORT_TOKENS:
        if token in v:
            return token
    return "none"


def _pick_meals(value: str | None) -> str:
    v = (value or "").lower()
    for token, mapped in _MEAL_TOKENS:
        if token in v:
            return mapped
    return "none"


def _pick_meal_code(value: str | None) -> str:
    return _MEAL_CODE_MAP.get((value or "").strip().lower(), "room_only")


# ─── CSV loading ───────────────────────────────────────────────────
def _read_csv(path: Path, encoding: str) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open("r", encoding=encoding, newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return []
    out: list[dict[str, str]] = []
    with path.open("r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            out.append({k: (raw.get(k, "") or "") for k in header})
    return out




# ─── Lookup caches (avoid thousands of DB round-trips) ─────────────
class _LookupCache:
    """
    In-memory set + dict cache for slug/name lookups during seeding.

    The seeder can insert hundreds of hotels and thousands of rooms in
    one run. Doing a SELECT for every one is slow over the network — the
    cache pre-loads existing values ONCE, then answers subsequent lookups
    in O(1) with no DB round-trip.

    New rows are added to the cache at insert time so subsequent rows
    find them without a re-query.
    """

    def __init__(self, session, model, key_attr: str):
        self.session = session
        self.model = model
        self.key_attr = key_attr
        col = getattr(model, key_attr)
        self.map: dict = {
            getattr(r, key_attr): r
            for r in session.scalars(select(model))
        }
        if key_attr != "slug":
            # also build a slug index for slug-based lookups
            self.by_slug: dict = {
                getattr(r, "slug"): r for r in self.map.values()
                if getattr(r, "slug", None)
            }
        else:
            self.by_slug = self.map

    def get(self, key):
        return self.map.get(key)

    def get_by_slug(self, slug):
        return self.by_slug.get(slug)

    def add(self, obj) -> None:
        self.map[getattr(obj, self.key_attr)] = obj
        if getattr(obj, "slug", None):
            self.by_slug[obj.slug] = obj

# ─── Name-collision helpers ────────────────────────────────────────
def _unique_activity_name(
    session: Session, *, name: str, code: str, destination_name: str
) -> str:
    """
    Return an activity name that does not collide with a different code.

    Fallback ladder:
        1. name                                (if free or owned by code)
        2. "<name> — <destination>"
        3. "<name> (<code>)"
        4. "<name> (<code>-<destination>)"
    """
    existing = session.scalar(select(Activity).where(Activity.name == name))
    if existing is None or existing.code == code:
        return name

    candidate = f"{name} — {destination_name}"
    existing = session.scalar(select(Activity).where(Activity.name == candidate))
    if existing is None or existing.code == code:
        return candidate

    candidate = f"{name} ({code})"
    existing = session.scalar(select(Activity).where(Activity.name == candidate))
    if existing is None or existing.code == code:
        return candidate

    return f"{name} ({code}-{destination_name})"


def _unique_package_name(
    session: Session, *, name: str, code: str, destination_name: str
) -> str:
    """Same strategy for packages."""
    existing = session.scalar(select(Package).where(Package.name == name))
    if existing is None or existing.code == code:
        return name

    candidate = f"{name} — {destination_name}"
    existing = session.scalar(select(Package).where(Package.name == candidate))
    if existing is None or existing.code == code:
        return candidate

    candidate = f"{name} ({code})"
    existing = session.scalar(select(Package).where(Package.name == candidate))
    if existing is None or existing.code == code:
        return candidate

    return f"{name} ({code}-{destination_name})"


# ─── Destination / Guide / Supplier helpers ────────────────────────
def _get_or_create_destination(
    session: Session, name: str | None, cache: "_LookupCache | None" = None
) -> Destination | None:
    """
    Find or create a destination, MATCHING BY SLUG (case-insensitive,
    hyphen-normalised) so that "Sharm El Sheikh" and "Sharm el Sheikh"
    resolve to the same row.

    If a cache is provided, lookups and inserts use the cache instead of
    issuing a DB query per call — this makes bulk seeding 100x faster
    over a networked database.
    """
    if not name:
        return None
    cleaned = re.sub(r"\s*[-–]\s*[A-Za-z]+\s*$", "", name).strip()
    if not cleaned:
        return None

    slug = Destination._generate_slug(cleaned)
    if not slug:
        return None

    # Fast path: cache
    if cache is not None:
        hit = cache.get_by_slug(slug)
        if hit is not None:
            return hit

    # Slow path: DB lookup
    existing = session.scalar(select(Destination).where(Destination.slug == slug))
    if existing:
        if cache is not None:
            cache.add(existing)
        return existing

    existing = session.scalar(select(Destination).where(Destination.name == cleaned))
    if existing:
        if cache is not None:
            cache.add(existing)
        return existing

    dest = Destination(
        name=cleaned,
        slug=Destination._generate_unique_slug(cleaned, session),
        country="Egypt",
    )
    session.add(dest)
    session.flush()
    if cache is not None:
        cache.add(dest)
    log.info("  + destination: %s", cleaned)
    return dest


def _get_or_create_guide(session: Session, raw_name: str | None) -> Guide | None:
    cleaned = _clean(raw_name)
    if not cleaned:
        return None
    name = cleaned.split(" - ", 1)[0].strip()
    existing = session.scalar(select(Guide).where(Guide.full_name == name))
    if existing:
        return existing
    base = re.sub(r"[^A-Za-z0-9]+", "-", name.upper()).strip("-")
    licence = f"EG-{base[:20] or 'GUIDE'}-001"
    suffix = 1
    while session.scalar(select(Guide).where(Guide.licence_number == licence)):
        suffix += 1
        licence = f"EG-{base[:20] or 'GUIDE'}-{suffix:03d}"
    guide = Guide(
        full_name=name, licence_number=licence, languages=["English"], is_active=True
    )
    session.add(guide)
    session.flush()
    log.info("  + guide: %s (%s)", name, licence)
    return guide


def _get_or_create_supplier(
    session: Session, raw_name: str | None, supplier_type: str = "airline"
) -> Supplier | None:
    cleaned = _clean(raw_name)
    if not cleaned:
        return None
    existing = session.scalar(select(Supplier).where(Supplier.name == cleaned))
    if existing:
        return existing
    supplier = Supplier(name=cleaned, type=supplier_type, is_active=True)
    session.add(supplier)
    session.flush()
    log.info("  + supplier: %s (%s)", cleaned, supplier_type)
    return supplier


# ─── Seeder: activities ────────────────────────────────────────────
def seed_activities(session: Session, rows: list[dict[str, str]]) -> int:
    log.info("Seeding %d activities ...", len(rows))
    created = 0
    skipped = 0

    for i, row in enumerate(rows, start=1):
        # Skip fully-blank rows (trailing lines in the CSV).
        if not (row.get("Trip ID", "").strip() or row.get("Trip Name", "").strip()):
            skipped += 1
            continue

        code = _clean(row.get("Trip ID")) or f"ACT-{i:04d}"
        name = _clean(row.get("Trip Name")) or f"Activity {i}"
        destination = _get_or_create_destination(session, row.get("Destination"))
        if destination is None:
            log.warning("  row %d: no destination, skipping activity %s", i, code)
            continue

        guide = _get_or_create_guide(session, row.get("Tour Guide"))

        activity = session.scalar(select(Activity).where(Activity.code == code))
        if activity is None:
            unique_name = _unique_activity_name(
                session,
                name=name,
                code=code,
                destination_name=destination.name,
            )
            activity = Activity(
                code=code, name=unique_name, destination_id=destination.id
            )
            session.add(activity)
            created += 1

        # Scalar fields
        activity.name = activity.name or name
        activity.slug = Activity._generate_unique_slug(
            activity.name, session
        )
        activity.destination_id = destination.id
        activity.guide_id = guide.id if guide else None
        activity.category = _pick_category(row.get("Trip Category"))
        activity.description = _clean(row.get("Description"))
        activity.duration_hours = _duration_to_hours(row.get("Duration"))
        activity.difficulty = _pick_difficulty(row.get("Trip Difficulty"))
        min_age, max_age = _age_range(row.get("Age Restrictions"))
        activity.min_age = min_age
        activity.max_age = max_age
        activity.schedule = _clean(row.get("Trip Schedule"))
        activity.meeting_point = _clean(row.get("Meeting Point"))
        activity.departure_time = _clean(row.get("Departure Time"))
        activity.return_time = _clean(row.get("Return Time"))
        activity.capacity = _to_int(row.get("Available Spots")) or 10
        activity.transportation_type = _pick_transport(row.get("Transportation Type"))
        activity.meals_included = _pick_meals(row.get("Meals Included"))
        activity.what_to_bring = _clean(row.get("What to Bring"))
        activity.cancellation_policy = _clean(row.get("Cancellation Policy"))
        activity.accessibility = _clean(row.get("Accessibility"))
        activity.special_offers = _clean(row.get("Special Offers"))
        activity.is_active = True

        session.flush()

        # Prices (one row per activity)
        adult = _to_decimal(row.get("Price Adult"))
        child = _to_decimal(row.get("Price Child"))
        if adult is not None and not session.scalar(
            select(ActivityPrice).where(ActivityPrice.activity_id == activity.id)
        ):
            session.add(
                ActivityPrice(
                    activity_id=activity.id,
                    adult_price=adult,
                    child_price=child or Decimal("0.00"),
                    currency="USD",
                )
            )

        # Image
        photo = _clean(row.get("Photo URL"))
        if photo and not _is_placeholder(photo) and not session.scalar(
            select(ActivityImage).where(
                ActivityImage.activity_id == activity.id,
                ActivityImage.url == photo,
            )
        ):
            session.add(
                ActivityImage(activity_id=activity.id, url=photo, sort_order=0)
            )

        # Inclusions / exclusions
        existing_inc = {
            r.item for r in session.scalars(
                select(ActivityInclusion).where(
                    ActivityInclusion.activity_id == activity.id
                )
            )
        }
        for idx, item in enumerate(_split_list(row.get("Included in Price"))):
            if item not in existing_inc:
                session.add(
                    ActivityInclusion(
                        activity_id=activity.id, item=item, sort_order=idx
                    )
                )
        existing_exc = {
            r.item for r in session.scalars(
                select(ActivityExclusion).where(
                    ActivityExclusion.activity_id == activity.id
                )
            )
        }
        for idx, item in enumerate(_split_list(row.get("Not Included"))):
            if item not in existing_exc:
                session.add(
                    ActivityExclusion(
                        activity_id=activity.id, item=item, sort_order=idx
                    )
                )

        # Languages
        existing_lang = {
            r.language for r in session.scalars(
                select(ActivityLanguage).where(
                    ActivityLanguage.activity_id == activity.id
                )
            )
        }
        for lang in _split_list(row.get("Languages Available")):
            if lang not in existing_lang:
                session.add(
                    ActivityLanguage(activity_id=activity.id, language=lang)
                )

        if i % 10 == 0:
            session.flush()
            log.info("  ...%d/%d", i, len(rows))

    session.flush()
    if skipped:
        log.info("  skipped %d blank rows", skipped)
    return created


# ─── Seeder: hotels ────────────────────────────────────────────────
def seed_hotels(session: Session, rows: list[dict[str, str]]) -> int:
    log.info("Seeding hotels from %d rate rows ...", len(rows))

    # Pre-load lookup tables ONCE — the hot loop below uses these caches
    # instead of issuing a DB query per row. This makes the seed 100x
    # faster over a networked database (Neon auto-suspends + Frankfurt
    # round-trips add up fast).
    dest_cache = _LookupCache(session, Destination, "slug")
    hotel_cache = _LookupCache(session, Hotel, "name")
    room_cache: dict[tuple[int, str], Room] = {
        (r.hotel_id, r.type): r for r in session.scalars(select(Room))
    }

    log.info(
        "  caches: %d destinations, %d hotels, %d rooms",
        len(dest_cache.map), len(hotel_cache.map), len(room_cache),
    )

    hotels_by_ext: dict[str, dict[str, Any]] = {}
    for row in rows:
        hid = _clean(row.get("HotelId"))
        if not hid:
            continue
        if hid not in hotels_by_ext:
            hotels_by_ext[hid] = {"rows": [], "first": row}
        hotels_by_ext[hid]["rows"].append(row)

    created = 0
    for i, (hid, bundle) in enumerate(hotels_by_ext.items(), start=1):
        first = bundle["first"]
        hname = _clean(first.get("HotelName")) or f"Hotel {hid}"
        destination = _get_or_create_destination(
            session, first.get("RegionName"), cache=dest_cache
        )
        if destination is None:
            log.warning("  hotel %s: no destination, skipping", hid)
            continue

        hotel = hotel_cache.get(hname)
        if hotel is None:
            hotel = Hotel(name=hname, destination_id=destination.id)
            session.add(hotel)
            session.flush()
            hotel_cache.add(hotel)
            created += 1

        hotel.slug = Hotel._generate_unique_slug(hname, session)
        hotel.destination_id = destination.id
        hotel.stars = _to_int(first.get("HotelStarRating")) or 3
        hotel.address = _clean(first.get("location"))
        hotel.description = _clean(first.get("HotelInfo"))
        hotel.total_capacity = hotel.total_capacity or 20
        hotel.is_active = True

        amenities_raw = _clean(first.get("Amenities")) or ""
        existing_fac = {
            f.name for f in session.scalars(
                select(HotelFacility).where(HotelFacility.hotel_id == hotel.id)
            )
        }
        for token in re.split(r"[,&]| and ", amenities_raw):
            token = token.strip()
            if token and token not in existing_fac:
                session.add(
                    HotelFacility(
                        hotel_id=hotel.id, name=token.title(), type="general"
                    )
                )

        existing_urls = {
            img.url for img in session.scalars(
                select(HotelImage).where(HotelImage.hotel_id == hotel.id)
            )
        }
        sort = 0
        for key, val in first.items():
            if _IMAGE_COLUMN.match(key):
                url = _clean(val)
                if url and not _is_placeholder(url) and url not in existing_urls:
                    session.add(
                        HotelImage(
                            hotel_id=hotel.id,
                            url=url,
                            type="exterior",
                            sort_order=sort,
                        )
                    )
                    existing_urls.add(url)
                    sort += 1

        # Preload existing rate keys for this hotel so re-runs are idempotent
        existing_rate_keys: set = set()
        for existing_room in [r for r in room_cache.values() if r.hotel_id == hotel.id]:
            for rr in session.scalars(
                select(RoomRate).where(RoomRate.room_id == existing_room.id)
            ):
                existing_rate_keys.add((rr.room_id, rr.valid_from, rr.valid_to))

        for rate in bundle["rows"]:
            rtid = _clean(rate.get("RoomTypeId"))
            mtid = _clean(rate.get("MealTypeId")) or "1"
            if not rtid:
                continue
            rname = _clean(rate.get("RoomTypeName")) or "Standard Room"
            meal = _pick_meal_code(rate.get("MealTypeName"))
            max_occ = _to_int(rate.get("MaxOccupancy")) or 2
            price = _to_decimal(rate.get("AdultPrice")) or Decimal("0.00")
            child_price = _to_decimal(rate.get("FirstChildPrice")) or Decimal("0.00")
            currency = _clean(rate.get("Currency")) or "EUR"

            room = room_cache.get((hotel.id, rname))
            if room is None:
                room = Room(hotel_id=hotel.id, type=rname)
                session.add(room)
                session.flush()
                room_cache[(hotel.id, rname)] = room

            # Room-level "base" fields: keep first non-default values
            room.meal_plan = meal
            room.max_occupancy = max_occ
            room.capacity = room.capacity or 5
            if not room.base_price_per_night:
                room.base_price_per_night = price
            room.is_active = True

            # Insert a seasonal RoomRate row for THIS CSV row
            valid_from = _to_date(rate.get("StartDate"))
            valid_to = _to_date(rate.get("EndDate"))

            # The CSV has year-end wrap windows like
            #   2027-12-24 -> 2027-01-03
            # The intent is clearly 24 Dec -> 3 Jan the FOLLOWING year.
            # If valid_to < valid_from and the gap is more than a few
            # months, roll valid_to forward by one year so the window
            # is a proper short span (10 days in this example).
            if (
                valid_from is not None
                and valid_to is not None
                and valid_to < valid_from
                and (valid_from - valid_to).days > 180
            ):
                try:
                    valid_to = valid_to.replace(year=valid_to.year + 1)
                except ValueError:
                    # 29 Feb -> no matching day; nudge to 28 Feb
                    valid_to = valid_to.replace(year=valid_to.year + 1, day=28)

            key = (room.id, valid_from, valid_to)
            if key in existing_rate_keys:
                continue
            session.add(RoomRate(
                room_id=room.id,
                adult_price=price,
                child_price=child_price,
                currency=currency,
                valid_from=valid_from,
                valid_to=valid_to,
            ))
            existing_rate_keys.add(key)

        if i % 20 == 0:
            session.flush()
            log.info("  ...%d/%d hotels", i, len(hotels_by_ext))

    # Drop any rate rows where the source CSV had the dates reversed.
    # These are bad rows in the CSV, not year-end wraps — we cannot
    # salvage them into a meaningful window, so we remove them.
    session.flush()
    deleted = session.execute(
        __import__("sqlalchemy").text(
            "DELETE FROM room_rates WHERE valid_to < valid_from"
        )
    ).rowcount
    if deleted:
        log.info("  dropped %d invalid room_rates rows (CSV had reversed dates)", deleted)

    session.flush()
    log.info("  total unique hotels: %d", len(hotels_by_ext))
    return created


# ─── Seeder: packages ──────────────────────────────────────────────
def _extract_day_itineraries(row: dict[str, str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for key, val in row.items():
        m = _DAY_COLUMN.match(key.strip())
        if not m:
            continue
        n = int(m.group(1))
        v = _clean(val)
        if v and n not in out:
            out[n] = v
    return out


def seed_packages(session: Session, rows: list[dict[str, str]]) -> int:
    log.info("Seeding %d packages ...", len(rows))
    created = 0

    for i, row in enumerate(rows, start=1):
        tid = _clean(row.get("TourID")) or f"PKG-{i:04d}"
        code = f"PKG-{tid.zfill(4)}"
        name = _clean(row.get("Package Name")) or f"Package {tid}"

        destination = _get_or_create_destination(session, row.get("Destination"))
        if destination is None:
            log.warning("  pkg %s: no destination, skipping", code)
            continue

        hname = _clean(row.get("HotelName")) or "Unnamed Hotel"
        hotel = session.scalar(select(Hotel).where(Hotel.name == hname))
        if hotel is None:
            hotel = Hotel(
                name=hname,
                destination_id=destination.id,
                stars=_to_int(row.get("Hotelstar")) or 3,
                total_capacity=10,
                is_active=True,
            )
            session.add(hotel)
            session.flush()
            # WHY: SlugMixin does not auto-generate; every Hotel
            # construction site must set slug explicitly or
            # url_for('public.hotel_detail', slug=hotel.slug) will
            # later fail with BuildError. Mirrors the pattern used
            # in seed_hotels() at ~line 704.
            hotel.slug = Hotel._generate_unique_slug(hname, session)

        rname = _clean(row.get("room_type")) or "Standard Room"
        meal_plan = _pick_meals(row.get("meal_plan")) or "room_only"
        room = session.scalar(
            select(Room).where(Room.hotel_id == hotel.id, Room.type == rname)
        )
        if room is None:
            room = Room(
                hotel_id=hotel.id,
                type=rname,
                meal_plan=meal_plan,
                max_occupancy=2,
                capacity=5,
                is_active=True,
            )
            session.add(room)
            session.flush()

        package = session.scalar(select(Package).where(Package.code == code))
        if package is None:
            unique_name = _unique_package_name(
                session,
                name=name,
                code=code,
                destination_name=destination.name,
            )
            package = Package(
                code=code,
                name=unique_name,
                # Required FKs MUST be set BEFORE the first flush, or the
                # NOT NULL constraint on packages.hotel_id fires.
                hotel_id=hotel.id,
                room_id=room.id,
                destination_id=destination.id,
                package_type=_pick_category(row.get("package_type")),
                duration_nights=_to_int(row.get("total_nights")) or 1,
                capacity=10,
                deposit_required=bool(
                    row.get("Deposit Required", "").strip()
                    and not row.get("Deposit Required", "")
                    .lower().startswith("whether")
                ),
                visa_required=bool(row.get("Visa Required", "").strip()),
                is_active=True,
            )
            session.add(package)
            session.flush()
            created += 1

        # Non-required fields — safe to assign after the flush.
        package.slug = Package._generate_unique_slug(package.name, session)
        package.description = _clean(row.get("description"))
        package.min_age = _to_int(row.get("minimum_age"))
        package.max_age = _to_int(row.get("maximum_age"))
        package.cancellation_policy = _clean(row.get("cancellation_policy"))
        package.booking_terms = _clean(row.get("booking_terms"))
        package.visa_fee = _to_decimal(row.get("Visa Fee"))
        # Ensure FKs stay set on re-runs of the seeder (idempotency)
        package.hotel_id = hotel.id
        package.room_id = room.id
        package.destination_id = destination.id

        session.flush()

        # Prices (one per package)
        adult = _to_decimal(row.get("adult_price")) or Decimal("0.00")
        child = _to_decimal(row.get("child_price")) or Decimal("0.00")
        if not session.scalar(
            select(PackagePrice).where(PackagePrice.package_id == package.id)
        ):
            session.add(
                PackagePrice(
                    package_id=package.id,
                    adult_price=adult,
                    child_price=child,
                    currency="EUR",
                )
            )

        # Images
        existing_imgs = {
            r.url for r in session.scalars(
                select(PackageImage).where(PackageImage.package_id == package.id)
            )
        }
        for sort, raw_url in enumerate(_split_list(row.get("hotel_image_urls"))):
            if _is_placeholder(raw_url) or raw_url in existing_imgs:
                continue
            session.add(
                PackageImage(
                    package_id=package.id,
                    url=raw_url,
                    type="hotel",
                    sort_order=sort,
                )
            )

        # Inclusions / exclusions
        existing_inc = {
            r.item for r in session.scalars(
                select(PackageInclusion).where(
                    PackageInclusion.package_id == package.id
                )
            )
        }
        for idx, item in enumerate(_split_list(row.get("Inclusions"))):
            if item not in existing_inc:
                session.add(
                    PackageInclusion(
                        package_id=package.id, item=item, sort_order=idx
                    )
                )
        existing_exc = {
            r.item for r in session.scalars(
                select(PackageExclusion).where(
                    PackageExclusion.package_id == package.id
                )
            )
        }
        for idx, item in enumerate(_split_list(row.get("Exclusions"))):
            if item not in existing_exc:
                session.add(
                    PackageExclusion(
                        package_id=package.id, item=item, sort_order=idx
                    )
                )

        # Itineraries
        existing_days = {
            r.day_number for r in session.scalars(
                select(PackageItinerary).where(
                    PackageItinerary.package_id == package.id
                )
            )
        }
        for day_n, text in sorted(_extract_day_itineraries(row).items()):
            if day_n in existing_days:
                continue
            session.add(
                PackageItinerary(
                    package_id=package.id,
                    day_number=day_n,
                    title=f"Day {day_n}",
                    description=text,
                )
            )

        # Flights (one per package if flights included)
        if (
            str(row.get("flights_included", "")).strip().lower()
            in {"yes", "true", "1"}
        ) and not session.scalar(
            select(Flight).where(Flight.package_id == package.id)
        ):
            supplier = _get_or_create_supplier(
                session, row.get("flights_name"), supplier_type="airline"
            )
            session.add(
                Flight(
                    package_id=package.id,
                    supplier_id=supplier.id if supplier else None,
                    flight_from=_clean(row.get("flights_from")) or "Unknown",
                    flight_to=destination.name,
                    airline_name=_clean(row.get("flights_name")),
                    luggage_allowance=_clean(row.get("Luggage Allowance")),
                    included=True,
                    is_active=True,
                )
            )

        # WHY: commit every 50 packages. Neon terminates connections that
        # sit idle in a transaction for more than 5 minutes. A single
        # uncommitted transaction across 1645 packages takes ~24 min, so it
        # will cross that 5-min idle window and be killed. Committing in
        # chunks bounds each transaction to well under a minute. The seed
        # is idempotent (matches by business key), so partial commits are
        # safe to re-run.
        if i % 25 == 0:
            log.info("  ...%d/%d packages", i, len(rows))
        if i % 50 == 0:
            session.commit()

    session.commit()
    return created


# ─── Entry point ───────────────────────────────────────────────────
def _run(file_key: str, dry_run: bool) -> None:
    app = create_app()
    _configure_seed_logging()
    with app.app_context():
        session: Session = db.session
        # WHY: Neon defaults idle_in_transaction_session_timeout to 5 min.
        # Even with chunked commits, a single slow package insert could
        # exceed that and kill the connection. Raise it to 30 min for the
        # seed process only; app runtime keeps the safer 5-min default.
        from sqlalchemy import text as _sql_text
        session.execute(_sql_text(
            "SET SESSION idle_in_transaction_session_timeout = '30min'"
        ))
        try:
            if file_key in ("trips", "all"):
                rows = _read_csv(TRIPS_CSV, encoding="utf-8")
                seed_activities(session, rows)

            if file_key in ("hotels", "all"):
                rows = _read_csv(HOTELS_CSV, encoding="utf-8-sig")
                seed_hotels(session, rows)

            if file_key in ("packages", "all"):
                rows = _read_csv(PACKAGES_CSV, encoding="utf-8-sig")
                seed_packages(session, rows)

            if dry_run:
                log.info("DRY RUN — rolling back")
                session.rollback()
            else:
                session.commit()
                log.info("Committed.")
        except Exception:
            session.rollback()
            log.exception("Seed failed — rolled back")
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed eltut-tours DB from CSVs")
    parser.add_argument(
        "--file",
        choices=["trips", "hotels", "packages", "all"],
        default="all",
        help="Which CSV to seed (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and build objects, then roll back without committing",
    )
    args = parser.parse_args()
    _run(args.file, args.dry_run)


if __name__ == "__main__":
    main()

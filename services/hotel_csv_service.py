# -*- coding: utf-8 -*-
"""
services/hotel_csv_service.py
Import/export hotels + rooms + rates from the Egypt.csv format.

The CSV is one row per (hotel, room_type, meal, date_window) combination.
Columns used:
    HotelId, HotelName, RegionName, IataCode, HotelStarRating,
    RoomTypeId, RoomTypeName, MealTypeName,
    StartDate, EndDate, MinOccupancy, MaxOccupancy,
    Currency, AdultPrice, FirstChildPrice,
    HotelInfo, Amenities, location
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from extensions import db
from models import Destination, Hotel, Room, RoomRate

log = logging.getLogger(__name__)


# Canonical export columns
EXPORT_COLS = [
    "HotelId", "HotelName", "RegionName", "IataCode", "HotelStarRating",
    "RoomTypeId", "RoomTypeName", "MealTypeName",
    "StartDate", "EndDate", "MinOccupancy", "MaxOccupancy",
    "Currency", "AdultPrice", "FirstChildPrice",
    "HotelInfo", "Amenities", "location",
]


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v, default=0):
    s = _clean(v)
    if not s:
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def _dec(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _date(v):
    s = _clean(v)
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _meal_label(v):
    """Normalise meal code / name to our Room.meal_plan format."""
    s = _clean(v)
    if not s:
        return "room_only"
    s = s.strip().lower()
    mapping = {
        "bb": "bed_breakfast", "bed and breakfast": "bed_breakfast",
        "hb": "half_board", "half board": "half_board",
        "fb": "full_board", "full board": "full_board",
        "ai": "all_inclusive", "all inclusive": "all_inclusive",
        "ro": "room_only", "room only": "room_only",
    }
    return mapping.get(s, s.replace(" ", "_"))


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "hotel"


def _get_or_create_destination(session, name, iata):
    if not name:
        return None
    slug = _slug(name)
    dest = session.scalar(select(Destination).where(Destination.slug == slug))
    if dest:
        if iata and not dest.airport_code:
            dest.airport_code = iata
        return dest
    dest = Destination(
        name=name.strip(),
        slug=slug,
        country="Egypt",
        airport_code=iata,
    )
    session.add(dest)
    session.flush()
    return dest


def import_csv(file_obj, *, replace: bool = False):
    """Import a hotel CSV. Returns (new_hotels, new_rooms, new_rates, errors)."""
    try:
        raw = file_obj.read()
        if isinstance(raw, bytes):
            text = raw.decode("utf-8-sig")
        else:
            text = raw
    except Exception as e:
        return (0, 0, 0, [f"Could not read file: {e}"])

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return (0, 0, 0, ["CSV is empty"])

    header = [h.strip() for h in reader.fieldnames]
    reader.fieldnames = header

    required = {"HotelId", "HotelName", "RoomTypeId", "RoomTypeName"}
    missing = required - set(header)
    if missing:
        return (0, 0, 0, [f"Missing required columns: {sorted(missing)}"])

    new_hotels = 0
    new_rooms = 0
    new_rates = 0
    errors = []

    if replace:
        # Only wipe rates — hotels/rooms are referenced by packages.
        db.session.query(RoomRate).delete()
        db.session.flush()

    # Caches keyed by CSV-level identifiers so we don't re-query the DB
    # for every row.
    hotel_cache = {}   # {csv_hotel_id: Hotel}
    room_cache = {}    # {(hotel.id, room_type_name, meal_plan): Room}

    for line_no, row in enumerate(reader, start=2):
        hotel_id_csv = _clean(row.get("HotelId"))
        hotel_name = _clean(row.get("HotelName"))
        room_type_csv = _clean(row.get("RoomTypeId"))
        room_type_name = _clean(row.get("RoomTypeName"))

        if not (hotel_id_csv and hotel_name and room_type_csv and room_type_name):
            continue

        region = _clean(row.get("RegionName"))
        iata = _clean(row.get("IataCode"))
        stars = _int(row.get("HotelStarRating"), 3)

        dest = _get_or_create_destination(db.session, region, iata)

        # ── Hotel ────────────────────────────────────────────────
        if hotel_id_csv in hotel_cache:
            hotel = hotel_cache[hotel_id_csv]
        else:
            hotel = db.session.scalar(
                select(Hotel).where(Hotel.name == hotel_name)
            )
            if hotel is None:
                hotel = Hotel(
                    name=hotel_name,
                    destination_id=dest.id if dest else None,
                    stars=stars,
                )
                db.session.add(hotel)
                db.session.flush()
                new_hotels += 1
            hotel_cache[hotel_id_csv] = hotel

        # ── Room ─────────────────────────────────────────────────
        # KEY FIX: room identity is (hotel, type, meal_plan), not just
        # (hotel, type). The CSV has multiple rows per room type — one
        # per meal plan / date window — so without meal_plan in the key
        # we'd create a fresh Room for every row.
        meal_plan = _meal_label(row.get("MealTypeName"))
        room_key = (hotel.id, room_type_name, meal_plan)

        if room_key in room_cache:
            room = room_cache[room_key]
        else:
            room = db.session.scalar(
                select(Room).where(
                    Room.hotel_id == hotel.id,
                    Room.type == room_type_name,
                    Room.meal_plan == meal_plan,
                )
            )
            if room is None:
                room = Room(
                    hotel_id=hotel.id,
                    type=room_type_name,
                    meal_plan=meal_plan,
                    max_occupancy=_int(row.get("MaxOccupancy"), 2),
                    capacity=_int(row.get("MaxOccupancy"), 2),
                    base_price_per_night=_dec(row.get("AdultPrice")) or Decimal("0"),
                )
                db.session.add(room)
                db.session.flush()
                new_rooms += 1
            room_cache[room_key] = room

        # ── Rate window ──────────────────────────────────────────
        vfrom = _date(row.get("StartDate"))
        vto = _date(row.get("EndDate"))
        adult = _dec(row.get("AdultPrice"))
        child = _dec(row.get("FirstChildPrice")) or Decimal("0")

        if not (vfrom and vto and adult):
            continue

        existing = db.session.scalar(
            select(RoomRate).where(
                RoomRate.room_id == room.id,
                RoomRate.valid_from == vfrom,
                RoomRate.valid_to == vto,
            )
        )
        if existing:
            existing.adult_price = adult
            existing.child_price = child
            existing.currency = "GBP"
        else:
            db.session.add(RoomRate(
                room_id=room.id,
                adult_price=adult,
                child_price=child,
                currency="GBP",
                valid_from=vfrom,
                valid_to=vto,
            ))
            new_rates += 1

    db.session.commit()
    return (new_hotels, new_rooms, new_rates, errors)


def export_csv():
    """Export hotels + rooms + rates as Egypt.csv-shaped CSV."""
    rows = db.session.execute(
        select(RoomRate, Room, Hotel, Destination)
        .join(Room, RoomRate.room_id == Room.id)
        .join(Hotel, Room.hotel_id == Hotel.id)
        .outerjoin(Destination, Hotel.destination_id == Destination.id)
        .order_by(Hotel.id, Room.id, RoomRate.valid_from)
    ).all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(EXPORT_COLS)

    for rate, room, hotel, dest in rows:
        writer.writerow([
            hotel.id, hotel.name,
            dest.name if dest else "",
            dest.airport_code if dest else "",
            hotel.stars or "",
            room.id, room.type, room.meal_plan,
            rate.valid_from.isoformat() if rate.valid_from else "",
            rate.valid_to.isoformat() if rate.valid_to else "",
            "", room.max_occupancy or "",
            rate.currency or "GBP",
            f"{rate.adult_price:.2f}" if rate.adult_price else "",
            f"{rate.child_price:.2f}" if rate.child_price else "",
            hotel.description or "", "", hotel.address or "",
        ])

    return out.getvalue()
"""
_audit.py - Read-only diagnostic for the ElTut Tours user journey (v2).

Scenario: Hurghada, 2027-01-20 -> 2027-01-27, 2 adults + 2 children.

Fixes in v2:
  - Uses real signatures discovered by inspect.signature():
      price_hotel(room_id, check_in, check_out, rooms=1, adults=1, children=0)
      hotel_room_availability(room_id, check_in, check_out)
      search(*, product_type, destination, check_in, check_out,
                activity_date, adults, children, page, per_page, sort, q)
  - Picks a room with base_price_per_night > 0 (49/631 rooms are zero)
  - Prints per-night adult/child breakdown for the hotel case
  - Reports search results with as much detail as available
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select

DESTINATION_NAME = "Hurghada"
CHECK_IN = date(2027, 1, 20)
CHECK_OUT = date(2027, 1, 27)
NIGHTS = (CHECK_OUT - CHECK_IN).days
ADULTS = 2
CHILDREN = 2


def banner(title):
    print()
    print("=" * 78)
    print("  " + title)
    print("=" * 78)


def sub(title):
    print()
    print("-- " + title + " " + "-" * max(0, 74 - len(title)))


def ok(msg):
    print("   [OK] " + msg)


def fail(msg):
    print("   [FAIL] " + msg)


def info(msg):
    print("      " + msg)


def money(value, currency="USD"):
    if value is None:
        return "None"
    try:
        return f"{Decimal(str(value)):.2f} {currency}"
    except Exception:
        return str(value)


banner("ELTUT TOURS - USER JOURNEY AUDIT (v2)")
print(f"Scenario: {DESTINATION_NAME} | {CHECK_IN} -> {CHECK_OUT} "
      f"({NIGHTS} nights) | {ADULTS}A + {CHILDREN}C")

from app import create_app
from extensions import db
from models.destination import Destination
from models.hotel import Hotel
from models.room import Room
from models.room_rate import RoomRate
from models.package import Package
from models.activity import Activity

from services import pricing_service
from services import availability_service
from services import search_service

app = create_app()


with app.app_context():

    # ══════════════════════════════════════════════════════════════
    banner("STEP 0 - Destination lookup")
    dest = db.session.execute(
        select(Destination).where(Destination.name == DESTINATION_NAME)
    ).scalar_one_or_none()

    if dest is None:
        fail(f"Destination {DESTINATION_NAME!r} not found - aborting.")
        sys.exit(1)

    ok(f"Found: id={dest.id} name={dest.name!r} slug={dest.slug!r}")
    destination_id = dest.id

    # ══════════════════════════════════════════════════════════════
    banner("STEP 1 - Pick one product of each type in this destination")

    # --- Hotel + a PRICED room ---
    hotel = db.session.execute(
        select(Hotel).where(Hotel.destination_id == destination_id).limit(1)
    ).scalar_one_or_none()

    if hotel:
        ok(f"Hotel:    id={hotel.id} name={hotel.name!r} stars={hotel.stars}")
    else:
        fail("No hotel found in this destination")

    # Pick a room with base_price_per_night > 0, else fall back to first room
    room = None
    if hotel:
        room = db.session.execute(
            select(Room)
            .where(Room.hotel_id == hotel.id, Room.base_price_per_night > 0)
            .limit(1)
        ).scalar_one_or_none()
        if room is None:
            room = db.session.execute(
                select(Room).where(Room.hotel_id == hotel.id).limit(1)
            ).scalar_one_or_none()
            fail(f"Hotel {hotel.id} has no priced room - using zero-price fallback")
        if room:
            ok(f"Room:     id={room.id} type={room.type!r} "
               f"base_price_per_night={money(room.base_price_per_night)}")

    # --- Package ---
    package = db.session.execute(
        select(Package).where(Package.destination_id == destination_id).limit(1)
    ).scalar_one_or_none()
    if package:
        ok(f"Package:  id={package.id} name={package.name!r} "
           f"nights={package.duration_nights}")
    else:
        fail("No package found in this destination")

    # --- Activity ---
    activity = db.session.execute(
        select(Activity).where(Activity.destination_id == destination_id).limit(1)
    ).scalar_one_or_none()
    if activity:
        ok(f"Activity: id={activity.id} name={activity.name!r} "
           f"category={activity.category}")
    else:
        fail("No activity found in this destination")

    # ══════════════════════════════════════════════════════════════
    banner("STEP 2 - Raw price rows in the DB")

    if hotel and room:
        sub("Hotel -> chosen room -> rates")
        info(f"Room id={room.id} type={room.type!r}")
        info(f"   base_price_per_night = {money(room.base_price_per_night)}")
        rates = db.session.execute(
            select(RoomRate).where(RoomRate.room_id == room.id)
        ).scalars().all()
        if not rates:
            info("   (no RoomRate rows - will use base_price_per_night)")
        for rate in rates:
            info(f"   Rate id={rate.id} "
                 f"adult={money(rate.adult_price)} "
                 f"child={money(rate.child_price)} "
                 f"valid {rate.valid_from} -> {rate.valid_to}")

    if package:
        sub("Package -> prices")
        for p in list(package.prices or []):
            info(f"Price id={p.id} "
                 f"adult={money(p.adult_price)} "
                 f"child={money(p.child_price)} "
                 f"valid {p.valid_from} -> {p.valid_to}")

    if activity:
        sub("Activity -> prices")
        for p in list(activity.prices or []):
            info(f"Price id={p.id} "
                 f"adult={money(p.adult_price)} "
                 f"child={money(p.child_price)} "
                 f"valid {p.valid_from} -> {p.valid_to}")

    # ══════════════════════════════════════════════════════════════
    banner("STEP 3 - pricing_service vs. locked formula")

    # --- Hotel ---
    sub("Hotel pricing")
    if hotel and room:
        try:
            svc_total = pricing_service.price_hotel(
                room_id=room.id,
                check_in=CHECK_IN,
                check_out=CHECK_OUT,
                rooms=1,
                adults=ADULTS,
                children=CHILDREN,
            )
            info(f"pricing_service.price_hotel(room={room.id}, "
                 f"{CHECK_IN}->{CHECK_OUT}, 1 room, {ADULTS}A+{CHILDREN}C)")
            info(f"   returned = {money(svc_total)}")

            # Find the rate that covers CHECK_IN (else use base)
            rate = db.session.execute(
                select(RoomRate).where(
                    RoomRate.room_id == room.id,
                    (RoomRate.valid_from.is_(None)) | (RoomRate.valid_from <= CHECK_IN),
                    (RoomRate.valid_to.is_(None)) | (RoomRate.valid_to >= CHECK_IN),
                )
            ).scalars().first()

            if rate:
                per_night = rate.adult_price * ADULTS + rate.child_price * CHILDREN
                expected = per_night * NIGHTS
                info(f"Hand-computed (rate {rate.id}): "
                     f"({money(rate.adult_price)} x {ADULTS}A + "
                     f"{money(rate.child_price)} x {CHILDREN}C) x {NIGHTS} nights")
                info(f"   per night = {money(per_night)}")
                info(f"   expected  = {money(expected)}")
            else:
                expected = room.base_price_per_night * NIGHTS
                info(f"Hand-computed (base_price_per_night x nights): "
                     f"{money(room.base_price_per_night)} x {NIGHTS} = {money(expected)}")

            if abs(Decimal(str(svc_total)) - Decimal(str(expected))) < Decimal("0.01"):
                ok("Match")
            else:
                diff = Decimal(str(svc_total)) - Decimal(str(expected))
                fail(f"Mismatch - service minus expected = {money(diff)}")
        except Exception as e:
            fail(f"price_hotel raised: {type(e).__name__}: {e}")
    else:
        fail("Skipping hotel pricing (no priced hotel/room)")

    # --- Package ---
    sub("Package pricing")
    if package:
        try:
            svc_total = pricing_service.price_package(
                package_id=package.id,
                adults=ADULTS,
                children=CHILDREN,
            )
            info(f"pricing_service.price_package(package={package.id}, "
                 f"{ADULTS}A+{CHILDREN}C) = {money(svc_total)}")

            if package.prices:
                p = package.prices[0]
                expected = (p.adult_price * ADULTS) + (p.child_price * CHILDREN)
                info(f"Hand-computed: "
                     f"({money(p.adult_price)} x {ADULTS}) + "
                     f"({money(p.child_price)} x {CHILDREN}) = {money(expected)}")
                if abs(Decimal(str(svc_total)) - expected) < Decimal("0.01"):
                    ok("Match")
                else:
                    fail(f"Mismatch - diff = {money(Decimal(str(svc_total)) - expected)}")
            else:
                fail("Package has no prices to compare against")
        except Exception as e:
            fail(f"price_package raised: {type(e).__name__}: {e}")

    # --- Activity ---
    sub("Activity pricing")
    if activity:
        try:
            svc_total = pricing_service.price_activity(
                activity_id=activity.id,
                adults=ADULTS,
                children=CHILDREN,
            )
            info(f"pricing_service.price_activity(activity={activity.id}, "
                 f"{ADULTS}A+{CHILDREN}C) = {money(svc_total)}")

            if activity.prices:
                p = activity.prices[0]
                expected = (p.adult_price * ADULTS) + (p.child_price * CHILDREN)
                info(f"Hand-computed: "
                     f"({money(p.adult_price)} x {ADULTS}) + "
                     f"({money(p.child_price)} x {CHILDREN}) = {money(expected)}")
                if abs(Decimal(str(svc_total)) - expected) < Decimal("0.01"):
                    ok("Match")
                else:
                    fail(f"Mismatch - diff = {money(Decimal(str(svc_total)) - expected)}")
            else:
                fail("Activity has no prices to compare against")
        except Exception as e:
            fail(f"price_activity raised: {type(e).__name__}: {e}")

    # ══════════════════════════════════════════════════════════════
    banner("STEP 4 - availability_service for 20-27 Jan 2027")

    if hotel and room:
        try:
            rooms_available = availability_service.hotel_room_availability(
                room_id=room.id,
                check_in=CHECK_IN,
                check_out=CHECK_OUT,
            )
            info(f"hotel_room_availability(room={room.id}, "
                 f"{CHECK_IN}->{CHECK_OUT}) -> {rooms_available} rooms available")
            ok("Did not raise")
        except Exception as e:
            fail(f"hotel_room_availability raised: {type(e).__name__}: {e}")

    if activity:
        try:
            seats = availability_service.activity_availability(
                activity_id=activity.id,
                target_date=CHECK_IN,
            )
            info(f"activity_availability(activity={activity.id}, "
                 f"{CHECK_IN}) -> {seats} seats")
            ok("Did not raise")
        except Exception as e:
            fail(f"activity_availability raised: {type(e).__name__}: {e}")

    if package:
        try:
            seats = availability_service.package_availability(
                package_id=package.id,
                target_date=CHECK_IN,
            )
            info(f"package_availability(package={package.id}, "
                 f"{CHECK_IN}) -> {seats} seats")
            ok("Did not raise")
        except Exception as e:
            fail(f"package_availability raised: {type(e).__name__}: {e}")

    # ══════════════════════════════════════════════════════════════
    banner("STEP 5 - search_service.search by product type")

    # --- Hotels ---
    sub("search(product_type='hotel', destination='Hurghada', dates, party)")
    try:
        result = search_service.search(
            product_type="hotel",
            destination=DESTINATION_NAME,
            check_in=CHECK_IN,
            check_out=CHECK_OUT,
            adults=ADULTS,
            children=CHILDREN,
            page=1,
            per_page=12,
            sort="newest",
        )
        info(f"Returned keys: {sorted(result.keys()) if isinstance(result, dict) else type(result).__name__}")
        if isinstance(result, dict):
            items = result.get("items") or result.get("results") or []
            total = result.get("total", len(items))
            info(f"total={total}  len(items)={len(items)}")
            for i, item in enumerate(items[:5], 1):
                name = item.get("name") or item.get("title") or "?"
                price = item.get("price") or item.get("price_from") or item.get("total_price")
                currency = item.get("currency", "USD")
                nights = item.get("nights")
                info(f"  [{i}] {name!r} price={money(price, currency)} nights={nights}")
            ok("Search executed") if items else fail("Search returned ZERO results")
    except Exception as e:
        fail(f"search(hotel) raised: {type(e).__name__}: {e}")

    # --- Packages ---
    sub("search(product_type='package', destination='Hurghada', dates, party)")
    try:
        result = search_service.search(
            product_type="package",
            destination=DESTINATION_NAME,
            check_in=CHECK_IN,
            check_out=CHECK_OUT,
            adults=ADULTS,
            children=CHILDREN,
            page=1,
            per_page=12,
            sort="newest",
        )
        info(f"Returned keys: {sorted(result.keys()) if isinstance(result, dict) else type(result).__name__}")
        if isinstance(result, dict):
            items = result.get("items") or result.get("results") or []
            total = result.get("total", len(items))
            info(f"total={total}  len(items)={len(items)}")
            for i, item in enumerate(items[:5], 1):
                name = item.get("name") or item.get("title") or "?"
                price = item.get("price") or item.get("price_from") or item.get("total_price")
                currency = item.get("currency", "USD")
                info(f"  [{i}] {name!r} price={money(price, currency)}")
            ok("Search executed") if items else fail("Search returned ZERO results")
    except Exception as e:
        fail(f"search(package) raised: {type(e).__name__}: {e}")

    # --- Activities ---
    sub("search(product_type='activity', destination='Hurghada', activity_date)")
    try:
        result = search_service.search(
            product_type="activity",
            destination=DESTINATION_NAME,
            activity_date=CHECK_IN,
            adults=ADULTS,
            children=CHILDREN,
            page=1,
            per_page=12,
            sort="newest",
        )
        info(f"Returned keys: {sorted(result.keys()) if isinstance(result, dict) else type(result).__name__}")
        if isinstance(result, dict):
            items = result.get("items") or result.get("results") or []
            total = result.get("total", len(items))
            info(f"total={total}  len(items)={len(items)}")
            for i, item in enumerate(items[:5], 1):
                name = item.get("name") or item.get("title") or "?"
                price = item.get("price") or item.get("price_from") or item.get("total_price")
                currency = item.get("currency", "USD")
                info(f"  [{i}] {name!r} price={money(price, currency)}")
            ok("Search executed") if items else fail("Search returned ZERO results")
    except Exception as e:
        fail(f"search(activity) raised: {type(e).__name__}: {e}")

    banner("AUDIT COMPLETE (v2)")
    print("Read the [OK] / [FAIL] lines above. Paste this entire output back.")
    print()
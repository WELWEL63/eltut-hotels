"""
services/flight_matching_service.py
────────────────────────────────────
Auto-matches flights to packages by finding valid outbound/return pairs
for each UK → Egypt route, then linking them to matching packages.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select

from extensions import db
from models import (
    Destination,
    FlightPrice,
    Package,
    PackageFlight,
    Room,
)

PREFERRED_DURATIONS = (7, 10, 12, 14)
MIN_NIGHTS = 6
MAX_NIGHTS = 15

AIRPORT_MAP = {
    "hurghada": "HRG",
    "sharm el sheikh": "SSH",
    "sharm el-sheikh": "SSH",
    "luxor": "LXR",
    "aswan": "ASW",
    "marsa alam": "RMF",
    "taba": "TCP",
    "el gouna": "HRG",
    "sahl hasheesh": "HRG",
    "soma bay": "HRG",
    "safaga": "HRG",
    "nile cruise": "LXR",
    "cairo": "CAI",
    "alexandria": "ALY",
}


def _normalize_airport(name):
    if not name:
        return None
    key = name.strip().lower()
    if key in AIRPORT_MAP:
        return AIRPORT_MAP[key]
    if len(key) == 3 and key.isalpha():
        return key.upper()
    return None


def _same_city(a, b):
    if not a or not b:
        return False
    return a.strip().upper() == b.strip().upper()


def _build_packages_by_airport():
    packages = list(
        db.session.scalars(
            select(Package).where(Package.is_active.is_(True))
        ).all()
    )
    packages_by_airport = defaultdict(list)
    for pkg in packages:
        dest = db.session.get(Destination, pkg.destination_id) if pkg.destination_id else None
        airport = _normalize_airport(dest.name if dest else None)
        if not airport:
            continue
        room = db.session.get(Room, pkg.room_id) if pkg.room_id else None
        if not room or not room.base_price_per_night or room.base_price_per_night <= 0:
            continue
        packages_by_airport[airport].append(pkg)
    return packages_by_airport


def _get_flights_for_airport(airport):
    out_flights = list(
        db.session.scalars(
            select(FlightPrice)
            .where(FlightPrice.direction == "out")
            .where(FlightPrice.destination.ilike(f"%{airport}%"))
        ).all()
    )
    back_flights = list(
        db.session.scalars(
            select(FlightPrice)
            .where(FlightPrice.direction == "back")
            .where(FlightPrice.origin.ilike(f"%{airport}%"))
        ).all()
    )
    return out_flights, back_flights


def _find_valid_combos(out_flights, back_flights):
    combos = []
    for back_f in back_flights:
        matching_outs = [
            out_f for out_f in out_flights
            if _same_city(out_f.origin, back_f.destination)
            and MIN_NIGHTS <= (back_f.departure_date - out_f.departure_date).days <= MAX_NIGHTS
        ]
        if not matching_outs:
            continue
        cheapest = min(matching_outs, key=lambda x: float(x.price_gbp))
        nights = (back_f.departure_date - cheapest.departure_date).days
        combos.append({
            "out": cheapest,
            "back": back_f,
            "nights": nights,
            "total_price": float(cheapest.price_gbp) + float(back_f.price_gbp),
        })
    return combos


def preview_matches() -> dict[str, Any]:
    packages_by_airport = _build_packages_by_airport()
    results = {}
    total_links = 0

    for airport, pkgs in packages_by_airport.items():
        out_flights, back_flights = _get_flights_for_airport(airport)

        if not out_flights or not back_flights:
            results[airport] = {
                "packages": len(pkgs),
                "outbound_flights": len(out_flights),
                "return_flights": len(back_flights),
                "valid_combos": 0,
                "links_to_create": 0,
                "skipped": True,
            }
            continue

        combos = _find_valid_combos(out_flights, back_flights)

        new_links = 0
        for combo in combos:
            for pkg in pkgs:
                existing = db.session.scalar(
                    select(PackageFlight)
                    .where(PackageFlight.package_id == pkg.id)
                    .where(PackageFlight.outbound_flight_id == combo["out"].id)
                    .where(PackageFlight.inbound_flight_id == combo["back"].id)
                )
                if not existing:
                    new_links += 1

        results[airport] = {
            "packages": len(pkgs),
            "outbound_flights": len(out_flights),
            "return_flights": len(back_flights),
            "valid_combos": len(combos),
            "links_to_create": new_links,
            "skipped": False,
        }
        total_links += new_links

    return {
        "total_links": total_links,
        "destinations": results,
    }


def apply_matches() -> dict[str, Any]:
    preview = preview_matches()
    created = 0
    errors = []

    packages_by_airport = _build_packages_by_airport()

    for airport, pkgs in packages_by_airport.items():
        info = preview["destinations"].get(airport, {})
        if info.get("skipped"):
            continue

        out_flights, back_flights = _get_flights_for_airport(airport)
        combos = _find_valid_combos(out_flights, back_flights)

        for combo in combos:
            cheapest = combo["out"]
            back_f = combo["back"]
            nights = combo["nights"]

            label = f"{cheapest.airline} -> {back_f.airline} ({nights} nights)"
            if cheapest.airline.lower() == back_f.airline.lower():
                label = f"{cheapest.airline} ({nights} nights)"

            for pkg in pkgs:
                existing = db.session.scalar(
                    select(PackageFlight)
                    .where(PackageFlight.package_id == pkg.id)
                    .where(PackageFlight.outbound_flight_id == cheapest.id)
                    .where(PackageFlight.inbound_flight_id == back_f.id)
                )
                if existing:
                    continue
                try:
                    pf = PackageFlight(
                        package_id=pkg.id,
                        outbound_flight_id=cheapest.id,
                        inbound_flight_id=back_f.id,
                        label=label,
                        sort_order=0,
                        is_active=True,
                    )
                    db.session.add(pf)
                    created += 1
                except Exception as e:
                    errors.append(f"Package {pkg.id}: {e}")

    db.session.commit()

    return {
        "created": created,
        "errors": errors,
        "total_links": preview["total_links"],
    }

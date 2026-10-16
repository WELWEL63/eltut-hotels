# -*- coding: utf-8 -*-
"""Dump all price tables to JSON before currency conversion."""
import io
import json
from datetime import date, datetime
from decimal import Decimal

from app import create_app
from extensions import db
from models import RoomRate, PackagePrice, ActivityPrice, Room


def _ser(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError


app = create_app()
with app.app_context():
    backup = {
        "room_rates": [],
        "package_prices": [],
        "activity_prices": [],
        "rooms": [],
    }

    for r in db.session.query(RoomRate).all():
        backup["room_rates"].append({
            "id": r.id, "room_id": r.room_id,
            "adult_price": str(r.adult_price),
            "child_price": str(r.child_price),
            "currency": r.currency,
            "valid_from": r.valid_from.isoformat() if r.valid_from else None,
            "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        })

    for r in db.session.query(PackagePrice).all():
        backup["package_prices"].append({
            "id": r.id, "package_id": r.package_id,
            "adult_price": str(r.adult_price),
            "child_price": str(r.child_price),
            "currency": r.currency,
            "valid_from": r.valid_from.isoformat() if r.valid_from else None,
            "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        })

    for r in db.session.query(ActivityPrice).all():
        backup["activity_prices"].append({
            "id": r.id, "activity_id": r.activity_id,
            "adult_price": str(r.adult_price),
            "child_price": str(r.child_price),
            "currency": r.currency,
            "valid_from": r.valid_from.isoformat() if r.valid_from else None,
            "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        })

    for r in db.session.query(Room).all():
        backup["rooms"].append({
            "id": r.id,
            "base_price_per_night": str(r.base_price_per_night) if r.base_price_per_night else None,
        })

    with io.open("backups/prices_before_gbp.json", "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=2)

    print("Backup complete:")
    for k, v in backup.items():
        print(f"  {k}: {len(v)} rows")
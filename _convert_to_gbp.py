# -*- coding: utf-8 -*-
"""Convert all EUR prices to GBP. Rate: 0.85 EUR -> 1 GBP."""
from decimal import Decimal, ROUND_HALF_UP

from app import create_app
from extensions import db
from models import RoomRate, PackagePrice, ActivityPrice, Room

RATE = Decimal("0.85")  # 1 EUR = 0.85 GBP
TWO = Decimal("0.01")


def to_gbp(v):
    if v is None:
        return None
    return (Decimal(str(v)) * RATE).quantize(TWO, rounding=ROUND_HALF_UP)


app = create_app()
with app.app_context():
    # RoomRates
    rr_count = 0
    for r in db.session.query(RoomRate).all():
        r.adult_price = to_gbp(r.adult_price)
        r.child_price = to_gbp(r.child_price)
        r.currency = "GBP"
        rr_count += 1

    # PackagePrices
    pp_count = 0
    for r in db.session.query(PackagePrice).all():
        r.adult_price = to_gbp(r.adult_price)
        r.child_price = to_gbp(r.child_price)
        r.currency = "GBP"
        pp_count += 1

    # ActivityPrices
    ap_count = 0
    for r in db.session.query(ActivityPrice).all():
        r.adult_price = to_gbp(r.adult_price)
        r.child_price = to_gbp(r.child_price)
        r.currency = "GBP"
        ap_count += 1

    # Room.base_price_per_night
    rooms_count = 0
    for r in db.session.query(Room).all():
        if r.base_price_per_night:
            r.base_price_per_night = to_gbp(r.base_price_per_night)
            rooms_count += 1

    db.session.commit()

    print(f"Converted:")
    print(f"  room_rates:          {rr_count}")
    print(f"  package_prices:      {pp_count}")
    print(f"  activity_prices:     {ap_count}")
    print(f"  rooms.base_price:    {rooms_count}")
    print()
    print("All rows now GBP.")
# -*- coding: utf-8 -*-
"""Relabel EUR -> GBP. No value change."""
from sqlalchemy import text
from app import create_app
from extensions import db

app = create_app()
with app.app_context():
    r1 = db.session.execute(text(
        "UPDATE room_rates SET currency = 'GBP' WHERE currency = 'EUR'"
    ))
    print(f"room_rates: {r1.rowcount}")

    r2 = db.session.execute(text(
        "UPDATE package_prices SET currency = 'GBP' WHERE currency = 'EUR'"
    ))
    print(f"package_prices: {r2.rowcount}")

    r3 = db.session.execute(text(
        "UPDATE activity_prices SET currency = 'GBP' WHERE currency = 'EUR'"
    ))
    print(f"activity_prices: {r3.rowcount}")

    db.session.commit()
    print("Done.")
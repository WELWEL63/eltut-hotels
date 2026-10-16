# -*- coding: utf-8 -*-
"""
services/flight_csv_service.py
CSV import/export for the flight_prices table.

CSV columns (see flight_template.csv):
    airline, origin, destination, departure_date, direction,
    price_gbp, currency, flight_number, departure_time, arrival_time,
    passengers_basis, luggage_kg, source_url, captured_at
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from extensions import db
from models import FlightPrice

log = logging.getLogger(__name__)


COLUMNS = [
    "airline", "origin", "destination", "departure_date", "direction",
    "price_gbp", "currency", "flight_number", "departure_time",
    "arrival_time", "passengers_basis", "luggage_kg", "source_url",
    "captured_at",
]


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_decimal(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_int(v, default):
    s = _clean(v)
    if not s:
        return default
    try:
        return int(s)
    except ValueError:
        return default


def import_csv(file_obj, *, replace: bool = False):
    """Import rows from a CSV file-like object.

    Returns (inserted, updated, errors).
    """
    try:
        raw = file_obj.read()
        if isinstance(raw, bytes):
            text = raw.decode("utf-8-sig")
        else:
            text = raw
    except Exception as e:
        return (0, 0, [f"Could not read file: {e}"])

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return (0, 0, ["CSV is empty"])

    # Normalise header names
    header = [h.strip().lower() for h in reader.fieldnames]
    reader.fieldnames = header

    required = {"airline", "origin", "destination", "departure_date",
                "direction", "price_gbp"}
    missing = required - set(header)
    if missing:
        return (0, 0, [f"Missing required columns: {sorted(missing)}"])

    inserted = 0
    updated = 0
    errors = []

    if replace:
        db.session.query(FlightPrice).delete()
        db.session.flush()

    for line_no, row in enumerate(reader, start=2):
        airline = _clean(row.get("airline"))
        origin = (_clean(row.get("origin")) or "").upper()
        destination = (_clean(row.get("destination")) or "").upper()
        dep_date = _parse_date(row.get("departure_date"))
        direction = (_clean(row.get("direction")) or "").lower()
        price = _parse_decimal(row.get("price_gbp"))

        if not airline or len(origin) != 3 or len(destination) != 3:
            errors.append(f"line {line_no}: bad airline/origin/destination")
            continue
        if dep_date is None:
            errors.append(f"line {line_no}: bad date")
            continue
        if direction not in ("out", "back"):
            errors.append(f"line {line_no}: direction must be out|back")
            continue
        if price is None or price <= 0:
            errors.append(f"line {line_no}: bad price")
            continue

        existing = db.session.scalar(
            select(FlightPrice).where(
                FlightPrice.airline == airline,
                FlightPrice.origin == origin,
                FlightPrice.destination == destination,
                FlightPrice.departure_date == dep_date,
                FlightPrice.direction == direction,
            )
        )

        if existing:
            existing.price_gbp = price
            existing.currency = "GBP"
            existing.flight_number = _clean(row.get("flight_number"))
            existing.departure_time = _clean(row.get("departure_time"))
            existing.arrival_time = _clean(row.get("arrival_time"))
            existing.passengers_basis = _clean(row.get("passengers_basis"))
            existing.luggage_kg = _parse_int(row.get("luggage_kg"), 23)
            existing.source_url = _clean(row.get("source_url"))
            cap = _clean(row.get("captured_at"))
            if cap:
                try:
                    existing.captured_at = datetime.fromisoformat(cap.replace("Z", "+00:00"))
                except ValueError:
                    pass
            updated += 1
        else:
            fp = FlightPrice(
                airline=airline,
                origin=origin,
                destination=destination,
                departure_date=dep_date,
                direction=direction,
                price_gbp=price,
                currency="GBP",
                flight_number=_clean(row.get("flight_number")),
                departure_time=_clean(row.get("departure_time")),
                arrival_time=_clean(row.get("arrival_time")),
                passengers_basis=_clean(row.get("passengers_basis")),
                luggage_kg=_parse_int(row.get("luggage_kg"), 23),
                source_url=_clean(row.get("source_url")),
            )
            cap = _clean(row.get("captured_at"))
            if cap:
                try:
                    fp.captured_at = datetime.fromisoformat(cap.replace("Z", "+00:00"))
                except ValueError:
                    pass
            db.session.add(fp)
            inserted += 1

    db.session.commit()
    return (inserted, updated, errors)


def export_csv():
    """Return CSV text of all flight_prices rows."""
    rows = db.session.scalars(
        select(FlightPrice).order_by(
            FlightPrice.origin, FlightPrice.destination,
            FlightPrice.departure_date, FlightPrice.direction,
        )
    ).all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for r in rows:
        writer.writerow([
            r.airline, r.origin, r.destination,
            r.departure_date.isoformat() if r.departure_date else "",
            r.direction,
            f"{r.price_gbp:.2f}" if r.price_gbp is not None else "",
            r.currency or "GBP",
            r.flight_number or "",
            r.departure_time or "",
            r.arrival_time or "",
            r.passengers_basis or "",
            r.luggage_kg if r.luggage_kg is not None else "",
            r.source_url or "",
            r.captured_at.isoformat() if r.captured_at else "",
        ])
    return out.getvalue()
"""
services/flight_import_service.py
─────────────────────────────────
Canonical CSV -> flight_prices table.

Public API
──────────
    ImportResult                -- summary dataclass
    parse_canonical_csv(source) -- CSV -> list[dict] (no DB)
    import_rows(rows, mode)     -- list[dict] -> DB, returns ImportResult
    import_csv(source, mode)    -- parse + import in one call

Source may be:
    * a path (str | Path)
    * an open file-like object (e.g. werkzeug FileStorage.stream)

Import modes
────────────
    "merge"   -- insert new rows; update price on existing ones (default)
    "replace" -- DELETE all flight_prices rows first, then insert

No Flask imports. No request context needed. Callable from scripts,
CLI tools, or admin routes.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import delete, select

from extensions import db
from models import FlightPrice


log = logging.getLogger(__name__)


# ─── Canonical column set ───────────────────────────────────────────
CANONICAL_COLUMNS = [
    "airline", "origin", "destination", "departure_date", "direction",
    "price_gbp", "currency", "flight_number", "departure_time",
    "arrival_time", "passengers_basis", "luggage_kg", "source_url",
    "captured_at",
]

REQUIRED_COLUMNS = {
    "airline", "origin", "destination",
    "departure_date", "direction", "price_gbp",
}

VALID_DIRECTIONS = {"out", "back"}
VALID_CURRENCIES = {"GBP"}  # extend later if needed


# ─── Result summary ─────────────────────────────────────────────────
@dataclass
class ImportResult:
    import_batch_id: str
    mode: str
    total_rows: int = 0
    inserted: int = 0
    updated: int = 0
    rejected: int = 0
    duplicates_in_csv: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "import_batch_id": self.import_batch_id,
            "mode": self.mode,
            "total_rows": self.total_rows,
            "inserted": self.inserted,
            "updated": self.updated,
            "rejected": self.rejected,
            "duplicates_in_csv": self.duplicates_in_csv,
            "errors": self.errors,
        }

    def __repr__(self) -> str:
        return (
            f"<ImportResult batch={self.import_batch_id} mode={self.mode} "
            f"inserted={self.inserted} updated={self.updated} "
            f"rejected={self.rejected}>"
        )


# ─── Batch ID ───────────────────────────────────────────────────────
def _make_batch_id() -> str:
    """2026-10-14-144830 — sortable, greppable, no UUID."""
    return datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")


# ─── Source resolution ──────────────────────────────────────────────
def _open_source(source: Any) -> tuple[io.TextIOBase, bool]:
    """
    Returns (file_obj, should_close).

    Accepts:
        - str path
        - Path
        - file-like object with .read()
    """
    if hasattr(source, "read"):
        # FileStorage.stream or similar — wrap to be safe
        return source, False  # type: ignore[return-value]
    path = Path(source)
    return path.open("r", encoding="utf-8-sig", newline=""), True


# ─── Field parsers ──────────────────────────────────────────────────
def _clean_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    s = _clean_str(value)
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_decimal(value: Optional[str]) -> Optional[Decimal]:
    s = _clean_str(value)
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    s = _clean_str(value)
    if not s:
        return None
    try:
        # Accept trailing Z (UTC designator)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    s = _clean_str(value)
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_time(value: Optional[str]) -> Optional[str]:
    """HH:MM, 24h, zero-padded. Returns None if malformed."""
    s = _clean_str(value)
    if not s:
        return None
    parts = s.split(":")
    if len(parts) != 2:
        return None
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


# ─── Row validation ─────────────────────────────────────────────────
def _normalise_row(raw: dict) -> tuple[Optional[dict], Optional[str]]:
    """
    Returns (clean_dict, None) on success,
            (None, reason) on failure.
    """
    airline = _clean_str(raw.get("airline"))
    if not airline:
        return None, "missing airline"

    origin = _clean_str(raw.get("origin"))
    if not origin or len(origin) != 3:
        return None, f"bad origin: {origin!r}"

    destination = _clean_str(raw.get("destination"))
    if not destination or len(destination) != 3:
        return None, f"bad destination: {destination!r}"

    dep_date = _parse_iso_date(raw.get("departure_date"))
    if dep_date is None:
        return None, f"bad departure_date: {raw.get('departure_date')!r}"

    direction = (_clean_str(raw.get("direction")) or "").lower()
    if direction not in VALID_DIRECTIONS:
        return None, f"bad direction: {direction!r}"

    price = _parse_decimal(raw.get("price_gbp"))
    if price is None or price <= 0:
        return None, f"bad price_gbp: {raw.get('price_gbp')!r}"

    currency = (_clean_str(raw.get("currency")) or "GBP").upper()
    if currency not in VALID_CURRENCIES:
        return None, f"unsupported currency: {currency!r}"

    luggage = _parse_int(raw.get("luggage_kg"))
    if luggage is None:
        luggage = 23
    elif not (0 <= luggage <= 50):
        return None, f"luggage_kg out of range: {luggage}"

    dep_time = _parse_time(raw.get("departure_time"))
    arr_time = _parse_time(raw.get("arrival_time"))

    return {
        "airline": airline,
        "origin": origin.upper(),
        "destination": destination.upper(),
        "departure_date": dep_date,
        "direction": direction,
        "price_gbp": price,
        "currency": currency,
        "flight_number": _clean_str(raw.get("flight_number")),
        "departure_time": dep_time,
        "arrival_time": arr_time,
        "passengers_basis": _clean_str(raw.get("passengers_basis")),
        "luggage_kg": luggage,
        "source_url": _clean_str(raw.get("source_url")),
        "captured_at": _parse_iso_datetime(raw.get("captured_at")),
    }, None


# ─── CSV parsing ────────────────────────────────────────────────────
def parse_canonical_csv(source: Any) -> tuple[list[dict], list[str]]:
    """
    Read a canonical CSV from a path or file-like object.

    Returns (rows, errors) where:
        rows   -- list of normalised dicts ready for import
        errors -- list of human-readable rejection reasons
    """
    rows: list[dict] = []
    errors: list[str] = []
    seen_keys: dict[tuple, int] = {}
    duplicates_in_csv = 0

    file_obj, should_close = _open_source(source)
    try:
        reader = csv.DictReader(file_obj)
        if not reader.fieldnames:
            return [], ["CSV is empty (no header row)"]

        header = [h.strip().lower() for h in reader.fieldnames]
        reader.fieldnames = header

        missing = REQUIRED_COLUMNS - set(header)
        if missing:
            return [], [
                f"missing required columns: {sorted(missing)}"
            ]

        for line_no, raw in enumerate(reader, start=2):  # header is line 1
            clean, reason = _normalise_row(raw)
            if clean is None:
                errors.append(f"line {line_no}: {reason}")
                continue

            key = (
                clean["airline"], clean["origin"], clean["destination"],
                clean["departure_date"], clean["direction"],
            )
            if key in seen_keys:
                # Duplicate in same CSV -- last wins (decision B)
                dup_idx = seen_keys[key]
                rows[dup_idx] = clean
                duplicates_in_csv += 1
                errors.append(
                    f"line {line_no}: duplicate of line "
                    f"{seen_keys[key] + 2} -- later row wins"
                )
            else:
                seen_keys[key] = len(rows)
                rows.append(clean)
    finally:
        if should_close:
            file_obj.close()

    return rows, errors


# ─── DB import ──────────────────────────────────────────────────────
def import_rows(
    rows: Iterable[dict],
    *,
    mode: str = "merge",
    batch_id: Optional[str] = None,
) -> ImportResult:
    """
    Write normalised rows to flight_prices.

    mode="merge"   -- upsert by (airline, origin, destination, dep_date, direction)
    mode="replace" -- delete all rows first, then insert

    Caller is responsible for db.session.commit() after this returns,
    unless they want to inspect first. We commit here by default.
    """
    if mode not in {"merge", "replace"}:
        raise ValueError(f"invalid mode: {mode!r}")

    batch = batch_id or _make_batch_id()
    result = ImportResult(import_batch_id=batch, mode=mode)

    rows = list(rows)
    result.total_rows = len(rows)

    if mode == "replace":
        db.session.execute(delete(FlightPrice))
        db.session.flush()

    for row in rows:
        # Look for an existing row by unique key
        existing = db.session.scalar(
            select(FlightPrice).where(
                FlightPrice.airline == row["airline"],
                FlightPrice.origin == row["origin"],
                FlightPrice.destination == row["destination"],
                FlightPrice.departure_date == row["departure_date"],
                FlightPrice.direction == row["direction"],
            )
        )

        if existing is None:
            db.session.add(FlightPrice(import_batch_id=batch, **row))
            result.inserted += 1
        else:
            existing.price_gbp = row["price_gbp"]
            existing.currency = row["currency"]
            existing.flight_number = row["flight_number"]
            existing.departure_time = row["departure_time"]
            existing.arrival_time = row["arrival_time"]
            existing.passengers_basis = row["passengers_basis"]
            existing.luggage_kg = row["luggage_kg"]
            existing.source_url = row["source_url"]
            existing.captured_at = row["captured_at"]
            existing.import_batch_id = batch
            result.updated += 1

    db.session.commit()
    return result


# ─── Convenience ────────────────────────────────────────────────────
def import_csv(source: Any, *, mode: str = "merge") -> ImportResult:
    """
    Parse + import in one call.

    source: path (str | Path) or file-like object.
    """
    rows, errors = parse_canonical_csv(source)
    result = import_rows(rows, mode=mode)
    result.rejected = len(errors)
    result.errors = errors
    return result


__all__ = [
    "CANONICAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "ImportResult",
    "parse_canonical_csv",
    "import_rows",
    "import_csv",
]
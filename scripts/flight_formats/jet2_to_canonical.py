"""
scripts/flight_formats/jet2_to_canonical.py
───────────────────────────────────────────
Convert a raw Jet2 fare scrape into the canonical flight CSV.

Usage
─────
    python -m scripts.flight_formats.jet2_to_canonical <input.csv> [output.csv] [--date-format uk|us|iso]

Handles Jet2 quirks:
    * Skips 'selected_flight_summary' rows (they duplicate calendar data)
    * Uses Jet2's direction column directly ('out' / 'back')
    * Keeps departure_time / arrival_time / flight_number when present
    * Applies default luggage_kg of 23 (not in raw)
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


CANONICAL_HEADER = [
    "airline", "origin", "destination", "departure_date", "direction",
    "price_gbp", "currency", "flight_number", "departure_time",
    "arrival_time", "passengers_basis", "luggage_kg", "source_url",
    "captured_at",
]


# ─── Field parsers ──────────────────────────────────────────────────
def parse_date(value: str, fmt: str = "uk") -> str | None:
    s = (value or "").strip()
    if not s:
        return None
    if fmt == "iso":
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    if fmt == "uk":
        patterns = ("%d/%m/%Y", "%d/%m/%y")
    elif fmt == "us":
        patterns = ("%m/%d/%Y", "%m/%d/%y")
    else:
        raise ValueError(f"unknown date format: {fmt!r}")
    for pattern in patterns:
        try:
            return datetime.strptime(s, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def parse_price(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    try:
        return f"{Decimal(s):.2f}"
    except (InvalidOperation, ValueError):
        return ""


def parse_time(value: str) -> str:
    """Normalise to HH:MM or empty string."""
    s = (value or "").strip()
    if not s:
        return ""
    parts = s.split(":")
    if len(parts) != 2:
        return ""
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return ""
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return ""
    return f"{h:02d}:{m:02d}"


def truncate(value: str, length: int) -> str:
    s = (value or "").strip()
    return s[:length] if len(s) > length else s


def is_summary_row(raw: dict) -> bool:
    return (raw.get("record_type") or "").strip().lower() == "selected_flight_summary"


# ─── Row transform ──────────────────────────────────────────────────
def transform_row(raw: dict, date_format: str = "uk") -> dict | None:
    if is_summary_row(raw):
        return None

    airline = (raw.get("airline") or "Jet2").strip()
    origin = (raw.get("origin_airport") or "").strip().upper()
    destination = (raw.get("destination_airport") or "").strip().upper()
    direction = (raw.get("direction") or "").strip().lower()

    if not airline or not origin or not destination:
        return None
    if direction not in {"out", "back"}:
        return None

    iso_date = parse_date(raw.get("departure_date", ""), date_format)
    if iso_date is None:
        return None

    price = parse_price(raw.get("price_gbp", ""))
    if not price:
        return None

    return {
        "airline":          airline,
        "origin":           origin,
        "destination":      destination,
        "departure_date":   iso_date,
        "direction":        direction,
        "price_gbp":        price,
        "currency":         "GBP",
        "flight_number":    (raw.get("flight_number") or "").strip(),
        "departure_time":   parse_time(raw.get("departure_time", "")),
        "arrival_time":     parse_time(raw.get("arrival_time", "")),
        "passengers_basis": truncate(raw.get("passengers", ""), 50),
        "luggage_kg":       "23",
        "source_url":       "",
        "captured_at":      (raw.get("captured_at_utc") or "").strip(),
    }


# ─── File-level conversion ──────────────────────────────────────────
def convert(input_path: Path, output_path: Path, date_format: str = "uk") -> tuple[int, int]:
    read_count = 0
    written_count = 0

    with input_path.open("r", encoding="utf-8-sig", newline="") as f_in, \
         output_path.open("w", encoding="utf-8", newline="") as f_out:

        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=CANONICAL_HEADER)
        writer.writeheader()

        for raw in reader:
            read_count += 1
            canonical = transform_row(raw, date_format=date_format)
            if canonical is None:
                continue
            writer.writerow(canonical)
            written_count += 1

    return read_count, written_count


# ─── CLI entry point ────────────────────────────────────────────────
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Convert raw Jet2 CSV to canonical format.",
    )
    parser.add_argument("input", help="Path to raw Jet2 CSV")
    parser.add_argument("output", nargs="?",
                        help="Output path (default: <input>_canonical.csv)")
    parser.add_argument(
        "--date-format",
        choices=["uk", "us", "iso"],
        default="uk",
        help="Date format in raw CSV (default: uk = D/M/YYYY)",
    )
    args = parser.parse_args(argv[1:])

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}")
        return 2

    output_path = Path(args.output) if args.output else \
        input_path.with_name(input_path.stem + "_canonical.csv")

    read_count, written_count = convert(input_path, output_path,
                                        date_format=args.date_format)

    print(f"Input:        {input_path}")
    print(f"Output:       {output_path}")
    print(f"Date format:  {args.date_format}")
    print(f"Rows read:    {read_count}")
    print(f"Rows written: {written_count}")
    print(f"Skipped:      {read_count - written_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
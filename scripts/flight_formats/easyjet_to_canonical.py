"""
scripts/flight_formats/easyjet_to_canonical.py
──────────────────────────────────────────────
Convert raw EasyJet CSV to canonical flight CSV.

Notes
─────
* The raw EasyJet scraper has its headers swapped:
  it says 'destination' but the value is really the origin, and vice versa.
  This transformer corrects the swap at read time.
* Date format is auto-detected (US by default for this scraper).
* Extra columns (price_basis, source_url) are dropped by default.
  Use --keep-extras to include them.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from scripts.flight_formats._date_format import detect_format


CANONICAL_HEADER = [
    "airline", "origin", "destination", "departure_date", "direction",
    "price_gbp", "currency",
]

CANONICAL_HEADER_EXTRAS = [
    "airline", "origin", "destination", "departure_date", "direction",
    "price_gbp", "currency", "flight_number", "departure_time",
    "arrival_time", "passengers_basis", "luggage_kg", "source_url",
    "captured_at",
]


def parse_date(value: str, fmt: str = "uk") -> str | None:
    s = (value or "").strip()
    if not s:
        return None
    if fmt == "iso":
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    patterns = ("%d/%m/%Y", "%d/%m/%y") if fmt == "uk" else ("%m/%d/%Y", "%m/%d/%y")
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


def transform_row(raw: dict, date_format: str = "us", keep_extras: bool = False) -> dict | None:
    """
    Map one raw row to canonical shape.

    Raw header (as written by scraper, WRONG labels):
        airline, destination, origin_airport, ...
    Actual data:
        airline, LGW,         HRG,            ...
    So we read column 'destination' as ORIGIN and 'origin_airport' as DESTINATION.
    """
    airline = (raw.get("airline") or "").strip()

    # NOTE: labels are swapped in the source file — correct them here.
    origin = (raw.get("destination") or "").strip().upper()
    destination = (raw.get("origin_airport") or "").strip().upper()

    if not airline or not origin or not destination:
        return None

    iso_date = parse_date(raw.get("departure_date", ""), date_format)
    if iso_date is None:
        return None

    price = parse_price(raw.get("price_gbp", ""))
    if not price:
        return None

    # Direction: LGW -> elsewhere = out; elsewhere -> LGW = back
    if origin == "LGW" and destination != "LGW":
        direction = "out"
    elif destination == "LGW" and origin != "LGW":
        direction = "back"
    else:
        direction = "out"

    row = {
        "airline":        airline,
        "origin":         origin,
        "destination":    destination,
        "departure_date": iso_date,
        "direction":      direction,
        "price_gbp":      price,
        "currency":       "GBP",
    }

    if keep_extras:
        row.update({
            "flight_number":    "",
            "departure_time":   "",
            "arrival_time":     "",
            "passengers_basis": (raw.get("price_basis") or "").strip()[:50],
            "luggage_kg":       "23",
            "source_url":       (raw.get("source_url") or "").strip(),
            "captured_at":      (raw.get("captured_at_utc") or "").strip(),
        })

    return row


def convert(input_path: Path, output_path: Path,
            date_format: str = "us", keep_extras: bool = False) -> tuple[int, int]:
    read_count = 0
    written_count = 0

    header = CANONICAL_HEADER_EXTRAS if keep_extras else CANONICAL_HEADER

    with input_path.open("r", encoding="utf-8-sig", newline="") as f_in, \
         output_path.open("w", encoding="utf-8", newline="") as f_out:

        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=header)
        writer.writeheader()

        for raw in reader:
            read_count += 1
            canonical = transform_row(raw, date_format=date_format, keep_extras=keep_extras)
            if canonical is None:
                continue
            writer.writerow(canonical)
            written_count += 1

    return read_count, written_count


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Convert raw EasyJet CSV to canonical format.",
    )
    parser.add_argument("input", help="Path to raw EasyJet CSV")
    parser.add_argument("output", nargs="?",
                        help="Output path (default: <input>_canonical.csv)")
    parser.add_argument(
        "--date-format",
        choices=["auto", "uk", "us", "iso"],
        default="auto",
        help="Date format (default: auto-detect)",
    )
    parser.add_argument(
        "--keep-extras",
        action="store_true",
        help="Include flight_number, times, passengers_basis, luggage_kg, source_url, captured_at",
    )
    args = parser.parse_args(argv[1:])

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}")
        return 2

    output_path = Path(args.output) if args.output else \
        input_path.with_name(input_path.stem + "_canonical.csv")

    date_format = args.date_format
    if date_format == "auto":
        try:
            with input_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                raw_dates = [row.get("departure_date", "") for row in reader]
            detected, reason = detect_format(raw_dates)
            date_format = detected
            print(f"[auto-detect] {reason}")
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 3

    read_count, written_count = convert(input_path, output_path,
                                        date_format=date_format,
                                        keep_extras=args.keep_extras)

    print(f"Input:        {input_path}")
    print(f"Output:       {output_path}")
    print(f"Date format:  {date_format}")
    print(f"Extras:       {'yes' if args.keep_extras else 'no'}")
    print(f"Rows read:    {read_count}")
    print(f"Rows written: {written_count}")
    print(f"Skipped:      {read_count - written_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
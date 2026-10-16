"""
scripts/flight_formats/_date_format.py
──────────────────────────────────────
Auto-detect date format from a list of raw date strings.

Public API
──────────
    detect_format(values) -> ("uk" | "us" | "iso", reason)
        raises ValueError if mixed or unknown

Rules
─────
* Any value matches YYYY-MM-DD              -> "iso"
* Any first part > 12 (and no ISO)          -> "uk"  (D/M/YYYY)
* Any second part > 12 (and no ISO)         -> "us"  (M/D/YYYY)
* Both first>12 and second>12 present       -> ValueError (mixed)
* All parts <= 12, D/M and M/D both valid   -> ValueError (ambiguous)
"""

from __future__ import annotations


def _split_date(value: str) -> tuple[int, int, str]:
    """
    Return (a, b, sep) where a and b are ints from the first two parts.

    Returns (0, 0, "iso") for ISO dates.
    Raises ValueError if the string isn't a recognisable date.
    """
    s = (value or "").strip().strip('"')
    if not s:
        raise ValueError("empty")

    if "-" in s:
        return 0, 0, "iso"

    if "/" in s:
        sep = "/"
    elif "." in s:
        sep = "."
    else:
        raise ValueError(f"unrecognised date: {s!r}")

    parts = s.split(sep)
    if len(parts) < 2:
        raise ValueError(f"unrecognised date: {s!r}")

    try:
        a = int(parts[0])
        b = int(parts[1])
    except ValueError:
        raise ValueError(f"non-numeric date parts: {s!r}")

    return a, b, sep


def detect_format(values: list[str]) -> tuple[str, str]:
    """
    Return (format, reason) where format is "uk", "us", or "iso".

    Raises ValueError if the values are mixed or ambiguous.
    """
    if not values:
        raise ValueError("no dates to inspect")

    has_iso = False
    first_over_12 = 0
    second_over_12 = 0
    total = 0

    for raw in values:
        try:
            a, b, sep = _split_date(raw)
        except ValueError:
            continue

        total += 1

        if sep == "iso":
            has_iso = True
            continue

        if a > 12:
            first_over_12 += 1

        if b > 12:
            second_over_12 += 1

    if total == 0:
        raise ValueError("no recognisable dates found in file")

    if has_iso and (first_over_12 or second_over_12):
        raise ValueError(
            "file mixes ISO dates with slash-formatted dates — "
            "please standardise to one format"
        )

    if has_iso:
        return "iso", f"all {total} dates are ISO (YYYY-MM-DD)"

    if first_over_12 and second_over_12:
        raise ValueError(
            "file contains BOTH US-style (second>12) and UK-style "
            "(first>12) dates — cannot auto-detect. "
            "Pass --date-format explicitly."
        )

    if first_over_12:
        return "uk", f"{first_over_12}/{total} dates prove UK format (first part > 12)"

    if second_over_12:
        return "us", f"{second_over_12}/{total} dates prove US format (second part > 12)"

    raise ValueError(
        f"all {total} dates are ambiguous (both parts <= 12). "
        "Cannot auto-detect — pass --date-format uk|us|iso explicitly."
    )


__all__ = ["detect_format"]
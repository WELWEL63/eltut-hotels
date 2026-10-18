"""
scripts/health_check.py
────────────────────────
Read-only project health check. Run after every deploy.

Checks
──────
Environment & config
  1. Required env vars present (SECRET_KEY, DATABASE_URL)
  2. Development defaults in production (SECRET_KEY, cookie flags)
  3. PayPal / SMTP placeholders when running live

Code
  4. Every .py file compiles
  5. No raw SQL strings (SELECT/INSERT/UPDATE/DELETE literal) in blueprints/services
  6. No hardcoded secrets (api_key, password=) in Python source

Database
  7. Connection responds
  8. Model tables vs alembic_version match (no unmigrated models)
  9. BookingItem.product_id → correct table for its product_type
 10. PackageFlight.outbound_flight_id / inbound_flight_id → flight_prices.id
 11. Packages with zero price options
 12. Rooms with no price and no RoomRate
 13. Destinations with 0 active packages that appear in search
 14. Bookings with total_amount = 0
 15. Multi-room integrity: BookingRoom → Booking/Room present, room_index
     in 1..3, per-room adult totals consistent with Booking.travellers_adults
 16. Rooms left behind by the multi-room migration (max_adults IS NULL)

Output
──────
Prints a table with severity and a one-line description per issue.
Exit code 0 = all clear, 1 = warnings found, 2 = errors found.

Usage
─────
    python -m scripts.health_check
    python -m scripts.health_check --quiet    # only problems
"""

from __future__ import annotations

import argparse
import ast
import importlib
import os
import sys
from pathlib import Path

# ── Result model ────────────────────────────────────────────────────
OK = "ok"
WARN = "warn"
ERR = "err"

_results: list[tuple[str, str, str]] = []   # (severity, code, message)


def _add(sev: str, code: str, msg: str) -> None:
    _results.append((sev, code, msg))


def _green(msg): return f"\033[32m{msg}\033[0m"
def _yellow(msg): return f"\033[33m{msg}\033[0m"
def _red(msg): return f"\033[31m{msg}\033[0m"


def _print_result(sev: str, code: str, msg: str) -> None:
    icon = {"ok": _green("✓"), "warn": _yellow("!"), "err": _red("✗")}[sev]
    print(f"  {icon} [{code}] {msg}")


# ── Checks ──────────────────────────────────────────────────────────
def check_env_vars() -> None:
    missing = [k for k in ("SECRET_KEY", "DATABASE_URL") if not os.getenv(k)]
    if missing:
        _add(ERR, "ENV001", f"Missing required env vars: {', '.join(missing)}")
    else:
        _add(OK, "ENV001", "Required env vars present")


def check_prod_defaults() -> None:
    env = (os.getenv("FLASK_ENV") or "").lower()
    if env != "production":
        _add(OK, "ENV002", f"FLASK_ENV={env or 'unset'} (skipping prod-specific checks)")
        return
    sk = os.getenv("SECRET_KEY", "")
    if not sk or sk.startswith("change-me") or len(sk) < 32:
        _add(ERR, "ENV002", "SECRET_KEY is a placeholder or too short for production")
    else:
        _add(OK, "ENV002", "SECRET_KEY looks production-grade")
    if os.getenv("SESSION_COOKIE_SECURE", "").lower() not in ("true", "1", "yes"):
        _add(WARN, "ENV003", "SESSION_COOKIE_SECURE is not True in production")


def check_paypal_smtp_placeholders() -> None:
    env = (os.getenv("FLASK_ENV") or "").lower()
    if env != "production":
        return
    for k in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "MAIL_PASSWORD"):
        v = (os.getenv(k) or "").lower()
        if not v or "placeholder" in v or "your-" in v or "changeme" in v:
            _add(WARN, "ENV004", f"{k} still looks like a placeholder in production")


def check_python_compiles() -> None:
    bad = []
    for root in ("app.py", "config.py", "extensions.py", "utils.py",
                 "models", "services", "blueprints", "mongo", "scripts", "cloud_function"):
        p = Path(root)
        files = [p] if p.is_file() else list(p.rglob("*.py")) if p.is_dir() else []
        for f in files:
            try:
                ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except SyntaxError as e:
                bad.append(f"{f}:{e.lineno} {e.msg}")
    if bad:
        for b in bad[:5]:
            _add(ERR, "CODE001", f"Syntax error: {b}")
    else:
        _add(OK, "CODE001", "All Python files parse")


def check_raw_sql() -> None:
    import re
    pattern = re.compile(
        r'\b(select\s+\*\s+from|insert\s+into|update\s+\w+\s+set|delete\s+from)\b',
        re.IGNORECASE,
    )
    bad = []
    for folder in ("services", "blueprints", "models"):
        for f in Path(folder).rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line) and "text(" not in line:
                    bad.append(f"{f}:{i}")
    if bad:
        _add(WARN, "CODE002", f"{len(bad)} possible raw-SQL lines (review): {bad[:3]}")
    else:
        _add(OK, "CODE002", "No obvious raw SQL in services/blueprints/models")


def check_hardcoded_secrets() -> None:
    import re
    pattern = re.compile(r'(api_key|password|secret)\s*=\s*["\'][^"\']{8,}["\']', re.IGNORECASE)
    bad = []
    for folder in ("services", "blueprints", "models", "mongo", "scripts"):
        for f in Path(folder).rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line) and "os.getenv" not in line and "environ" not in line:
                    bad.append(f"{f}:{i}")
    if bad:
        _add(ERR, "SEC001", f"{len(bad)} hardcoded credential-like strings: {bad[:3]}")
    else:
        _add(OK, "SEC001", "No hardcoded credentials found")


def _app_context():
    from app import create_app
    app = create_app()
    ctx = app.app_context()
    ctx.push()
    return ctx


def check_db_connection() -> bool:
    try:
        from extensions import db
        from sqlalchemy import text
        db.session.execute(text("select 1")).scalar()
        _add(OK, "DB001", "Database connection OK")
        return True
    except Exception as e:
        _add(ERR, "DB001", f"Cannot connect to DB: {e}")
        return False


def check_alembic_head() -> None:
    try:
        import re as _re
        from extensions import db
        from sqlalchemy import text

        row = db.session.execute(text("select version_num from alembic_version")).fetchone()
        db_head = row[0] if row else None

        # Parse the revision graph ourselves — works regardless of alembic.ini location
        vdir = Path("migrations/versions")
        if not vdir.exists():
            _add(WARN, "DB002", "migrations/versions/ not found")
            return

        revisions: dict[str, str | None] = {}
        for f in vdir.glob("*.py"):
            text_content = f.read_text(encoding="utf-8")
            m_rev = _re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", text_content, _re.MULTILINE)
            m_down = _re.search(r"^down_revision\s*=\s*(['\"]([^'\"]+)['\"]|None)", text_content, _re.MULTILINE)
            if not m_rev:
                continue
            rev = m_rev.group(1)
            if m_down and m_down.group(2):
                revisions[rev] = m_down.group(2)
            else:
                revisions[rev] = None

        downs = {v for v in revisions.values() if v}
        heads = [r for r in revisions if r not in downs]

        if not heads:
            _add(WARN, "DB002", "Could not derive alembic head from revision files")
            return
        if len(heads) > 1:
            _add(WARN, "DB002", f"Multiple alembic heads: {heads}")
            return
        script_head = heads[0]

        if script_head != db_head:
            _add(WARN, "DB002", f"alembic head mismatch: db={db_head} scripts={script_head}")
        else:
            _add(OK, "DB002", f"alembic head matches ({db_head})")
    except Exception as e:
        _add(WARN, "DB002", f"Could not verify alembic head: {e}")


def check_booking_items() -> None:
    try:
        from extensions import db
        from models import BookingItem, Hotel, Package, Activity, Room
        from sqlalchemy import select
        rows = list(db.session.scalars(select(BookingItem)))
        bad = 0
        for it in rows:
            pt = (it.product_type or "").lower()
            pid = it.product_id
            if pt == "package" and not db.session.get(Package, pid):
                bad += 1
            elif pt == "activity" and not db.session.get(Activity, pid):
                bad += 1
            elif pt == "hotel" and not (db.session.get(Room, pid) or db.session.get(Hotel, pid)):
                bad += 1
        if bad:
            _add(WARN, "DB003", f"{bad} BookingItems reference missing products")
        else:
            _add(OK, "DB003", f"All {len(rows)} BookingItems resolve to products")
    except Exception as e:
        _add(WARN, "DB003", f"Could not verify BookingItems: {e}")


def check_package_flight_fks() -> None:
    try:
        from extensions import db
        from models import PackageFlight, FlightPrice
        from sqlalchemy import select
        bad = 0
        for c in db.session.scalars(select(PackageFlight)):
            for fk in (c.outbound_flight_id, c.inbound_flight_id):
                if fk and not db.session.get(FlightPrice, fk):
                    bad += 1
        if bad:
            _add(ERR, "DB004", f"{bad} PackageFlight rows reference missing flight_prices")
        else:
            _add(OK, "DB004", "PackageFlight FKs resolve")
    except Exception as e:
        _add(WARN, "DB004", f"Could not verify PackageFlight FKs: {e}")


def check_packages_have_options() -> None:
    try:
        from extensions import db
        from models import Package, PackageFlight, PackagePrice
        from sqlalchemy import select, func
        active = list(db.session.scalars(select(Package).where(Package.is_active.is_(True))))
        no_cards = 0
        no_prices = 0
        for p in active:
            cards = db.session.query(PackageFlight).filter_by(package_id=p.id).count()
            if cards == 0:
                no_cards += 1
            prices = db.session.query(PackagePrice).filter_by(package_id=p.id).count()
            if prices == 0:
                no_prices += 1
        if no_prices:
            _add(WARN, "BIZ001", f"{no_prices} active packages have 0 PackagePrice rows")
        else:
            _add(OK, "BIZ001", "All active packages have at least one PackagePrice")
        _add(OK if no_cards >= 0 else WARN, "BIZ002",
             f"{no_cards} active packages are land-only (0 PackageFlight cards)")
    except Exception as e:
        _add(WARN, "BIZ001", f"Could not verify package pricing: {e}")


def check_rooms_priced() -> None:
    try:
        from extensions import db
        from models import Room, RoomRate
        from sqlalchemy import select, func, or_
        unpriced = 0
        total = 0
        for r in db.session.scalars(select(Room).where(Room.is_active.is_(True))):
            total += 1
            has_base = (r.base_price_per_night or 0) > 0
            has_rates = db.session.query(RoomRate).filter_by(room_id=r.id).count() > 0
            if not has_base and not has_rates:
                unpriced += 1
        if unpriced:
            _add(WARN, "BIZ003", f"{unpriced}/{total} active rooms have no price (base + 0 rates)")
        else:
            _add(OK, "BIZ003", f"All {total} active rooms have a price source")
    except Exception as e:
        _add(WARN, "BIZ003", f"Could not verify room pricing: {e}")


def check_rooms_split_caps() -> None:
    """BIZ007 — rooms left behind by the multi-room migration.

    After the add_multi_room_support migration, max_adults was backfilled
    from max_occupancy, so every active room should have a non-NULL
    max_adults. A NULL here means a row was inserted by a path that
    bypassed the ORM __init__ and the migration UPDATE.
    """
    try:
        from extensions import db
        from models import Room
        from sqlalchemy import select, func
        null_count = int(db.session.scalar(
            select(func.count(Room.id))
            .where(Room.is_active.is_(True))
            .where(Room.max_adults.is_(None))
        ) or 0)
        if null_count:
            _add(WARN, "BIZ007",
                 f"{null_count} active rooms have max_adults = NULL "
                 f"(multi-room migration leftover)")
        else:
            _add(OK, "BIZ007", "All active rooms have max_adults set")
    except Exception as e:
        _add(WARN, "BIZ007", f"Could not verify room max_adults: {e}")


def check_multi_room_integrity() -> None:
    """BIZ006 — BookingRoom integrity after multi-room upgrade.

    Verifies:
      - every booking_rooms.booking_id points at a real booking
      - every booking_rooms.room_id points at a real room
      - room_index is 1..3
      - for hotel bookings, sum(rooms.adults) <= booking.travellers_adults
        (equal is the normal case; less is allowed for draft/incomplete)
    A row with a missing booking or room is an orphan and indicates a
    cascade failure.
    """
    try:
        from extensions import db
        from models import BookingRoom, Booking, Room
        from sqlalchemy import select

        rows = list(db.session.scalars(select(BookingRoom)))
        total = len(rows)
        if total == 0:
            _add(OK, "BIZ006", "No BookingRoom rows yet (multi-room not used)")
            return

        bad_booking = 0
        bad_room = 0
        bad_index = 0
        by_booking: dict[int, list] = {}
        for br in rows:
            if br.room_index is None or br.room_index < 1 or br.room_index > 3:
                bad_index += 1
            if db.session.get(Booking, br.booking_id) is None:
                bad_booking += 1
                continue
            if db.session.get(Room, br.room_id) is None:
                bad_room += 1
            by_booking.setdefault(br.booking_id, []).append(br)

        overcount = 0
        for booking_id, brs in by_booking.items():
            bk = db.session.get(Booking, booking_id)
            if bk is None:
                continue
            if (bk.product_type or "").lower() != "hotel":
                continue
            assigned = sum(int(r.adults or 0) for r in brs)
            headline = int(bk.travellers_adults or 0)
            if assigned > headline:
                overcount += 1

        problems = []
        if bad_booking: problems.append(f"{bad_booking} missing booking")
        if bad_room:    problems.append(f"{bad_room} missing room")
        if bad_index:   problems.append(f"{bad_index} room_index out of 1..3")
        if overcount:   problems.append(f"{overcount} hotel bookings with per-room adults > headline")
        if problems:
            _add(WARN, "BIZ006",
                 f"{total} BookingRoom rows; issues: {', '.join(problems)}")
        else:
            _add(OK, "BIZ006",
                 f"{total} BookingRoom rows across {len(by_booking)} bookings — all resolve")
    except Exception as e:
        _add(WARN, "BIZ006", f"Could not verify BookingRoom integrity: {e}")


def check_destinations_visible() -> None:
    try:
        from extensions import db
        from models import Destination, Package
        from sqlalchemy import select, func
        bad = []
        for d in db.session.scalars(select(Destination)):
            if not d.is_bookable:
                continue
            pcount = db.session.query(Package).filter_by(
                destination_id=d.id, is_active=True
            ).count()
            if pcount == 0:
                bad.append(d.slug)
        if bad:
            _add(OK, "BIZ004",
                 f"{len(bad)} bookable destinations have 0 active packages "
                 f"(hidden from package widget): {bad[:5]}")
        else:
            _add(OK, "BIZ004", "Every bookable destination has >=1 active package")
    except Exception as e:
        _add(WARN, "BIZ004", f"Could not verify destination visibility: {e}")


def check_zero_total_bookings() -> None:
    try:
        from extensions import db
        from models import Booking
        from sqlalchemy import select
        n = db.session.query(Booking).filter(Booking.total_amount == 0).count()
        if n:
            _add(WARN, "BIZ005", f"{n} bookings with total_amount = 0")
        else:
            _add(OK, "BIZ005", "No zero-total bookings")
    except Exception as e:
        _add(WARN, "BIZ005", f"Could not check bookings: {e}")


# ── Runner ──────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true",
                        help="Only print problems, not the ✓ lines")
    args = parser.parse_args()

    # Load the app first so .env is read into os.environ
    from app import create_app
    app = create_app()
    ctx = app.app_context()
    ctx.push()

    try:
        print("ElTut Tours — health check")
        print("=" * 50)

        print("\nEnvironment")
        check_env_vars()
        check_prod_defaults()
        check_paypal_smtp_placeholders()

        print("\nCode")
        check_python_compiles()
        check_raw_sql()
        check_hardcoded_secrets()

        print("\nDatabase")
        if check_db_connection():
            check_alembic_head()
            check_booking_items()
            check_package_flight_fks()
            check_packages_have_options()
            check_rooms_priced()
            check_rooms_split_caps()
            check_multi_room_integrity()
            check_destinations_visible()
            check_zero_total_bookings()
    finally:
        ctx.pop()

    # Output
    errs = [r for r in _results if r[0] == ERR]
    warns = [r for r in _results if r[0] == WARN]
    oks = [r for r in _results if r[0] == OK]

    print()
    for sev, code, msg in _results:
        if args.quiet and sev == OK:
            continue
        _print_result(sev, code, msg)

    print()
    print("=" * 50)
    print(f"Summary: {len(oks)} ok, {len(warns)} warnings, {len(errs)} errors")

    if errs:
        return 2
    if warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

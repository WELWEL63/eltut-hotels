"""
scripts/reset_db.py
───────────────────
Development helper: wipe the SQL database and optionally re-seed.

USAGE
    python -m scripts.reset_db --truncate --yes
        Delete all rows from every table (fast). Schema untouched.

    python -m scripts.reset_db --drop --yes
        Drop every table, then recreate it from the current models.
        Slower but cleans up stale indexes / constraints.

    python -m scripts.reset_db --truncate --yes --with-seed --with-admin
        Wipe, re-seed from CSVs, and re-create the admin account in one go.

    python -m scripts.reset_db --truncate
        DRY RUN — prints what would happen, does nothing. (No --yes.)

SAFETY
    - Requires --yes to actually do anything. Without it, prints a
      description and exits.
    - Refuses to run in production (FLASK_ENV=production) unless
      --confirm-prod is also passed.
    - SQL ONLY. Mongo collections (reviews, search_events, logs, etc.)
      are managed by their own TTL indexes and are NOT touched.

ORDERING
    Tables are dropped in reverse-dependency order using SQLAlchemy's
    sorted_tables so foreign keys do not block DROP TABLE.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys

from sqlalchemy import text

from app import create_app
from extensions import db
from models import Base


log = logging.getLogger("reset_db")


def _configure_logging() -> None:
    if log.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        )
    )
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def _truncate_all(app) -> None:
    """DELETE FROM every table in reverse-dependency order."""
    # sorted_tables gives us tables in dependency order (parents first).
    # Reverse gives us children first so FK constraints don't complain.
    tables = list(reversed(Base.metadata.sorted_tables))
    log.info("Truncating %d tables ...", len(tables))
    with app.app_context():
        with db.engine.begin() as conn:
            # Disable FK checks per-session for Postgres? Not needed if we
            # delete in the right order, but wrapping in one transaction
            # with ON DELETE CASCADE handles edge cases.
            for t in tables:
                # TRUNCATE ... RESTART IDENTITY CASCADE resets sequences and
                # cascades to any FK references — the fastest way to wipe.
                conn.execute(
                    text(
                        f'TRUNCATE TABLE "{t.name}" '
                        "RESTART IDENTITY CASCADE"
                    )
                )
                log.info("  truncated %s", t.name)


def _drop_and_recreate(app) -> None:
    """Drop every table, then create from the current models."""
    with app.app_context():
        log.info("Dropping all tables ...")
        Base.metadata.drop_all(bind=db.engine)
        log.info("Recreating all tables from models ...")
        Base.metadata.create_all(bind=db.engine)
        log.info("Recreated %d tables", len(Base.metadata.tables))


def _run_subprocess(module: str, *args: str) -> None:
    """Run another script as a subprocess so it gets a clean app instance."""
    cmd = [sys.executable, "-m", module, *args]
    log.info("running: %s", " ".join(cmd))
    rc = subprocess.run(cmd, check=False).returncode
    if rc != 0:
        log.error("%s exited with code %d", module, rc)
        sys.exit(rc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset eltut-tours SQL database")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--truncate",
        action="store_true",
        help="DELETE all rows from every table (fast, keeps schema)",
    )
    mode.add_argument(
        "--drop",
        action="store_true",
        help="DROP all tables and recreate from models (slower, cleaner)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required to actually execute; without it, does a dry run",
    )
    parser.add_argument(
        "--with-seed",
        action="store_true",
        help="after reset, run scripts.seed_from_csv",
    )
    parser.add_argument(
        "--with-admin",
        action="store_true",
        help="after reset, run scripts.create_admin",
    )
    parser.add_argument(
        "--confirm-prod",
        action="store_true",
        help="extra guard required when FLASK_ENV=production",
    )
    args = parser.parse_args()

    _configure_logging()

    env = os.getenv("FLASK_ENV", "development").lower()
    if env == "production" and not args.confirm_prod:
        log.error(
            "refusing to run in production without --confirm-prod"
        )
        sys.exit(2)

    mode_name = "TRUNCATE" if args.truncate else "DROP + RECREATE"

    if not args.yes:
        log.info("DRY RUN — would %s all tables.", mode_name)
        log.info("Pass --yes to actually execute.")
        if args.with_seed:
            log.info("  then run scripts.seed_from_csv")
        if args.with_admin:
            log.info("  then run scripts.create_admin")
        return

    app = create_app()

    if args.truncate:
        _truncate_all(app)
    else:
        _drop_and_recreate(app)

    log.info("Reset complete.")

    if args.with_seed:
        _run_subprocess("scripts.seed_from_csv", "--file", "all")
    if args.with_admin:
        _run_subprocess("scripts.create_admin")


if __name__ == "__main__":
    main()

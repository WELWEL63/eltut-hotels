"""
scripts/create_admin.py
───────────────────────
Create (or reset) the admin account for the eltut-tours-platform.

Reads ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME from .env by default, but
every value can be overridden via CLI flags.

USAGE
    python -m scripts.create_admin
        Create or update the admin using .env values.
        Existing admin: name/role/active/verified are refreshed, password
        is NOT touched.

    python -m scripts.create_admin --force
        Same, but the password is reset even if the account exists.

    python -m scripts.create_admin --role customer \\
        --email test@example.com --password Test1234 --name "Test User"
        Create a customer account (useful for testing the public site).

    python -m scripts.create_admin --delete --email test@example.com
        Delete an account by email (handy during development).

DESIGN NOTES
    - Password hashing uses User.set_password() which uses bcrypt with
      BCRYPT_ROUNDS=12 (same as the login flow).
    - Idempotent: running twice does not create duplicates — the second
      run updates the existing row.
    - Uses the same app factory / SQLAlchemy session as the rest of the
      app, so `.env` config and Neon connection are reused.
    - No Flask request context needed — runs purely in the CLI.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import create_app
from extensions import db
from models import User, ROLE_ADMIN, ROLE_CUSTOMER


log = logging.getLogger("create_admin")


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


def _validate_email(email: str) -> str:
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError(f"invalid email: {email!r}")
    return email.strip().lower()


def _validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    if not re.search(r"[A-Z]", password):
        raise ValueError("password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("password must contain at least one digit")
    return password


def _validate_role(role: str) -> str:
    if role not in (ROLE_ADMIN, ROLE_CUSTOMER):
        raise ValueError(f"role must be '{ROLE_ADMIN}' or '{ROLE_CUSTOMER}'")
    return role


def _upsert_user(
    session: Session,
    *,
    email: str,
    password: str,
    name: str,
    role: str,
    force_password: bool,
) -> tuple[User, str]:
    """Create or update a user. Returns (user, action) where action is
    'created', 'updated', or 'unchanged'."""
    existing = session.scalar(select(User).where(User.email == email))
    if existing is None:
        user = User(
            email=email,
            full_name=name,
            role=role,
            is_active=True,
            is_verified=True,
        )
        user.set_password(password)
        session.add(user)
        session.flush()
        return user, "created"

    # Update non-password fields
    changed = False
    if existing.full_name != name:
        existing.full_name = name
        changed = True
    if existing.role != role:
        existing.role = role
        changed = True
    if not existing.is_active:
        existing.is_active = True
        changed = True
    if not existing.is_verified:
        existing.is_verified = True
        changed = True

    if force_password:
        existing.set_password(password)
        changed = True

    return existing, "updated" if changed else "unchanged"


def _delete_user(session: Session, email: str) -> bool:
    existing = session.scalar(select(User).where(User.email == email))
    if existing is None:
        return False
    session.delete(existing)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or reset a user account for eltut-tours-platform"
    )
    parser.add_argument("--email", help="overrides ADMIN_EMAIL from .env")
    parser.add_argument("--password", help="overrides ADMIN_PASSWORD from .env")
    parser.add_argument("--name", help="overrides ADMIN_NAME from .env")
    parser.add_argument(
        "--role",
        default=ROLE_ADMIN,
        choices=[ROLE_ADMIN, ROLE_CUSTOMER],
        help="role for the account (default: admin)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="reset the password even if the account already exists",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="delete the account instead of creating/updating it",
    )
    args = parser.parse_args()

    email = args.email or os.getenv("ADMIN_EMAIL")
    password = args.password or os.getenv("ADMIN_PASSWORD")
    name = args.name or os.getenv("ADMIN_NAME", "ElTut Admin")

    if not email:
        log.error("no email provided (set ADMIN_EMAIL in .env or use --email)")
        sys.exit(1)
    if not args.delete and not password:
        log.error(
            "no password provided (set ADMIN_PASSWORD in .env or use --password)"
        )
        sys.exit(1)

    try:
        email = _validate_email(email)
        if not args.delete:
            _validate_password(password)  # type: ignore[arg-type]
        role = _validate_role(args.role)
    except ValueError as exc:
        log.error(str(exc))
        sys.exit(1)

    app = create_app()
    _configure_logging()
    with app.app_context():
        session: Session = db.session
        try:
            if args.delete:
                deleted = _delete_user(session, email)
                session.commit()
                if deleted:
                    log.info("deleted user %s", email)
                else:
                    log.warning("no user found with email %s", email)
                return

            user, action = _upsert_user(
                session,
                email=email,
                password=password,  # type: ignore[arg-type]
                name=name,
                role=role,
                force_password=args.force,
            )
            session.commit()
            log.info("%s %s user id=%s role=%s", action, email, user.id, user.role)
        except Exception:
            session.rollback()
            log.exception("failed")
            sys.exit(1)


if __name__ == "__main__":
    main()

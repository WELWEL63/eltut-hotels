"""
models/user.py
──────────────
The users table — the anchor of auth, roles, and everything that
references a person (bookings, reviews, enquiries, activity logs).

DESIGN NOTES
    - Roles are a string column with a CHECK constraint, not a Python Enum,
      so adding new roles later ("guide", "supplier_contact") does not
      require a Postgres type migration.
    - Passwords and reset/verification tokens are stored as bcrypt hashes,
      never as plaintext. The `raw` value only ever lives in memory or in
      an outbound email.
    - Email is stored lowercased and enforced unique, so logins are
      case-insensitive without needing a functional index.
    - `is_active` is a DB column (admin togglable). Flask-Login reads it
      via UserMixin. It is distinct from `is_verified`, which reflects
      email confirmation.
    - Instance defaults (role, is_active, is_verified) are set in __init__
      as well as via SQLAlchemy `default=`, so freshly constructed
      (unsaved) instances behave the same as DB-loaded ones.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from flask_login import UserMixin
from sqlalchemy import Boolean, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
ROLE_CUSTOMER: str = "customer"
ROLE_ADMIN: str = "admin"
VALID_ROLES: tuple[str, ...] = (ROLE_CUSTOMER, ROLE_ADMIN)

BCRYPT_ROUNDS: int = 12


class User(Base, TimestampMixin, UserMixin):
    """A registered account (customer or admin)."""

    __tablename__ = "users"
    __table_args__ = (
        # NB: constraint name is SUFFIX-only. The metadata naming convention
        # in models/__init__.py adds the "ck_<table>_" prefix, producing
        # ck_users_role_check.
        CheckConstraint(
            "role IN ('customer', 'admin')",
            name="role_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)

    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ROLE_CUSTOMER,
        server_default=ROLE_CUSTOMER,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    verification_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)

    reset_token_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor — apply defaults before SQLAlchemy sets attributes
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        email = kwargs.get("email")
        if isinstance(email, str):
            kwargs["email"] = email.strip().lower()

        kwargs.setdefault("role", ROLE_CUSTOMER)
        kwargs.setdefault("is_active", True)
        kwargs.setdefault("is_verified", False)

        super().__init__(**kwargs)

    # ═══════════════════════════════════════════════════════════════
    #  Passwords
    # ═══════════════════════════════════════════════════════════════
    def set_password(self, raw_password: str) -> None:
        if not raw_password:
            raise ValueError("Password must not be empty.")
        self.password_hash = bcrypt.hashpw(
            raw_password.encode("utf-8"),
            bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
        ).decode("utf-8")

    def check_password(self, raw_password: str) -> bool:
        if not raw_password or not self.password_hash:
            return False
        try:
            return bcrypt.checkpw(
                raw_password.encode("utf-8"),
                self.password_hash.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False

    # ═══════════════════════════════════════════════════════════════
    #  Reset / verification tokens
    # ═══════════════════════════════════════════════════════════════
    def set_reset_token(self, raw_token: str, ttl_minutes: int = 30) -> None:
        self.reset_token = bcrypt.hashpw(
            raw_token.encode("utf-8"),
            bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
        ).decode("utf-8")
        self.reset_token_expires = datetime.now(timezone.utc).replace(
            microsecond=0
        ) + timedelta(minutes=ttl_minutes)

    def check_reset_token(self, raw_token: str) -> bool:
        if not self.reset_token or self.reset_token_expires is None:
            return False
        if self.reset_token_expires < datetime.now(timezone.utc):
            return False
        try:
            return bcrypt.checkpw(
                raw_token.encode("utf-8"),
                self.reset_token.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False

    def clear_reset_token(self) -> None:
        self.reset_token = None
        self.reset_token_expires = None

    def set_verification_token(self, raw_token: str) -> None:
        self.verification_token = bcrypt.hashpw(
            raw_token.encode("utf-8"),
            bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
        ).decode("utf-8")

    def check_verification_token(self, raw_token: str) -> bool:
        if not self.verification_token:
            return False
        try:
            return bcrypt.checkpw(
                raw_token.encode("utf-8"),
                self.verification_token.encode("utf-8"),
            )
        except (ValueError, TypeError):
            return False

    def clear_verification_token(self) -> None:
        self.verification_token = None
        self.is_verified = True

    # ═══════════════════════════════════════════════════════════════
    #  Role helpers
    # ═══════════════════════════════════════════════════════════════
    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_customer(self) -> bool:
        return self.role == ROLE_CUSTOMER

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role}>"

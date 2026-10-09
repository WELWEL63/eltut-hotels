"""
models/supplier.py
──────────────────
The suppliers table — external vendors that provide services used inside
packages and bookings (airlines, transfer companies, activity operators).

Referenced by flights.supplier_id (nullable — a flight may be listed
without a supplier link, or the supplier may be added later).

DESIGN NOTES
    - `name` is UNIQUE — a supplier is identified by its legal/trading
      name; two rows for the same company would break reporting.
    - `type` is a string with a CHECK constraint over a small known set.
      This is stricter than free-form, easier to report on than an Enum,
      and cheap to extend via a future migration.
    - Contact fields are optional: supplier contacts change often and we
      do not want to force them on every row.
    - `is_active` is a soft-delete flag; historical flights must remain
      readable even if the supplier is no longer used.
    - Instance defaults are applied in __init__ so unsaved instances
      behave the same as DB-loaded ones (see models/user.py).
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
SUPPLIER_TYPE_AIRLINE: str = "airline"
SUPPLIER_TYPE_TRANSFER: str = "transfer"
SUPPLIER_TYPE_ACTIVITY_OPERATOR: str = "activity_operator"
SUPPLIER_TYPE_OTHER: str = "other"

VALID_SUPPLIER_TYPES: tuple[str, ...] = (
    SUPPLIER_TYPE_AIRLINE,
    SUPPLIER_TYPE_TRANSFER,
    SUPPLIER_TYPE_ACTIVITY_OPERATOR,
    SUPPLIER_TYPE_OTHER,
)

DEFAULT_SUPPLIER_TYPE: str = SUPPLIER_TYPE_OTHER


class Supplier(Base, TimestampMixin):
    """
    An external service provider.

    Columns
    -------
    id            : surrogate PK
    name          : unique trading name
    type          : airline | transfer | activity_operator | other (CHECK)
    contact_email : optional contact email
    contact_phone : optional contact phone
    notes         : free-form internal notes (contract terms, hours, ...)
    is_active     : soft-disable flag; keeps history intact
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "suppliers"
    __table_args__ = (
        # Suffix-only; Base.metadata naming convention produces
        # ck_suppliers_type_check
        CheckConstraint(
            "type IN ('airline', 'transfer', 'activity_operator', 'other')",
            name="type_check",
        ),
    )

    # ─── Identity ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(150), unique=True, nullable=False, index=True
    )

    # ─── Classification ────────────────────────────────────────────
    type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DEFAULT_SUPPLIER_TYPE,
        server_default=DEFAULT_SUPPLIER_TYPE,
    )

    # ─── Contact ───────────────────────────────────────────────────
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ─── Internal ──────────────────────────────────────────────────
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── State ─────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default=true(),
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor — normalise + instance defaults
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        """
        Apply defaults and normalise input before SQLAlchemy sets attrs.

        - name, contact_email, contact_phone, type are stripped
        - contact_email is lowercased for reliable lookups
        - type defaults to 'other' if missing OR whitespace-only
        - is_active defaults to True so freshly constructed instances read
          the same as DB-loaded ones
        """
        # Strip every string field INCLUDING type — otherwise "   " passes
        # the truthiness check below and lands in the DB as whitespace.
        for key in ("name", "contact_email", "contact_phone", "type"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        email = kwargs.get("contact_email")
        if isinstance(email, str) and email:
            kwargs["contact_email"] = email.lower()

        # After stripping, treat empty type as missing so the default applies.
        if not kwargs.get("type"):
            kwargs["type"] = DEFAULT_SUPPLIER_TYPE

        kwargs.setdefault("is_active", True)

        super().__init__(**kwargs)

    # ═══════════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════════
    @property
    def is_airline(self) -> bool:
        """Convenience flag — used by report templates that group by type."""
        return self.type == SUPPLIER_TYPE_AIRLINE

    # ─── Cosmetic ──────────────────────────────────────────────────
    def __repr__(self) -> str:  # pragma: no cover
        return f"<Supplier id={self.id} name={self.name!r} type={self.type!r}>"

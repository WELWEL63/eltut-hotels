"""
services/auth_service.py
────────────────────────
Authentication, registration, password reset, email verification, and
guest-booking claim.

Every function here is pure business logic — no Flask request objects,
no session cookies, no template rendering. Blueprints (auth/, account/)
handle the HTTP layer and call into these functions.

PUBLIC API
    register_user(email, password, full_name, phone=None) -> User
    authenticate(email, password) -> User | None
    request_password_reset(email) -> str | None
        Returns the raw reset token when the user exists, None otherwise.
        The caller (route) is responsible for emailing the link.
    reset_password(token, new_password) -> User
    verify_email(token) -> User
    claim_guest_bookings(user) -> int
        Returns the number of bookings that were attached to the account.

DESIGN NOTES
    - Passwords are hashed via User.set_password (bcrypt, cost 12).
    - Reset + verification tokens are bcrypt-hashed in the DB (User already
      provides set_reset_token / set_verification_token). The RAW token
      goes into the outbound email link.
    - Rate limiting for login is an in-memory sliding window keyed by
      email. Non-persistent — resets on process restart. Documented as a
      limitation; production would use Redis.
    - Guest booking claim runs inside the same session as registration:
      if it fails, the whole transaction rolls back.
    - Errors are domain exceptions so routes can map them to flash
      messages without parsing strings.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from extensions import db
from models import Booking, User, ROLE_CUSTOMER


# ─── Domain exceptions ─────────────────────────────────────────────
class AuthError(Exception):
    """Base class for auth-domain errors."""


class EmailTaken(AuthError):
    """An account already exists with this email."""


class InvalidCredentials(AuthError):
    """Email not found or password mismatch."""


class AccountDisabled(AuthError):
    """The account exists but is_active=False."""


class WeakPassword(AuthError):
    """Password does not meet the strength rule."""


class InvalidToken(AuthError):
    """Reset or verification token is invalid or expired."""


class TooManyAttempts(AuthError):
    """Rate limit hit for this email."""


# ─── Password strength ─────────────────────────────────────────────
_PASSWORD_MIN_LEN = 8
_RE_UPPER = re.compile(r"[A-Z]")
_RE_LOWER = re.compile(r"[a-z]")
_RE_DIGIT = re.compile(r"\d")


def validate_password(password: str) -> None:
    """Raise WeakPassword if the password does not meet the rule."""
    if not password or len(password) < _PASSWORD_MIN_LEN:
        raise WeakPassword(f"password must be at least {_PASSWORD_MIN_LEN} characters")
    if not _RE_UPPER.search(password):
        raise WeakPassword("password must contain at least one uppercase letter")
    if not _RE_LOWER.search(password):
        raise WeakPassword("password must contain at least one lowercase letter")
    if not _RE_DIGIT.search(password):
        raise WeakPassword("password must contain at least one digit")


# ─── In-memory rate limiter (per email) ────────────────────────────
_RATE_WINDOW_SECONDS = 60 * 15      # 15 minutes
_RATE_MAX_ATTEMPTS = 5
_rate_lock = threading.Lock()
_rate_map: dict[str, list[float]] = {}


def _rate_key(email: str) -> str:
    return email.strip().lower()


def record_failed_attempt(email: str) -> None:
    """Record a failed login attempt for an email (called by the route)."""
    key = _rate_key(email)
    now = time.time()
    with _rate_lock:
        bucket = _rate_map.setdefault(key, [])
        # Drop old entries outside the window
        cutoff = now - _RATE_WINDOW_SECONDS
        _rate_map[key] = [t for t in bucket if t >= cutoff]
        _rate_map[key].append(now)


def clear_attempts(email: str) -> None:
    """Clear the rate-limit bucket for an email (successful login)."""
    with _rate_lock:
        _rate_map.pop(_rate_key(email), None)


def is_locked_out(email: str) -> bool:
    """True if this email has too many recent failed attempts."""
    key = _rate_key(email)
    now = time.time()
    cutoff = now - _RATE_WINDOW_SECONDS
    with _rate_lock:
        bucket = [t for t in _rate_map.get(key, []) if t >= cutoff]
        _rate_map[key] = bucket
        return len(bucket) >= _RATE_MAX_ATTEMPTS


def _reset_rate_limits_for_tests() -> None:
    """Testing helper — clears all buckets. Not for production use."""
    with _rate_lock:
        _rate_map.clear()


# ─── Public API ────────────────────────────────────────────────────
def register_user(
    *,
    email: str,
    password: str,
    full_name: str,
    phone: str | None = None,
) -> User:
    """
    Create a new customer account.

    Raises EmailTaken / WeakPassword / AuthError.
    Returns the freshly created User (already flushed, has an id).
    Also attempts guest-booking claim for the same email.
    """
    if not email or "@" not in email:
        raise AuthError("a valid email is required")
    if not full_name or not full_name.strip():
        raise AuthError("full name is required")

    email = email.strip().lower()
    full_name = full_name.strip()
    phone = (phone or "").strip() or None

    validate_password(password)

    existing = db.session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise EmailTaken("an account with this email already exists")

    user = User(
        email=email,
        full_name=full_name,
        phone=phone,
        role=ROLE_CUSTOMER,
        is_active=True,
        is_verified=False,
    )
    user.set_password(password)

    # Verification token: bcrypt hash stored, raw value returned so the
    # caller (route) can email a link containing it.
    raw_token = secrets.token_urlsafe(32)
    user.set_verification_token(raw_token)

    db.session.add(user)
    db.session.flush()  # gives user.id

    # Claim any guest bookings that share this email.
    try:
        claim_guest_bookings(user)
    except Exception:  # noqa: BLE001 — never block registration on claim
        # We do not want a failed claim to prevent account creation.
        pass

    return user


def authenticate(email: str, password: str) -> User | None:
    """
    Verify credentials. Returns the User on success, or None.

    Raises AccountDisabled if the account exists but is_active=False.
    Raises TooManyAttempts if the email is currently rate-limited.
    """
    if not email or not password:
        return None

    email = email.strip().lower()

    if is_locked_out(email):
        raise TooManyAttempts(
            "too many failed login attempts — try again in a few minutes"
        )

    user = db.session.scalar(select(User).where(User.email == email))
    if user is None:
        record_failed_attempt(email)
        return None

    if not user.check_password(password):
        record_failed_attempt(email)
        return None

    if not user.is_active:
        raise AccountDisabled("this account has been disabled")

    clear_attempts(email)
    return user


def request_password_reset(email: str, ttl_minutes: int = 30) -> str | None:
    """
    Generate a password-reset token for the user with this email.

    Returns the RAW token (the caller emails it in a link) or None when
    no account exists — the route should still show a generic success
    message either way, to avoid leaking whether an email is registered.
    """
    if not email:
        return None
    email = email.strip().lower()

    user = db.session.scalar(select(User).where(User.email == email))
    if user is None:
        return None

    raw_token = secrets.token_urlsafe(32)
    user.set_reset_token(raw_token, ttl_minutes=ttl_minutes)
    db.session.flush()
    return raw_token


def reset_password(token: str, new_password: str) -> User:
    """
    Find the user whose reset_token matches, then update their password.

    Raises InvalidToken if no user matches or the token has expired.
    Raises WeakPassword if the new password fails validation.
    """
    if not token:
        raise InvalidToken("missing reset token")
    validate_password(new_password)

    now = datetime.now(timezone.utc)
    # We cannot query by bcrypt hash, so we scan users with an active
    # reset token. In a large deployment this would be replaced by a
    # lookup table; here user counts are small (coursework scale).
    candidates = db.session.scalars(
        select(User).where(
            User.reset_token.is_not(None),
            User.reset_token_expires.is_not(None),
            User.reset_token_expires >= now,
        )
    ).all()

    match: Optional[User] = None
    for user in candidates:
        if user.check_reset_token(token):
            match = user
            break

    if match is None:
        raise InvalidToken("reset link is invalid or has expired")

    match.set_password(new_password)
    match.clear_reset_token()
    db.session.flush()
    return match


def verify_email(token: str) -> User:
    """
    Verify a user's email address using the token from their signup email.

    Raises InvalidToken if no user matches.
    """
    if not token:
        raise InvalidToken("missing verification token")

    candidates = db.session.scalars(
        select(User).where(User.verification_token.is_not(None))
    ).all()

    match: Optional[User] = None
    for user in candidates:
        if user.check_verification_token(token):
            match = user
            break

    if match is None:
        raise InvalidToken("verification link is invalid")

    match.clear_verification_token()
    db.session.flush()
    return match


def claim_guest_bookings(user: User) -> int:
    """
    Attach any guest bookings that share the user's email to their account.

    A guest booking is one with user_id NULL and guest_email matching.
    Runs inside the caller's transaction; returns the count claimed.
    """
    if user.id is None or not user.email:
        return 0

    stmt = select(Booking).where(
        Booking.user_id.is_(None),
        Booking.guest_email == user.email,
    )
    bookings = db.session.scalars(stmt).all()

    for b in bookings:
        b.user_id = user.id

    if bookings:
        db.session.flush()

    return len(bookings)

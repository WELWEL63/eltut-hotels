"""
blueprints/auth/forms.py
────────────────────────
Flask-WTF forms for the auth blueprint.

Each form maps 1:1 to an auth route and enforces the same validation
rules that services.auth_service enforces — belt and braces, so that a
user sees a nice inline error before the service layer raises.
"""

from __future__ import annotations

import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    ValidationError,
)


# ─── Custom validators ────────────────────────────────────────────
_RE_UPPER = re.compile(r"[A-Z]")
_RE_LOWER = re.compile(r"[a-z]")
_RE_DIGIT = re.compile(r"\d")


def _strong_password(form, field):
    """Mirror of services.auth_service.validate_password."""
    pw = field.data or ""
    if len(pw) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if not _RE_UPPER.search(pw):
        raise ValidationError("Password must contain an uppercase letter.")
    if not _RE_LOWER.search(pw):
        raise ValidationError("Password must contain a lowercase letter.")
    if not _RE_DIGIT.search(pw):
        raise ValidationError("Password must contain a digit.")


# ─── Forms ────────────────────────────────────────────────────────
class RegisterForm(FlaskForm):
    full_name = StringField(
        "Full name",
        validators=[DataRequired(), Length(min=2, max=120)],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    phone = StringField("Phone (optional)", validators=[Length(max=40)])
    password = PasswordField(
        "Password",
        validators=[DataRequired(), _strong_password],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    accept_terms = BooleanField(
        "I agree to the terms and privacy policy",
        validators=[DataRequired(message="Please accept the terms to continue.")],
    )
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class ForgotPasswordForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    submit = SubmitField("Send reset link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password",
        validators=[DataRequired(), _strong_password],
    )
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Change password")


class LogoutForm(FlaskForm):
    """Empty CSRF-carrying form for the logout POST."""

    submit = SubmitField("Log out")

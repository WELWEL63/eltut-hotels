"""
blueprints/account/forms.py
───────────────────────────
Forms for the customer account area.
"""

from __future__ import annotations

import re

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    EqualTo,
    Length,
    Optional,
    ValidationError,
)


_RE_UPPER = re.compile(r"[A-Z]")
_RE_LOWER = re.compile(r"[a-z]")
_RE_DIGIT = re.compile(r"\d")


def _strong_password(form, field):
    pw = field.data or ""
    if len(pw) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if not _RE_UPPER.search(pw):
        raise ValidationError("Password must contain an uppercase letter.")
    if not _RE_LOWER.search(pw):
        raise ValidationError("Password must contain a lowercase letter.")
    if not _RE_DIGIT.search(pw):
        raise ValidationError("Password must contain a digit.")


class ProfileForm(FlaskForm):
    full_name = StringField(
        "Full name",
        validators=[DataRequired(), Length(min=2, max=120)],
    )
    phone = StringField("Phone", validators=[Optional(), Length(max=40)])
    submit = SubmitField("Save changes")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Current password", validators=[DataRequired()]
    )
    new_password = PasswordField(
        "New password", validators=[DataRequired(), _strong_password]
    )
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")],
    )
    submit = SubmitField("Change password")

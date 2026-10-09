"""
blueprints/auth/password_routes.py
──────────────────────────────────
Password reset flow.

ROUTES
    GET/POST /forgot-password            request reset email
    GET/POST /reset-password/<token>     set new password
"""

from __future__ import annotations

from flask import (
    flash,
    redirect,
    render_template,
    url_for,
)
from flask_login import current_user

from blueprints.auth import auth_bp
from blueprints.auth.forms import ForgotPasswordForm, ResetPasswordForm
from extensions import db

from services import auth_service, email_service


# ─── Request reset ─────────────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Ask for a reset link by email."""
    if current_user.is_authenticated:
        return redirect(url_for("public.index"))

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        token = auth_service.request_password_reset(form.email.data)
        if token is not None:
            user = db.session.scalar(
                __import__("sqlalchemy").select(
                    __import__("models").User
                ).where(
                    __import__("models").User.email == form.email.data.strip().lower()
                )
            )
            if user is not None:
                try:
                    email_service.send_password_reset(user, token)
                except Exception:  # noqa: BLE001
                    pass
            db.session.commit()

        # Always show the same message so we don't leak whether the email exists.
        flash(
            "If that email is registered, we've sent a reset link.",
            "info",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


# ─── Reset with token ──────────────────────────────────────────────
@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """Set a new password using a valid reset token."""
    if current_user.is_authenticated:
        return redirect(url_for("public.index"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            user = auth_service.reset_password(token, form.password.data)
        except auth_service.InvalidToken:
            flash("That reset link is invalid or has expired.", "danger")
            return redirect(url_for("auth.forgot_password"))
        except auth_service.WeakPassword as exc:
            flash(str(exc), "danger")
            return render_template("auth/reset_password.html", form=form, token=token)

        db.session.commit()
        flash("Your password has been changed. Please sign in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", form=form, token=token)

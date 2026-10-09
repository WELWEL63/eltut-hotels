"""
blueprints/auth/routes.py
─────────────────────────
Register, login, logout, and email verification.

ROUTES
    GET/POST /register              create account
    GET/POST /login                 sign in
    POST     /logout                sign out
    GET      /verify-email/<token>  confirm email address
"""

from __future__ import annotations

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_user, logout_user

from blueprints.auth import auth_bp
from blueprints.auth.forms import LoginForm, LogoutForm, RegisterForm
from extensions import db

from services import auth_service, email_service


# ─── Register ──────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Create a new customer account."""
    if current_user.is_authenticated:
        flash("You're already signed in.", "info")
        return redirect(url_for("public.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            user = auth_service.register_user(
                email=form.email.data,
                password=form.password.data,
                full_name=form.full_name.data,
                phone=form.phone.data or None,
            )
        except auth_service.EmailTaken:
            flash("An account with this email already exists.", "danger")
            return render_template("auth/register.html", form=form)
        except auth_service.WeakPassword as exc:
            flash(str(exc), "danger")
            return render_template("auth/register.html", form=form)
        except auth_service.AuthError as exc:
            flash(str(exc), "danger")
            return render_template("auth/register.html", form=form)

        # Send the welcome + verify email (best-effort)
        try:
            email_service.send_welcome(user)
        except Exception:  # noqa: BLE001
            pass

        db.session.commit()

        # Auto sign in
        login_user(user)

        flash(
            f"Welcome, {user.full_name}! Your account is ready.",
            "success",
        )
        return redirect(url_for("public.index"))

    return render_template("auth/register.html", form=form)


# ─── Login ─────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Sign a user in."""
    if current_user.is_authenticated:
        return redirect(url_for("public.index"))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = auth_service.authenticate(
                email=form.email.data,
                password=form.password.data,
            )
        except auth_service.TooManyAttempts as exc:
            flash(str(exc), "danger")
            return render_template("auth/login.html", form=form)
        except auth_service.AccountDisabled:
            flash("This account has been disabled.", "danger")
            return render_template("auth/login.html", form=form)

        if user is None:
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", form=form)

        login_user(user, remember=bool(form.remember.data))

        next_url = request.args.get("next") or request.form.get("next") or ""
        # Prevent open redirects: only accept local paths.
        if next_url and not next_url.startswith("/"):
            next_url = ""

        flash(f"Welcome back, {user.full_name}!", "success")
        return redirect(next_url or url_for("public.index"))

    return render_template("auth/login.html", form=form)


# ─── Logout ────────────────────────────────────────────────────────
@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Sign the current user out."""
    if current_user.is_authenticated:
        logout_user()
        flash("You've been signed out.", "info")
    return redirect(url_for("public.index"))


# ─── Email verification ────────────────────────────────────────────
@auth_bp.route("/verify-email/<token>")
def verify_email(token: str):
    """Confirm an email address using a token from the welcome email."""
    try:
        user = auth_service.verify_email(token)
    except auth_service.InvalidToken:
        flash("That verification link is invalid or has expired.", "danger")
        return redirect(url_for("public.index"))

    db.session.commit()
    flash("Your email has been verified. Thank you!", "success")
    return redirect(url_for("public.index"))

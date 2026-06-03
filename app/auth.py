"""Authentication routes: login, signup, logout."""

from __future__ import annotations

import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from . import db
from .models import User
from .session_idle import touch_session

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _safe_next_url(raw: str | None) -> str:
    if not raw:
        return url_for("main.analysis")
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return url_for("main.analysis")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.analysis"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", email=email), 401
        login_user(user, remember=bool(request.form.get("remember")))
        touch_session()
        flash(f"Welcome back, {user.label}!", "success")
        return redirect(_safe_next_url(request.args.get("next")))

    return render_template(
        "auth/login.html",
        email=(request.args.get("email") or "").strip().lower(),
    )


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.analysis"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        display_name = (request.form.get("display_name") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        if not _EMAIL_RE.match(email):
            flash("Enter a valid email address.", "danger")
            return render_template("auth/signup.html", email=email, display_name=display_name), 400
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/signup.html", email=email, display_name=display_name), 400
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/signup.html", email=email, display_name=display_name), 400
        existing = User.query.filter_by(email=email).first()
        if existing:
            if existing.check_password(password):
                login_user(existing)
                touch_session()
                flash(f"Welcome back, {existing.label}!", "success")
                return redirect(_safe_next_url(request.args.get("next")))
            flash("An account with this email already exists. Sign in with your password.", "warning")
            return redirect(
                url_for("auth.login", email=email, next=request.args.get("next"))
            )

        user = User(email=email, display_name=display_name or email.split("@")[0])
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        touch_session()
        flash("Account created. You can now save History and create tickets.", "success")
        return redirect(_safe_next_url(request.args.get("next")))

    return render_template("auth/signup.html", email="", display_name="")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.home"))

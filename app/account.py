"""Account settings, integrations, and account deletion."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required, logout_user

from . import db
from .avatar_utils import avatar_disk_path, avatar_exists, delete_avatar_file, save_avatar
from .crypto_utils import encrypt_secret
from .models import ProcessingLog, Review, Ticket, User, UserIntegrationSettings
from .ticketing import _jira_from_integration, _zendesk_from_integration, create_jira_ticket, create_zendesk_ticket
from .user_context import get_or_create_integration

account_bp = Blueprint("account", __name__, url_prefix="/account")


class _StubReview:
    source = "ReviewBridge"
    app_name = "Connection Test"
    author = "ReviewBridge"
    rating = 3
    content = "Integration test from ReviewBridge account settings."
    sentiment = "neutral"
    category = "support"
    confidence = 0.9
    id = 0


def _clear_jira_fields(integration: UserIntegrationSettings) -> None:
    integration.jira_base_url = None
    integration.jira_email = None
    integration.jira_api_token_encrypted = None
    integration.jira_project_key = None
    integration.jira_issue_type = None


def _clear_zendesk_fields(integration: UserIntegrationSettings) -> None:
    integration.zendesk_subdomain = None
    integration.zendesk_email = None
    integration.zendesk_api_token_encrypted = None


@account_bp.route("/avatar")
@login_required
def avatar():
    if not current_user.avatar_filename or not avatar_exists(current_user.id):
        abort(404)
    path = avatar_disk_path(current_user.id, current_user.avatar_filename)
    if path is None or not path.is_file():
        abort(404)
    response = send_file(path, mimetype="image/webp", conditional=True)
    response.cache_control.private = True
    response.cache_control.max_age = 3600
    return response


@account_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    integration = get_or_create_integration(current_user.id)
    active_tab = request.args.get("tab", "profile")

    if request.method == "POST":
        form_type = request.form.get("form_type", "profile")

        if form_type == "profile":
            display_name = (request.form.get("display_name") or "").strip()
            current_user.display_name = display_name or current_user.email.split("@")[0]
            new_password = request.form.get("new_password") or ""
            confirm_password = request.form.get("confirm_password") or ""
            if new_password:
                if len(new_password) < 8:
                    flash("New password must be at least 8 characters.", "danger")
                    return redirect(url_for("account.settings", tab="profile"))
                if new_password != confirm_password:
                    flash("Password confirmation does not match.", "danger")
                    return redirect(url_for("account.settings", tab="profile"))
                current_user.set_password(new_password)

            avatar_file = request.files.get("avatar")
            if avatar_file and avatar_file.filename:
                try:
                    old_filename = current_user.avatar_filename
                    current_user.avatar_filename = save_avatar(current_user.id, avatar_file)
                    if old_filename and old_filename != current_user.avatar_filename:
                        delete_avatar_file(current_user.id, old_filename)
                except ValueError as exc:
                    flash(str(exc), "danger")
                    return redirect(url_for("account.settings", tab="profile"))

            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("account.settings", tab="profile"))

        if form_type == "remove_avatar":
            old_filename = current_user.avatar_filename
            current_user.avatar_filename = None
            delete_avatar_file(current_user.id, old_filename)
            db.session.commit()
            flash("Profile photo removed.", "success")
            return redirect(url_for("account.settings", tab="profile"))

        if form_type == "save_jira":
            integration.jira_enabled = bool(request.form.get("jira_enabled"))
            if integration.jira_enabled:
                integration.jira_base_url = (request.form.get("jira_base_url") or "").strip() or None
                integration.jira_email = (request.form.get("jira_email") or "").strip() or None
                integration.jira_project_key = (request.form.get("jira_project_key") or "").strip() or None
                integration.jira_issue_type = (request.form.get("jira_issue_type") or "").strip() or None
                jira_token = (request.form.get("jira_api_token") or "").strip()
                if jira_token:
                    integration.jira_api_token_encrypted = encrypt_secret(jira_token)
            else:
                _clear_jira_fields(integration)
            db.session.commit()
            flash("Jira settings saved.", "success")
            return redirect(url_for("account.settings", tab="integrations"))

        if form_type == "save_zendesk":
            integration.zendesk_enabled = bool(request.form.get("zendesk_enabled"))
            if integration.zendesk_enabled:
                integration.zendesk_subdomain = (request.form.get("zendesk_subdomain") or "").strip() or None
                integration.zendesk_email = (request.form.get("zendesk_email") or "").strip() or None
                zendesk_token = (request.form.get("zendesk_api_token") or "").strip()
                if zendesk_token:
                    integration.zendesk_api_token_encrypted = encrypt_secret(zendesk_token)
            else:
                _clear_zendesk_fields(integration)
            db.session.commit()
            flash("Zendesk settings saved.", "success")
            return redirect(url_for("account.settings", tab="integrations"))

        if form_type == "test_jira":
            if not integration.jira_enabled:
                flash("Enable Jira before testing the connection.", "warning")
                return redirect(url_for("account.settings", tab="integrations"))
            if _jira_from_integration(integration) is None:
                flash("Complete all Jira fields and API token before testing.", "danger")
                return redirect(url_for("account.settings", tab="integrations"))
            try:
                result = create_jira_ticket(_StubReview(), 0, integration=integration)
                mode = result.get("mode", "mock")
                flash(f"Jira test OK ({mode}): {result.get('external_ticket_id')}", "success")
            except Exception as exc:
                flash(f"Jira test failed: {exc}", "danger")
            return redirect(url_for("account.settings", tab="integrations"))

        if form_type == "test_zendesk":
            if not integration.zendesk_enabled:
                flash("Enable Zendesk before testing the connection.", "warning")
                return redirect(url_for("account.settings", tab="integrations"))
            if _zendesk_from_integration(integration) is None:
                flash("Complete all Zendesk fields and API token before testing.", "danger")
                return redirect(url_for("account.settings", tab="integrations"))
            try:
                result = create_zendesk_ticket(_StubReview(), 0, integration=integration)
                mode = result.get("mode", "mock")
                flash(f"Zendesk test OK ({mode}): {result.get('external_ticket_id')}", "success")
            except Exception as exc:
                flash(f"Zendesk test failed: {exc}", "danger")
            return redirect(url_for("account.settings", tab="integrations"))

    jira_token_set = bool(integration.jira_api_token_encrypted)
    zendesk_token_set = bool(integration.zendesk_api_token_encrypted)
    has_avatar = avatar_exists(current_user.id)

    return render_template(
        "account/settings.html",
        active_tab=active_tab,
        integration=integration,
        jira_token_set=jira_token_set,
        zendesk_token_set=zendesk_token_set,
        has_avatar=has_avatar,
    )


@account_bp.route("/delete", methods=["POST"])
@login_required
def delete_account():
    phrase = (request.form.get("confirm_phrase") or "").strip().lower()
    if phrase != "delete":
        flash("Confirmation phrase was missing or incorrect.", "danger")
        return redirect(url_for("account.settings", tab="danger"))

    password = request.form.get("password") or ""
    confirm = (request.form.get("confirm_email") or "").strip().lower()
    if not current_user.check_password(password):
        flash("Incorrect password. Account was not deleted.", "danger")
        return redirect(url_for("account.settings", tab="danger"))
    if confirm != current_user.email.lower():
        flash("Email confirmation did not match. Account was not deleted.", "danger")
        return redirect(url_for("account.settings", tab="danger"))

    user_id = current_user.id
    avatar_filename = current_user.avatar_filename
    review_ids = [r.id for r in Review.query.filter_by(user_id=user_id).all()]
    if review_ids:
        Ticket.query.filter(Ticket.review_id.in_(review_ids)).delete(synchronize_session=False)
    Ticket.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Review.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    ProcessingLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    UserIntegrationSettings.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    User.query.filter_by(id=user_id).delete(synchronize_session=False)
    db.session.commit()
    delete_avatar_file(user_id, avatar_filename)
    logout_user()
    flash("Your account and saved data have been permanently deleted.", "info")
    return redirect(url_for("main.home"))

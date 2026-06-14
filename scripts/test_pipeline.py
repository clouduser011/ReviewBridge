"""Smoke-test analysis pipeline API and analysis workspace markup."""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app, db
from app.analyzer import review_storage_id, scoped_storage_id, stable_review_id
from app.app_catalog import catalog_status, load_catalog, rank_apps, score_app_match, search_local_catalog
from app.google_play import (
    _finalize_fetch_rows,
    _merge_rows,
    _normalize_play_lang,
    _resolve_fetch_countries,
    _resolve_search_countries,
    _review_entry_from_play_row,
    _sort_rows_by_date,
    merge_and_rank_suggestions,
)
from app.models import Review, Ticket, User, UserIntegrationSettings
from app.user_context import OwnerContext
from app.datetime_utils import normalize_play_review_at
from app.routes import (
    _batch_now,
    _batch_reviews_query,
    _coerce_review_datetime,
    _normalize_batch_dt,
    _parse_csv_review_date,
    _parse_review_count,
    _parse_review_row,
    _process_review,
)

CSV_PATH = ROOT / "data" / "sample_reviews.csv"

TICKET_OWNER = OwnerContext(user_id=1, owner_session_key=None, allow_tickets=True, integration=None)
BATCH_OWNER = OwnerContext(
    user_id=None,
    owner_session_key="test-pipeline-session",
    allow_tickets=False,
    integration=None,
)


def _signup_client(client, email="pipeline@test.local", password="testpass123"):
    client.post(
        "/auth/signup",
        data={
            "email": email,
            "display_name": "Pipeline Tester",
            "password": password,
            "confirm_password": password,
        },
        follow_redirects=True,
    )
    return client


def _login_client(client, email="pipeline@test.local", password="testpass123"):
    client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )
    return client


def _test_app():
    """Flask app backed by in-memory SQLite — never touches instance/reviewbridge.db."""
    return create_app(testing=True)


# --- Template / CSS smoke tests ---


def test_analysis_markup():
    html = (ROOT / "app" / "templates" / "analysis.html").read_text(encoding="utf-8")
    filter_partial = (ROOT / "app" / "templates" / "_review_filter_toolbar.html").read_text(encoding="utf-8")
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    html_bundle = html + filter_partial
    required = [
        "analysisPipelineCard",
        "analysis-empty-onboarding",
        "analysis-onboarding-steps",
        "rb-onboarding-stepper",
        "rb-onboarding-toolbar",
        "pipelineCurrentAction",
        "pipelineSteps",
        "pipelineStats",
        "csvUploadForm",
        "importPanelPlay",
        "importPanelCsv",
        "rb-import-card",
        "rb-import-quick-row",
        "rb-pipeline-stepper",
        "rb-pipeline-stats",
        "quickPicksCard",
        "quick-picks-scroll",
        "analysisMainContent",
        "rb-ticket-platform-strip",
        "rb-ticket-platform-chip",
        "rb-tickets-panel-body",
        "tickets-list-wrap",
        "liveAnalysisPanels",
        "sentimentChart",
        "fetchCountryInput",
        "fetchLangHidden",
        "fetchSortHidden",
        "statRefreshed",
        "rb-page-header",
        "main.history",
        "data-review-filter-root",
        "rb-analysis-reviews-body",
        "reviewsResultsCard",
        "rb-review-filter-select",
        "rb-review-filter-toolbar",
        "_review_filter_toolbar.html",
        "review-filter.js",
    ]
    missing = [x for x in required if x not in html_bundle]
    assert not missing, f"Missing in analysis.html: {missing}"
    idx_import = html.find("rb-import-quick-row")
    idx_pipeline = html.find("analysisPipelineCard")
    idx_main = html.find('id="analysisMainContent"')
    idx_adv_toggle = html.find("toggleAdvancedOptionsSwitch")
    idx_fetch_btn = html.find("btnFetchLimited")
    assert 0 <= idx_import < idx_pipeline < idx_main, (
        "Expected import row, then pipeline card, then analysisMainContent"
    )
    assert 0 <= idx_adv_toggle < idx_fetch_btn, (
        "Expected Advanced options to appear before fetch buttons in analysis import form"
    )
    assert "analysis-demo-showcase" not in html
    assert "Tickets (batch)" not in html
    assert "tickets_total" not in html
    assert "dashboardTopMetrics" not in html
    assert "_rb_demo_insight.html" not in html
    assert "fetchStatusCard" not in html
    assert "pipelineLogStream" not in html
    assert 'value="us" selected' in html or "United States" in html
    assert 'max="5000"' not in html
    assert ".rb-import-advanced" in theme_css
    assert "margin-bottom: 0.75rem;" in theme_css
    workspace_actions = html[html.find('class="rb-page-actions"'):html.find('class="rb-page-actions"') + 600]
    assert "main.history" in workspace_actions
    assert "is_authenticated" in workspace_actions
    assert "next=url_for('main.history')" not in workspace_actions
    print("OK analysis markup")


def test_app_nav_has_home_link():
    import re

    base_html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    site_nav = (ROOT / "app" / "templates" / "_site_nav.html").read_text(encoding="utf-8")

    assert "_site_nav.html" in base_html
    assert "nav_mode = 'app'" in base_html
    assert "nav-scroll.js" in base_html
    assert "_site_nav.html" in landing_base
    assert "nav_mode = 'landing'" in landing_base
    assert "nav-scroll.js" in landing_base
    assert "nav-transition.js" not in base_html
    assert "nav-transition.js" not in landing_base

    pills_landing = site_nav.split("{% if nav_mode == 'landing' %}")[1].split("{% endif %}")[0]
    actions_section = site_nav.split("rb-nav-actions")[1]
    app_match = re.search(
        r"\{% if nav_mode == 'app' %\}(.*?)\n      \{% endif %\}\n      \{% else %\}",
        actions_section,
        re.DOTALL,
    )
    assert app_match, "app nav actions block not found"
    app_actions = app_match.group(1)
    landing_match = re.search(
        r"\{% else %\}\n      <a href=\"\{\{ url_for\('main.analysis'\) \}\}\".*?\n      \{% endif %\}\n    </div>",
        actions_section,
        re.DOTALL,
    )
    assert landing_match, "landing nav actions block not found"
    landing_actions = landing_match.group(0)

    assert "rb-nav-pills--shell" in site_nav
    assert "rb-nav-home-action" in app_actions
    assert "main.home" in app_actions
    assert ">Home</a>" in app_actions
    assert "main.analysis" in app_actions
    assert ">Analysis</a>" in app_actions
    assert "rb-nav-action" in app_actions
    assert ">Start analysis</a>" not in app_actions
    assert "auth.login" in app_actions
    assert "{% if is_authenticated %}" in app_actions
    assert "main.home" not in pills_landing

    assert 'href="#top"' in pills_landing
    assert 'data-nav-section="top"' in pills_landing
    assert 'data-nav-section="features"' in pills_landing
    assert "rb-nav-pills-indicator" in pills_landing
    assert "rb-nav-section-links" in pills_landing
    assert "data-nav-sections" in pills_landing
    assert ">Home</a>" in pills_landing
    assert "main.analysis" in landing_actions
    assert ">Start analysis</a>" in landing_actions
    assert "main.history" not in landing_actions
    assert "auth.login" in landing_actions
    assert "auth.signup" in landing_actions
    assert landing_actions.index("main.analysis") < landing_actions.index("auth.login")
    print("OK app nav has home link")


def test_flash_messages_shared():
    flash_partial = (ROOT / "app" / "templates" / "_flash_messages.html").read_text(encoding="utf-8")
    base_html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    flash_js = (ROOT / "app" / "static" / "js" / "flash-messages.js").read_text(encoding="utf-8")
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")

    assert "data-flash-root" in flash_partial
    assert "js-alert-auto-hide" in flash_partial
    assert "data-auto-hide-ms" in flash_partial
    assert "_flash_messages.html" in base_html
    assert "_flash_messages.html" in landing_base
    assert "flash-messages.js" in base_html
    assert "flash-messages.js" in landing_base
    assert "closed.bs.alert" in flash_js
    assert "js-alert-auto-hide" in flash_js
    assert "landing-container pt-3" not in landing_base
    assert ".rb-flash-messages" in theme_css
    print("OK flash messages shared")


def test_sticky_nav_scroll_offset_css():
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    style_css = (ROOT / "app" / "static" / "css" / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "js" / "analysis.js").read_text(encoding="utf-8")

    assert "--rb-sticky-nav-offset:" in theme_css
    assert "scroll-padding-top: var(--rb-sticky-nav-offset)" in theme_css
    assert "#dataImportCard" in theme_css
    assert "scroll-margin-top: var(--rb-sticky-nav-offset)" in theme_css

    pipeline_block = style_css.split("#analysisPipelineCard")[1].split("}")[0]
    assert "scroll-margin-top: var(--rb-sticky-nav-offset)" in pipeline_block

    assert "function getStickyNavScrollOffset()" in js
    assert "getBoundingClientRect().height" in js
    assert "window.scrollTo" in js
    assert "RB_SCROLL_PIPELINE_KEY" in js
    assert "function markRestorePipelineScroll()" in js
    assert "function consumeRestorePipelineScroll()" in js
    activate_block = js.split("const activateCompletedBatch")[1].split("const abortToDashboard")[0]
    assert "markRestorePipelineScroll()" in activate_block
    assert "batch_started_at" in activate_block
    init_block = js.split("function initAnalysisPipeline")[1].split("function initAppSuggestions")[0]
    assert "consumeRestorePipelineScroll()" in init_block
    print("OK sticky nav scroll offset")


def test_footer_sticky_layout_css():
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    landing_css = (ROOT / "app" / "static" / "css" / "landing.css").read_text(encoding="utf-8")

    assert "html {" in theme_css and "height: 100%" in theme_css
    app_body_block = theme_css.split(".app-body {")[1].split("/* Nav */")[0]
    assert "min-height: 100vh" in app_body_block
    assert "min-height: 100dvh" in app_body_block
    assert "flex-direction: column" in app_body_block
    assert ".app-body > main" in theme_css
    assert "flex: 1 0 auto" in theme_css

    footer_block = theme_css.split(".rb-app-footer,")[1].split(".rb-app-footer-inner")[0]
    assert "flex-shrink: 0" in footer_block
    assert ".landing-footer" in footer_block

    landing_footer_block = landing_css.split(".landing-footer")[1].split("}")[0]
    assert "flex-shrink: 0" not in landing_footer_block
    print("OK footer sticky layout")


def test_dead_css_removed():
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    for dead in (
        "rb-insight-panel",
        "landing-preview-donut",
        "rb-preview-donut",
        "--rb-muted",
        "rb-btn-ghost.active",
    ):
        assert dead not in theme_css, f"dead selector still in theme.css: {dead}"
    print("OK dead CSS removed")


def test_landing_nav_modern_theme():
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    landing_css = (ROOT / "app" / "static" / "css" / "landing.css").read_text(encoding="utf-8")
    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    site_nav = (ROOT / "app" / "templates" / "_site_nav.html").read_text(encoding="utf-8")

    assert "--rb-nav-landing-capsule-offset:" in theme_css
    assert "var(--rb-sticky-nav-offset)" in theme_css.split("--rb-nav-landing-capsule-offset:")[1].split(";")[0]
    assert "--rb-nav-link-color:" in theme_css
    assert "--rb-nav-pill-bg:" in theme_css

    assert ".rb-nav.rb-nav--landing" in theme_css
    assert "background: rgba(255, 255, 255, 0.82)" in theme_css

    shared_nav_block = theme_css.split(".rb-nav.rb-nav--app,")[1].split("}")[0]
    assert "position: sticky" in shared_nav_block

    assert ".rb-nav-inner--unified" in theme_css
    assert "rb-nav-inner--unified" in site_nav
    assert "_site_nav.html" in landing_base
    assert "rb-nav-section-links" in theme_css
    assert "rb-nav-pills-indicator" in theme_css
    assert "rb-nav-flight-layer" not in theme_css

    active_block = theme_css.split(".rb-nav--landing .rb-nav-link.is-active {")[1].split("}")[0]
    assert "color: var(--rb-nav-link-active)" in active_block
    assert "background: transparent" in active_block

    link_block = theme_css.split("\n.rb-nav-link {")[1].split("}")[0]
    assert "color: var(--rb-nav-link-color)" in link_block
    assert "0.9375rem" in link_block

    indicator_block = theme_css.split(".rb-nav--landing .rb-nav-pills-indicator {")[1].split("}")[0]
    assert "background: #fff" in indicator_block
    assert "var(--rb-nav-active-shadow)" in indicator_block
    assert "translateX(var(--nav-indicator-x" in indicator_block

    assert "var(--rb-nav-landing-capsule-offset)" in landing_css
    assert "calc(var(--rb-sticky-nav-offset) + 3rem)" in landing_css
    assert "#features," in landing_css
    assert "scroll-margin-top: var(--rb-nav-landing-capsule-offset)" in landing_css
    print("OK landing nav modern theme")


def test_export_download_options():
    analysis_html = (ROOT / "app" / "templates" / "analysis.html").read_text(encoding="utf-8")
    history_html = (ROOT / "app" / "templates" / "history.html").read_text(encoding="utf-8")
    routes_py = (ROOT / "app" / "routes.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    home_html = (ROOT / "app" / "templates" / "home.html").read_text(encoding="utf-8")

    assert "export_analysis_csv" in analysis_html
    assert "export_analysis_xlsx" in analysis_html
    assert "clear_analysis" in analysis_html
    assert "export_history_csv" in history_html
    assert "export_history_xlsx" in history_html

    for html in (analysis_html, history_html):
        assert "_pdf" not in html
        assert "PDF</a>" not in html
        assert "(report + data)" not in html
        assert "(colors)" not in html
        assert ">CSV</a>" in html
        assert ">Excel</a>" in html

    assert "export_analysis_csv" in routes_py
    assert "export_dashboard_csv" in routes_py
    assert "clear_analysis" in routes_py
    assert "export_dashboard_pdf" not in routes_py
    assert "export_history_pdf" not in routes_py
    assert "_build_professional_pdf" not in routes_py
    assert "reportlab" not in routes_py.lower()

    assert "reportlab" not in requirements.lower()
    assert "pdf for presentations" not in home_html.lower()

    app = _test_app()
    with app.app_context():
        client = app.test_client()
        assert client.get("/export/dashboard.pdf").status_code == 404
        assert client.get("/export/history.pdf").status_code == 404
        csv_res = client.get("/export/analysis.csv")
        assert csv_res.status_code == 200
        assert "analysis_batch_reviews.csv" in csv_res.headers.get("Content-Disposition", "")
        legacy_csv = client.get("/export/dashboard.csv")
        assert legacy_csv.status_code == 200
    print("OK export download options")


def test_nav_scroll_shared_js():
    nav_js = (ROOT / "app" / "static" / "js" / "nav-scroll.js").read_text(encoding="utf-8")
    base_html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    landing_js = (ROOT / "app" / "static" / "js" / "landing.js").read_text(encoding="utf-8")
    site_nav = (ROOT / "app" / "templates" / "_site_nav.html").read_text(encoding="utf-8")

    assert "function initNavScrolled" in nav_js
    assert "function initLandingNavScrollSpy" in nav_js
    assert "updateNavPillsIndicator" in nav_js
    assert "nav-scroll.js" in base_html
    assert 'initNavScrolled("appNav")' in base_html
    assert "nav-scroll.js" in landing_base
    assert "nav-transition.js" not in base_html
    assert "nav-transition.js" not in landing_base
    assert "data-nav-expand-pending" not in landing_js
    assert 'initLandingNavScrollSpy("landingNav")' in landing_js
    assert "data-nav-pills" in site_nav
    assert "data-nav-transition" not in site_nav
    print("OK nav scroll shared JS")


def test_nav_static_assets():
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    site_nav = (ROOT / "app" / "templates" / "_site_nav.html").read_text(encoding="utf-8")

    assert (ROOT / "app" / "templates" / "_site_nav.html").is_file()
    assert not (ROOT / "app" / "static" / "js" / "nav-transition.js").is_file()
    assert "rb-nav-flight-layer" not in site_nav
    assert "data-nav-home-target" not in site_nav
    assert "data-nav-transition" not in site_nav
    assert "rb-nav-home-action" in site_nav
    assert "rb-nav-section-links" in site_nav
    assert "data-nav-sections" in site_nav
    assert "rb-nav-pills-indicator" in theme_css
    assert "rb-nav-flight" not in theme_css
    assert "is-nav-leaving-landing" not in theme_css
    assert "prefers-reduced-motion: reduce" in theme_css
    print("OK nav static assets")


def test_history_page_no_dashboard_charts():
    app = _test_app()
    with app.app_context():
        client = app.test_client()
        resp = client.get("/history")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")

    with app.app_context():
        client = app.test_client()
        _signup_client(client)
        resp = client.get("/history")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "chart.umd.min.js" not in html
    assert "analysis.js" not in html
    assert "sentimentChart" not in html
    print("OK history page without chart scripts")


def test_history_scrollable_layout():
    history_html = (ROOT / "app" / "templates" / "history.html").read_text(encoding="utf-8")
    filter_partial = (ROOT / "app" / "templates" / "_review_filter_toolbar.html").read_text(encoding="utf-8")
    history_bundle = history_html + filter_partial
    history_js = (ROOT / "app" / "static" / "js" / "history.js").read_text(encoding="utf-8")
    style_css = (ROOT / "app" / "static" / "css" / "style.css").read_text(encoding="utf-8")

    for marker in (
        "rb-history-app-strip",
        "rb-history-app-chip",
        "rb-history-reviews-scroll",
        "rb-history-tickets-scroll",
        "rb-history-logs-scroll",
        'role="tablist"',
        "history.js",
        "data-review-filter-root",
        "rb-review-filter-toolbar",
        "rb-review-filter-select",
        "review-snippet",
        "rb-review-row",
        "review-filter.js",
    ):
        assert marker in history_bundle, f"missing {marker} in history.html"

    assert "initHistoryAppTabs" in history_js or "activateHistoryApp" in history_js
    assert "initHistoryReviewFilters" in history_js
    assert ".rb-history-app-strip" in style_css
    assert ".rb-history-reviews-scroll" in style_css

    filter_js = (ROOT / "app" / "static" / "js" / "review-filter.js").read_text(encoding="utf-8")
    assert "mountReviewTableFilter" in filter_js

    app = _test_app()
    with app.app_context():
        client = app.test_client()
        _signup_client(client, email="history-scroll@test.local")
        resp = client.get("/history")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "rb-history-logs-scroll" in body
    assert "review-filter.js" in body
    print("OK history scrollable layout")


def test_storage_health_endpoint():
    app = _test_app()
    with app.app_context():
        Review.query.delete()
        Ticket.query.delete()
        db.session.commit()
        resp = app.test_client().get("/api/storage-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_reviews"] == 0
    assert data["total_tickets"] == 0
    assert "per_app" in data
    print("OK storage health endpoint")


def test_hash_then_play_single_review_single_ticket():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        Ticket.query.delete()
        db.session.commit()

        app_name = "Dedupe Test App"
        batch1 = _batch_now()
        play_id = "play-dedupe-99"

        ok1, reason1, meta1 = _process_review(
            app_name,
            "alice",
            2,
            "App crashes on login",
            batch_started_at=batch1,
            play_review_id=None,
            owner=TICKET_OWNER,
        )
        assert ok1 and reason1 == "processed"
        assert meta1.get("platform")
        db.session.commit()

        assert Review.query.count() == 1
        assert Ticket.query.count() == 1
        row = Review.query.first()
        assert ":app crashes on login" in row.review_id.lower() or row.review_id.startswith("u1:")

        batch2 = _normalize_batch_dt(batch1 + timedelta(seconds=3))
        ok2, reason2, meta2 = _process_review(
            app_name,
            "alice",
            2,
            "App crashes on login",
            batch_started_at=batch2,
            play_review_id=play_id,
            owner=TICKET_OWNER,
        )
        assert ok2 and reason2 == "refreshed"
        assert meta2.get("platform") is None
        db.session.commit()

        assert Review.query.count() == 1
        assert Ticket.query.count() == 1
        row = Review.query.first()
        assert row.review_id == f"u1:play:{play_id}"
    print("OK hash then play dedupe")


def test_skip_positive_tickets_when_enabled():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        Ticket.query.delete()
        db.session.commit()

        app_name = "Skip Positive App"
        batch = _batch_now()
        ok, reason, _ = _process_review(
            app_name,
            "fan",
            5,
            "Absolutely love this app, amazing experience every day!",
            batch_started_at=batch,
            skip_positive_tickets=True,
            owner=TICKET_OWNER,
        )
        assert ok and reason == "processed"
        db.session.commit()
        assert Review.query.count() == 1
        assert Ticket.query.count() == 0
        assert Review.query.first().sentiment == "positive"
    print("OK skip positive tickets when enabled")


def test_skip_positive_tickets_default_off():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        Ticket.query.delete()
        db.session.commit()

        app_name = "Skip Positive Off App"
        batch = _batch_now()
        ok, reason, meta = _process_review(
            app_name,
            "fan",
            5,
            "Absolutely love this app, amazing experience every day!",
            batch_started_at=batch,
            skip_positive_tickets=False,
            owner=TICKET_OWNER,
        )
        assert ok and reason == "processed"
        assert meta.get("platform")
        db.session.commit()
        assert Review.query.count() == 1
        assert Ticket.query.count() == 1
    print("OK skip positive tickets default off")


def test_review_results_filter_js():
    filter_js = (ROOT / "app" / "static" / "js" / "review-filter.js").read_text(encoding="utf-8")
    analysis_js = (ROOT / "app" / "static" / "js" / "analysis.js").read_text(encoding="utf-8")
    assert "mountReviewTableFilter" in filter_js
    assert "is-filtered-out" in filter_js
    assert "function initReviewResultsFilter" in analysis_js
    assert "mountReviewTableFilter" in analysis_js
    assert "initReviewResultsFilter();" in analysis_js
    init_suggestions_block = analysis_js.split("function initAppSuggestions()", 1)[1].split("function initReviewResultsFilter()", 1)[0]
    assert "form.requestSubmit();" not in init_suggestions_block
    print("OK review results filter JS")


def test_app_match_ranking_name_first():
    whatsapp = {
        "app_name": "WhatsApp Messenger",
        "package_name": "com.whatsapp",
        "icon": "",
        "developer": "WhatsApp LLC",
    }
    variant = {
        "app_name": "WhatsApp Business",
        "package_name": "com.whatsapp.w4b",
        "icon": "",
        "developer": "WhatsApp LLC",
    }
    unrelated = {
        "app_name": "Photo Editor Pro",
        "package_name": "com.example.photo",
        "icon": "",
        "developer": "Other",
    }
    ranked = rank_apps("whatsapp", [unrelated, variant, whatsapp], 3)
    assert ranked[0]["package_name"] == "com.whatsapp"
    assert score_app_match("whatsapp", whatsapp) > score_app_match("whatsapp", unrelated)
    print("OK app match ranking name first")


def test_merge_and_rank_suggestions_local_first():
    local = [
        {
            "app_name": "Instagram",
            "package_name": "com.instagram.android",
            "icon": "",
            "developer": "Meta",
        }
    ]
    play = [
        {
            "app_name": "Random App",
            "package_name": "com.random.app",
            "icon": "",
            "developer": "X",
        },
        {
            "app_name": "Instagram Lite",
            "package_name": "com.instagram.lite",
            "icon": "",
            "developer": "Meta",
        },
    ]
    merged = merge_and_rank_suggestions(local, play, "instagram", 5)
    assert merged[0]["package_name"] == "com.instagram.android"
    print("OK merge and rank suggestions local first")


def test_app_catalog_status_endpoint():
    app = _test_app()
    client = app.test_client()
    res = client.get("/api/app-catalog/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "count" in data
    assert "ready" in data
    assert "path_exists" in data
    status = catalog_status()
    if status.get("path_exists") and status.get("count", 0) >= 3000:
        assert data["count"] >= 3000
    print(f"OK app catalog status endpoint (count={data.get('count')})")


def test_app_catalog_module_loads():
    apps = load_catalog()
    assert isinstance(apps, list)
    print(f"OK app catalog module loads ({len(apps)} apps)")


def test_pk_priority_apps_file():
    path = ROOT / "data" / "pk_priority_apps.json"
    assert path.is_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw.get("packages"), list)
    assert isinstance(raw.get("search_terms"), list)
    assert len(raw["packages"]) >= 40
    assert len(raw["search_terms"]) >= 20
    assert "com.sadapay.app" in raw["packages"]
    print("OK pk priority apps file")


def test_build_catalog_pk_seeds():
    scripts_dir = ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from build_app_catalog import _pk_seed_queries, seed_queries

    pk = _pk_seed_queries()
    assert "sadapay" in pk
    assert "jazzcash" in pk
    assert "daraz" in pk
    seeds = seed_queries()
    assert len(seeds) >= 500
    assert seeds.index("sadapay") < seeds.index("whatsapp")
    print(f"OK build catalog pk seeds ({len(seeds)} total)")


def test_build_catalog_uses_multi_country():
    text = (ROOT / "scripts" / "build_app_catalog.py").read_text(encoding="utf-8")
    assert 'BUILD_COUNTRIES = ("pk", "in", "us")' in text
    assert 'search(q, n_hits=30, lang="en", country="us")' not in text
    assert "_play_search" in text
    assert "_bootstrap_pk_priority" in text
    print("OK build catalog uses multi country")


def test_catalog_pk_apps_local_search():
    status = catalog_status()
    if not status.get("path_exists") or status.get("count", 0) < 3000:
        print("SKIP catalog pk apps local search (catalog < 3000 apps)")
        return

    load_catalog(force_reload=True)
    found = False
    for query in ("sadapay", "nayapay", "jazzcash", "daraz", "bykea"):
        results = search_local_catalog(query, limit=5)
        if results:
            found = True
            break
    assert found, "expected at least one PK app in local catalog search"
    print("OK catalog pk apps local search")


def test_app_suggestions_typed_search():
    status = catalog_status()
    if not status.get("path_exists") or status.get("count", 0) < 100:
        print("SKIP app suggestions typed search (catalog not built)")
        return

    app = _test_app()
    client = app.test_client()

    res = client.get("/api/app-suggestions?q=whatsapp&limit=10")
    assert res.status_code == 200
    apps = res.get_json()
    assert isinstance(apps, list)
    assert len(apps) > 0
    top = apps[0]
    name_l = (top.get("app_name") or "").lower()
    pkg_l = (top.get("package_name") or "").lower()
    assert "whatsapp" in name_l or "whatsapp" in pkg_l

    res2 = client.get("/api/app-suggestions?q=instagram&limit=10")
    assert res2.status_code == 200
    apps2 = res2.get_json()
    assert len(apps2) > 0
    top2 = apps2[0]
    assert "instagram" in (top2.get("app_name") or "").lower() or "instagram" in (
        top2.get("package_name") or ""
    ).lower()
    print("OK app suggestions typed search")


def test_app_suggestions_local_only_endpoint():
    status = catalog_status()
    if not status.get("path_exists") or status.get("count", 0) < 100:
        print("SKIP app suggestions local_only endpoint (catalog not built)")
        return

    app = _test_app()
    client = app.test_client()

    res = client.get("/api/app-suggestions?q=whatsapp&limit=2&local_only=1")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, dict)
    assert "apps" in data
    assert "needs_play" in data
    assert isinstance(data["apps"], list)
    assert len(data["apps"]) > 0
    assert data["needs_play"] is False

    res_empty = client.get("/api/app-suggestions?q=zzzznotarealappname999&limit=10&local_only=1")
    assert res_empty.status_code == 200
    empty_data = res_empty.get_json()
    assert isinstance(empty_data, dict)
    assert empty_data.get("apps") == []
    assert empty_data.get("needs_play") is True
    print("OK app suggestions local_only endpoint")


def test_app_suggestions_play_only_endpoint():
    app = _test_app()
    client = app.test_client()

    res = client.get("/api/app-suggestions?q=whatsapp&limit=5&play_only=1")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    print("OK app suggestions play_only endpoint")


def test_normalize_play_lang():
    assert _normalize_play_lang("") == "en"
    assert _normalize_play_lang("  ") == "en"
    assert _normalize_play_lang("ur") == "ur"
    assert _normalize_play_lang(" en ") == "en"
    print("OK normalize play lang")


def test_resolve_search_countries_pk():
    pk = _resolve_search_countries("pk")
    assert pk[0] == "pk"
    assert "in" in pk
    assert "us" in pk

    ww = _resolve_search_countries("ww")
    assert ww[0] == "us"
    assert "pk" in ww
    assert ww.index("pk") < ww.index("gb")

    ae = _resolve_search_countries("ae")
    assert ae[0] == "ae"
    assert "pk" in ae
    print("OK resolve search countries pk")


def test_app_suggestions_play_only_pk_smoke():
    app = _test_app()
    client = app.test_client()

    try:
        res = client.get("/api/app-suggestions?q=jazzcash&limit=5&play_only=1&country=pk&lang=en")
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        if not data:
            print("SKIP app suggestions play_only pk smoke (no network results)")
            return
        name_l = (data[0].get("app_name") or "").lower()
        pkg_l = (data[0].get("package_name") or "").lower()
        assert "jazz" in name_l or "jazz" in pkg_l
        print("OK app suggestions play_only pk smoke")
    except Exception as exc:
        print(f"SKIP app suggestions play_only pk smoke ({exc})")


def test_search_js_country_change_rerun():
    js = (ROOT / "app" / "static" / "js" / "analysis.js").read_text(encoding="utf-8")
    init_block = js.split("function initAppSuggestions()", 1)[1].split("function initReviewResultsFilter()", 1)[0]
    assert "fetchCountryInput" in init_block
    assert "runSearch" in init_block
    assert 'addEventListener("change"' in init_block
    assert 'lang || "en"' in init_block
    print("OK search JS country change rerun")


def test_search_js_play_loading_state():
    js = (ROOT / "app" / "static" / "js" / "analysis.js").read_text(encoding="utf-8")
    style_css = (ROOT / "app" / "static" / "css" / "style.css").read_text(encoding="utf-8")
    init_block = js.split("function initAppSuggestions()", 1)[1].split("function initReviewResultsFilter()", 1)[0]
    assert "debounceTimer" in init_block
    assert "/api/app-suggestions" in init_block
    assert "local_only" in init_block
    assert "play_only" in init_block
    assert "renderDefaultSuggestions" in init_block
    assert "renderSearchingPlay" in init_block
    assert "Searching Google Play" in init_block
    assert "fetchSuggestions" in init_block
    assert "runSearch" in init_block
    assert "fetchCountryInput" in init_block
    assert 'lang || "en"' in init_block
    assert "form.requestSubmit();" not in init_block
    assert "handleSearchInput" not in init_block
    assert "loadAppCatalog" not in init_block
    assert "app-suggestions-panel--floating" not in init_block
    assert ".suggestion-searching" in style_css
    assert "#dataImportCard" in style_css
    assert "overflow: visible" in style_css
    assert ".app-search-wrap" in style_css
    assert "max-width: 22rem" in style_css
    print("OK search JS play loading state")


def test_search_js_simple_api_debounce():
    test_search_js_play_loading_state()


def test_form_switch_refined_styles():
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    assert "--rb-switch-off" in theme_css
    assert ".app-body .form-switch" in theme_css
    assert "width: 2em" in theme_css
    assert "width: 2.75em" not in theme_css
    assert "fill='%23fff'" not in theme_css
    print("OK form switch refined styles")


def test_skip_positive_tickets_markup():
    html = (ROOT / "app" / "templates" / "analysis.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "js" / "analysis.js").read_text(encoding="utf-8")
    assert "rb-import-switches-row" in html
    assert "skipPositiveTicketsSwitch" in html
    assert "skipPositiveTicketsSwitchCsv" in html
    assert "Skip tickets for positive reviews" in html
    row_start = html.index("rb-import-switches-row")
    row_end = html.index("advancedOptionsPanel", row_start)
    switches_row = html[row_start:row_end]
    assert "toggleAdvancedOptionsSwitch" in switches_row
    assert "skipPositiveTicketsSwitch" in switches_row
    assert html.index("skipPositiveTicketsSwitch") < html.index("advancedOptionsPanel")
    assert html.index("advancedOptionsPanel") < html.index("btnFetchLimited")
    tabs_end = html.index("rb-import-tabs") + len("rb-import-tabs")
    assert html.index("skipPositiveTicketsSwitch") > tabs_end
    assert "appendSkipPositiveTickets" in js
    assert "isSkipPositiveTicketsEnabled" in js
    assert "syncSkipPositiveTicketsSwitches" in js
    assert "skip_positive_tickets" in js
    print("OK skip positive tickets markup")


def test_quick_picks_fill_fields_only():
    html = (ROOT / "app" / "templates" / "analysis.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "js" / "analysis.js").read_text(encoding="utf-8")
    assert "fillLiveFetchAppFromPick" in js
    assert "quickPickFetchAllToggle" not in html
    assert "Instant fetch" not in html
    assert "Select an app to fill the import form" in html
    popular_block = js.split("function initPopularAppButtons()", 1)[1].split("function initFetchAllButton()", 1)[0]
    assert "form.requestSubmit();" not in popular_block
    assert "fillLiveFetchAppFromPick" in popular_block
    assert "importTabPlay" in popular_block
    print("OK quick picks fill fields only")


def test_quick_picks_hover_css():
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    style_css = (ROOT / "app" / "static" / "css" / "style.css").read_text(encoding="utf-8")
    scroll_block = theme_css.split(".rb-import-quick-row .quick-picks-scroll")[1].split("}", 1)[0]
    assert "padding: 3px" in scroll_block or "padding-top: 3px" in scroll_block
    assert ".quick-pick-card:hover" in style_css
    assert "translateY(-1px)" in style_css
    assert "border-color: #93c5fd" in style_css
    print("OK quick picks hover CSS")


def test_refresh_does_not_create_second_ticket():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        Ticket.query.delete()
        db.session.commit()

        app_name = "Ticket Once App"
        batch1 = _batch_now()
        play_id = "play-ticket-once-1"

        _process_review(
            app_name,
            "bob",
            1,
            "Terrible experience",
            batch_started_at=batch1,
            play_review_id=play_id,
            owner=TICKET_OWNER,
        )
        db.session.commit()
        assert Ticket.query.count() == 1

        batch2 = _normalize_batch_dt(batch1 + timedelta(seconds=2))
        _process_review(
            app_name,
            "bob",
            1,
            "Terrible experience",
            batch_started_at=batch2,
            play_review_id=play_id,
            owner=TICKET_OWNER,
        )
        db.session.commit()
        assert Review.query.count() == 1
        assert Ticket.query.count() == 1
    print("OK refresh does not create second ticket")


def test_parse_review_row_helper():
    row = {
        "author": " A ",
        "content": " hi ",
        "rating": "4",
        "play_rank": 2,
        "at": "2024-01-15T12:00:00",
        "play_review_id": "abc123",
    }
    parsed = _parse_review_row(row, default_rank=0)
    assert parsed["author"] == "A"
    assert parsed["text"] == "hi"
    assert parsed["rating"] == 4
    assert parsed["play_rank"] == 2
    assert parsed["play_review_id"] == "abc123"
    assert parsed["reviewed_at"] is not None

    fallback = _parse_review_row({"content": "x"}, default_rank=7)
    assert fallback["play_rank"] == 7
    assert fallback["play_review_id"] is None
    print("OK parse review row helper")


def test_parse_review_count_no_upper_cap():
    assert _parse_review_count("100") == 100
    assert _parse_review_count("10000") == 10000
    assert _parse_review_count("50000") == 50000
    assert _parse_review_count(None, default=50) == 50
    assert _parse_review_count("invalid", default=25) == 25
    try:
        _parse_review_count("0")
        assert False, "expected ValueError for zero"
    except ValueError:
        pass
    try:
        _parse_review_count("-5")
        assert False, "expected ValueError for negative"
    except ValueError:
        pass
    print("OK parse review count no upper cap")


def test_home_page_loads():
    home_html = (ROOT / "app" / "templates" / "home.html").read_text(encoding="utf-8")
    assert "_rb_demo_workspace.html" in home_html
    assert 'id="access"' in home_html
    assert "Sign in" in home_html
    assert "Sign in for history" not in home_html
    assert "App search" in home_html
    assert "6200+" not in home_html
    assert "landing-access-card" in home_html
    assert "_rb_demo_insight.html" not in home_html
    assert "_rb_demo_dashboard.html" not in home_html
    assert "variant='compact'" in home_html or 'variant="compact"' in home_html
    assert "variant='full'" in home_html or 'variant="full"' in home_html
    assert "landing-preview reveal" not in home_html.replace(" ", "")

    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    assert "chart.js" not in landing_base.lower()

    app = _test_app()
    client = app.test_client()

    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'href="/analysis"' in html or "/analysis" in html
    assert "Start analysis" in html
    assert "landing-hero-title" in html
    assert "rb-demo-pipeline" not in html
    assert "rb-overview-shell" in html
    assert "percent-bars-inline" in html
    assert "sent-pill" in html
    assert "rb-demo-chart-svg" in html
    assert "rb-demo-dashboard" not in html
    assert 'id="sentimentChart"' not in html
    assert 'id="categoryChart"' not in html
    assert "analysisPipelineCard" not in html
    assert "liveFetchForm" not in html
    print("OK home page loads")


def test_home_demo_workspace_markup():
    workspace = (ROOT / "app" / "templates" / "_rb_demo_workspace.html").read_text(encoding="utf-8")
    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    landing_js = (ROOT / "app" / "static" / "js" / "landing.js").read_text(encoding="utf-8")

    assert "variant == 'compact'" in workspace
    assert "variant == 'full'" in workspace
    assert "rb-demo-workspace--compact" in workspace
    assert "rb-demo-workspace--full" in workspace
    assert "rb-demo-pipeline" not in workspace
    assert "rb-ticket-platform-strip" in workspace
    assert "JIRA-A1B2C3" in workspace
    assert "dashboardTopMetrics" not in workspace
    assert "rb-metric-grid" not in workspace
    assert "rb-demo-chart-svg" in workspace
    assert "rb-demo-bar-chart" in workspace
    assert "tickets-panel-card" in workspace
    assert "reviews-panel-card" in workspace
    assert "sentiment_pill(" in workspace
    assert "category_pill(" in workspace
    assert "_macros.html" in workspace
    assert "<canvas" not in workspace
    assert "sentimentChart" not in workspace
    assert "categoryChart" not in workspace

    assert "chart.js" not in landing_base.lower()
    assert "createDemoCharts" not in landing_js
    assert "revealVisibleInViewport" not in landing_js

    landing_css = (ROOT / "app" / "static" / "css" / "landing.css").read_text(encoding="utf-8")
    assert ".landing-preview," in landing_css or ".landing-preview" in landing_css
    assert "opacity: 1 !important" in landing_css
    assert "rb-demo-pipeline" not in landing_css
    assert "max-width: 1320px" in landing_css
    assert ".landing-access-card" in landing_css
    print("OK home demo workspace markup")


def test_analysis_empty_onboarding_copy():
    analysis_html = (ROOT / "app" / "templates" / "analysis.html").read_text(encoding="utf-8")
    assert "Free to explore" in analysis_html
    assert "Sign in for history" not in analysis_html
    assert "Go to data import" not in analysis_html
    assert "rb-onboarding-actions" not in analysis_html
    assert "platform strip" in analysis_html
    assert "Learn more on the home page" not in analysis_html
    assert "local catalog" not in analysis_html
    assert "Search Google Play or use a quick pick" in analysis_html

    app = _test_app()
    client = app.test_client()
    res = client.get("/analysis")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Free to explore" in html
    assert "filterable reviews" in html.lower() or "platform strip" in html.lower()
    print("OK analysis empty onboarding copy")


def test_analysis_empty_shows_guided_onboarding():
    app = _test_app()
    client = app.test_client()

    res = client.get("/analysis")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "analysis-empty-onboarding" in html
    assert "analysis-onboarding-steps" in html
    assert "analysis-demo-showcase" not in html
    assert "Sample preview" not in html
    assert "Sample data" not in html
    assert 'data-charts-enabled="true"' in html
    assert "sentimentChart" in html
    assert "dashboardTopMetrics" not in html
    assert "liveFetchForm" in html
    assert "dataImportCard" in html
    assert 'max="5000"' not in html
    print("OK analysis empty shows guided onboarding")


def test_clean_no_job_shows_pipeline():
    app = _test_app()
    client = app.test_client()

    res = client.get("/analysis")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    pipeline_class = html.split('id="analysisPipelineCard"')[1].split(">")[0]
    assert "d-none" not in pipeline_class
    assert "is-idle" in pipeline_class
    assert "progress-bar-animated" not in html.split("pipelineProgressBar")[1].split("</div>")[0]
    prepare_idx = html.find('data-phase="prepare"')
    prepare_region = html[max(0, prepare_idx - 120) : prepare_idx + 40]
    assert "is-active" not in prepare_region
    assert "is-pending" in prepare_region
    assert "Ready" in html
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") is None
    print("OK clean no job shows pipeline")


def test_clean_clears_stale_snapshot():
    app = _test_app()
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["pipeline_snapshot"] = {"status": "completed", "progress": 100}

    res = client.get("/analysis")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    pipeline_class = html.split('id="analysisPipelineCard"')[1].split(">")[0]
    assert "analysisPipelineCard" in html
    assert "d-none" not in pipeline_class
    assert "is-idle" in pipeline_class
    assert 'data-has-review-results="false"' in pipeline_class
    assert 'data-pipeline-snapshot="null"' in pipeline_class or "data-pipeline-snapshot='null'" in pipeline_class
    assert "Ready" in html
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") is None
    print("OK clean clears stale snapshot")


def test_clear_analysis_clears_pipeline_snapshot():
    app = _test_app()
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["pipeline_snapshot"] = {"status": "completed", "progress": 100, "phase": "finalize"}

    clear_res = client.post("/analysis/clear", follow_redirects=True)
    assert clear_res.status_code == 200
    html = clear_res.get_data(as_text=True)
    pipeline_class = html.split('id="analysisPipelineCard"')[1].split(">")[0]
    assert "is-idle" in pipeline_class
    assert 'data-has-review-results="false"' in pipeline_class
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") is None

    with client.session_transaction() as sess:
        sess["pipeline_snapshot"] = {"status": "completed", "progress": 100, "phase": "finalize"}
    legacy_clear = client.post("/dashboard/clear", follow_redirects=True)
    assert legacy_clear.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") is None
    print("OK clear analysis clears pipeline snapshot")


def test_play_fetch_helpers():
    assert _resolve_fetch_countries("ww", limited=True) == ["us"]
    assert _resolve_fetch_countries("pk", limited=True) == ["pk"]
    assert len(_resolve_fetch_countries("ww", limited=False)) > 5

    now = datetime.utcnow()
    rows = [
        {"author": "a", "content": "old", "rating": 1, "at": now - timedelta(days=10)},
        {"author": "b", "content": "new", "rating": 5, "at": now},
    ]
    sorted_rows = _sort_rows_by_date(rows)
    assert sorted_rows[0]["author"] == "b"
    print("OK play fetch helpers")


def test_stale_job_status():
    app = _test_app()
    client = app.test_client()

    res = client.get("/fetch/status/00000000-0000-0000-0000-000000000099")
    assert res.status_code == 404
    data = res.get_json()
    assert data.get("stale") is True
    assert not data.get("ok")
    print("OK stale job status")


def test_analysis_prunes_stale_active_job():
    app = _test_app()
    client = app.test_client()
    stale_id = "00000000-0000-0000-0000-000000000099"

    with client.session_transaction() as sess:
        sess["active_fetch_job_id"] = stale_id

    res = client.get("/analysis")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert stale_id not in html

    with client.session_transaction() as sess:
        assert sess.get("active_fetch_job_id") is None
    print("OK analysis prunes stale active job")


def test_dismiss_active():
    app = _test_app()
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["active_fetch_job_id"] = "some-job-id"
        sess["pipeline_snapshot"] = {"status": "completed"}

    res = client.post("/fetch/dismiss-active")
    assert res.status_code == 200
    assert res.get_json().get("ok")

    with client.session_transaction() as sess:
        assert sess.get("active_fetch_job_id") is None
        assert sess.get("pipeline_snapshot") == {"status": "completed"}
    print("OK dismiss active job")


def test_csv_job_flow():
    app = _test_app()
    client = app.test_client()
    _signup_client(client, email="csv-job@test.local")

    with open(CSV_PATH, "rb") as f:
        res = client.post(
            "/upload/start",
            data={"app_name": "Pipeline Test", "review_file": (f, "sample_reviews.csv")},
            content_type="multipart/form-data",
        )
    assert res.status_code == 200, res.get_data(as_text=True)
    payload = res.get_json()
    assert payload.get("ok"), payload
    job_id = payload["job_id"]

    data = {}
    for _ in range(180):
        status_res = client.get(f"/fetch/status/{job_id}")
        assert status_res.status_code == 200
        data = status_res.get_json()
        assert data.get("ok"), data
        if data.get("status") in ("completed", "error", "cancelled"):
            break
        time.sleep(0.5)

    assert data.get("status") == "completed", data
    assert data.get("phase") == "finalize"
    assert data.get("progress") == 100

    act = client.post(f"/fetch/activate/{job_id}")
    assert act.status_code == 200
    act_data = act.get_json()
    assert act_data.get("ok")
    assert act_data.get("pipeline_snapshot")
    assert act_data["pipeline_snapshot"].get("status") == "completed"
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") is not None

    since = act_data.get("batch_started_at")
    assert since
    batch_res = client.get(f"/analysis?since={since}")
    assert batch_res.status_code == 200
    batch_html = batch_res.get_data(as_text=True)
    assert "rb-ticket-platform-strip" in batch_html
    pipeline_class = batch_html.split('id="analysisPipelineCard"')[1].split(">")[0]
    assert "d-none" not in pipeline_class
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") is not None
    print(f"OK csv job processed={data.get('processed')} skipped={data.get('skipped')}")


def test_batch_with_snapshot_keeps_pipeline_visible():
    app = _test_app()
    client = app.test_client()
    email = "batch-snapshot@test.local"
    _signup_client(client, email=email)

    with app.app_context():
        Review.query.delete()
        db.session.commit()
        user = User.query.filter_by(email=email).one()
        owner = OwnerContext(user_id=user.id, owner_session_key=None, allow_tickets=True, integration=None)
        batch = _batch_now()
        _process_review(
            "Bridge Test",
            "alice",
            5,
            "Great app",
            batch_started_at=batch,
            play_rank=0,
            owner=owner,
        )
        db.session.commit()
        since_iso = batch.isoformat()

    snapshot = {"status": "completed", "progress": 100, "phase": "finalize"}
    with client.session_transaction() as sess:
        sess["pipeline_snapshot"] = snapshot

    res = client.get(f"/analysis?since={since_iso}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "rb-ticket-platform-strip" in html
    pipeline_class = html.split('id="analysisPipelineCard"')[1].split(">")[0]
    assert "d-none" not in pipeline_class
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") == snapshot
    print("OK batch with snapshot keeps pipeline visible")


def test_review_storage_id():
    play_id = "gp:AOqpTOEabc123"
    author, content, rating = "user1", "Great app", 5
    app_name = "Test App"
    assert review_storage_id(app_name, play_id, author, content, rating) == f"play:{play_id}"
    h = stable_review_id(author, content, rating)
    assert review_storage_id(app_name, "", author, content, rating) == f"test app:{h}"
    assert review_storage_id(app_name, None, author, content, rating) == f"test app:{h}"
    print("OK review_storage_id")


def test_play_row_metadata():
    epoch = datetime(2024, 6, 15, 12, 30, 0).timestamp()
    row = {
        "userName": "Alice",
        "score": 4,
        "content": "Nice",
        "reviewId": "rid-99",
        "at": datetime.fromtimestamp(epoch),
    }
    entry = _review_entry_from_play_row(row)
    assert entry["play_review_id"] == "rid-99"
    assert entry["at"] == datetime.utcfromtimestamp(epoch)
    print("OK play row metadata")


def test_play_rank_on_merge():
    out = []
    seen = set()
    play_rows = [
        {"userName": "A", "score": 5, "content": "first", "reviewId": "r1"},
        {"userName": "B", "score": 4, "content": "second", "reviewId": "r2"},
        {"userName": "C", "score": 3, "content": "third", "reviewId": "r3"},
    ]
    _merge_rows(play_rows, out, seen, None)
    assert [r["play_rank"] for r in out] == [0, 1, 2]
    assert [r["author"] for r in out] == ["A", "B", "C"]
    print("OK play_rank on merge")


def test_merge_skips_empty_content():
    out = []
    seen = set()
    play_rows = [
        {"userName": "A", "score": 5, "content": "", "reviewId": "r1"},
        {"userName": "B", "score": 4, "content": "has text", "reviewId": "r2"},
        {"userName": "C", "score": 3, "content": "", "reviewId": "r3"},
    ]
    _merge_rows(play_rows, out, seen, None)
    assert len(out) == 1
    assert out[0]["author"] == "B"
    assert out[0]["play_rank"] == 0
    print("OK merge skips empty content")


def test_merge_stops_at_target():
    out = []
    seen = set()
    play_rows = [
        {"userName": f"U{i}", "score": 5, "content": f"text{i}", "reviewId": f"r{i}"} for i in range(5)
    ]
    _merge_rows(play_rows, out, seen, 3)
    assert len(out) == 3
    assert [r["play_rank"] for r in out] == [0, 1, 2]
    print("OK merge stops at target")


def test_coerce_review_datetime_formats():
    dt = datetime(2024, 3, 15, 10, 30, 0)
    assert _coerce_review_datetime(dt) == dt
    assert _coerce_review_datetime("2024-03-15T10:30:00Z").year == 2024
    ts_ms = int(dt.timestamp() * 1000)
    assert _coerce_review_datetime(ts_ms).year == 2024
    print("OK coerce_review_datetime formats")


def test_normalize_play_review_at_local_to_utc():
    epoch = datetime(2024, 6, 15, 14, 30, 0).timestamp()
    local_naive = datetime.fromtimestamp(epoch)
    utc_expected = datetime.utcfromtimestamp(epoch)
    assert normalize_play_review_at(local_naive) == utc_expected
    assert normalize_play_review_at("2024-06-15T14:30:00Z") == utc_expected.replace(
        hour=14, minute=30, second=0
    )
    print("OK normalize play review at local to utc")


def test_csv_upload_passes_reviewed_at():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        db.session.commit()

        batch = _batch_now()
        row = {
            "author": "csv_user",
            "content": "CSV dated review",
            "rating": "5",
            "date": "2024-03-15T10:30:00Z",
        }
        reviewed_at = _parse_csv_review_date(row)
        assert reviewed_at is not None
        assert reviewed_at.year == 2024
        assert reviewed_at.month == 3
        assert reviewed_at.day == 15

        _process_review(
            "CSV Date App",
            row["author"],
            int(row["rating"]),
            row["content"],
            batch_started_at=batch,
            reviewed_at=reviewed_at,
            play_rank=0,
            owner=BATCH_OWNER,
        )
        db.session.commit()

        review = Review.query.filter_by(app_name="CSV Date App").first()
        assert review is not None
        assert review.reviewed_at == reviewed_at
    print("OK csv upload passes reviewed_at")


def test_reviewed_at_updated_on_refresh():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        db.session.commit()

        batch1 = _batch_now()
        play_id = "date-refresh-1"
        old_date = datetime(2023, 1, 10, 12, 0, 0)
        new_date = datetime(2025, 6, 1, 8, 0, 0)

        _process_review(
            "Date Test",
            "user",
            4,
            "hello",
            batch_started_at=batch1,
            play_review_id=play_id,
            reviewed_at=old_date,
            play_rank=0,
            owner=TICKET_OWNER,
        )
        db.session.commit()

        batch2 = _normalize_batch_dt(batch1 + timedelta(seconds=5))
        _process_review(
            "Date Test",
            "user",
            4,
            "hello",
            batch_started_at=batch2,
            play_review_id=play_id,
            reviewed_at=new_date,
            play_rank=0,
            owner=TICKET_OWNER,
        )
        db.session.commit()

        review = Review.query.filter_by(review_id=f"u1:play:{play_id}").first()
        assert review.reviewed_at == new_date
    print("OK reviewed_at updated on refresh")


def test_finalize_preserves_api_order_for_newest():
    now = datetime.utcnow()
    rows = [
        {"author": "play_top", "content": "a", "rating": 5, "at": now - timedelta(days=30), "play_rank": 0},
        {"author": "play_second", "content": "b", "rating": 4, "at": now, "play_rank": 1},
    ]
    result = _finalize_fetch_rows(rows, "newest", multi_country=False)
    assert [r["author"] for r in result] == ["play_top", "play_second"]
    by_date = _sort_rows_by_date(list(rows))
    assert [r["author"] for r in by_date] == ["play_second", "play_top"]
    print("OK finalize preserves API order for newest")


def test_batch_query_orders_by_play_rank():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        db.session.commit()

        batch = _batch_now()
        app_name = "Order Test"
        for rank, author in enumerate(["first", "second", "third"]):
            _process_review(
                app_name,
                author,
                5,
                f"text {author}",
                batch_started_at=batch,
                play_rank=rank,
                reviewed_at=batch - timedelta(days=rank),
                owner=BATCH_OWNER,
            )
        db.session.commit()

        ordered = _batch_reviews_query(batch, BATCH_OWNER).all()
        assert [r.author for r in ordered] == ["first", "second", "third"]
    print("OK batch query orders by play_rank")


def test_refetch_refreshes_into_batch():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        db.session.commit()

        app_name = "Refresh Test App"
        batch1 = _batch_now()
        play_id = "play-test-refresh-1"
        storage_id = scoped_storage_id(1, None, app_name, play_id, "bob", "Works well", 5)

        ok1, reason1, _ = _process_review(
            app_name,
            "bob",
            5,
            "Works well",
            batch_started_at=batch1,
            play_review_id=play_id,
            reviewed_at=batch1 - timedelta(days=2),
            play_rank=0,
            owner=TICKET_OWNER,
        )
        assert ok1 and reason1 == "processed"
        db.session.commit()

        batch2 = _normalize_batch_dt(batch1 + timedelta(seconds=5))
        ok2, reason2, _ = _process_review(
            app_name,
            "bob",
            5,
            "Works well",
            batch_started_at=batch2,
            play_review_id=play_id,
            reviewed_at=batch1 - timedelta(days=2),
            play_rank=0,
            owner=TICKET_OWNER,
        )
        assert ok2 and reason2 == "refreshed"
        db.session.commit()

        assert Review.query.filter_by(review_id=storage_id).count() == 1
        review = Review.query.filter_by(review_id=storage_id).first()
        assert review.last_batch_at == batch2

        in_batch1 = _batch_reviews_query(batch1, TICKET_OWNER).all()
        in_batch2 = _batch_reviews_query(batch2, TICKET_OWNER).all()
        assert len(in_batch1) == 0
        assert len(in_batch2) == 1
        assert in_batch2[0].id == review.id
    print("OK refetch refreshes into batch")


def test_auth_pages_modern_markup():
    login_tpl = (ROOT / "app" / "templates" / "auth" / "login.html").read_text(encoding="utf-8")
    signup_tpl = (ROOT / "app" / "templates" / "auth" / "signup.html").read_text(encoding="utf-8")
    base_tpl = (ROOT / "app" / "templates" / "auth" / "_base_auth.html").read_text(encoding="utf-8")
    auth_css = (ROOT / "app" / "static" / "css" / "auth.css").read_text(encoding="utf-8")
    auth_js = (ROOT / "app" / "static" / "js" / "auth.js").read_text(encoding="utf-8")

    assert 'extends "auth/_base_auth.html"' in login_tpl
    assert 'extends "auth/_base_auth.html"' in signup_tpl
    assert "<!doctype html>" not in login_tpl
    assert "<!doctype html>" not in signup_tpl

    assert "auth-showcase" in base_tpl
    assert "auth-bg" in base_tpl
    assert "auth-container" in base_tpl
    assert "auth-nav" in base_tpl
    assert "auth-nav-actions" in base_tpl
    nav_actions_block = base_tpl.split("auth-nav-actions")[1].split("</div>")[0]
    assert "main.home" in nav_actions_block
    assert "main.analysis" in nav_actions_block
    assert ">Home</a>" in nav_actions_block
    assert ">Analysis</a>" in nav_actions_block
    assert "_site_nav.html" not in base_tpl
    assert "nav_mode = 'auth'" not in base_tpl
    assert "auth.js" in base_tpl
    assert "nav-scroll.js" not in base_tpl
    assert "landing.css" not in base_tpl
    assert "_auth_showcase.html" not in base_tpl
    assert not (ROOT / "app" / "templates" / "auth" / "_auth_showcase.html").is_file()

    assert 'name="email"' in login_tpl
    assert 'name="password"' in login_tpl
    assert 'name="remember"' in login_tpl
    assert 'name="display_name"' in signup_tpl
    assert 'name="confirm_password"' in signup_tpl
    assert "data-password-toggle" in login_tpl
    assert "data-auth-form" in login_tpl

    assert ".auth-showcase" in auth_css
    assert ".auth-container" in auth_css
    assert "max-width: 1320px" in auth_css
    assert "auth-showcase-preview" not in auth_css
    assert ".auth-nav" in auth_css
    assert ".auth-nav-actions" in auth_css
    assert ".auth-form-card" in auth_css
    assert ".auth-field-control" in auth_css
    assert "prefers-reduced-motion" in auth_css
    assert "data-password-toggle" in auth_js
    assert "is-ready" in auth_js
    assert "is-loading" in auth_js

    app = _test_app()
    client = app.test_client()
    login_page = client.get("/auth/login")
    signup_page = client.get("/auth/signup")
    assert login_page.status_code == 200
    assert signup_page.status_code == 200
    login_html = login_page.get_data(as_text=True)
    signup_html = signup_page.get_data(as_text=True)
    assert "auth-showcase" in login_html
    assert "auth-form-card" in login_html
    assert "auth-nav" in login_html
    assert "auth-nav-actions" in login_html
    assert ">Home</a>" in login_html
    assert ">Analysis</a>" in login_html
    assert "auth.js" in login_html
    assert "nav-scroll.js" not in login_html
    assert 'name="email"' in login_html
    assert "Create account" in login_html
    assert "rb-demo-workspace" not in login_html
    assert "Analysis workspace" not in login_html
    assert "auth-showcase" in signup_html
    assert 'name="confirm_password"' in signup_html
    assert "rb-demo-workspace" not in signup_html
    print("OK auth pages modern markup")


def test_auth_signup_login_logout():
    app = _test_app()
    client = app.test_client()
    email = "auth-flow@test.local"
    password = "testpass123"

    signup = client.post(
        "/auth/signup",
        data={
            "email": email,
            "display_name": "Auth Flow",
            "password": password,
            "confirm_password": password,
        },
        follow_redirects=True,
    )
    assert signup.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user is not None

    logout = client.post("/auth/logout", follow_redirects=False)
    assert logout.status_code in (200, 302)

    login = client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )
    assert login.status_code == 200
    assert b"Analysis" in login.data or b"analysis" in login.data.lower()
    print("OK auth signup login logout")


def test_anonymous_process_no_tickets():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        Ticket.query.delete()
        db.session.commit()
        batch = _batch_now()
        ok, reason, meta = _process_review(
            "Anon App",
            "user",
            1,
            "Broken login keeps failing",
            batch_started_at=batch,
            owner=BATCH_OWNER,
        )
        assert ok and reason == "processed"
        assert meta.get("platform") is None
        db.session.commit()
        assert Review.query.count() == 1
        assert Ticket.query.count() == 0
        review = Review.query.first()
        assert review.owner_session_key == BATCH_OWNER.owner_session_key
        assert review.user_id is None
    print("OK anonymous process no tickets")


def test_logged_in_process_creates_mock_ticket():
    app = _test_app()

    with app.app_context():
        Review.query.delete()
        Ticket.query.delete()
        db.session.commit()
        batch = _batch_now()
        ok, reason, meta = _process_review(
            "Logged In App",
            "user",
            1,
            "Broken login keeps failing",
            batch_started_at=batch,
            owner=TICKET_OWNER,
        )
        assert ok and reason == "processed"
        assert meta.get("platform")
        db.session.commit()
        assert Review.query.count() == 1
        assert Ticket.query.count() == 1
        ticket = Ticket.query.first()
        assert ticket.external_ticket_id != "FAILED"
        assert ticket.external_ticket_id.startswith(("JIRA-", "ZD-", "RA-"))
    print("OK logged in process creates mock ticket")


def test_disabled_integration_uses_mock_not_env():
    from app.ticketing import create_jira_ticket, create_zendesk_ticket

    class _Review:
        source = "Google Play"
        app_name = "Test App"
        author = "user"
        rating = 2
        content = "App crashes on login"
        sentiment = "negative"
        category = "bug"
        confidence = 0.8

    integration = UserIntegrationSettings(user_id=99, jira_enabled=False, zendesk_enabled=False)
    jira = create_jira_ticket(_Review(), 1, integration=integration)
    zendesk = create_zendesk_ticket(_Review(), 1, integration=integration)
    assert jira["mode"] == "mock"
    assert jira["external_ticket_id"].startswith("JIRA-")
    assert jira["external_ticket_id"] != "FAILED"
    assert zendesk["mode"] == "mock"
    assert zendesk["external_ticket_id"].startswith("ZD-")
    print("OK disabled integration uses mock not env")


def test_enabled_incomplete_integration_uses_mock():
    from app.ticketing import create_jira_ticket

    class _Review:
        source = "Google Play"
        app_name = "Test App"
        author = "user"
        rating = 2
        content = "Needs help"
        sentiment = "negative"
        category = "support"
        confidence = 0.8

    integration = UserIntegrationSettings(
        user_id=100,
        jira_enabled=True,
        jira_base_url="https://example.atlassian.net",
        jira_email="dev@example.com",
        jira_project_key="PRJ",
        jira_api_token_encrypted=None,
    )
    result = create_jira_ticket(_Review(), 2, integration=integration)
    assert result["mode"] == "mock"
    assert result["external_ticket_id"].startswith("JIRA-")
    assert result["external_ticket_id"] != "FAILED"
    print("OK enabled incomplete integration uses mock")


def test_integrations_ui_split_cards():
    html = (ROOT / "app" / "templates" / "account" / "settings.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "js" / "settings-integrations.js").read_text(encoding="utf-8")
    assert "save_jira" in html
    assert "save_zendesk" in html
    assert "settings-integration-card--jira" in html
    assert "settings-integration-card--zendesk" in html
    assert "data-integration-card" in html
    assert "data-integration-toggle" in html
    assert "data-integration-fields" in html
    assert 'value="{{ integration.jira_project_key or \'\' }}"' in html
    assert 'or \'RA\'' not in html
    assert "settings-integrations.js" in html
    assert "data-integration-toggle" in js
    print("OK integrations UI split cards")


def test_jira_adf_description_format():
    from app.ticketing import _plain_text_to_adf

    adf = _plain_text_to_adf("Source: Google Play\nRating: 3/5\n\nReview:\nApp crashes")
    assert adf["type"] == "doc"
    assert adf["version"] == 1
    assert len(adf["content"]) == 5
    assert adf["content"][0]["type"] == "paragraph"
    assert adf["content"][0]["content"][0]["text"] == "Source: Google Play"
    assert adf["content"][2]["content"] == []
    assert adf["content"][4]["content"][0]["text"] == "App crashes"

    empty = _plain_text_to_adf("")
    assert empty["type"] == "doc"
    assert len(empty["content"]) == 1
    assert empty["content"][0]["content"] == []
    print("OK jira adf description format")


def test_user_initials_property():
    user = User(email="a@b.com", display_name="Jane Doe", password_hash="x")
    assert user.initials == "JD"
    user.display_name = "Alice"
    assert user.initials == "AL"
    user.display_name = ""
    user.email = "solo@example.com"
    assert user.initials == "SO"
    print("OK user initials property")


def test_avatar_nav_markup():
    base_html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    landing_html = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    site_nav = (ROOT / "app" / "templates" / "_site_nav.html").read_text(encoding="utf-8")
    dropdown_partial = (ROOT / "app" / "templates" / "_nav_account_dropdown.html").read_text(encoding="utf-8")
    macros_html = (ROOT / "app" / "templates" / "_macros.html").read_text(encoding="utf-8")
    style_css = (ROOT / "app" / "static" / "css" / "style.css").read_text(encoding="utf-8")

    assert "_site_nav.html" in base_html
    assert "_site_nav.html" in landing_html
    assert "_nav_account_dropdown.html" in site_nav
    assert "rb-nav-avatar-link" not in base_html
    assert "rb-nav-avatar-link" not in landing_html
    assert "rb-nav-avatar-link" not in site_nav
    assert "rb-nav-avatar-toggle" in dropdown_partial
    assert dropdown_partial.count('data-bs-toggle="dropdown"') == 1
    assert "current_user.label" in dropdown_partial
    assert 'title="{{ current_user.label }}"' in dropdown_partial
    assert 'aria-label="Account menu for {{ current_user.label }}"' in dropdown_partial
    assert "current_user.email" in dropdown_partial
    assert "account.settings" in dropdown_partial
    assert "auth.logout" in dropdown_partial
    assert "user_avatar" in dropdown_partial
    assert "account.avatar" in macros_html
    assert ".rb-nav-avatar-toggle" in style_css
    assert ".rb-avatar" in style_css
    print("OK avatar nav markup")


def test_settings_profile_avatar_markup():
    html = (ROOT / "app" / "templates" / "account" / "settings.html").read_text(encoding="utf-8")
    assert 'enctype="multipart/form-data"' in html
    assert 'name="avatar"' in html
    assert "remove_avatar" in html
    assert "profile-avatar-row" in html
    assert "user_avatar" in html
    print("OK settings profile avatar markup")


def test_avatar_route_requires_login():
    app = _test_app()
    client = app.test_client()
    resp = client.get("/account/avatar")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")
    print("OK avatar route requires login")


def test_history_requires_login():
    app = _test_app()
    client = app.test_client()
    resp = client.get("/history")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")
    print("OK history requires login")


def test_settings_requires_login():
    app = _test_app()
    client = app.test_client()
    resp = client.get("/account/settings")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")

    _signup_client(client, email="settings@test.local")
    resp = client.get("/account/settings")
    assert resp.status_code == 200
    assert b"Integrations" in resp.data
    print("OK settings requires login")


def test_delete_account_modal_markup():
    html = (ROOT / "app" / "templates" / "account" / "settings.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "js" / "settings-delete-account.js").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "css" / "auth.css").read_text(encoding="utf-8")

    assert "deleteAccountModal" in html
    assert "deletePhraseInput" in html
    open_btn = html.split('id="deleteAccountOpen"')[0][-80:] + 'id="deleteAccountOpen"' + html.split('id="deleteAccountOpen"')[1][:120]
    assert 'type="button"' in open_btn
    assert "deleteAccountOpen" in open_btn
    assert "settings-delete-account.js" in html
    assert "confirm_phrase" in html
    assert "account.delete_account" in html
    assert 'name="confirm_email"' in html
    assert 'name="password"' in html
    assert "deleteAccountSubmit" in html
    assert "rb-delete-modal" in html
    assert "initDeleteAccountModal" in js
    assert 'PHRASE = "delete"' in js or 'PHRASE = \"delete\"' in js
    assert ".rb-delete-modal" in css
    print("OK delete account modal markup")


def test_delete_account_requires_confirm_phrase():
    app = _test_app()
    client = app.test_client()
    email = "delete-guard@test.local"
    password = "testpass123"
    _signup_client(client, email=email, password=password)

    resp = client.post(
        "/account/delete",
        data={
            "confirm_email": email,
            "password": password,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Confirmation phrase was missing or incorrect" in resp.data

    with app.app_context():
        assert User.query.filter_by(email=email).first() is not None
    print("OK delete account requires confirm phrase")


def test_history_user_scoped():
    app = _test_app()
    client = app.test_client()
    email_a = "user-a@test.local"
    email_b = "user-b@test.local"

    with app.app_context():
        for email in (email_a, email_b):
            user = User.query.filter_by(email=email).first()
            if not user:
                continue
            Review.query.filter_by(user_id=user.id).delete()
            Ticket.query.filter_by(user_id=user.id).delete()
            db.session.delete(user)
        db.session.commit()

    _signup_client(client, email=email_a)
    with app.app_context():
        user_a = User.query.filter_by(email=email_a).one()
        batch = _batch_now()
        _process_review(
            "Scoped App",
            "alice",
            2,
            "Needs help with billing",
            batch_started_at=batch,
            owner=OwnerContext(user_a.id, None, True, None),
        )
        db.session.commit()

    resp_a = client.get("/history")
    assert resp_a.status_code == 200
    assert b"Scoped App" in resp_a.data

    client.post("/auth/logout")
    _signup_client(client, email=email_b)
    resp_b = client.get("/history")
    assert resp_b.status_code == 200
    assert b"Scoped App" not in resp_b.data
    print("OK history user scoped")


def test_idle_session_expires():
    from datetime import datetime, timezone

    from app.session_idle import LAST_ACTIVITY_KEY

    app = _test_app()
    app.config["SESSION_IDLE_TIMEOUT_MINUTES"] = 30
    client = app.test_client()
    _signup_client(client, email="idle-expire@test.local")

    with client.session_transaction() as sess:
        sess[LAST_ACTIVITY_KEY] = datetime.now(timezone.utc).timestamp() - 3600

    resp = client.get("/history")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")

    _signup_client(client, email="idle-expire2@test.local")
    resp = client.get("/account/settings")
    assert resp.status_code == 200
    print("OK idle session expires")


def test_idle_session_touch_keeps_login():
    from datetime import datetime, timezone

    from app.session_idle import LAST_ACTIVITY_KEY

    app = _test_app()
    client = app.test_client()
    _signup_client(client, email="idle-touch@test.local")

    with client.session_transaction() as sess:
        sess[LAST_ACTIVITY_KEY] = datetime.now(timezone.utc).timestamp()

    resp = client.get("/history")
    assert resp.status_code == 200
    print("OK idle session touch keeps login")


def test_idle_session_fetch_returns_401_json():
    from datetime import datetime, timezone

    from app.session_idle import LAST_ACTIVITY_KEY

    app = _test_app()
    client = app.test_client()
    _signup_client(client, email="idle-fetch@test.local")

    with client.session_transaction() as sess:
        sess[LAST_ACTIVITY_KEY] = datetime.now(timezone.utc).timestamp() - 3600

    resp = client.get("/fetch/status/nonexistent-job")
    assert resp.status_code == 401
    data = resp.get_json()
    assert data.get("login_required") is True
    assert "Session expired" in data.get("error", "")
    print("OK idle session fetch returns 401 json")


def test_testing_uses_isolated_database():
    app = create_app(testing=True)
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert ":memory:" in uri
    assert "reviewbridge.db" not in uri.replace("\\", "/")

    with app.app_context():
        engine_url = str(db.engine.url)
        assert ":memory:" in engine_url
    print("OK testing uses isolated database")


def test_database_uri_is_canonical_absolute():
    app = create_app(testing=False)
    uri = app.config["SQLALCHEMY_DATABASE_URI"].replace("\\", "/")
    assert "/instance/instance/" not in uri
    assert uri.endswith("/instance/reviewbridge.db")

    with app.app_context():
        engine_url = str(db.engine.url).replace("\\", "/")
        assert "/instance/instance/" not in engine_url
        assert engine_url.endswith("/instance/reviewbridge.db")
    print("OK database uri is canonical absolute")


def test_signup_existing_email_logs_in_with_password():
    app = _test_app()
    client = app.test_client()
    email = "signup-dup-ok@test.local"
    password = "testpass123"

    _signup_client(client, email=email, password=password)
    client.post("/auth/logout")

    resp = client.post(
        "/auth/signup",
        data={
            "email": email,
            "display_name": "Dup",
            "password": password,
            "confirm_password": password,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/auth/login" not in resp.headers.get("Location", "")

    history = client.get("/history")
    assert history.status_code == 200
    print("OK signup existing email logs in with password")


def test_signup_existing_email_wrong_password_redirects_login():
    app = _test_app()
    client = app.test_client()
    email = "signup-dup-bad@test.local"
    password = "testpass123"

    _signup_client(client, email=email, password=password)
    client.post("/auth/logout")

    resp = client.post(
        "/auth/signup",
        data={
            "email": email,
            "display_name": "Dup",
            "password": "wrongpassword99",
            "confirm_password": "wrongpassword99",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    loc = resp.headers.get("Location", "")
    assert "/auth/login" in loc
    assert "email=" in loc
    assert email.replace("@", "%40") in loc or email in loc

    history = client.get("/history")
    assert history.status_code == 302
    assert "/auth/login" in history.headers.get("Location", "")

    login_page = client.get(f"/auth/login?email={email}")
    assert login_page.status_code == 200
    assert email in login_page.get_data(as_text=True)
    print("OK signup existing email wrong password redirects login")


if __name__ == "__main__":
    test_home_page_loads()
    test_home_demo_workspace_markup()
    test_analysis_empty_onboarding_copy()
    test_analysis_empty_shows_guided_onboarding()
    test_clean_no_job_shows_pipeline()
    test_clean_clears_stale_snapshot()
    test_clear_analysis_clears_pipeline_snapshot()
    test_analysis_markup()
    test_review_results_filter_js()
    test_app_match_ranking_name_first()
    test_merge_and_rank_suggestions_local_first()
    test_app_catalog_status_endpoint()
    test_app_catalog_module_loads()
    test_pk_priority_apps_file()
    test_build_catalog_pk_seeds()
    test_build_catalog_uses_multi_country()
    test_catalog_pk_apps_local_search()
    test_app_suggestions_typed_search()
    test_app_suggestions_local_only_endpoint()
    test_app_suggestions_play_only_endpoint()
    test_normalize_play_lang()
    test_resolve_search_countries_pk()
    test_app_suggestions_play_only_pk_smoke()
    test_search_js_country_change_rerun()
    test_search_js_play_loading_state()
    test_form_switch_refined_styles()
    test_app_nav_has_home_link()
    test_flash_messages_shared()
    test_sticky_nav_scroll_offset_css()
    test_footer_sticky_layout_css()
    test_dead_css_removed()
    test_landing_nav_modern_theme()
    test_export_download_options()
    test_nav_scroll_shared_js()
    test_nav_static_assets()
    test_history_page_no_dashboard_charts()
    test_history_scrollable_layout()
    test_storage_health_endpoint()
    test_hash_then_play_single_review_single_ticket()
    test_skip_positive_tickets_when_enabled()
    test_skip_positive_tickets_default_off()
    test_skip_positive_tickets_markup()
    test_quick_picks_fill_fields_only()
    test_quick_picks_hover_css()
    test_refresh_does_not_create_second_ticket()
    test_parse_review_row_helper()
    test_parse_review_count_no_upper_cap()
    test_play_fetch_helpers()
    test_review_storage_id()
    test_play_row_metadata()
    test_play_rank_on_merge()
    test_merge_skips_empty_content()
    test_merge_stops_at_target()
    test_coerce_review_datetime_formats()
    test_normalize_play_review_at_local_to_utc()
    test_csv_upload_passes_reviewed_at()
    test_reviewed_at_updated_on_refresh()
    test_finalize_preserves_api_order_for_newest()
    test_batch_query_orders_by_play_rank()
    test_refetch_refreshes_into_batch()
    test_auth_pages_modern_markup()
    test_auth_signup_login_logout()
    test_anonymous_process_no_tickets()
    test_logged_in_process_creates_mock_ticket()
    test_history_requires_login()
    test_settings_requires_login()
    test_delete_account_modal_markup()
    test_delete_account_requires_confirm_phrase()
    test_history_user_scoped()
    test_idle_session_expires()
    test_idle_session_touch_keeps_login()
    test_idle_session_fetch_returns_401_json()
    test_testing_uses_isolated_database()
    test_database_uri_is_canonical_absolute()
    test_signup_existing_email_logs_in_with_password()
    test_signup_existing_email_wrong_password_redirects_login()
    test_disabled_integration_uses_mock_not_env()
    test_enabled_incomplete_integration_uses_mock()
    test_integrations_ui_split_cards()
    test_jira_adf_description_format()
    test_user_initials_property()
    test_avatar_nav_markup()
    test_settings_profile_avatar_markup()
    test_avatar_route_requires_login()
    test_stale_job_status()
    test_analysis_prunes_stale_active_job()
    test_dismiss_active()
    test_batch_with_snapshot_keeps_pipeline_visible()
    test_csv_job_flow()
    print("All pipeline smoke tests passed.")

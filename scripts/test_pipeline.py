"""Smoke-test analysis pipeline API and dashboard markup."""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app, db
from app.analyzer import review_storage_id, stable_review_id
from app.google_play import (
    _finalize_fetch_rows,
    _merge_rows,
    _resolve_fetch_countries,
    _review_entry_from_play_row,
    _sort_rows_by_date,
)
from app.models import Review
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


def test_analysis_markup():
    html = (ROOT / "app" / "templates" / "analysis.html").read_text(encoding="utf-8")
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
        "dashboardMainContent",
        "dashboardTopMetrics",
        "liveAnalysisPanels",
        "sentimentChart",
        "fetchCountryInput",
        "fetchLangHidden",
        "fetchSortHidden",
        "statRefreshed",
        "rb-page-header",
    ]
    missing = [x for x in required if x not in html]
    assert not missing, f"Missing in analysis.html: {missing}"
    idx_import = html.find("rb-import-quick-row")
    idx_pipeline = html.find("analysisPipelineCard")
    idx_main = html.find('id="dashboardMainContent"')
    assert 0 <= idx_import < idx_pipeline < idx_main, (
        "Expected import row, then pipeline card, then dashboardMainContent"
    )
    assert "analysis-demo-showcase" not in html
    assert "_rb_demo_insight.html" not in html
    assert "fetchStatusCard" not in html
    assert "pipelineLogStream" not in html
    assert 'value="us" selected' in html or "United States" in html
    assert 'max="5000"' not in html
    print("OK analysis markup")


def test_app_nav_has_home_link():
    base_html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")

    assert 'class="rb-nav rb-nav--app"' in base_html
    assert "rb-nav-pills" in base_html
    assert "rb-nav-link" in base_html
    nav_block = base_html.split('class="rb-nav-pills"')[1].split("</div>")[0]
    assert "main.home" in nav_block
    assert ">Home</a>" in nav_block
    assert nav_block.index(">Home</a>") < nav_block.index(">Analysis</a>")

    assert "rb-nav-inner--landing" in landing_base
    landing_pills = landing_base.split('class="rb-nav-pills"')[1].split("</div>")[0]
    assert "main.home" in landing_pills
    assert ">Home</a>" in landing_pills
    assert "main.analysis" not in landing_pills
    assert "main.history" not in landing_pills
    assert ">Analysis</a>" not in landing_pills
    assert ">History</a>" not in landing_pills

    landing_actions = landing_base.split('class="landing-nav-actions"')[1].split("</div>")[0]
    assert "main.analysis" in landing_actions
    assert "main.history" in landing_actions
    print("OK app nav has home link")


def test_sticky_nav_scroll_offset_css():
    theme_css = (ROOT / "app" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    style_css = (ROOT / "app" / "static" / "css" / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

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

    for token in (
        "--rb-nav-landing-shell-bg:",
        "--rb-nav-landing-aurora:",
        "--rb-nav-landing-active-gradient:",
        "--rb-nav-landing-capsule-offset:",
    ):
        assert token in theme_css, f"missing landing nav token: {token}"

    landing_nav_block = theme_css.split(".rb-nav--landing {")[1].split(".rb-nav--landing > .landing-container")[0]
    assert "position: fixed" in landing_nav_block
    assert "background: transparent" in landing_nav_block
    assert "var(--rb-nav-landing-bg)" not in landing_nav_block

    shell_block = theme_css.split(".rb-nav--landing > .landing-container {")[1].split(
        ".rb-nav--landing > .landing-container::after"
    )[0]
    assert "backdrop-filter: blur(20px)" in shell_block
    assert "border-radius: 16px" in shell_block
    assert "var(--rb-nav-landing-shell-bg)" in shell_block

    assert "var(--rb-nav-landing-aurora)" in theme_css
    assert ".rb-nav--landing > .landing-container::after" in theme_css

    active_block = theme_css.split(".rb-nav--landing .rb-nav-link.is-active {")[1].split("}")[0]
    assert "var(--rb-nav-landing-active-gradient)" in active_block
    assert "var(--rb-nav-landing-active-glow)" in active_block

    assert "var(--rb-nav-landing-capsule-offset)" in landing_css
    assert "padding: calc(var(--rb-nav-landing-capsule-offset) + 4rem)" in landing_css
    print("OK landing nav modern theme")


def test_export_download_options():
    analysis_html = (ROOT / "app" / "templates" / "analysis.html").read_text(encoding="utf-8")
    history_html = (ROOT / "app" / "templates" / "history.html").read_text(encoding="utf-8")
    routes_py = (ROOT / "app" / "routes.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    home_html = (ROOT / "app" / "templates" / "home.html").read_text(encoding="utf-8")

    assert "export_dashboard_csv" in analysis_html
    assert "export_dashboard_xlsx" in analysis_html
    assert "export_history_csv" in history_html
    assert "export_history_xlsx" in history_html

    for html in (analysis_html, history_html):
        assert "_pdf" not in html
        assert "PDF</a>" not in html
        assert "(report + data)" not in html
        assert "(colors)" not in html
        assert ">CSV</a>" in html
        assert ">Excel</a>" in html

    assert "export_dashboard_pdf" not in routes_py
    assert "export_history_pdf" not in routes_py
    assert "_build_professional_pdf" not in routes_py
    assert "reportlab" not in routes_py.lower()

    assert "reportlab" not in requirements.lower()
    assert "pdf for presentations" not in home_html.lower()

    app = create_app()
    with app.app_context():
        client = app.test_client()
        assert client.get("/export/dashboard.pdf").status_code == 404
        assert client.get("/export/history.pdf").status_code == 404
    print("OK export download options")


def test_nav_scroll_shared_js():
    nav_js = (ROOT / "app" / "static" / "js" / "nav-scroll.js").read_text(encoding="utf-8")
    base_html = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    landing_js = (ROOT / "app" / "static" / "js" / "landing.js").read_text(encoding="utf-8")

    assert "function initNavScrolled" in nav_js
    assert "nav-scroll.js" in base_html
    assert 'initNavScrolled("appNav")' in base_html
    assert "nav-scroll.js" in landing_base
    assert 'initNavScrolled("landingNav")' in landing_js
    print("OK nav scroll shared JS")


def test_history_page_no_dashboard_charts():
    app = create_app()
    with app.app_context():
        client = app.test_client()
        resp = client.get("/history")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "chart.umd.min.js" not in html
    assert "dashboard.js" not in html
    assert "sentimentChart" not in html
    print("OK history page without chart scripts")


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
    assert "_rb_demo_insight.html" not in home_html
    assert "_rb_demo_dashboard.html" not in home_html
    assert "variant='compact'" in home_html or 'variant="compact"' in home_html
    assert "variant='full'" in home_html or 'variant="full"' in home_html
    assert "landing-preview reveal" not in home_html.replace(" ", "")

    landing_base = (ROOT / "app" / "templates" / "base_landing.html").read_text(encoding="utf-8")
    assert "chart.js" not in landing_base.lower()

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'href="/analysis"' in html or "/analysis" in html
    assert "Start analysis" in html
    assert "landing-hero-title" in html
    assert "rb-metric-grid" in html
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
    print("OK home demo workspace markup")


def test_analysis_empty_shows_guided_onboarding():
    app = create_app()
    app.config["TESTING"] = True
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
    assert "dashboardTopMetrics" in html
    assert "liveFetchForm" in html
    assert "dataImportCard" in html
    assert 'max="5000"' not in html
    print("OK analysis empty shows guided onboarding")


def test_clean_no_job_shows_pipeline():
    app = create_app()
    app.config["TESTING"] = True
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
    app = create_app()
    app.config["TESTING"] = True
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


def test_clear_dashboard_clears_pipeline_snapshot():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["pipeline_snapshot"] = {"status": "completed", "progress": 100, "phase": "finalize"}

    clear_res = client.post("/dashboard/clear", follow_redirects=True)
    assert clear_res.status_code == 200
    html = clear_res.get_data(as_text=True)
    pipeline_class = html.split('id="analysisPipelineCard"')[1].split(">")[0]
    assert "is-idle" in pipeline_class
    assert 'data-has-review-results="false"' in pipeline_class
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") is None
    print("OK clear dashboard clears pipeline snapshot")


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
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    res = client.get("/fetch/status/00000000-0000-0000-0000-000000000099")
    assert res.status_code == 404
    data = res.get_json()
    assert data.get("stale") is True
    assert not data.get("ok")
    print("OK stale job status")


def test_analysis_prunes_stale_active_job():
    app = create_app()
    app.config["TESTING"] = True
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
    app = create_app()
    app.config["TESTING"] = True
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
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

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
    assert "dashboardTopMetrics" in batch_html
    pipeline_class = batch_html.split('id="analysisPipelineCard"')[1].split(">")[0]
    assert "d-none" not in pipeline_class
    with client.session_transaction() as sess:
        assert sess.get("pipeline_snapshot") is not None
    print(f"OK csv job processed={data.get('processed')} skipped={data.get('skipped')}")


def test_batch_with_snapshot_keeps_pipeline_visible():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    with app.app_context():
        Review.query.delete()
        db.session.commit()
        batch = _batch_now()
        _process_review(
            "Bridge Test",
            "alice",
            5,
            "Great app",
            batch_started_at=batch,
            play_rank=0,
        )
        db.session.commit()
        since_iso = batch.isoformat()

    snapshot = {"status": "completed", "progress": 100, "phase": "finalize"}
    with client.session_transaction() as sess:
        sess["pipeline_snapshot"] = snapshot

    res = client.get(f"/analysis?since={since_iso}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "dashboardTopMetrics" in html
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
    app = create_app()
    app.config["TESTING"] = True

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
        )
        db.session.commit()

        review = Review.query.filter_by(app_name="CSV Date App").first()
        assert review is not None
        assert review.reviewed_at == reviewed_at
    print("OK csv upload passes reviewed_at")


def test_reviewed_at_updated_on_refresh():
    app = create_app()
    app.config["TESTING"] = True

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
        )
        db.session.commit()

        review = Review.query.filter_by(review_id=f"play:{play_id}").first()
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
    app = create_app()
    app.config["TESTING"] = True

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
            )
        db.session.commit()

        ordered = _batch_reviews_query(batch).all()
        assert [r.author for r in ordered] == ["first", "second", "third"]
    print("OK batch query orders by play_rank")


def test_refetch_refreshes_into_batch():
    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        Review.query.delete()
        db.session.commit()

        app_name = "Refresh Test App"
        batch1 = _batch_now()
        play_id = "play-test-refresh-1"
        storage_id = review_storage_id(app_name, play_id, "bob", "Works well", 5)

        ok1, reason1, _ = _process_review(
            app_name,
            "bob",
            5,
            "Works well",
            batch_started_at=batch1,
            play_review_id=play_id,
            reviewed_at=batch1 - timedelta(days=2),
            play_rank=0,
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
        )
        assert ok2 and reason2 == "refreshed"
        db.session.commit()

        assert Review.query.filter_by(review_id=storage_id).count() == 1
        review = Review.query.filter_by(review_id=storage_id).first()
        assert review.last_batch_at == batch2

        in_batch1 = _batch_reviews_query(batch1).all()
        in_batch2 = _batch_reviews_query(batch2).all()
        assert len(in_batch1) == 0
        assert len(in_batch2) == 1
        assert in_batch2[0].id == review.id
    print("OK refetch refreshes into batch")


if __name__ == "__main__":
    test_home_page_loads()
    test_home_demo_workspace_markup()
    test_analysis_empty_shows_guided_onboarding()
    test_clean_no_job_shows_pipeline()
    test_clean_clears_stale_snapshot()
    test_clear_dashboard_clears_pipeline_snapshot()
    test_analysis_markup()
    test_app_nav_has_home_link()
    test_sticky_nav_scroll_offset_css()
    test_footer_sticky_layout_css()
    test_dead_css_removed()
    test_landing_nav_modern_theme()
    test_export_download_options()
    test_nav_scroll_shared_js()
    test_history_page_no_dashboard_charts()
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
    test_stale_job_status()
    test_analysis_prunes_stale_active_job()
    test_dismiss_active()
    test_batch_with_snapshot_keeps_pipeline_visible()
    test_csv_job_flow()
    print("All pipeline smoke tests passed.")

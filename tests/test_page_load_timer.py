"""Static regression guard for static/js/page_load_timer.js.

A prior change swapped this file's content for an unrelated
Navigation-Timing metrics collector that POSTed to a backend endpoint
that was never implemented, and dropped the startTask/endTask API that
static/js/kinjo-app.js depends on for its loading overlay. These checks
make sure that regression cannot silently reappear.
"""
from pathlib import Path


PAGE_LOAD_TIMER_PATH = Path("static/js/page_load_timer.js")
KINJO_APP_PATH = Path("static/js/kinjo-app.js")


def test_page_load_timer_exposes_start_and_end_task_api():
    content = PAGE_LOAD_TIMER_PATH.read_text(encoding="utf-8")
    assert "window.PageLoadTimer" in content
    assert "startTask" in content
    assert "endTask" in content


def test_page_load_timer_does_not_post_to_missing_endpoint():
    content = PAGE_LOAD_TIMER_PATH.read_text(encoding="utf-8")
    assert "/api/performance/page-load" not in content


def test_kinjo_app_loading_overlay_still_uses_start_task_contract():
    content = KINJO_APP_PATH.read_text(encoding="utf-8")
    assert "window.PageLoadTimer.startTask()" in content
    assert "__kinjoLoadingTaskEnd" in content

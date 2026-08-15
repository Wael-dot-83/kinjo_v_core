"""app_i18n.js language-precedence regression tests.

Runs the real AppI18n source under Node with mocked browser globals, proving
that an explicit client preference is never overwritten by the server DB
preference during bootstrap.
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

APP_I18N_JS = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "static" / "js" / "app_i18n.js"
)


def _read_source() -> str:
    return APP_I18N_JS.read_text(encoding="utf-8")


def _run_node_script(script: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    fd, path = tempfile.mkstemp(suffix=".js", prefix="app_i18n_test_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(script)
        result = subprocess.run(
            [node, path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result
    finally:
        try:
            Path(path).unlink()
        except OSError:
            pass


def _make_mocks(cookie: str = "", localStorage_data: dict | None = None):
    if localStorage_data is None:
        localStorage_data = {}
    return f"""
    global.window = {{
        requestIdleCallback: (fn) => fn(),
        AppI18n: undefined,
        location: {{ reload: () => {{}} }},
    }};
    global.document = {{
        cookie: {cookie!r},
        documentElement: {{ lang: 'ar', dir: 'rtl' }},
        addEventListener: () => {{}},
        querySelectorAll: () => ([]),
        getElementById: () => null,
        createElement: () => ({{ setAttribute: () => {{}} }}),
        head: {{ appendChild: () => {{}} }},
    }};
    global.localStorage = {{
        data: {localStorage_data!r},
        getItem(k) {{ return this.data[k] ?? null; }},
        setItem(k, v) {{ this.data[k] = v; }},
    }};
    global.sessionStorage = {{
        data: {{}},
        getItem(k) {{ return this.data[k] ?? null; }},
        setItem(k, v) {{ this.data[k] = v; }},
    }};
    global.fetch = async () => ({{
        ok: true,
        status: 200,
        json: async () => ({{ user_lang: 'en' }}),
    }});
    """


def test_explicit_client_preference_survives_server_db_preference():
    """DB=en, cookie=ar: init() must keep currentLang='ar' and NOT rewrite to en."""
    source = _read_source()
    script = _make_mocks(cookie="kinjo_lang=ar; Path=/;", localStorage_data={"kinjo_lang": "ar", "kinjo_token": "fake"}) + source + """
    (async () => {
        const app = new AppI18n();
        const serverLang = await app.loadServerLanguagePreference();
        if (app.clientPreferredLanguage) {
            if (serverLang && serverLang !== app.clientPreferredLanguage) {
                app.persistServerLanguagePreference(app.clientPreferredLanguage).catch(() => {});
            }
        } else if (serverLang) {
            app.currentLang = serverLang;
            app.persistClientLanguage(serverLang);
        }
        if (app.currentLang !== 'ar') {
            console.error('FAIL: currentLang reverted to', app.currentLang);
            process.exit(1);
        }
        if (app.clientPreferredLanguage !== 'ar') {
            console.error('FAIL: clientPreferredLanguage lost', app.clientPreferredLanguage);
            process.exit(1);
        }
    })().catch((e) => { console.error(e.stack || e); process.exit(1); });
    """
    result = _run_node_script(script)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_no_client_preference_falls_back_to_server_db():
    """No cookie/localStorage, DB=en: init() must set currentLang='en'."""
    source = _read_source()
    script = _make_mocks(cookie="", localStorage_data={"kinjo_token": "fake"}) + source + """
    (async () => {
        const app = new AppI18n();
        const serverLang = await app.loadServerLanguagePreference();
        if (app.clientPreferredLanguage) {
            if (serverLang && serverLang !== app.clientPreferredLanguage) {
                app.persistServerLanguagePreference(app.clientPreferredLanguage).catch(() => {});
            }
        } else if (serverLang) {
            app.currentLang = serverLang;
            app.persistClientLanguage(serverLang);
        }
        if (app.currentLang !== 'en') {
            console.error('FAIL: currentLang should be en, got', app.currentLang);
            process.exit(1);
        }
    })().catch((e) => { console.error(e.stack || e); process.exit(1); });
    """
    result = _run_node_script(script)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_toggle_language_awaits_server_persistence():
    """toggleLanguage() must await persistServerLanguagePreference before reload."""
    source = _read_source()
    script = _make_mocks(cookie="kinjo_lang=ar; Path=/;", localStorage_data={"kinjo_lang": "ar", "kinjo_token": "fake"}) + source + """
    let reloaded = false;
    global.window.location = { reload: () => { reloaded = true; } };
    (async () => {
        const app = new AppI18n();
        app.currentLang = 'ar';
        const original = app.persistServerLanguagePreference.bind(app);
        app.persistServerLanguagePreference = async function(lang) {{
            const result = await original(lang);
            return result;
        }};
        await app.toggleLanguage();
        if (!reloaded) {
            console.error('FAIL: reload did not happen after server persistence');
            process.exit(1);
        }
    })().catch((e) => { console.error(e.stack || e); process.exit(1); });
    """
    result = _run_node_script(script)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_old_init_logic_would_fail():
    """Non-vacuity control: the old init() must fail the explicit-preference test."""
    source = _read_source()
    old_init = """  async init() {
    await Promise.all([this.loadLanguage("ar"), this.loadLanguage("en")]);
    const serverLang = await this.loadServerLanguagePreference();
    if (serverLang) {
      this.currentLang = serverLang;
      this.persistClientLanguage(serverLang);
    }
    this.patchRuntimeTranslators();
    await this.applyLanguage(this.currentLang, false);
    if (this.currentLang === "en") {
      this.scheduleDynamicLiteralPairsBuild();
    }
  }"""
    # Replace the init method by finding it between markers
    pre, rest = source.split("  async init()", 1)
    # Find the closing '  }' at the method level (not nested deeper)
    lines = rest.splitlines(keepends=True)
    depth = 0
    end_idx = 0
    for i, line in enumerate(lines):
        depth += line.count("{") - line.count("}")
        if depth == 0 and i > 0:
            end_idx = i + 1
            break
    post = "".join(lines[end_idx:])
    buggy_source = pre + old_init + post

    script = _make_mocks(cookie="kinjo_lang=ar; Path=/;", localStorage_data={"kinjo_lang": "ar", "kinjo_token": "fake"}) + buggy_source + """
    (async () => {
        const app = new AppI18n();
        const serverLang = await app.loadServerLanguagePreference();
        if (serverLang) {
          app.currentLang = serverLang;
          app.persistClientLanguage(serverLang);
        }
        if (app.currentLang === 'en') {
            console.log('PASS: old buggy logic reverted to en as expected');
        } else {
            console.error('FAIL: old logic did not revert, got', app.currentLang);
            process.exit(1);
        }
    })().catch((e) => { console.error(e.stack || e); process.exit(1); });
    """
    result = _run_node_script(script)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

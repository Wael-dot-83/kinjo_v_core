"""fetchWithAuth() (static/js/auth.js) used to throw response.statusText
only ("Conflict", "Bad Request") on any non-2xx response, discarding the
JSON error body entirely. This meant KinJoAPI.request()'s JSON-error-
parsing logic (kinjo-api.js) was dead code -- every admin page across the
whole panel showed a meaningless generic error on every failed
POST/PUT/PATCH/DELETE regardless of what the backend actually said (e.g.
"Username already exists" became "Conflict"). Fixed to read the response
body and surface the real `detail` (string or Pydantic validation array)
or `message` field before throwing.

These tests run the real fetchWithAuth source (extracted verbatim from
auth.js) under Node with a mocked fetch/window/AuthStorage, proving the
fix against the actual shapes FastAPI returns -- not just asserting a
string is present in the file.
"""
import re
import shutil
import subprocess

import pytest

AUTH_JS = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "static" / "js" / "auth.js"
)


def _extract_fetch_with_auth_source() -> str:
    text = AUTH_JS.read_text(encoding="utf-8")
    match = re.search(
        r"async function fetchWithAuth\(url, options = \{\}\) \{.*?\n\}\n",
        text,
        re.DOTALL,
    )
    assert match, "fetchWithAuth function not found in auth.js"
    return match.group(0)


def _run_node_scenario(mock_response_js: str, assertion_js: str) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")

    source = _extract_fetch_with_auth_source()
    script = f"""
global.window = {{ location: {{ href: '' }} }};
global.AuthStorage = {{ isAuthenticated: () => true, clearAll: () => {{}} }};
{source}

global.fetch = async (url, options) => ({mock_response_js});

(async () => {{
    {assertion_js}
}})().catch((e) => {{ console.error('SCRIPT ERROR:', e.stack || e); process.exit(1); }});
"""
    result = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


def test_standardized_api_error_envelope_is_surfaced():
    """The most common shape in this codebase: admin_security.py's APIError
    (conflict_error()/validation_error()/etc.) is serialized by
    api_error_handler() as {"error": {"code","message","fields",
    "correlation_id","details"}} -- NOT the plain {"detail": "..."} shape
    the fix was first written against. Discovered live: a real duplicate-
    username submission on /admin/users/create returned exactly this
    envelope and the first version of the fix fell through to the
    "Conflict" statusText fallback, silently reproducing the original bug
    for every APIError-raising endpoint (a large fraction of admin_
    endpoints.py). error.fields is also attached to the thrown Error for
    callers that want per-field messages."""
    mock = """{
        ok: false, status: 409, statusText: 'Conflict',
        headers: { get: () => 'application/json' },
        json: async () => ({ error: {
            code: 'CONFLICT', message: 'Username already exists',
            fields: { username: 'Username is already taken' },
            correlation_id: 'abc-123', details: null,
        } }),
    }"""
    assertion = """
        try {
            await fetchWithAuth('/api/admin/users', { method: 'POST' });
            throw new Error('expected fetchWithAuth to throw');
        } catch (e) {
            if (e.message !== 'Username already exists') {
                throw new Error('wrong message: ' + e.message);
            }
            if (!e.fields || e.fields.username !== 'Username is already taken') {
                throw new Error('fields not attached: ' + JSON.stringify(e.fields));
            }
        }
    """
    _run_node_scenario(mock, assertion)


def test_string_detail_is_surfaced():
    """The common HTTPException(detail="...") shape used by admin_security.py's
    conflict_error()/validation_error() helpers."""
    mock = """{
        ok: false, status: 409, statusText: 'Conflict',
        headers: { get: () => 'application/json' },
        json: async () => ({ detail: 'Username already exists' }),
    }"""
    assertion = """
        try {
            await fetchWithAuth('/api/admin/users', { method: 'POST' });
            throw new Error('expected fetchWithAuth to throw');
        } catch (e) {
            if (e.message !== 'Username already exists') {
                throw new Error('wrong message: ' + e.message);
            }
            if (e.status !== 409) {
                throw new Error('wrong status: ' + e.status);
            }
        }
    """
    _run_node_scenario(mock, assertion)


def test_pydantic_validation_array_detail_is_surfaced():
    """FastAPI's native 422 shape: {"detail": [{"loc":..., "msg":..., "type":...}]}."""
    mock = """{
        ok: false, status: 422, statusText: 'Unprocessable Entity',
        headers: { get: () => 'application/json' },
        json: async () => ({ detail: [
            { loc: ['body', 'email'], msg: 'field required', type: 'value_error.missing' },
            { loc: ['body', 'password'], msg: 'ensure this value has at least 8 characters', type: 'value_error' },
        ] }),
    }"""
    assertion = """
        try {
            await fetchWithAuth('/api/admin/users', { method: 'POST' });
            throw new Error('expected fetchWithAuth to throw');
        } catch (e) {
            const expected = 'field required; ensure this value has at least 8 characters';
            if (e.message !== expected) {
                throw new Error('wrong message: ' + e.message);
            }
        }
    """
    _run_node_scenario(mock, assertion)


def test_message_field_fallback_is_surfaced():
    mock = """{
        ok: false, status: 400, statusText: 'Bad Request',
        headers: { get: () => 'application/json' },
        json: async () => ({ message: 'Supervisor must belong to a kindergarten' }),
    }"""
    assertion = """
        try {
            await fetchWithAuth('/api/admin/users', { method: 'POST' });
            throw new Error('expected fetchWithAuth to throw');
        } catch (e) {
            if (e.message !== 'Supervisor must belong to a kindergarten') {
                throw new Error('wrong message: ' + e.message);
            }
        }
    """
    _run_node_scenario(mock, assertion)


def test_non_json_body_falls_back_to_status_text():
    mock = """{
        ok: false, status: 500, statusText: 'Internal Server Error',
        headers: { get: () => 'text/plain' },
        json: async () => { throw new Error('not json'); },
    }"""
    assertion = """
        try {
            await fetchWithAuth('/api/admin/users', { method: 'POST' });
            throw new Error('expected fetchWithAuth to throw');
        } catch (e) {
            if (e.message !== 'Internal Server Error') {
                throw new Error('wrong message: ' + e.message);
            }
        }
    """
    _run_node_scenario(mock, assertion)


def test_success_response_is_returned_not_thrown():
    """Confirms the fix didn't change the success path -- ok responses must
    still be returned as-is, not consumed/thrown."""
    mock = """{
        ok: true, status: 200, statusText: 'OK',
        headers: { get: () => 'application/json' },
        json: async () => ({ id: 1 }),
    }"""
    assertion = """
        const response = await fetchWithAuth('/api/admin/users', { method: 'GET' });
        if (!response || response.status !== 200) {
            throw new Error('expected success response to be returned, got: ' + JSON.stringify(response));
        }
    """
    _run_node_scenario(mock, assertion)

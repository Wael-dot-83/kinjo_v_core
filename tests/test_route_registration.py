from collections import defaultdict

from main import app


def iter_effective_routes(route, prefix=""):
    included = getattr(route, "original_router", None)
    context = getattr(route, "include_context", None)
    if included is not None and context is not None:
        next_prefix = f"{prefix}{context.prefix or ''}"
        for child in included.routes:
            yield from iter_effective_routes(child, next_prefix)
        return
    path = getattr(route, "path", None)
    if path:
        yield route, f"{prefix}{path}"


def test_no_duplicate_route_method_registrations():
    registrations = defaultdict(list)
    for route in app.routes:
        for effective_route, path in iter_effective_routes(route):
            methods = getattr(effective_route, "methods", None)
            if not methods:
                continue
            endpoint = getattr(effective_route, "endpoint", None)
            for method in methods - {"HEAD", "OPTIONS"}:
                registrations[(method, path)].append(endpoint.__name__ if endpoint else repr(effective_route))

    duplicates = {
        f"{method} {path}": endpoints
        for (method, path), endpoints in registrations.items()
        if len(endpoints) > 1
    }
    assert duplicates == {}


def test_openapi_schema_generation_succeeds():
    """Every documented route must use OpenAPI-compatible parameter types."""
    app.openapi_schema = None
    schema = app.openapi()

    assert schema["openapi"]
    assert "/api/analytics/predict/{metric}" in schema["paths"]
    assert schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"] == "/token"


def test_openapi_http_response_preserves_authentication_schema(client):
    """Response sanitization must not remove password definitions from docs."""
    app.openapi_schema = None
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    password_flow = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]
    assert password_flow["tokenUrl"] == "/token"
    token_body_ref = schema["paths"]["/token"]["post"]["requestBody"]["content"][
        "application/x-www-form-urlencoded"
    ]["schema"]["$ref"]
    token_body_name = token_body_ref.rsplit("/", 1)[-1]
    assert "password" in schema["components"]["schemas"][token_body_name]["properties"]


def test_api_docs_use_local_favicon(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert 'href="/static/favicon.svg"' in response.text
    assert "fastapi.tiangolo.com/img/favicon.png" not in response.text

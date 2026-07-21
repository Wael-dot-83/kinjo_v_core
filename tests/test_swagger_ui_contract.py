"""Functional contracts for Swagger UI, OpenAPI auth, and documented admin APIs."""

import os
import subprocess
import sys

from config import settings


def test_oauth_login_is_not_blocked_by_csrf_in_non_testing_mode(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "TESTING", False)

    response = client.post(
        "/token",
        data={"username": "not-a-user", "password": "not-a-password"},
    )

    assert response.status_code == 401
    assert "CSRF" not in response.text


def test_bearer_requests_are_not_blocked_by_csrf_in_non_testing_mode(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "TESTING", False)

    response = client.post(
        "/api/heatmap/alerts/unknown/acknowledge",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert "CSRF" not in response.text


def test_heatmap_etl_routes_require_authentication(client):
    response = client.get("/api/heatmap/indicators")

    assert response.status_code == 401


def test_heatmap_etl_routes_require_admin_role(client, auth_headers_parent):
    response = client.get(
        "/api/heatmap/indicators",
        headers=auth_headers_parent,
    )

    assert response.status_code == 403


def test_heatmap_pipeline_rejects_paths_outside_data_directory(
    client, auth_headers_admin
):
    response = client.post(
        "/api/heatmap/pipeline/run",
        params={"csv_path": "main.py"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 400
    assert "heatmap data directory" in response.json()["detail"]


def test_heatmap_etl_routes_are_documented_as_secured(client):
    schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/api/heatmap/pipeline/run"]["post"]
    assert operation["security"] == [{"OAuth2PasswordBearer": []}]
    assert operation["responses"]["401"]["description"] == "Not authenticated"
    assert operation["responses"]["403"]["description"] == "Not authorized"


def test_all_documented_operations_have_tags(client):
    schema = client.get("/openapi.json").json()
    methods = {"get", "post", "put", "patch", "delete", "head", "options"}

    untagged = [
        f"{method.upper()} {path}"
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method in methods and not operation.get("tags")
    ]
    assert untagged == []


def test_disabling_api_docs_also_disables_openapi_document():
    env = os.environ.copy()
    env.update(
        {
            "API_DOCS_ENABLED": "false",
            "DATABASE_URL": "sqlite:///:memory:",
            "ENVIRONMENT": "development",
            "TESTING": "true",
            "RATE_LIMIT_STORAGE_URI": "memory://",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from main import app; "
                "assert app.openapi_url is None; "
                "assert all(getattr(route, 'path', None) != '/openapi.json' "
                "for route in app.routes)"
            ),
        ],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_heatmap_pipeline_default_does_not_disclose_host_path(client):
    schema = client.get("/openapi.json").json()
    parameters = schema["paths"]["/api/heatmap/pipeline/run"]["post"]["parameters"]
    csv_path = next(parameter for parameter in parameters if parameter["name"] == "csv_path")

    assert csv_path["schema"]["default"] == "test_data.csv"

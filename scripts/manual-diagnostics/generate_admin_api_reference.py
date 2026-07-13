"""Generate the Admin API reference from FastAPI's registered OpenAPI schema.

Run from the repository root:
    .venvT\\Scripts\\python.exe scripts/manual-diagnostics/generate_admin_api_reference.py
"""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from main import app  # noqa: E402


HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _schema_label(schema: dict | None) -> str:
    if not schema:
        return "—"
    ref = schema.get("$ref")
    if ref:
        return f"`{ref.rsplit('/', 1)[-1]}`"
    if schema.get("type") == "array":
        return f"array[{_schema_label(schema.get('items'))}]"
    if "anyOf" in schema:
        return " / ".join(_schema_label(item) for item in schema["anyOf"])
    return f"`{schema.get('type', 'object')}`"


def _request_label(operation: dict) -> str:
    body = operation.get("requestBody", {})
    content = body.get("content", {})
    if not content:
        return "—"
    labels = []
    for media_type, definition in content.items():
        labels.append(f"{media_type}: {_schema_label(definition.get('schema'))}")
    return "<br>".join(labels)


def _parameter_label(operation: dict) -> str:
    labels = []
    for parameter in operation.get("parameters", []):
        required = "required" if parameter.get("required") else "optional"
        schema = parameter.get("schema", {})
        data_type = schema.get("type") or schema.get("format") or "value"
        labels.append(f"`{parameter.get('name')}` ({parameter.get('in')}, {data_type}, {required})")
    return "<br>".join(labels) or "—"


def _response_label(operation: dict) -> str:
    labels = []
    for status, response in operation.get("responses", {}).items():
        content = response.get("content", {})
        schemas = [_schema_label(item.get("schema")) for item in content.values()]
        result = " / ".join(dict.fromkeys(schemas)) if schemas else response.get("description", "—")
        labels.append(f"`{status}` {result}")
    return "<br>".join(labels) or "—"


def _iter_effective_routes(route, prefix: str = ""):
    included = getattr(route, "original_router", None)
    context = getattr(route, "include_context", None)
    if included is not None and context is not None:
        next_prefix = f"{prefix}{context.prefix or ''}"
        for child in included.routes:
            yield from _iter_effective_routes(child, next_prefix)
        return
    path = getattr(route, "path", None)
    if path:
        yield route, f"{prefix}{path}"


def generate() -> str:
    schema = app.openapi()
    admin_paths = {
        path: definition
        for path, definition in schema["paths"].items()
        if path.startswith("/api/admin") or path.startswith("/admin/charts")
    }
    lines = [
        "# KinJo Admin API Reference",
        "",
        "> Generated from the registered FastAPI OpenAPI schema. Do not edit endpoint rows by hand; regenerate them with `scripts/manual-diagnostics/generate_admin_api_reference.py`.",
        "",
        "## Integration contract",
        "",
        "- Canonical API prefix: `/api/admin`.",
        "- Authentication: HttpOnly `kinjo_session` JWT cookie or bearer JWT for every endpoint except the two rate-limited self-service password-reset operations.",
        "- Authorization: admin role unless an endpoint explicitly supports the narrower admin-or-manager policy documented in the main Admin Guide.",
        "- Browser writes: send the `kinjo_csrf_token` cookie and matching `X-CSRF-Token` header. The shared `auth.js`/`fetchWithAuth` layer does this automatically.",
        "- Errors: JSON API errors include an HTTP status, stable error code/message where available, and `X-Correlation-ID` response header.",
        "- Pagination: list endpoints use the parameter names shown below; do not assume a universal page size.",
        "- Live interactive schemas and examples are also available at `/docs` and `/openapi.json` in an authorized environment.",
        "",
        f"## Registered operations ({sum(1 for value in admin_paths.values() for method in HTTP_METHODS if method in value)})",
        "",
        "| Method | Path | Purpose | Parameters | Request body | Success/error responses |",
        "|---|---|---|---|---|---|",
    ]
    for path, definition in sorted(admin_paths.items()):
        for method in HTTP_METHODS:
            operation = definition.get(method)
            if not operation:
                continue
            summary = (operation.get("summary") or operation.get("operationId") or "Admin operation").replace("|", "\\|")
            lines.append(
                f"| `{method.upper()}` | `{path}` | {summary} | {_parameter_label(operation)} | "
                f"{_request_label(operation)} | {_response_label(operation)} |"
            )

    documented = {(method.upper(), path) for path, definition in admin_paths.items() for method in HTTP_METHODS if method in definition}
    hidden = set()
    for route in app.routes:
        for effective_route, path in _iter_effective_routes(route):
            if not path.startswith("/api/admin"):
                continue
            openapi_path = re.sub(r":(?:int|float|path|uuid|str)(?=})", "", path)
            for method in getattr(effective_route, "methods", set()) or set():
                if method in {"HEAD", "OPTIONS"} or (method, openapi_path) in documented:
                    continue
                hidden.add((method, path))

    lines.extend([
        "",
        "## Compatibility operations excluded from OpenAPI",
        "",
        "These registered routes are intentionally hidden from the public schema. They remain covered by route/security tests and must delegate to the canonical implementation.",
        "",
        "| Method | Path | Status |",
        "|---|---|---|",
    ])
    for method, path in sorted(hidden, key=lambda item: (item[1], item[0])):
        lines.append(f"| `{method}` | `{path}` | Compatibility/internal route |")
    if not hidden:
        lines.append("| — | — | None |")

    lines.extend([
        "",
        "## Schema definitions",
        "",
        "Request and response model names in the table resolve to JSON Schema definitions in `/openapi.json` under `components.schemas`. Keeping the schema canonical avoids duplicating field constraints, enums, nullable rules, and examples in prose that can drift from runtime validation.",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    output = ROOT / "docs" / "ADMIN_API_REFERENCE.md"
    output.write_text(generate(), encoding="utf-8", newline="\n")
    print(f"Wrote {output.relative_to(ROOT)}")

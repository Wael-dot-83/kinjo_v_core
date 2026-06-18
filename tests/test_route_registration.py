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

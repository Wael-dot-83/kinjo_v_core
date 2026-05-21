from collections import defaultdict

from main import app


def test_no_duplicate_route_method_registrations():
    registrations = defaultdict(list)
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if not methods or not path:
            continue
        for method in methods - {"HEAD", "OPTIONS"}:
            registrations[(method, path)].append(endpoint.__name__ if endpoint else repr(route))

    duplicates = {
        f"{method} {path}": endpoints
        for (method, path), endpoints in registrations.items()
        if len(endpoints) > 1
    }
    assert duplicates == {}

import os
import re
import sys

sys.path.insert(0, ".")

from main import app


def _join_route(prefix: str, path: str) -> str:
    if not prefix:
        return path
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}".replace("//", "/")


def _walk_routes(router, prefix: str = ""):
    for route in getattr(router, "routes", []):
        if type(route).__name__ == "_IncludedRouter":
            ctx = getattr(route, "include_context", None)
            if ctx:
                yield from _walk_routes(
                    ctx.included_router,
                    _join_route(prefix, ctx.prefix or ""),
                )
            continue
        if hasattr(route, "path") and getattr(route, "methods", None):
            yield _join_route(prefix, route.path)


valid_routes = set()
for route in app.routes:
    if type(route).__name__ == "_IncludedRouter":
        ctx = getattr(route, "include_context", None)
        if ctx:
            valid_routes.update(_walk_routes(ctx.included_router, ctx.prefix or ""))
    elif hasattr(route, "path") and getattr(route, "methods", None):
        valid_routes.add(route.path)


def _route_matches(path: str) -> bool:
    path_parts = path.strip("/").split("/") if path != "/" else [""]
    for route in valid_routes:
        route_parts = route.strip("/").split("/") if route != "/" else [""]
        if len(route_parts) != len(path_parts):
            continue
        if all(
            (route_part.startswith("{") and route_part.endswith("}")) or route_part == path_part
            for route_part, path_part in zip(route_parts, path_parts)
        ):
            return True
    return False


template_dir = "D:/Final Version/templates"
patterns = [
    r'<a\s+[^>]*href=["\'](/admin[^"\']*)["\']',
    r'<a\s+[^>]*href=["\'](/api/admin[^"\']*)["\']',
]

issues = []
with open("D:/Final Version/link_audit.txt", "w", encoding="utf-8") as f:
    for root, dirs, files in os.walk(template_dir):
        for filename in files:
            if not filename.endswith(".html"):
                continue
            filepath = os.path.join(root, filename)
            relpath = os.path.relpath(filepath, template_dir)
            with open(filepath, "r", encoding="utf-8") as tf:
                content = tf.read()
            for pattern in patterns:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    path = match.group(1)
                    base = path.split("?")[0].split("#")[0]
                    if "$" in base or "{" in base:
                        continue
                    if not _route_matches(base):
                        found = any(route.startswith(f"{base}/") or base.startswith(f"{route}/") for route in valid_routes)
                        if not found:
                            line_num = content[: match.start(1)].count(chr(10)) + 1
                            msg = f"{relpath}:{line_num} => {base} (NOT FOUND in routes)"
                            issues.append(msg)
                            f.write(msg + chr(10))
    if not issues:
        f.write("All internal admin links appear to point to registered routes.\n")

print(f"Found {len(issues)} link issues")

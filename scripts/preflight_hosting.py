"""Preflight checks for deployment readiness."""

from __future__ import annotations

from pathlib import Path
from typing import List
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require_paths() -> List[str]:
    required = [
        ROOT / "main.py",
        ROOT / "requirements.txt",
        ROOT / "Dockerfile",
        ROOT / "docker-compose.yml",
        ROOT / "alembic.ini",
        ROOT / "alembic",
    ]
    errors: List[str] = []
    for path in required:
        if not path.exists():
            errors.append(f"Missing required path: {path}")
    return errors


def check_routes() -> List[str]:
    errors: List[str] = []
    try:
        from main import app
    except Exception as exc:  # pragma: no cover - preflight only
        return [f"Unable to import app from main.py: {exc}"]

    route_methods = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, path)
            if key in route_methods:
                errors.append(f"Duplicate route detected: {method} {path}")
            route_methods.add(key)
    return errors


def check_alembic_heads() -> List[str]:
    errors: List[str] = []
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        errors.append(f"Expected exactly 1 alembic head, found {len(heads)}: {heads}")
    return errors


def main() -> int:
    errors: List[str] = []
    errors.extend(require_paths())
    errors.extend(check_routes())
    errors.extend(check_alembic_heads())

    if errors:
        print("Preflight failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

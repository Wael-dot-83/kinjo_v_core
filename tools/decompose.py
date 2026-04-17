"""
Decompose missing_endpoints.py into domain modules.

Reads the monolithic file (5081 lines), splits into domain-organized
modules under api/, and creates an aggregator missing_endpoints.py.

Line ranges verified via AST analysis 2025-06.
"""
import os

SRC = "missing_endpoints.py"

with open(SRC, "r", encoding="utf-8") as f:
    all_lines = f.readlines()

total = len(all_lines)
print(f"Read {total} lines from {SRC}")
assert total > 5000, f"Expected ~5081 lines, got {total}"

# ---------------------------------------------------------------------------
# Common imports – written at the top of every domain module
# ---------------------------------------------------------------------------
COMMON_IMPORTS = """\
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import date, datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

import models
import validators
from config import settings
from database import get_db
from dependencies import get_current_user

"""

# ---------------------------------------------------------------------------
# Domain definitions: (filename, tag, line_ranges, extra_imports, extra_top)
#   line_ranges: list of (start, end)  1-indexed inclusive
# ---------------------------------------------------------------------------
DOMAINS = [
    # ── Users  L28-929 ───────────────────────────────────────────────────
    (
        "api/users.py", "Users",
        [(28, 929)],
        [
            "from slowapi import Limiter",
            "from slowapi.util import get_remote_address",
            "from api.auth.password_reset_service import (",
            "    issue_password_reset_token,",
            "    resolve_valid_token,",
            "    deliver_password_reset_email,",
            ")",
        ],
        "limiter = Limiter(key_func=get_remote_address)\n"
        "if settings.TESTING:\n"
        "    limiter.enabled = False\n",
    ),

    # ── Kindergartens  L932-1452 ─────────────────────────────────────────
    (
        "api/kindergartens.py", "Kindergartens",
        [(932, 1452)],
        [],
        "",
    ),

    # ── Classes  L1454-1843 ──────────────────────────────────────────────
    (
        "api/classes.py", "Classes",
        [(1454, 1843)],
        [],
        "",
    ),

    # ── Enrollments  L1847-1913  +  L2806-2975 ──────────────────────────
    (
        "api/enrollment.py", "Enrollment",
        [(1847, 1913), (2806, 2975)],
        [],
        "",
    ),

    # ── Manager dashboards  L1921-2295 ───────────────────────────────────
    (
        "api/manager.py", "Manager",
        [(1921, 2295)],
        [],
        "",
    ),

    # ── Parent dashboard  L2303-2384 ─────────────────────────────────────
    (
        "api/parent.py", "Parent",
        [(2303, 2384)],
        [],
        "",
    ),

    # ── Tasks  L2391-2698 ────────────────────────────────────────────────
    (
        "api/tasks.py", "Tasks",
        [(2391, 2698)],
        [],
        "",
    ),

    # ── Registration  L2705-2799 ─────────────────────────────────────────
    (
        "api/registration.py", "Registration",
        [(2705, 2799)],
        [],
        "",
    ),

    # ── Attendance  L2983-3298 ───────────────────────────────────────────
    (
        "api/attendance_routes.py", "Attendance",
        [(2983, 3298)],
        [
            "from notification_service import (",
            "    notify_attendance_corrected,",
            ")",
        ],
        "",
    ),

    # ── Daily Reports  L3305-3512 ────────────────────────────────────────
    (
        "api/daily_reports_routes.py", "Daily Reports",
        [(3305, 3512)],
        [],
        "",
    ),

    # ── Profiles + Incidents  L3520-3811 ─────────────────────────────────
    (
        "api/children.py", "Children",
        [(3520, 3811)],
        [
            "from notification_service import notify_incident_created",
        ],
        "",
    ),

    # ── KPI  L3819-4069 ─────────────────────────────────────────────────
    (
        "api/kpi_routes.py", "KPI",
        [(3819, 4069)],  # includes commented-out block + governance score
        [],
        "",
    ),

    # ── Supervisor  L4076-4608 ───────────────────────────────────────────
    (
        "api/supervisor.py", "Supervisor",
        [(4076, 4608)],
        [],
        "",
    ),

    # ── Portfolio + Health Alerts  L4615-4921 ────────────────────────────
    (
        "api/portfolio.py", "Portfolio",
        [(4615, 4921)],
        [],
        "",
    ),

    # ── Audit Logs  L4929-5081 ───────────────────────────────────────────
    (
        "api/audit_routes.py", "Audit",
        [(4929, 5081)],
        [],
        "",
    ),
]


def extract_lines(ranges):
    result = []
    for start, end in ranges:
        result.extend(all_lines[start - 1 : end])
    return result


def write_domain(filename, tag, line_ranges, extra_imports, extra_top):
    lines = extract_lines(line_ranges)
    content = f'"""\n{tag} domain endpoints\n"""\n'
    content += COMMON_IMPORTS
    if extra_imports:
        content += "\n".join(extra_imports) + "\n\n"
    content += f'router = APIRouter(tags=["{tag}"])\n\n'
    if extra_top:
        content += extra_top + "\n"
    content += "".join(lines)

    filepath = os.path.join(os.getcwd(), filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  {filename:40s} {len(lines):>5} lines  (L{line_ranges[0][0]}-L{line_ranges[-1][1]})")


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------
print("\nExtracting domain modules...")
for d in DOMAINS:
    write_domain(*d)

# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------
print("\nCreating aggregator missing_endpoints.py...")

# Build import + include lines dynamically
import_lines = []
include_lines = []
for filename, tag, *_ in DOMAINS:
    module = filename.replace("/", ".").replace(".py", "")
    var = tag.lower().replace(" ", "_") + "_router"
    import_lines.append(f"from {module} import router as {var}")
    include_lines.append(f"router.include_router({var})")

aggregator = '''\
"""
Missing Critical Endpoints - Aggregator
Routes are organized into domain modules under api/.
This file re-exports a unified router for backward compatibility.
"""
from fastapi import APIRouter

router = APIRouter()

# Import domain routers
{imports}

# Mount all domain routers
{includes}

# Re-export for backward compatibility
# notification_service.py imports get_supervisor_classes
from api.supervisor import get_supervisor_classes  # noqa: F401
'''.format(
    imports="\n".join(import_lines),
    includes="\n".join(include_lines),
)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(aggregator)
print(f"  Rewrote {SRC}
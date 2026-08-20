"""ADMIN-001 — centralized permission model.

Covers the policy table, the three enforcement entry points, the bilingual
403 payload, and the section 10 conformance sweep that no inline role
comparison is left in the tree.
"""

import subprocess
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import models
from dependencies import (
    Permission,
    ROLE_PERMISSIONS,
    enforce_permission,
    enforce_role,
    get_current_user,
    has_global_scope,
    has_permission,
    has_role,
    missing_permissions,
    permissions_for_role,
    require_permission,
)

ROOT = Path(__file__).resolve().parents[2]


class _FakeUser:
    """Minimal stand-in: the permission layer only reads ``role``."""

    def __init__(self, role):
        self.role = role


ADMIN = _FakeUser(models.UserRole.ADMIN)
MANAGER = _FakeUser(models.UserRole.MANAGER)
SUPERVISOR = _FakeUser(models.UserRole.SUPERVISOR)
PARENT = _FakeUser(models.UserRole.PARENT)


class TestPolicyTable:
    def test_every_role_is_mapped(self):
        assert set(ROLE_PERMISSIONS) == set(models.UserRole)

    def test_admin_holds_every_permission(self):
        assert permissions_for_role(models.UserRole.ADMIN) == set(Permission)

    def test_manager_grants_match_the_specification(self):
        assert permissions_for_role(models.UserRole.MANAGER) == {
            Permission.ADMIN_READ,
            Permission.KG_READ,
            Permission.KG_WRITE,
            Permission.REPORT_GENERATE,
            Permission.REPORT_EXPORT,
        }

    def test_supervisor_grants_match_the_specification(self):
        assert permissions_for_role(models.UserRole.SUPERVISOR) == {
            Permission.KG_READ,
            Permission.REPORT_GENERATE,
        }

    def test_parent_holds_nothing(self):
        assert permissions_for_role(models.UserRole.PARENT) == set()

    def test_admin_panel_is_admin_only(self):
        """Guards the ADMIN-001 deviation.

        The specification grants ADMIN_READ to MANAGER. Remapping the existing
        require_admin dependency onto ADMIN_READ would have opened every
        admin-only endpoint to managers. ADMIN_PANEL must stay admin-only or
        that privilege escalation comes back.
        """
        for role in models.UserRole:
            granted = Permission.ADMIN_PANEL in permissions_for_role(role)
            assert granted is (role == models.UserRole.ADMIN), role

    def test_scope_all_is_admin_only(self):
        for role in models.UserRole:
            granted = Permission.SCOPE_ALL in permissions_for_role(role)
            assert granted is (role == models.UserRole.ADMIN), role

    def test_unknown_role_grants_nothing(self):
        assert permissions_for_role("NOT_A_ROLE") == set()


class TestHasPermission:
    def test_admin_short_circuits_every_permission(self):
        for permission in Permission:
            assert has_permission(ADMIN, permission)

    def test_manager_holds_its_grants(self):
        assert has_permission(MANAGER, Permission.KG_WRITE)
        assert has_permission(MANAGER, Permission.REPORT_EXPORT)

    def test_manager_denied_admin_only_permissions(self):
        assert not has_permission(MANAGER, Permission.USER_MANAGE)
        assert not has_permission(MANAGER, Permission.IMPERSONATE)
        assert not has_permission(MANAGER, Permission.AUDIT_READ)
        assert not has_permission(MANAGER, Permission.ADMIN_PANEL)

    def test_supervisor_cannot_export(self):
        assert has_permission(SUPERVISOR, Permission.REPORT_GENERATE)
        assert not has_permission(SUPERVISOR, Permission.REPORT_EXPORT)

    def test_all_permissions_required_not_any(self):
        assert not has_permission(
            MANAGER, Permission.KG_READ, Permission.USER_MANAGE
        )
        assert has_permission(MANAGER, Permission.KG_READ, Permission.KG_WRITE)

    def test_anonymous_holds_nothing(self):
        assert not has_permission(None, Permission.KG_READ)

    def test_missing_permissions_reports_only_the_gaps(self):
        gaps = missing_permissions(
            MANAGER, Permission.KG_READ, Permission.USER_MANAGE, Permission.AUDIT_READ
        )
        assert gaps == [Permission.USER_MANAGE, Permission.AUDIT_READ]
        assert missing_permissions(ADMIN, Permission.USER_MANAGE) == []


class TestHasGlobalScope:
    def test_only_admin_has_global_scope(self):
        assert has_global_scope(ADMIN)
        assert not has_global_scope(MANAGER)
        assert not has_global_scope(SUPERVISOR)
        assert not has_global_scope(PARENT)
        assert not has_global_scope(None)


class TestEnforcePermission:
    def test_allows_and_returns_the_user(self):
        assert enforce_permission(MANAGER, Permission.KG_READ) is MANAGER

    def test_denies_with_403(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            enforce_permission(MANAGER, Permission.USER_MANAGE)

        assert exc.value.status_code == 403

    def test_denial_payload_is_bilingual(self):
        """Mandate 1: the error a user sees carries Arabic and English."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            enforce_permission(SUPERVISOR, Permission.AUDIT_READ)

        detail = exc.value.detail
        assert detail["code"] == "INSUFFICIENT_PERMISSIONS"
        assert detail["missing"] == ["admin:audit:read"]
        assert detail["message_en"] == "You do not have the required permission"
        assert detail["message_ar"].strip()
        assert detail["message_ar"] != detail["message_en"]
        # `message` stays Arabic-first, matching the platform default.
        assert detail["message"] == detail["message_ar"]

    def test_anonymous_gets_401_not_403(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            enforce_permission(None, Permission.KG_READ)

        assert exc.value.status_code == 401


class TestRoleGuards:
    def test_has_role(self):
        assert has_role(PARENT, models.UserRole.PARENT)
        assert has_role(MANAGER, models.UserRole.ADMIN, models.UserRole.MANAGER)
        assert not has_role(MANAGER, models.UserRole.PARENT)
        assert not has_role(None, models.UserRole.PARENT)

    def test_enforce_role_allows(self):
        assert enforce_role(PARENT, models.UserRole.PARENT) is PARENT

    def test_enforce_role_denies_with_403(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            enforce_role(MANAGER, models.UserRole.PARENT, detail="Parent access only")

        assert exc.value.status_code == 403
        assert exc.value.detail == "Parent access only"


class TestRequirePermissionDependency:
    """require_permission() must work as a real FastAPI dependency."""

    @staticmethod
    def _app(user):
        app = FastAPI()

        @app.get("/guarded")
        def guarded(
            actor=Depends(require_permission(Permission.USER_MANAGE)),
        ):
            return {"role": actor.role.value}

        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    def test_admin_allowed(self):
        response = self._app(ADMIN).get("/guarded")

        assert response.status_code == 200
        assert response.json() == {"role": "ADMIN"}

    def test_manager_denied(self):
        response = self._app(MANAGER).get("/guarded")

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "INSUFFICIENT_PERMISSIONS"
        assert response.json()["detail"]["missing"] == ["admin:users:manage"]

    def test_factory_is_also_directly_callable(self):
        """Section 2.1 calls the factory result on a user object directly."""
        checker = require_permission(Permission.KG_READ)

        assert checker(MANAGER) is MANAGER


class TestNoInlineRoleChecksRemain:
    """Section 10, acceptance criterion 1."""

    @staticmethod
    def _tracked_python_files():
        out = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return [line for line in out.stdout.split() if line]

    def _sweep(self, needle):
        offenders = []
        for rel in self._tracked_python_files():
            path = ROOT / rel
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if needle in line:
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
        return offenders

    def test_no_inequality_role_comparisons(self):
        offenders = self._sweep("role != models.UserRole")

        assert offenders == [], (
            "Inline role comparisons must route through the ADMIN-001 "
            "permission layer:\n" + "\n".join(offenders)
        )

    def test_no_role_membership_lists(self):
        offenders = self._sweep("role not in [models.UserRole")

        assert offenders == [], (
            "Role membership gates must use has_role()/require_permission():\n"
            + "\n".join(offenders)
        )

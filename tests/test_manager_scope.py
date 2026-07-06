"""
Tests for manager_scope.py (ManagerScope).

manager_scope.py used to carry 12 additional filter_*/validate_*
methods with zero call sites anywhere in the codebase, several of which
referenced a bare `db` name that was never a parameter or defined
locally -- calling any of them would raise NameError. They were removed
entirely; only the 3 methods actually used by
manager_analytics_endpoints.py remain. This file locks in that the
remaining methods still work and that the dead methods stay gone.
"""
import pytest
from fastapi import HTTPException

import models
from manager_scope import ManagerScope, ManagerScopeError


def _user(role, kindergarten_id=None):
    return models.User(role=role, kindergarten_id=kindergarten_id)


class TestValidateManager:
    def test_manager_with_kindergarten_passes(self):
        ManagerScope.validate_manager(_user(models.UserRole.MANAGER, kindergarten_id=1))

    def test_non_manager_rejected(self):
        with pytest.raises(HTTPException) as exc:
            ManagerScope.validate_manager(_user(models.UserRole.SUPERVISOR, kindergarten_id=1))
        assert exc.value.status_code == 403

    def test_manager_without_kindergarten_rejected(self):
        with pytest.raises(HTTPException) as exc:
            ManagerScope.validate_manager(_user(models.UserRole.MANAGER))
        assert exc.value.status_code == 400


class TestValidateKindergartenAccess:
    def test_admin_can_access_any_kindergarten(self):
        ManagerScope.validate_kindergarten_access(_user(models.UserRole.ADMIN), 999)

    def test_manager_can_access_own_kindergarten(self):
        ManagerScope.validate_kindergarten_access(_user(models.UserRole.MANAGER, kindergarten_id=1), 1)

    def test_manager_cannot_access_other_kindergarten(self):
        with pytest.raises(HTTPException) as exc:
            ManagerScope.validate_kindergarten_access(_user(models.UserRole.MANAGER, kindergarten_id=1), 2)
        assert exc.value.status_code == 404

    def test_non_manager_non_admin_rejected(self):
        with pytest.raises(HTTPException) as exc:
            ManagerScope.validate_kindergarten_access(_user(models.UserRole.SUPERVISOR, kindergarten_id=1), 1)
        assert exc.value.status_code == 403


class TestGetManagerKindergartenId:
    def test_returns_kindergarten_id(self):
        assert ManagerScope.get_manager_kindergarten_id(_user(models.UserRole.MANAGER, kindergarten_id=5)) == 5

    def test_admin_rejected(self):
        with pytest.raises(HTTPException) as exc:
            ManagerScope.get_manager_kindergarten_id(_user(models.UserRole.ADMIN))
        assert exc.value.status_code == 400


class TestDeadCodeRemoved:
    """Guard against the removed methods silently coming back."""

    def test_no_filter_by_kindergarten_methods_remain(self):
        dead_methods = [
            "filter_user_by_kindergarten",
            "filter_class_by_kindergarten",
            "filter_enrollment_by_kindergarten",
            "filter_incident_by_kindergarten",
            "filter_daily_report_by_kindergarten",
            "filter_child_by_kindergarten",
            "filter_supervisor_by_kindergarten",
            "validate_supervisor_assignment",
            "validate_child_enrollment",
            "validate_class_ownership",
            "validate_daily_report_ownership",
            "validate_incident_ownership",
        ]
        for name in dead_methods:
            assert not hasattr(ManagerScope, name), f"{name} should have been removed as dead code"

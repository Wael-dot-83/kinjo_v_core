"""
Unit tests for Messaging Permissions
"""
import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session
import models
from messaging_permissions import (
    normalize_message_type,
    normalize_roles,
    ensure_kindergartens_exist,
    ensure_classes_exist,
    resolve_announcement_scope,
    parent_active_kindergarten_ids,
    parent_has_active_enrollment,
    parent_has_active_enrollment_in_scope,
    get_manager_for_kindergarten,
    resolve_direct_kindergarten_id,
    resolve_direct_recipient,
    validate_announcement_permissions,
    build_audience_recipients,
    validate_direct_permissions,
    resolve_recipients,
    get_audience_options,
    AudienceDefinition,
    AudienceScope,
    FilterOperator,
    FilterClause
)


class TestMessageTypeNormalization:
    """Test message type normalization"""

    def test_normalize_announcement(self):
        """Test normalizing 'broadcast' to 'announcement'"""
        assert normalize_message_type("broadcast") == "announcement"

    def test_normalize_announcement_direct(self):
        """Test normalizing announcement and direct"""
        assert normalize_message_type("announcement") == "announcement"
        assert normalize_message_type("direct") == "direct"

    def test_normalize_invalid_type(self):
        """Test invalid message type raises error"""
        with pytest.raises(Exception):
            normalize_message_type("invalid")


class TestRoleNormalization:
    """Test role normalization"""

    def test_normalize_single_role(self):
        """Test normalizing single role"""
        roles = normalize_roles(["ADMIN"])
        assert len(roles) == 1
        assert roles[0] == models.UserRole.ADMIN

    def test_normalize_all_roles(self):
        """Test normalizing 'ALL' to all roles"""
        roles = normalize_roles(["ALL"])
        expected_roles = [
            models.UserRole.ADMIN,
            models.UserRole.MANAGER,
            models.UserRole.SUPERVISOR,
            models.UserRole.PARENT
        ]
        assert set(roles) == set(expected_roles)

    def test_normalize_mixed_roles(self):
        """Test normalizing mixed roles with invalid role raises exception"""
        with pytest.raises(Exception):
            normalize_roles(["ADMIN", "MANAGER", "invalid"])

    def test_normalize_deduplication(self):
        """Test role deduplication"""
        roles = normalize_roles(["ADMIN", "admin", "ADMIN"])
        assert len(roles) == 1
        assert roles[0] == models.UserRole.ADMIN


class TestExistenceValidation:
    """Test kindergarten and class existence validation"""

    def test_ensure_kindergartens_exist_valid(self, test_db, sample_kindergarten):
        """Test ensuring valid kindergartens exist"""
        # Should not raise exception
        ensure_kindergartens_exist(test_db, [sample_kindergarten.id])

    def test_ensure_kindergartens_exist_invalid(self, test_db):
        """Test ensuring invalid kindergartens raises error"""
        with pytest.raises(Exception):
            ensure_kindergartens_exist(test_db, [99999])

    def test_ensure_classes_exist_valid(self, test_db, sample_kindergarten, sample_class):
        """Test ensuring valid classes exist"""
        # Should not raise exception
        ensure_classes_exist(test_db, [sample_class.id])

    def test_ensure_classes_exist_invalid(self, test_db):
        """Test ensuring invalid classes raises error"""
        with pytest.raises(Exception):
            ensure_classes_exist(test_db, [99999])


class TestAnnouncementScopeResolution:
    """Test announcement scope resolution"""

    def test_resolve_scope_admin_global(self, test_db):
        """Test admin can send global announcements"""
        admin_user = models.User(role=models.UserRole.ADMIN)
        scope_ids = resolve_announcement_scope(
            None, None, None, admin_user, test_db
        )
        assert scope_ids is None  # Global scope

    def test_resolve_scope_manager_own_kindergarten(self, test_db, sample_kindergarten, manager_user):
        """Test manager can only send to own kindergarten"""
        scope_ids = resolve_announcement_scope(
            None, None, None, manager_user, test_db
        )
        assert scope_ids == [sample_kindergarten.id]

    def test_resolve_scope_manager_invalid_kindergarten(self, test_db, sample_kindergarten, manager_user):
        """Test manager cannot send to other kindergartens"""
        # Create another kindergarten
        kg2 = models.Kindergarten(
            name_ar="Test KG 2",
            name_en="Test KG 2",
            governorate="Amman",
            city="Amman",
            area="Area 2",
            address_line="456 Second St",
            contact_phone="+962792345678",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg2)
        test_db.commit()
        test_db.refresh(kg2)

        # Should raise forbidden error
        with pytest.raises(Exception):
            resolve_announcement_scope(
                None, kg2.id, None, manager_user, test_db
            )


class TestParentEnrollmentChecks:
    """Test parent enrollment related functions"""

    def test_parent_active_kindergarten_ids(self, test_db, parent_user, sample_kindergarten, parent_enrollment):
        """Test getting active kindergarten IDs for parent"""
        # Test function
        kg_ids = parent_active_kindergarten_ids(test_db, parent_user.id)
        assert kg_ids == [sample_kindergarten.id]

    def test_parent_has_active_enrollment(self, test_db, parent_user, sample_kindergarten, parent_enrollment):
        """Test checking if parent has active enrollment"""
        # Test function
        has_enrollment = parent_has_active_enrollment(test_db, parent_user.id, sample_kindergarten.id)
        assert has_enrollment is True

        # Test non-existent enrollment
        has_enrollment = parent_has_active_enrollment(test_db, parent_user.id, 99999)
        assert has_enrollment is False


class TestManagerRetrieval:
    """Test manager retrieval functions"""

    def test_get_manager_for_kindergarten(self, test_db, sample_kindergarten, manager_user):
        """Test getting manager for kindergarten"""
        # Test function
        retrieved_manager = get_manager_for_kindergarten(test_db, sample_kindergarten.id)
        assert retrieved_manager.id == manager_user.id

    def test_get_manager_for_kindergarten_not_found(self, test_db):
        """Test getting manager for kindergarten with no manager"""
        # Create test kindergarten without manager
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            city="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="1234567890",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        # Should raise not found error
        with pytest.raises(Exception):
            get_manager_for_kindergarten(test_db, kg.id)


class TestDirectMessageResolution:
    """Test direct message recipient resolution"""

    def test_resolve_direct_kindergarten_id_matching(self, test_db):
        """Test resolving kindergarten ID when recipient matches"""
        sender = models.User(kindergarten_id=1)
        recipient = models.User(kindergarten_id=1)

        kg_id = resolve_direct_kindergarten_id(sender, recipient, 1)
        assert kg_id == 1

    def test_resolve_direct_kindergarten_id_from_recipient(self, test_db):
        """Test resolving kindergarten ID from recipient"""
        sender = models.User(kindergarten_id=1)
        recipient = models.User(kindergarten_id=2)

        kg_id = resolve_direct_kindergarten_id(sender, recipient, None)
        assert kg_id == 2

    def test_resolve_direct_recipient_by_id(self, test_db, admin_user, parent_user):
        """Test resolving direct recipient by ID"""
        resolved_recipient, kg_id = resolve_direct_recipient(
            test_db, admin_user, parent_user.id, None
        )
        assert resolved_recipient.id == parent_user.id

    def test_resolve_direct_recipient_parent_to_manager(self, test_db, parent_user, sample_kindergarten, manager_user, parent_enrollment):
        """Test parent resolving recipient as manager"""
        # Test resolution
        resolved_recipient, kg_id = resolve_direct_recipient(
            test_db, parent_user, None, sample_kindergarten.id
        )
        assert resolved_recipient.id == manager_user.id
        assert kg_id == sample_kindergarten.id


class TestAnnouncementPermissions:
    """Test announcement permission validation"""

    def test_validate_announcement_permissions_admin(self, test_db):
        """Test admin can send announcements"""
        admin = models.User(role=models.UserRole.ADMIN)

        # Should not raise exception
        validate_announcement_permissions(
            test_db, admin, [models.UserRole.PARENT], [], [], None
        )

    def test_validate_announcement_permissions_manager_valid(self, test_db, sample_kindergarten, manager_user):
        """Test manager can send to parents and supervisors"""
        # Should not raise exception
        validate_announcement_permissions(
            test_db, manager_user, [models.UserRole.PARENT], [], [], [sample_kindergarten.id]
        )

    def test_validate_announcement_permissions_manager_invalid_role(self, test_db, sample_kindergarten, manager_user):
        """Test manager cannot send to admins"""
        # Should raise forbidden error
        with pytest.raises(Exception):
            validate_announcement_permissions(
                test_db, manager_user, [models.UserRole.ADMIN], [], [], [sample_kindergarten.id]
            )


class TestAudienceBuilding:
    """Test audience recipient building"""

    def test_build_audience_recipients_by_role(self, test_db, parent_user, parent_enrollment):
        """Test building recipients by role"""
        recipients = build_audience_recipients(
            test_db, [models.UserRole.PARENT], [], [], None
        )
        assert parent_user.id in recipients

    def test_build_audience_recipients_by_user_ids(self, test_db, parent_user):
        """Test building recipients by user IDs"""
        recipients = build_audience_recipients(
            test_db, [], [parent_user.id], [], None
        )
        assert parent_user.id in recipients


class TestDirectPermissions:
    """Test direct message permission validation"""

    def test_validate_direct_permissions_admin(self, test_db):
        """Test admin can send direct messages to anyone"""
        admin = models.User(role=models.UserRole.ADMIN)
        recipient = models.User(role=models.UserRole.PARENT)

        # Should not raise exception
        validate_direct_permissions(test_db, admin, recipient)

    def test_validate_direct_permissions_manager_to_supervisor(self, test_db, sample_kindergarten, manager_user, supervisor_user):
        """Test manager can send to supervisor in same kindergarten"""
        # Should not raise exception
        validate_direct_permissions(test_db, manager_user, supervisor_user)

    def test_validate_direct_permissions_manager_to_different_kg_supervisor(self, test_db, sample_kindergarten, manager_user):
        """Test manager cannot send to supervisor in different kindergarten"""
        # Create another kindergarten
        kg2 = models.Kindergarten(
            name_ar="Test KG 2",
            name_en="Test KG 2",
            governorate="Amman",
            city="Amman",
            area="Area 2",
            address_line="456 Second St",
            contact_phone="+962792345678",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg2)
        test_db.commit()
        test_db.refresh(kg2)

        supervisor2 = models.User(
            username="supervisor2",
            email="supervisor2@test.com",
            hashed_password="hashed",
            role=models.UserRole.SUPERVISOR,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kg2.id
        )
        test_db.add(supervisor2)
        test_db.commit()
        test_db.refresh(supervisor2)

        # Should raise forbidden error
        with pytest.raises(Exception):
            validate_direct_permissions(test_db, manager_user, supervisor2)


class TestAudienceResolution:
    """Test audience recipient resolution"""

    def test_resolve_recipients_admin_global(self, test_db, parent_user):
        """Test admin resolving global audience"""
        admin = models.User(role=models.UserRole.ADMIN)

        audience = AudienceDefinition(
            include_roles=[models.UserRole.PARENT]
        )

        recipients = resolve_recipients(test_db, audience, admin)
        assert parent_user.id in recipients

    def test_resolve_recipients_manager_limited_scope(self, test_db, sample_kindergarten, manager_user, parent_user, parent_enrollment):
        """Test manager resolving recipients in limited scope"""
        audience = AudienceDefinition(
            include_roles=[models.UserRole.PARENT]
        )

        recipients = resolve_recipients(test_db, audience, manager_user)
        assert parent_user.id in recipients


class TestAudienceOptions:
    """Test getting audience options"""

    def test_get_audience_options_admin(self, test_db, admin_user, sample_kindergarten):
        """Test getting audience options for admin"""
        options = get_audience_options(test_db, admin_user)

        assert "roles" in options
        assert "governorates" in options
        assert "kindergartens" in options
        assert "classes" in options

        assert len(options["roles"]) > 0
        assert "Amman" in options["governorates"]

    def test_get_audience_options_manager(self, test_db, manager_user, sample_kindergarten):
        """Test getting audience options for manager"""
        options = get_audience_options(test_db, manager_user)

        # Manager should only see their own kindergarten
        assert len(options["kindergartens"]) == 1
        assert options["kindergartens"][0]["id"] == sample_kindergarten.id
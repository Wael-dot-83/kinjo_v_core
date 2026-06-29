"""
Unit tests for Notification Service
"""
import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session
import models
from auth import get_password_hash
from notification_service import (
    create_daily_report_notification,
    notify_parent_daily_report,
    notify_manager_report_submitted,
    notify_supervisor_report_rejected,
    notify_missing_daily_report_alert,
    _build_notification_payload,
    _queue_notification_tasks,
    create_message_notifications
)


class TestDailyReportNotifications:
    """Test daily report notification creation"""

    def test_create_daily_report_notification_sent(self, test_db, parent_user, parent_enrollment, sample_child, sample_kindergarten):
        """Test creating notification for sent daily report"""

        report = models.DailyReport(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            date=date.today(),
            submitted_by=parent_user.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        # Mock settings to enable notifications
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True
            mock_settings.NOTIFICATIONS_PUSH_ENABLED = True

            notification = create_daily_report_notification(
                test_db,
                report,
                parent_user,
                models.NotificationType.DAILY_REPORT_SENT
            )

            assert notification is not None
            # Check that notifications were created in database
            notifications = test_db.query(models.Notification).filter(
                models.Notification.daily_report_id == report.id
            ).all()
            assert len(notifications) == 3  # EMAIL, PUSH, IN_APP

    def test_create_daily_report_notification_testing_mode(self, test_db, parent_user, sample_child, sample_kindergarten):
        """Test notification creation in testing mode returns None"""

        report = models.DailyReport(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            date=date.today(),
            submitted_by=parent_user.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        # Mock settings for testing mode
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = True

            notification = create_daily_report_notification(
                test_db,
                report,
                parent_user,
                models.NotificationType.DAILY_REPORT_SENT
            )

            assert notification is None

    def test_create_daily_report_notification_submitted(self, test_db, parent_user, sample_child, supervisor_user, sample_kindergarten):
        """Test creating notification for submitted daily report"""

        report = models.DailyReport(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            date=date.today(),
            submitted_by=parent_user.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        # Mock settings
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True
            mock_settings.NOTIFICATIONS_PUSH_ENABLED = False

            notification = create_daily_report_notification(
                test_db,
                report,
                supervisor_user,
                models.NotificationType.DAILY_REPORT_SUBMITTED
            )

            assert notification is not None

    def test_create_daily_report_notification_rejected(self, test_db, parent_user, sample_child, supervisor_user, sample_kindergarten):
        """Test creating notification for rejected daily report"""

        report = models.DailyReport(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            date=date.today(),
            submitted_by=parent_user.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        # Mock settings
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True
            mock_settings.NOTIFICATIONS_PUSH_ENABLED = False

            notification = create_daily_report_notification(
                test_db,
                report,
                supervisor_user,
                models.NotificationType.DAILY_REPORT_REJECTED,
                "Report needs more details"
            )

            assert notification is not None

    def test_create_daily_report_notification_missing(self, test_db, manager_user):
        """Test creating notification for missing daily report"""

        # Mock settings
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True
            mock_settings.NOTIFICATIONS_PUSH_ENABLED = False

            notification = create_daily_report_notification(
                test_db,
                None,  # No report for missing notifications
                manager_user,
                models.NotificationType.DAILY_REPORT_MISSING,
                "Missing reports for 3 children"
            )

            assert notification is not None


class TestParentNotifications:
    """Test parent notification functions"""

    def test_notify_parent_daily_report_success(self, test_db, parent_user, sample_child, sample_kindergarten):
        """Test notifying parent of daily report successfully"""

        report = models.DailyReport(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            date=date.today(),
            submitted_by=parent_user.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        # Mock settings
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True

            result = notify_parent_daily_report(test_db, report)
            assert result is True

    def test_notify_parent_daily_report_no_parent(self, test_db, sample_kindergarten):
        """Test notifying parent when child has invalid parent reference"""
        # Create a child with a parent_id that doesn't exist in parent_profiles
        child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=99999,  # Non-existent parent profile ID
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Test Father",
            mother_first_name="Test Mother",
            mother_last_name="Last Name",
            mother_nationality="Jordanian"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        # Create a submitter user for the report
        submitter = models.User(
            username="testsubmitter",
            email="submitter@test.com",
            hashed_password=get_password_hash("Password1!"),
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=sample_kindergarten.id
        )
        test_db.add(submitter)
        test_db.commit()
        test_db.refresh(submitter)

        report = models.DailyReport(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            date=date.today(),
            submitted_by=submitter.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        result = notify_parent_daily_report(test_db, report)
        assert result is False


class TestManagerNotifications:
    """Test manager notification functions"""

    def test_notify_manager_report_submitted_success(self, test_db):
        """Test notifying manager of submitted report successfully"""
        # Create test data
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            district="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="1234567890",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        manager = models.User(
            username="testmanager",
            email="manager@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kg.id
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        parent_profile = models.ParentProfile(
            user_id=manager.id,
            first_name="Test",
            last_name="Parent",
            phone_number="1234567890",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="1234567890",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Test Father",
            mother_first_name="Test Mother",
            mother_last_name="Last Name",
            mother_nationality="Jordanian"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        report = models.DailyReport(
            child_id=child.id,
            kindergarten_id=kg.id,
            date=date.today(),
            submitted_by=manager.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        # Mock settings
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True

            result = notify_manager_report_submitted(test_db, report, kg.id)
            assert result is True

    def test_notify_manager_report_submitted_no_manager(self, test_db):
        """Test notifying manager when no manager exists"""
        # Create test kindergarten without manager
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            district="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="1234567890",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        parent_profile = models.ParentProfile(
            user_id=1,
            first_name="Test",
            last_name="Parent",
            phone_number="1234567890",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="1234567890",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Test Father",
            mother_first_name="Test Mother",
            mother_last_name="Last Name",
            mother_nationality="Jordanian"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        # Create a submitter user for the report (not a manager)
        submitter = models.User(
            username="testsubmitter2",
            email="submitter2@test.com",
            hashed_password=get_password_hash("Password1!"),
            role=models.UserRole.SUPERVISOR,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kg.id
        )
        test_db.add(submitter)
        test_db.commit()
        test_db.refresh(submitter)

        report = models.DailyReport(
            child_id=child.id,
            kindergarten_id=kg.id,
            date=date.today(),
            submitted_by=submitter.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        result = notify_manager_report_submitted(test_db, report, kg.id)
        assert result is False


class TestSupervisorNotifications:
    """Test supervisor notification functions"""

    def test_notify_supervisor_report_rejected_success(self, test_db, supervisor_user, sample_kindergarten):
        """Test notifying supervisor of rejected report successfully"""

        parent_profile = models.ParentProfile(
            user_id=supervisor_user.id,
            first_name="Test",
            last_name="Parent",
            phone_number="1234567890",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="1234567890",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Test Father",
            mother_first_name="Test Mother",
            mother_last_name="Last Name",
            mother_nationality="Jordanian"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        report = models.DailyReport(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            date=date.today(),
            submitted_by=supervisor_user.id,
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        # Mock settings
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True

            result = notify_supervisor_report_rejected(test_db, report, "Needs revision")
            assert result is True

    def test_notify_supervisor_report_rejected_no_submitter(self, test_db, sample_kindergarten):
        """Test notifying supervisor when report has no submitter"""
        parent_profile = models.ParentProfile(
            user_id=1,
            first_name="Test",
            last_name="Parent",
            phone_number="1234567890",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="1234567890",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Test Area",
            home_address_line="Test Address"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Test Father",
            mother_first_name="Test Mother",
            mother_last_name="Last Name",
            mother_nationality="Jordanian"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        # Create a submitter user for the report
        submitter = models.User(
            username="testsubmitter3",
            email="submitter3@test.com",
            hashed_password=get_password_hash("Password1!"),
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=sample_kindergarten.id
        )
        test_db.add(submitter)
        test_db.commit()
        test_db.refresh(submitter)

        report = models.DailyReport(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            date=date.today(),
            submitted_by=99999,  # Non-existent submitter ID
            arrival_time="08:00",
            leave_time="15:00"
        )
        test_db.add(report)
        test_db.commit()
        test_db.refresh(report)

        result = notify_supervisor_report_rejected(test_db, report)
        assert result is False


class TestMissingReportAlerts:
    """Test missing daily report alert notifications"""

    def test_notify_missing_daily_report_alert_success(self, test_db):
        """Test notifying user of missing daily reports successfully"""
        # Create test data
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            district="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="1234567890",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        manager = models.User(
            username="testmanager",
            email="manager@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=kg.id,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        missing_children = [
            {"child_name": "Child 1", "child_id": 1},
            {"child_name": "Child 2", "child_id": 2},
            {"child_name": "Child 3", "child_id": 3}
        ]

        # Mock settings
        with patch('notification_service.settings') as mock_settings, \
             patch('notification_service.send_email_notification.delay') as mock_email_task, \
             patch('notification_service.send_push_notification.delay') as mock_push_task:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True
            mock_settings.NOTIFICATIONS_PUSH_ENABLED = True
            mock_email_task.return_value = None
            mock_push_task.return_value = None

            result = notify_missing_daily_report_alert(
                test_db,
                manager,
                missing_children,
                date.today(),
                "Daily reports missing"
            )
            assert result is True

    def test_notify_missing_daily_report_alert_testing_mode(self, test_db):
        """Test missing report alert in testing mode returns False"""
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            district="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="1234567890",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        manager = models.User(
            username="testmanager",
            email="manager@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=kg.id,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        missing_children = [{"child_name": "Child 1", "child_id": 1}]

        # Mock settings for testing mode
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = True

            result = notify_missing_daily_report_alert(
                test_db,
                manager,
                missing_children,
                date.today(),
                "Daily reports missing"
            )
            assert result is False

    def test_notify_missing_daily_report_alert_no_children(self, test_db):
        """Test missing report alert with no missing children"""
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            district="Amman",
            area="Test Area",
            address_line="Test Address",
            contact_phone="1234567890",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        manager = models.User(
            username="testmanager",
            email="manager@test.com",
            hashed_password=get_password_hash("Manager123!"),
            role=models.UserRole.MANAGER,
            kindergarten_id=kg.id,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(manager)
        test_db.commit()
        test_db.refresh(manager)

        result = notify_missing_daily_report_alert(
            test_db,
            manager,
            [],  # No missing children
            date.today(),
            "Daily reports missing"
        )
        assert result is False


class TestPayloadBuilding:
    """Test notification payload building"""

    def test_build_notification_payload_with_subject(self, test_db):
        """Test building payload for message with subject"""
        message = models.Message(
            subject="Test Subject",
            message_body="Test message body"
        )

        payload = _build_notification_payload(message)
        assert payload["subject"] == "Test Subject"
        assert payload["title"] == "Test Subject"
        assert "Test message body" in payload["body"]

    def test_build_notification_payload_no_subject(self, test_db):
        """Test building payload for message without subject"""
        message = models.Message(
            subject=None,
            message_body="Test message body"
        )

        payload = _build_notification_payload(message)
        assert payload["subject"] == "New message"
        assert payload["title"] == "New message"
        assert "Test message body" in payload["body"]

    def test_build_notification_payload_long_body(self, test_db):
        """Test building payload for message with long body"""
        long_body = "A" * 300  # Longer than 240 chars
        message = models.Message(
            subject="Test Subject",
            message_body=long_body
        )

        payload = _build_notification_payload(message)
        assert len(payload["body"]) <= 240  # Should be truncated


class TestMessageNotifications:
    """Test message notification creation"""

    def test_create_message_notifications_success(self, test_db):
        """Test creating notifications for message successfully"""
        # Create test data
        sender = models.User(
            username="testsender",
            email="sender@test.com",
            hashed_password=get_password_hash("Sender123!"),
            role=models.UserRole.ADMIN,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(sender)
        test_db.commit()
        test_db.refresh(sender)

        recipient1 = models.User(
            username="testrecipient1",
            email="recipient1@test.com",
            hashed_password=get_password_hash("Recipient123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        recipient2 = models.User(
            username="testrecipient2",
            email="recipient2@test.com",
            hashed_password=get_password_hash("Recipient123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add_all([recipient1, recipient2])
        test_db.commit()
        test_db.refresh(recipient1)
        test_db.refresh(recipient2)

        message = models.Message(
            subject="Test Message",
            message_body="Test message body",
            sender_id=sender.id,
            thread_type=models.MessageThreadType.DIRECT
        )
        test_db.add(message)
        test_db.commit()
        test_db.refresh(message)

        recipients = [recipient1, recipient2]

        # Mock settings
        with patch('notification_service.settings') as mock_settings, \
             patch('notification_service.send_email_notification.delay') as mock_email_task, \
             patch('notification_service.send_push_notification.delay') as mock_push_task:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = True
            mock_settings.NOTIFICATIONS_PUSH_ENABLED = True
            mock_email_task.return_value = None
            mock_push_task.return_value = None

            result = create_message_notifications(test_db, message, recipients)
            assert result is True

            # Check notifications were created
            notifications = test_db.query(models.Notification).filter(
                models.Notification.message_id == message.id
            ).all()
            assert len(notifications) == 4  # 2 recipients × 2 channels each

    def test_create_message_notifications_testing_mode(self, test_db):
        """Test message notifications in testing mode returns False"""
        message = models.Message(subject="Test", message_body="Test body")
        recipients = []

        # Mock settings for testing mode
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = True

            result = create_message_notifications(test_db, message, recipients)
            assert result is False

    def test_create_message_notifications_no_channels(self, test_db):
        """Test message notifications when no channels enabled"""
        message = models.Message(subject="Test", message_body="Test body")
        recipients = [models.User(id=1, username="test")]

        # Mock settings with no channels enabled
        with patch('notification_service.settings') as mock_settings:
            mock_settings.TESTING = False
            mock_settings.NOTIFICATIONS_EMAIL_ENABLED = False
            mock_settings.NOTIFICATIONS_PUSH_ENABLED = False

            result = create_message_notifications(test_db, message, recipients)
            assert result is False


class TestNotificationQueueing:
    """Test notification task queueing"""

    @patch('notification_service.send_email_notification')
    @patch('notification_service.send_push_notification')
    def test_queue_notification_tasks(self, mock_push, mock_email, test_db):
        """Test queueing notification tasks"""
        # Create test notifications
        email_notification = models.Notification(
            user_id=1,
            channel=models.NotificationChannel.EMAIL,
            status=models.NotificationStatus.PENDING
        )
        push_notification = models.Notification(
            user_id=1,
            channel=models.NotificationChannel.PUSH,
            status=models.NotificationStatus.PENDING
        )
        in_app_notification = models.Notification(
            user_id=1,
            channel=models.NotificationChannel.IN_APP,
            status=models.NotificationStatus.PENDING
        )

        notifications = [email_notification, push_notification, in_app_notification]

        # Mock the delay methods
        mock_email.delay = Mock()
        mock_push.delay = Mock()

        _queue_notification_tasks(notifications)

        # Check that email and push tasks were queued
        mock_email.delay.assert_called_once_with(email_notification.id)
        mock_push.delay.assert_called_once_with(push_notification.id)
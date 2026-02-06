# TODO: Admin Messaging Implementation

## Phase 1: Backend Enhancement

- [x] 1.1 Add parent governorate resolution helper function
- [x] 1.2 Update \_resolve_admin_recipient_ids for better search handling
- [x] 1.3 Add recipient preview endpoint (GET /api/admin/message-recipients/preview)
- [x] 1.4 Add governorates options endpoint (GET /api/admin/options/governorates)
- [x] 1.5 Ensure RBAC properly enforced for all admin endpoints

## Phase 2: Frontend UI Updates

- [x] 2.1 Add admin targeting section to new_message.html modal
- [x] 2.2 Implement adminTargetMode selector with modes 3.1-3.5
- [x] 2.3 Add governorate multi-select dropdown
- [x] 2.4 Add kindergarten multi-select with search
- [x] 2.5 Add role checkboxes (Manager/Supervisor/Parent)
- [x] 2.6 Add search input (name/email/phone)
- [x] 2.7 Implement recipient count preview functionality
- [x] 2.8 Connect submit button to /api/admin/messages endpoint
- [x] 2.9 Ensure RTL and Arabic-first styling

## Phase 3: Testing

- [x] 3.1 Test ALL_USERS mode
- [x] 3.2 Test ALL_MANAGERS mode
- [x] 3.3 Test ALL_PARENTS mode
- [x] 3.4 Test GOVERNORATE mode with roles
- [x] 3.5 Test KINDERGARTENS mode with multi-select
- [x] 3.6 Test search filtering
- [x] 3.7 Test recipient deduplication
- [x] 3.8 Test RBAC (non-admin blocked)
- [x] 3.9 Test inbox visibility

## Phase 4: Integration & Validation

- [x] 4.1 Verify existing Manager announcements still work
- [x] 4.2 Verify inbox queries include admin messages
- [x] 4.3 Test performance with large recipient sets
- [x] 4.4 Verify rate limiting applies correctly
- [x] 4.5 Check audit logging completeness

## Quick Commands

```bash
# Run admin messaging tests
pytest tests/test_admin_messaging.py -v

# Run all messaging tests
pytest tests/test_messaging.py tests/test_messages_phase*.py -v

# Run with coverage
pytest tests/test_admin_messaging.py --cov=admin_endpoints --cov-report=html

# Test specific functionality
pytest tests/test_admin_messaging.py::test_admin_send_all_users_and_roles -v
```

## Notes

- The backend foundation is already in place with `admin_endpoints.py`
- The MessageRecipient table already exists for tracking recipients
- Tests are in `tests/test_admin_messaging.py`
- Frontend modal is in `templates/communication/modals/new_message.html`

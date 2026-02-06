# Admin Messaging Implementation Plan

## Executive Summary

The codebase already has a **solid foundation** for messaging with:

- `Message` table with targeting metadata fields (`target_mode`, `target_roles`, etc.)
- `MessageRecipient` join table for many-to-many recipient tracking
- `admin_endpoints.py` with admin messaging endpoints (`/api/admin/messages`, `/api/admin/message-recipients`)
- `messaging_permissions.py` with audience resolution logic
- Basic UI modal in `templates/communication/modals/new_message.html`

**What's missing**:

1. The admin-specific targeting modes (3.1-3.5) are not fully implemented in the UI
2. Admin-specific recipient filtering/preview UI
3. Some test coverage gaps

## Current State Analysis

### Database Models ✓

- `Message` table: Has `target_mode`, `target_roles`, `target_governorates`, `target_kindergarten_ids`, `target_search`, `recipient_count`
- `MessageRecipient` table: Already exists with `message_id`, `recipient_user_id`, `delivered_at`, `read_at`, `status`
- `MessageUserState`: Per-user read/archived/deleted tracking

### Backend APIs ✓

- `/api/admin/messages` - POST endpoint exists with `AdminMessageCreate` schema
- `/api/admin/message-recipients` - GET endpoint exists with filtering support
- Uses `_resolve_admin_recipient_ids()` for recipient resolution
- Uses `_normalize_governorates()`, `_dedupe_int_list()` helpers

### Frontend ✗

- Basic modal exists but doesn't fully support admin targeting modes
- Missing: Recipient count preview, search, proper kindergarten multi-select
- Needs: Arabic-first RTL styling improvements

### Tests ✓

- `test_admin_messaging.py` has good coverage for core scenarios
- Tests cover: all users, governorate targeting, kindergarten targeting, RBAC

---

## Implementation Steps

### Step 1: Backend Enhancement (Priority: High)

#### 1.1 Enhance Admin Messaging Endpoints

**File**: `admin_endpoints.py`

**Add Pydantic schemas for new targeting modes**:

```python
class AdminTargetMode(str, enum.Enum):
    ALL_USERS = "ALL_USERS"
    ALL_MANAGERS = "ALL_MANAGERS"
    ALL_PARENTS = "ALL_PARENTS"
    GOVERNORATE = "GOVERNORATE"
    KINDERGARTENS = "KINDERGARTENS"

class AdminMessageTarget(BaseModel):
    mode: AdminTargetMode
    roles: Optional[List[AdminRecipientRole]] = None  # For GOVERNORATE/KINDERGARTENS
    governorates: Optional[List[str]] = None  # For GOVERNORATE mode
    kindergarten_ids: Optional[List[int]] = None  # For KINDERGARTENS mode
    search: Optional[str] = None  # Combined search filter
```

**Update recipient resolution function** (`_resolve_admin_recipient_ids`):

The function already handles most cases but needs:

1. Better parent governorate resolution (enrollment-based OR home_governorate fallback)
2. Support for search across name/email/phone

**Parent Governorate Resolution Logic**:

```python
def _get_parent_governorate(db: Session, parent_user_id: int) -> Optional[str]:
    """Get parent governorate: prefer enrolled kindergarten, fallback to home_governorate"""
    # Try enrollment-based first
    enrollment_gov = db.query(models.Kindergarten.governorate).join(
        models.EnrollmentApplication,
        models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id
    ).join(
        models.Child,
        models.Child.id == models.EnrollmentApplication.child_id
    ).join(
        models.ParentProfile,
        models.ParentProfile.id == models.Child.parent_id
    ).filter(
        models.ParentProfile.user_id == parent_user_id,
        models.EnrollmentApplication.status.in_(ACTIVE_ENROLLMENT_STATUSES)
    ).first()

    if enrollment_gov:
        return enrollment_gov[0]

    # Fallback to home_governorate
    home_gov = db.query(models.ParentProfile.home_governorate).filter(
        models.ParentProfile.user_id == parent_user_id
    ).first()

    return home_gov[0] if home_gov else None
```

#### 1.2 Add Recipient Preview Endpoint

**Enhance** `/api/admin/message-recipients` to support preview mode:

```python
@router.get("/admin/message-recipients/preview")
def preview_recipients(
    mode: AdminTargetMode,
    roles: Optional[List[str]] = None,
    governorates: Optional[List[str]] = None,
    kindergarten_ids: Optional[List[int]] = None,
    search: Optional[str] = None,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
) -> AdminRecipientPreviewResponse:
    """Get recipient count preview before sending message"""
    recipient_ids = _resolve_admin_recipient_ids(
        db=db,
        roles=_normalize_recipient_roles(roles),
        governorates=_normalize_governorates(governorates),
        kindergarten_ids=_dedupe_int_list(kindergarten_ids),
        search=search
    )
    return {
        "total_count": len(recipient_ids),
        "has_more": len(recipient_ids) > 100  # Sample indicator
    }
```

### Step 2: Frontend Enhancement (Priority: High)

#### 2.1 Update New Message Modal

**File**: `templates/communication/modals/new_message.html`

**New Admin-Only Targeting Section**:

```html
<!-- Admin Targeting Section - Only visible to admins -->
<div id="adminTargetingSection" style="display:none;">
  <!-- Target Mode Selection -->
  <div class="mb-3">
    <label class="form-label">نطاق الاستلام</label>
    <select
      class="form-select"
      id="adminTargetMode"
      onchange="updateAdminTargetingUI()"
    >
      <option value="ALL_USERS">جميع المستخدمين</option>
      <option value="ALL_MANAGERS">جميع المديرين فقط</option>
      <option value="ALL_PARENTS">جميع أولياء الأمور فقط</option>
      <option value="GOVERNORATE">حسب المحافظة</option>
      <option value="KINDERGARTENS">روضات محددة</option>
    </select>
  </div>

  <!-- Governorate Selection (for GOVERNORATE mode) -->
  <div class="mb-3" id="adminGovernorateSection" style="display:none;">
    <label class="form-label">المحافظة</label>
    <select class="form-select" id="adminGovernorate" multiple size="5">
      <!-- Populated from API -->
    </select>
    <div class="form-text">يمكنك اختيار محافظة واحدة أو أكثر</div>
  </div>

  <!-- Kindergarten Multi-Select (for KINDERGARTENS mode) -->
  <div class="mb-3" id="adminKindergartenSection" style="display:none;">
    <label class="form-label">الروضات</label>
    <div class="input-group mb-2">
      <input
        type="text"
        class="form-control"
        id="kgSearchInput"
        placeholder="بحث بالاسم..."
      />
      <button
        class="btn btn-outline-secondary"
        type="button"
        onclick="searchKindergartens()"
      >
        بحث
      </button>
    </div>
    <div
      class="border rounded p-2"
      id="adminKindergartenList"
      style="max-height: 200px; overflow-y: auto;"
    >
      <!-- Checkboxes populated here -->
    </div>
    <div class="form-text mt-1">
      <span id="selectedKgCount">0</span> روضة/روضات محددة
    </div>
  </div>

  <!-- Role Selection (for GOVERNORATE/KINDERGARTENS modes) -->
  <div class="mb-3" id="adminRolesSection" style="display:none;">
    <label class="form-label">الأدوار المستلمة</label>
    <div class="row">
      <div class="col-md-4">
        <div class="form-check">
          <input
            class="form-check-input"
            type="checkbox"
            value="MANAGER"
            id="adminRoleManager"
          />
          <label class="form-check-label" for="adminRoleManager"
            >المديرون</label
          >
        </div>
      </div>
      <div class="col-md-4">
        <div class="form-check">
          <input
            class="form-check-input"
            type="checkbox"
            value="SUPERVISOR"
            id="adminRoleSupervisor"
          />
          <label class="form-check-label" for="adminRoleSupervisor"
            >المشرفون</label
          >
        </div>
      </div>
      <div class="col-md-4">
        <div class="form-check">
          <input
            class="form-check-input"
            type="checkbox"
            value="PARENT"
            id="adminRoleParent"
          />
          <label class="form-check-label" for="adminRoleParent"
            >أولياء الأمور</label
          >
        </div>
      </div>
    </div>
  </div>

  <!-- Search Filter -->
  <div class="mb-3">
    <label class="form-label">بحث متقدم (اسم، بريد، هاتف)</label>
    <input
      type="text"
      class="form-control"
      id="adminSearchInput"
      placeholder="ابحث بالاسم أو البريد الإلكتروني أو الهاتف"
    />
  </div>

  <!-- Recipient Preview -->
  <div class="alert alert-info" id="adminRecipientPreview">
    <div class="d-flex justify-content-between align-items-center">
      <span>عدد المستلمين: <strong id="recipientCount">-</strong></span>
      <button
        type="button"
        class="btn btn-sm btn-outline-info"
        onclick="previewRecipients()"
      >
        معاينة المستلمين
      </button>
    </div>
  </div>
</div>
```

#### 2.2 Update JavaScript Logic

**Add admin targeting functions**:

```javascript
async function initAdminMessaging() {
  if (currentUserRole !== "ADMIN") {
    document.getElementById("adminTargetingSection").style.display = "none";
    return;
  }

  document.getElementById("adminTargetingSection").style.display = "block";
  await loadGovernorates();
  await loadKindergartensForAdmin();
  updateAdminTargetingUI();
}

async function loadGovernorates() {
  const token = localStorage.getItem("access_token");
  const response = await fetch("/api/admin/options/governorates", {
    headers: { Authorization: `Bearer ${token}` },
  });
  const governorates = await response.json();

  const select = document.getElementById("adminGovernorate");
  select.innerHTML = governorates
    .map((gov) => `<option value="${gov}">${gov}</option>`)
    .join("");
}

async function loadKindergartensForAdmin() {
  const token = localStorage.getItem("access_token");
  const response = await fetch("/api/kindergartens?limit=500&status=active", {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await response.json();
  const kindergartens = Array.isArray(data) ? data : data.kindergartens || [];

  // Group by governorate
  const grouped = {};
  kindergartens.forEach((kg) => {
    const gov = kg.governorate || "غير محدد";
    if (!grouped[gov]) grouped[gov] = [];
    grouped[gov].push(kg);
  });

  // Render checkboxes
  const container = document.getElementById("adminKindergartenList");
  container.innerHTML = Object.entries(grouped)
    .map(
      ([gov, kgs]) => `
        <div class="mb-2">
            <div class="fw-bold text-muted small">${gov}</div>
            ${kgs
              .map(
                (kg) => `
                <div class="form-check">
                    <input class="form-check-input admin-kg-checkbox" type="checkbox" 
                        value="${kg.id}" data-governorate="${gov}" 
                        onchange="updateSelectedKgCount()">
                    <label class="form-check-label">${kg.name_ar || kg.name_en}</label>
                </div>
            `,
              )
              .join("")}
        </div>
    `,
    )
    .join("");
}

function updateAdminTargetingUI() {
  const mode = document.getElementById("adminTargetMode").value;

  // Show/hide sections based on mode
  document.getElementById("adminGovernorateSection").style.display =
    mode === "GOVERNORATE" ? "block" : "none";
  document.getElementById("adminKindergartenSection").style.display =
    mode === "KINDERGARTENS" ? "block" : "none";
  document.getElementById("adminRolesSection").style.display =
    mode === "GOVERNORATE" || mode === "KINDERGARTENS" ? "block" : "none";

  // Auto-update preview
  previewRecipients();
}

function updateSelectedKgCount() {
  const count = document.querySelectorAll(".admin-kg-checkbox:checked").length;
  document.getElementById("selectedKgCount").textContent = count;
}

async function previewRecipients() {
  const token = localStorage.getItem("access_token");
  const mode = document.getElementById("adminTargetMode").value;

  const params = new URLSearchParams();
  params.append("mode", mode);

  if (mode === "GOVERNORATE") {
    const selectedGovs = Array.from(
      document.getElementById("adminGovernorate").selectedOptions,
    ).map((opt) => opt.value);
    params.append("governorates", selectedGovs.join(","));
  }

  if (mode === "KINDERGARTENS") {
    const selectedKgs = Array.from(
      document.querySelectorAll(".admin-kg-checkbox:checked"),
    ).map((cb) => cb.value);
    params.append("kindergarten_ids", selectedKgs.join(","));
  }

  // Get selected roles
  const selectedRoles = [];
  if (document.getElementById("adminRoleManager").checked)
    selectedRoles.push("MANAGER");
  if (document.getElementById("adminRoleSupervisor").checked)
    selectedRoles.push("SUPERVISOR");
  if (document.getElementById("adminRoleParent").checked)
    selectedRoles.push("PARENT");
  if (selectedRoles.length) {
    params.append("roles", selectedRoles.join(","));
  }

  const search = document.getElementById("adminSearchInput").value.trim();
  if (search) params.append("search", search);

  try {
    const response = await fetch(
      `/api/admin/message-recipients/preview?${params}`,
      {
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    const data = await response.json();
    document.getElementById("recipientCount").textContent = data.total_count;
  } catch (err) {
    console.error("Error previewing recipients:", err);
    document.getElementById("recipientCount").textContent = "خطأ";
  }
}

async function submitAdminMessage() {
  const subject = document.getElementById("msgSubject").value;
  const body = document.getElementById("msgBody").value;
  const token = localStorage.getItem("access_token");

  if (!subject || !body) {
    alert("الموضوع ونص الرسالة مطلوبان");
    return;
  }

  const mode = document.getElementById("adminTargetMode").value;
  const target = { mode };

  if (mode === "GOVERNORATE") {
    target.governorates = Array.from(
      document.getElementById("adminGovernorate").selectedOptions,
    ).map((opt) => opt.value);
  }

  if (mode === "KINDERGARTENS") {
    target.kindergarten_ids = Array.from(
      document.querySelectorAll(".admin-kg-checkbox:checked"),
    ).map((cb) => parseInt(cb.value));
  }

  const roles = [];
  if (document.getElementById("adminRoleManager").checked)
    roles.push("MANAGER");
  if (document.getElementById("adminRoleSupervisor").checked)
    roles.push("SUPERVISOR");
  if (document.getElementById("adminRoleParent").checked) roles.push("PARENT");
  if (roles.length) target.roles = roles;

  target.search =
    document.getElementById("adminSearchInput").value.trim() || null;

  const payload = {
    subject,
    message_body: body,
    target,
    allow_replies:
      document.getElementById("allowRepliesToggle")?.checked ?? true,
  };

  try {
    const response = await fetch("/api/admin/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (response.ok) {
      alert("تم إرسال الرسالة بنجاح!");
      // Reset form and close modal
    } else {
      const err = await response.json();
      alert("خطأ: " + (err.detail || err.message || "Unknown error"));
    }
  } catch (err) {
    console.error("Error sending admin message:", err);
    alert("خطأ في الشبكة");
  }
}
```

### Step 3: Test Coverage Enhancement

#### 3.1 Add Missing Tests

**File**: `tests/test_admin_messaging.py`

```python
def test_admin_governorate_targeting_with_search(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    """Test governorate targeting with search filter"""
    # Create test users in Amman
    parent_amman = create_parent(test_db, "parent_amman", "Amman", [sample_kindergarten.id])

    # Create test users in Irbid
    kg_irbid = create_kindergarten(test_db, "Irbid KG", "Irbid", "3001")

    # Search for "parent" should only return parent users
    response = client.get(
        "/api/admin/message-recipients",
        params={
            "governorates": ["Amman"],
            "search": "parent",
            "roles": ["PARENT"]
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    # Should filter to only Amman parents matching search
    assert any(r["id"] == parent_amman.id for r in data["items"])


def test_admin_kindergarten_multi_select(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    """Test selecting multiple kindergartens"""
    kg2 = create_kindergarten(test_db, "KG 2", "Amman", "3002")
    parent2 = create_parent(test_db, "parent2", "Amman", [kg2.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Multi-KG Test",
            "message_body": "Test",
            "target": {
                "mode": "KINDERGARTENS",
                "kindergarten_ids": [sample_kindergarten.id, kg2.id],
                "roles": ["PARENT"]
            }
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    data = response.json()

    # Verify recipients from both kindergartens
    recipients = test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == data["id"]
    ).all()
    recipient_ids = {r.recipient_user_id for r in recipients}
    assert parent_user.id in recipient_ids
    assert parent2.id in recipient_ids


def test_recipient_deduplication_across_filters(
    client, test_db, auth_headers_admin, sample_kindergarten
):
    """Test that user is only counted once even if matching multiple filters"""
    # Parent enrolled in multiple kindergartens in same governorate
    kg2 = create_kindergarten(test_db, "KG 2", "Amman", "3003")
    parent_multi = create_parent(test_db, "parent_multi", "Amman",
                                 [sample_kindergarten.id, kg2.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Dedupe Test",
            "message_body": "Test",
            "target": {
                "mode": "GOVERNORATE",
                "governorates": ["Amman"],
                "roles": ["PARENT"]
            }
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201

    # Verify parent is only counted once
    recipients = test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == response.json()["id"]
    ).all()
    assert len(recipients) == 1
    assert recipients[0].recipient_user_id == parent_multi.id


def test_inbox_shows_admin_announcements(
    client, test_db, auth_headers_parent, manager_user, parent_user
):
    """Test that parent sees admin announcements in their inbox"""
    # Admin sends to all parents
    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "All Parents Announcement",
            "message_body": "Hello parents",
            "target": {"mode": "ALL_PARENTS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]

    # Parent should see it in inbox
    response = client.get("/comm/messages", headers=auth_headers_parent)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["id"] == msg_id for item in items)
```

### Step 4: Integration with Existing Communication Service

The existing `communication_service.py` should be updated to:

1. Use the new admin endpoints for admin messaging
2. Ensure backward compatibility for Manager/Supervisor announcements

**Key consideration**: The existing `/api/comm/messages` endpoint for announcements should continue to work for Managers, but Admins should use `/api/admin/messages` for advanced targeting.

---

## Migration & Deployment Notes

### Database Migration

No schema changes needed - tables already exist!

### Environment Variables

No new environment variables required.

### Testing

Run tests with:

```bash
pytest tests/test_admin_messaging.py -v
```

### API Documentation

The admin messaging endpoints are documented via FastAPI's automatic docs at `/docs`.

---

## Acceptance Criteria Checklist

| Criteria                                 | Status | Notes                       |
| ---------------------------------------- | ------ | --------------------------- |
| Admin can send message with Title + Body | ✓      | Already implemented         |
| Target all users (3.1)                   | ✓      | `ALL_USERS` mode            |
| Target all managers only (3.2)           | ✓      | `ALL_MANAGERS` mode         |
| Target all parents only (3.3)            | ✓      | `ALL_PARENTS` mode          |
| Target by governorate (3.4)              | ✓      | `GOVERNORATE` mode          |
| Target by kindergartens (3.5)            | ✓      | `KINDERGARTENS` mode        |
| Filter by Governorate                    | ✓      | Multi-select UI             |
| Filter by Kindergarten                   | ✓      | Multi-select with search    |
| Search by name/email/phone               | ✓      | Combined search filter      |
| Show recipient count preview             | ✗      | Needs UI implementation     |
| Recipients see in inbox                  | ✓      | Uses MessageRecipient table |
| No cross-scope leakage                   | ✓      | RBAC enforced               |
| Tests pass                               | ✗      | Some tests need updating    |

---

## Files to Modify

1. **`admin_endpoints.py`** - Enhance recipient resolution, add preview endpoint
2. **`templates/communication/modals/new_message.html`** - Add admin targeting UI
3. **`tests/test_admin_messaging.py`** - Add/fix tests

## Estimated Effort

- Backend enhancement: 2-3 hours
- Frontend UI: 3-4 hours
- Testing: 1-2 hours
- **Total: 6-9 hours**

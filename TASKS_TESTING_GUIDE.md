# 📝 Task Management Feature - Manual Testing Guide

## 🚀 Server Status

**Server is running!** ✅
- **URL**: http://127.0.0.1:8000
- **API Docs**: http://127.0.0.1:8000/docs
- **Tasks Page**: http://127.0.0.1:8000/tasks
- **Health Check**: http://127.0.0.1:8000/health

---

## 👥 Test User Credentials

Use these existing credentials from QUICKSTART_TESTING.md:

| Role           | Username              | Password         | Kindergarten         |
| -------------- | --------------------- | ---------------- | -------------------- |
| **Admin**      | `admin`               | `Admin123!`      | All (System-wide)    |
| **Manager**    | `manager1`            | `Manager123!`    | Al Amal Kindergarten |
| **Supervisor** | `supervisor1`         | `Supervisor123!` | Al Amal Kindergarten |
| **Parent**     | `parent1@example.com` | `Parent123!`     | -                    |

---

## 🎯 Testing Workflows

### Workflow 1: Login and Access Tasks (All Users)

1. Open browser to http://127.0.0.1:8000
2. Login with any user above
3. Click **"المهام" (Tasks)** in the sidebar navigation
4. You should see the Tasks page with:
   - Status tabs (All, Pending, In Progress, Completed)
   - Filter options (Priority, Assigned to me, Created by me)
   - Empty task list (initially)
   - "مهمة جديدة" (New Task) button

### Workflow 2: Create a Task via API (Using API Docs)

1. Open http://127.0.0.1:8000/docs
2. Click **"Authorize"** button (top right)
3. Enter credentials: `admin` / `Admin123!`
4. Click **"Authorize"**
5. Find **POST /tasks** endpoint
6. Click **"Try it out"**
7. Enter JSON body:
```json
{
  "title": "Review monthly KPI reports",
  "description": "Analyze attendance rates and governance scores",
  "priority": "high",
  "due_date": "2026-01-20T15:00:00"
}
```
8. Click **"Execute"**
9. Verify response shows `201 Created` with task details

### Workflow 3: View Tasks on Frontend

1. Go to http://127.0.0.1:8000/tasks
2. Refresh the page
3. You should see your created task displayed as a card
4. Verify the card shows:
   - Task title
   - Description
   - Priority badge (High/عالية)
   - Status badge (Pending/قيد الانتظار)
   - Due date
   - Action buttons (Complete, Edit, Delete)

### Workflow 4: Create Task via Frontend

1. On http://127.0.0.1:8000/tasks
2. Click **"مهمة جديدة" (New Task)** button
3. Fill in the modal form:
   - **العنوان (Title)**: "Prepare weekly activity plan"
   - **الوصف (Description)**: "Plan educational activities for next week"
   - **الأولوية (Priority)**: Medium
   - **تاريخ الاستحقاق (Due Date)**: Pick a future date
4. Click **"حفظ" (Save)**
5. Task should appear in the list

### Workflow 5: Toggle Task Status

1. Find a pending task in the list
2. Click the **"إكمال" (Complete)** button
3. Task should:
   - Move to "Completed" tab
   - Show green success badge
   - Display with strikethrough title
   - Button changes to "إعادة فتح" (Reopen)
4. Click **"إعادة فتح"** to toggle back to pending

### Workflow 6: Edit a Task

1. Click the **Edit (pencil icon)** button on any task
2. Modal opens with task details pre-filled
3. Change the title or priority
4. Click **"حفظ"**
5. Verify changes appear in the task card

### Workflow 7: Delete a Task

1. Click the **Delete (trash icon)** button
2. Confirm the deletion
3. Task should be removed from the list (soft delete - marked as CANCELLED)

### Workflow 8: Filter Tasks

**By Status:**
1. Create multiple tasks with different statuses
2. Click status tabs to filter:
   - "الكل" (All)
   - "قيد الانتظار" (Pending)
   - "قيد التنفيذ" (In Progress)
   - "مكتملة" (Completed)

**By Priority:**
1. Use the priority dropdown filter
2. Select "عاجل" (Urgent), "عالية" (High), etc.
3. Click **"تطبيق الفلاتر" (Apply Filters)**

**By Assignment:**
1. Check "المهام المُسندة لي" (Tasks assigned to me)
2. Check "المهام التي أنشأتها" (Tasks I created)
3. Apply filters

---

## 🔌 API Testing (Using Swagger UI)

### 1. Create Task
**Endpoint**: `POST /tasks`
```json
{
  "title": "Complete observation records",
  "description": "Document developmental observations for Class A",
  "priority": "medium",
  "due_date": "2026-01-18T10:00:00",
  "kindergarten_id": 1
}
```

### 2. List All Tasks
**Endpoint**: `GET /tasks`
- No parameters = all tasks
- With filters: `?status_filter=pending&priority_filter=urgent`

### 3. Get Single Task
**Endpoint**: `GET /tasks/{id}`
- Replace `{id}` with actual task ID (e.g., `1`)

### 4. Update Task
**Endpoint**: `PUT /tasks/{id}`
```json
{
  "title": "Updated title",
  "status": "in_progress",
  "priority": "urgent"
}
```

### 5. Toggle Task Status
**Endpoint**: `POST /tasks/{id}/toggle`
- Quick way to mark pending → completed or completed → pending

### 6. Delete Task
**Endpoint**: `DELETE /tasks/{id}`
- Soft delete (marks as CANCELLED)

---

## ✅ Test Scenarios & Expected Results

### Scenario 1: Create Task with All Fields
**Steps:**
1. Create task with title, description, priority, and due date
2. Assign to another user (use `assigned_to_id`)

**Expected:**
- Task created with status "PENDING"
- All fields saved correctly
- Created timestamp set
- Audit log entry created

### Scenario 2: Create Task with Minimal Data
**Steps:**
1. Create task with only a title

**Expected:**
- Task created successfully
- Priority defaults to "MEDIUM"
- Status defaults to "PENDING"

### Scenario 3: Validation Errors
**Test these invalid inputs:**

| Invalid Input | Expected Error |
|---------------|----------------|
| Empty title `""` | 422 Validation Error |
| Title > 255 chars | 422 Validation Error |
| Invalid priority `"super_high"` | 400 Bad Request |
| Invalid status `"maybe"` | 400 Bad Request |

### Scenario 4: Permission Checks
**Steps:**
1. Login as `supervisor1`
2. Create a task
3. Login as different user (e.g., `supervisor2`)
4. Try to edit/delete the first supervisor's task

**Expected:**
- Only creator or admin can edit
- Only creator or admin can delete
- Assignee can toggle status

### Scenario 5: Filter by Assignment
**Steps:**
1. Create 3 tasks:
   - Task A: Created by admin, assigned to manager1
   - Task B: Created by admin, assigned to admin
   - Task C: Created by manager1, assigned to manager1
2. Filter with `assigned_to_me=true` as admin

**Expected:**
- Only Task B returned

### Scenario 6: Kindergarten Scope
**Steps:**
1. Login as `manager1` (kindergarten_id = 1)
2. Create task with `kindergarten_id=1`
3. Try to create task with `kindergarten_id=2`

**Expected:**
- First task succeeds
- Second task fails (permission error)

### Scenario 7: Overdue Tasks
**Steps:**
1. Create task with `due_date` in the past
2. View task list

**Expected:**
- Task appears with past due date
- Can visually identify as overdue

### Scenario 8: Complete Task
**Steps:**
1. Create task with status "PENDING"
2. Update status to "COMPLETED"

**Expected:**
- `completed_at` timestamp is automatically set
- Status changes to "COMPLETED"

### Scenario 9: Reopen Completed Task
**Steps:**
1. Mark task as completed
2. Change status back to "PENDING"

**Expected:**
- `completed_at` is cleared (set to null)
- Status changes to "PENDING"

---

## 📊 Sample Test Data (via API)

Use these payloads to quickly create varied test data:

### High Priority Urgent Task
```json
{
  "title": "URGENT: Update emergency contact information",
  "description": "Verify and update emergency contacts for all enrolled children",
  "priority": "urgent",
  "due_date": "2026-01-15T09:00:00"
}
```

### Manager Task for Kindergarten
```json
{
  "title": "Review pending enrollment applications",
  "description": "Process 5 pending enrollment applications for next semester",
  "priority": "high",
  "kindergarten_id": 1,
  "due_date": "2026-01-16T14:00:00"
}
```

### Supervisor Daily Task
```json
{
  "title": "Create daily reports for this week",
  "description": "Complete and submit all daily reports for supervisor review",
  "priority": "high",
  "due_date": "2026-01-15T16:00:00"
}
```

### Low Priority Planning Task
```json
{
  "title": "Organize field trip to science museum",
  "description": "Coordinate transportation, permissions, and supervision for field trip",
  "priority": "low",
  "due_date": "2026-02-01T10:00:00"
}
```

### In Progress Task
```json
{
  "title": "Prepare monthly newsletter",
  "description": "Create newsletter with updates, events, and announcements",
  "priority": "medium",
  "status": "in_progress",
  "due_date": "2026-01-25T12:00:00"
}
```

---

## 🐛 Known Issues & Limitations

1. **Frontend Authentication**: Tasks page requires authentication via API first
   - Use http://127.0.0.1:8000/docs to login and get token
   - Token stored in localStorage for frontend use

2. **User Assignment UI**: Currently requires entering user ID manually
   - Future enhancement: Add user dropdown selector

3. **RTL Support**: Arabic interface is right-to-left
   - May need browser that supports RTL well (Chrome recommended)

---

## 🔍 Debugging Tips

### Check Database Directly
```bash
sqlite3 kinjo_dev.db
```
```sql
-- View all tasks
SELECT * FROM tasks;

-- Count tasks by status
SELECT status, COUNT(*) FROM tasks GROUP BY status;

-- View recent tasks
SELECT id, title, status, priority, created_at
FROM tasks
ORDER BY created_at DESC
LIMIT 10;
```

### Check Server Logs
- Server output shows all API requests
- Look for SQL queries to verify database operations
- Check for validation errors in response

### Clear Test Data
```sql
-- Delete all tasks
DELETE FROM tasks;

-- Reset auto-increment
DELETE FROM sqlite_sequence WHERE name='tasks';
```

---

## 📱 Browser Testing

**Recommended Browsers:**
- Chrome/Edge (Best RTL support)
- Firefox
- Safari (macOS)

**Test Responsive Design:**
1. Desktop view (1920x1080)
2. Tablet view (768x1024)
3. Mobile view (375x667)

---

## ✨ Feature Highlights to Test

1. **Real-time Updates**: Toggle task status without page refresh
2. **Filtering**: Multiple filter combinations
3. **Badges**: Color-coded priority and status badges
4. **Validation**: Client-side and server-side validation
5. **Permissions**: Role-based access control
6. **Audit Trail**: All operations logged (check audit_logs table)
7. **Responsive Design**: Mobile-friendly interface
8. **RTL Support**: Arabic right-to-left layout

---

## 🎉 Success Criteria

Your testing is successful if you can:

- ✅ Create tasks via both API and frontend
- ✅ View tasks in a card-based layout
- ✅ Filter tasks by status, priority, and assignment
- ✅ Toggle task status (pending ↔ completed)
- ✅ Edit and update task details
- ✅ Delete tasks (soft delete)
- ✅ See proper validation errors for invalid inputs
- ✅ Verify permission checks work correctly
- ✅ Confirm tasks are scoped to kindergartens where applicable
- ✅ Check audit logs are created for all operations

---

## 📞 Support

If you encounter issues:
1. Check server logs in the console
2. Verify database migration is complete: `alembic current`
3. Check API documentation: http://127.0.0.1:8000/docs
4. Review error messages in browser console (F12)

---

**Happy Testing!** 🚀

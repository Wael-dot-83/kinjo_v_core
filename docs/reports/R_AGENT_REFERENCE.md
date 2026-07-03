# R_AGENT_REFERENCE

> **Master Reference for AI Agent Fine-Tuning — Full-Stack Development**
> Version: 1.1.0 | Last Updated: 2026-04-19 | Reviewed by: Lead Full-Stack Architect

---

## Table of Contents

1. [Code Philosophy & Ethics](#1-code-philosophy--ethics)
2. [Language & Framework Conventions](#2-language--framework-conventions)
3. [File & Project Structure Rules](#3-file--project-structure-rules)
4. [Naming & Commenting Standards](#4-naming--commenting-standards)
5. [Error Handling & Logging](#5-error-handling--logging)
6. [Security & Compliance](#6-security--compliance)
7. [Testing Requirements](#7-testing-requirements)
8. [API Design Standards](#8-api-design-standards)
9. [Database & Schema Guidelines](#9-database--schema-guidelines)
10. [Performance & Scalability](#10-performance--scalability)
11. [Documentation & Examples](#11-documentation--examples)
12. [Fine-Tuning Instructions for AI Agents](#12-fine-tuning-instructions-for-ai-agents)
13. [Observability & Monitoring](#13-observability--monitoring)
14. [CI/CD Pipeline Standards](#14-cicd-pipeline-standards)
15. [Background Jobs & Task Queues](#15-background-jobs--task-queues)
16. [Quick Reference Table](#quick-reference-table)
17. [Self-Correction Protocol](#self-correction-protocol)

---

## 1. Code Philosophy & Ethics

### 1.1 Core Principles

- Write code for humans first, machines second.
- Favor readability over cleverness.
- Every line must have a reason to exist. Remove dead code.
- Prefer composition over inheritance.
- Follow the principle of least surprise: code must behave as its name and signature imply.
- Treat warnings as errors. A clean build has zero warnings.
- Never commit secrets, tokens, or credentials into source control.

### 1.2 Do / Avoid / Why

✅ **Do this:**

```typescript
// Single responsibility: one function, one job
function calculateTax(amount: number, rate: number): number {
  return amount * rate;
}

function formatCurrency(value: number, locale: string = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
  }).format(value);
}
```

❌ **Avoid this:**

```typescript
// God function: calculates, formats, logs, and sends email
function processOrder(order) {
  let tax = order.amount * 0.08;
  let total = order.amount + tax;
  console.log("Total: $" + total);
  sendEmail(order.email, "Your total is $" + total);
  db.save({ ...order, total });
  return total;
}
```

**Why it matters:** Single-responsibility functions are testable, reusable, and debuggable in isolation.

### 1.3 Ethical Guardrails

- Never generate code that intentionally bypasses security controls.
- Never produce code that discriminates based on protected characteristics.
- Flag any user request that implies data exfiltration, unauthorized access, or destructive operations.
- Respect software licenses. Do not reproduce copyrighted code verbatim.

---

## 2. Language & Framework Conventions

### 2.1 TypeScript vs JavaScript

**Rule: Default to TypeScript for all new projects. Use JavaScript only when the project explicitly requires it.**

| Aspect             | TypeScript                                | JavaScript                                     |
| ------------------ | ----------------------------------------- | ---------------------------------------------- |
| Type Safety        | Strict mode enabled (`"strict": true`)    | Use JSDoc annotations if TS is unavailable     |
| Null Handling      | Enable `strictNullChecks`                 | Always check for `null`/`undefined` explicitly |
| Module System      | ES Modules (`import`/`export`)            | ES Modules preferred; CommonJS only for legacy |
| Compilation Target | ES2020+ unless supporting legacy browsers | N/A                                            |

✅ **Do this:**

```typescript
// Explicit types, strict null checks, readonly where applicable
interface User {
  readonly id: string;
  name: string;
  email: string;
  role: "admin" | "user" | "viewer";
  createdAt: Date;
}

function getUserById(id: string): Promise<User | null> {
  // Implementation
}
```

❌ **Avoid this:**

```javascript
// No types, `any` everywhere, no null safety
function getUserById(id) {
  return db.query("SELECT * FROM users WHERE id = " + id); // SQL injection risk
}
```

**Why it matters:** TypeScript catches entire categories of bugs at compile time that would otherwise surface in production.

### 2.2 Async Patterns

**Rule: Use `async`/`await` as the default. Use raw Promises only when concurrent execution is required.**

✅ **Do this:**

```typescript
// Sequential: async/await
async function fetchUserWithPosts(userId: string): Promise<UserWithPosts> {
  const user = await userRepository.findById(userId);
  if (!user) throw new NotFoundError(`User ${userId} not found`);
  const posts = await postRepository.findByUserId(userId);
  return { ...user, posts };
}

// Concurrent: Promise.all for independent operations
async function fetchDashboardData(userId: string): Promise<DashboardData> {
  const [user, notifications, analytics] = await Promise.all([
    userService.getUser(userId),
    notificationService.getUnread(userId),
    analyticsService.getSummary(userId),
  ]);
  return { user, notifications, analytics };
}
```

❌ **Avoid this:**

```typescript
// Callback hell
function fetchUserWithPosts(userId, callback) {
  db.getUser(userId, (err, user) => {
    if (err) return callback(err);
    db.getPosts(userId, (err2, posts) => {
      if (err2) return callback(err2);
      callback(null, { ...user, posts });
    });
  });
}

// Unhandled promise
async function riskyFetch() {
  fetch("/api/data"); // No await, no .catch — silent failure
}
```

**Why it matters:** `async`/`await` produces linear, readable control flow and makes error handling explicit through `try`/`catch`.

#### Promise.all vs Promise.allSettled

```typescript
// Promise.all — fails fast if ANY promise rejects. Use when all results are required.
const [user, plan] = await Promise.all([
  userService.getUser(userId),
  billingService.getPlan(userId),
]);

// Promise.allSettled — waits for ALL, collects both successes and failures.
// Use when partial results are acceptable (e.g., enriching data from optional sources).
const results = await Promise.allSettled([
  analyticsService.getStats(userId),
  notificationService.getUnread(userId),
  badgeService.getEarned(userId),
]);

const stats = results[0].status === "fulfilled" ? results[0].value : null;
const unread = results[1].status === "fulfilled" ? results[1].value : [];
```

**Rule: Never use `Promise.all` when a failing sub-operation should not abort the entire request.
Never use `Promise.allSettled` when all results are mandatory — the caller won't get a failure signal.**

### 2.3 Frontend Frameworks

#### React

- Use functional components with hooks exclusively. No class components in new code.
- Colocate state with the component that owns it. Lift state only when necessary.
- Use React Server Components for data-fetching pages when using Next.js 13+.

#### Vue

- Use Composition API (`<script setup>`) for all new components.
- Use Pinia for state management. Vuex is legacy.

#### Angular

- Follow Angular CLI conventions strictly.
- Use standalone components (Angular 14+).
- Use signals for reactive state (Angular 16+).

### 2.4 Backend Frameworks

#### Node.js / Express / Fastify

- Use Fastify for new projects (schema validation, performance).
- Use Express only for existing projects or ecosystem compatibility.

#### Python / FastAPI / Django

- Use FastAPI for new API services (type hints, async, auto-docs).
- Use Django for full-stack applications requiring admin, ORM, and templating.
- Use Pydantic models for all request/response validation.

```python
# FastAPI with Pydantic
from pydantic import BaseModel, Field, EmailStr
from fastapi import FastAPI, HTTPException, status

class CreateUserRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    role: str = Field(default="user", pattern=r"^(admin|user|viewer)$")

app = FastAPI()

@app.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(request: CreateUserRequest) -> dict:
    # Validated automatically by Pydantic
    user = await user_service.create(request)
    return {"id": user.id, "name": user.name}
```

#### Go

- Follow the standard project layout.
- Use `context.Context` for cancellation and timeouts on all service boundaries.
- Prefer the standard library; add dependencies only when justified.

#### Rust

- Use `Result<T, E>` for all fallible operations. Never `unwrap()` in production code.
- Use `thiserror` for library errors, `anyhow` for application errors.
- Follow the Rust API Guidelines for public interfaces.

---

## 3. File & Project Structure Rules

### 3.1 General Principles

- Group by feature, not by file type (except shared utilities).
- Every directory must have a clear, single purpose.
- Limit file length to 300 lines. Extract when exceeding.
- Limit function length to 40 lines.
- No circular imports.

### 3.2 Backend Project Structure (Python / FastAPI)

```
project/
├── alembic/                    # Database migrations
│   └── versions/
├── api/                        # Route handlers grouped by domain
│   ├── __init__.py
│   ├── users.py
│   ├── auth.py
│   └── reports.py
├── core/                       # Cross-cutting: config, security, deps
│   ├── config.py
│   ├── security.py
│   └── dependencies.py
├── models/                     # SQLAlchemy / ORM models
│   ├── __init__.py
│   ├── user.py
│   └── report.py
├── schemas/                    # Pydantic request/response models
│   ├── user.py
│   └── report.py
├── services/                   # Business logic
│   ├── user_service.py
│   └── report_service.py
├── repositories/               # Data access layer
│   ├── user_repository.py
│   └── report_repository.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── main.py
├── requirements.txt
└── pyproject.toml
```

### 3.3 Backend Project Structure (Node.js / TypeScript)

```
project/
├── src/
│   ├── modules/
│   │   ├── users/
│   │   │   ├── users.controller.ts
│   │   │   ├── users.service.ts
│   │   │   ├── users.repository.ts
│   │   │   ├── users.schema.ts
│   │   │   ├── users.types.ts
│   │   │   └── __tests__/
│   │   └── auth/
│   ├── common/
│   │   ├── middleware/
│   │   ├── guards/
│   │   ├── filters/
│   │   └── utils/
│   ├── config/
│   │   ├── index.ts
│   │   └── validation.ts
│   └── main.ts
├── tests/
│   ├── integration/
│   └── e2e/
├── package.json
└── tsconfig.json
```

### 3.4 Frontend Project Structure (React / TypeScript)

```
src/
├── features/
│   ├── auth/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── types.ts
│   │   └── index.ts              # Public API barrel
│   └── dashboard/
├── shared/
│   ├── components/
│   ├── hooks/
│   ├── utils/
│   └── types/
├── layouts/
├── pages/                        # Route-level components
├── App.tsx
└── main.tsx
```

✅ **Do this:**

```
src/features/auth/components/LoginForm.tsx
src/features/auth/hooks/useAuth.ts
src/features/auth/services/authApi.ts
```

❌ **Avoid this:**

```
src/components/LoginForm.tsx
src/components/Dashboard.tsx
src/components/UserProfile.tsx
src/components/Report.tsx
# 200 files in one folder with no domain grouping
```

**Why it matters:** Feature-based grouping enables teams to work on isolated domains without merge conflicts and makes code navigation intuitive.

---

## 4. Naming & Commenting Standards

### 4.1 Naming Conventions

| Element                      | Convention                                 | Example                                 |
| ---------------------------- | ------------------------------------------ | --------------------------------------- |
| Variables / Functions        | camelCase                                  | `getUserById`, `isActive`               |
| Classes / Interfaces / Types | PascalCase                                 | `UserService`, `CreateUserRequest`      |
| Constants                    | UPPER_SNAKE_CASE                           | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT_MS` |
| Files (TS/JS)                | kebab-case or dot-notation                 | `user.service.ts`, `auth-guard.ts`      |
| Files (Python)               | snake_case                                 | `user_service.py`, `auth_guard.py`      |
| Database Tables              | snake_case, plural                         | `users`, `enrollment_records`           |
| Database Columns             | snake_case                                 | `created_at`, `first_name`              |
| Environment Variables        | UPPER_SNAKE_CASE                           | `DATABASE_URL`, `JWT_SECRET`            |
| CSS Classes                  | kebab-case or BEM                          | `btn-primary`, `card__header--active`   |
| REST Endpoints               | kebab-case, plural nouns                   | `/api/v1/user-profiles`                 |
| Boolean Variables            | Prefixed with `is`, `has`, `can`, `should` | `isActive`, `hasPermission`             |

### 4.2 Naming Anti-Patterns

❌ **Avoid these names:**

```typescript
// Too vague
const data = fetchData();
const result = process(data);
const temp = calculate();

// Abbreviated beyond recognition
const usrMgr = new UserManager();
const cnt = getCount();
const cb = () => {};

// Misleading
const userList: Map<string, User> = new Map(); // Not a list
const isNotDisabled = true; // Double negative
```

✅ **Use descriptive, intention-revealing names:**

```typescript
const activeUsers = await userRepository.findActive();
const enrollmentCount =
  await enrollmentService.countByKindergarten(kindergartenId);
const handleSubmit = (formData: CreateUserRequest) => {
  /* ... */
};
```

**Why it matters:** Code is read 10x more than it is written. Clear names eliminate the need for comments explaining what something is.

### 4.3 Commenting Standards

**Rule: Code should be self-documenting. Comments explain WHY, not WHAT.**

✅ **Do this:**

```typescript
// Business rule: children under 3 require a 1:4 staff ratio (MOE regulation §4.2)
const TODDLER_STAFF_RATIO = 4;

/**
 * Calculates the minimum required staff for a given class.
 * Uses age-based ratios mandated by the Ministry of Education.
 */
function calculateMinimumStaff(childCount: number, ageGroup: AgeGroup): number {
  const ratio = STAFF_RATIOS[ageGroup];
  return Math.ceil(childCount / ratio);
}
```

❌ **Avoid this:**

```typescript
// Get user
function getUser(id) { ... }

// Increment counter by 1
counter += 1;

// TODO: fix this later
// HACK: don't touch this
// This is a workaround for a bug in the library
```

**Why it matters:** Redundant comments rot faster than the code they describe, creating dangerous misinformation.

### 4.4 JSDoc / Docstring Requirements

- All public functions and methods must have JSDoc (TS/JS) or docstrings (Python).
- Include: purpose, parameters, return type, exceptions thrown.
- Omit for trivial getters/setters and private helper functions.

```typescript
/**
 * Enrolls a child in a kindergarten class.
 *
 * @param childId - Unique identifier of the child
 * @param classId - Target class identifier
 * @param startDate - Enrollment start date (must be a future date)
 * @returns The created enrollment record
 * @throws {ConflictError} If the child is already enrolled in another class
 * @throws {CapacityError} If the class has reached maximum capacity
 */
async function enrollChild(
  childId: string,
  classId: string,
  startDate: Date,
): Promise<EnrollmentRecord> {
  // ...
}
```

```python
async def enroll_child(child_id: str, class_id: str, start_date: date) -> EnrollmentRecord:
    """Enroll a child in a kindergarten class.

    Args:
        child_id: Unique identifier of the child.
        class_id: Target class identifier.
        start_date: Enrollment start date. Must be a future date.

    Returns:
        The created enrollment record.

    Raises:
        ConflictError: If the child is already enrolled in another class.
        CapacityError: If the class has reached maximum capacity.
    """
```

---

## 5. Error Handling & Logging

### 5.1 Error Handling Principles

- Fail fast at system boundaries (API input, file I/O, external services).
- Use typed/custom error classes. Never throw raw strings.
- Catch errors at the appropriate level — not too early, not too late.
- Never swallow errors silently.
- Distinguish between operational errors (expected, recoverable) and programmer errors (bugs).

### 5.2 Custom Error Hierarchy

```typescript
// Base application error
abstract class AppError extends Error {
  abstract readonly statusCode: number;
  abstract readonly isOperational: boolean;

  constructor(
    message: string,
    public readonly context?: Record<string, unknown>,
  ) {
    super(message);
    this.name = this.constructor.name;
    Error.captureStackTrace(this, this.constructor);
  }
}

class NotFoundError extends AppError {
  readonly statusCode = 404;
  readonly isOperational = true;
}

class ValidationError extends AppError {
  readonly statusCode = 400;
  readonly isOperational = true;

  constructor(
    message: string,
    public readonly fields: Record<string, string>,
  ) {
    super(message, { fields });
  }
}

class InternalError extends AppError {
  readonly statusCode = 500;
  readonly isOperational = false;
}
```

```python
class AppError(Exception):
    """Base application error."""
    def __init__(self, message: str, status_code: int = 500, context: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.context = context or {}
        super().__init__(self.message)

class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} with id '{identifier}' not found",
            status_code=404,
            context={"resource": resource, "identifier": identifier},
        )

class ValidationError(AppError):
    def __init__(self, message: str, fields: dict[str, str]):
        super().__init__(message=message, status_code=400, context={"fields": fields})
```

### 5.3 Error Boundaries and Retries

✅ **Do this:**

```typescript
// Centralized error handler middleware (Express/Fastify)
function errorHandler(
  err: Error,
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  if (err instanceof AppError && err.isOperational) {
    logger.warn({ err, requestId: req.id }, err.message);
    res.status(err.statusCode).json({
      error: { code: err.name, message: err.message, context: err.context },
    });
    return;
  }
  // Programmer error — log full stack, return generic message
  logger.error({ err, requestId: req.id }, "Unhandled error");
  res.status(500).json({
    error: { code: "INTERNAL_ERROR", message: "An unexpected error occurred" },
  });
}

// Retry with exponential backoff for transient failures
async function withRetry<T>(
  fn: () => Promise<T>,
  options: {
    maxAttempts?: number;
    baseDelayMs?: number;
    retryableErrors?: string[];
  } = {},
): Promise<T> {
  const { maxAttempts = 3, baseDelayMs = 200, retryableErrors = [] } = options;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      const isRetryable =
        retryableErrors.length === 0 ||
        retryableErrors.includes((error as Error).name);
      if (attempt === maxAttempts || !isRetryable) throw error;

      const delay =
        baseDelayMs * Math.pow(2, attempt - 1) + Math.random() * 100;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  throw new Error("Unreachable");
}
```

#### Global Unhandled Rejection Handler

Register these in your application entrypoint (`main.ts` / `server.ts`). Unhandled promise rejections silently kill Node.js processes.

```typescript
// main.ts — register before anything else
process.on("unhandledRejection", (reason: unknown, promise: Promise<unknown>) => {
  logger.error({ reason, promise }, "Unhandled promise rejection — shutting down");
  // Give logger time to flush, then exit so the process manager restarts cleanly
  process.exit(1);
});

process.on("uncaughtException", (error: Error) => {
  logger.error({ err: error }, "Uncaught exception — shutting down");
  process.exit(1);
});
```

```python
# FastAPI lifespan — catch and log unexpected startup/shutdown errors
import asyncio, logging

def handle_exception(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    msg = context.get("exception", context["message"])
    logging.critical("Unhandled async exception: %s", msg, exc_info=context.get("exception"))

loop = asyncio.get_event_loop()
loop.set_exception_handler(handle_exception)
```

❌ **Avoid this:**

```typescript
// Swallowing errors
try {
  await sendNotification(userId);
} catch (e) {
  // ignore
}

// Catching too broadly
try {
  const user = await getUser(id);
  const posts = await getPosts(user.id);
  const analytics = await getAnalytics(user.id);
  await sendReport(user, posts, analytics);
} catch (e) {
  console.log("Something went wrong"); // Which operation failed? Unknown.
}
```

**Why it matters:** Silent failures are the most expensive bugs in production — they corrupt data and erode trust without any alert.

### 5.4 Logging Standards

**Rule: Use structured logging. Never use `console.log` in production code.**

```typescript
import pino from "pino";

const logger = pino({
  level: process.env.LOG_LEVEL || "info",
  formatters: {
    level: (label) => ({ level: label }),
  },
  redact: ["req.headers.authorization", "body.password", "body.ssn"],
});

// Contextual logging
logger.info({ userId, action: "login", ip: req.ip }, "User logged in");
logger.warn({ userId, attemptCount }, "Rate limit approaching threshold");
logger.error({ err, requestId, userId }, "Failed to process payment");
```

```python
import structlog

logger = structlog.get_logger()

# Contextual logging
logger.info("user_logged_in", user_id=user_id, ip=request.client.host)
logger.warning("rate_limit_approaching", user_id=user_id, attempt_count=count)
logger.error("payment_failed", user_id=user_id, error=str(err), request_id=request_id)
```

| Log Level | Usage                                                     |
| --------- | --------------------------------------------------------- |
| `error`   | Unrecoverable failures requiring immediate attention      |
| `warn`    | Degraded behavior, approaching limits, recoverable issues |
| `info`    | Significant business events (login, enrollment, payment)  |
| `debug`   | Diagnostic detail for development and troubleshooting     |
| `trace`   | Fine-grained execution flow (disabled in production)      |

**Rules:**

- Never log passwords, tokens, PII, or secrets.
- Always include a correlation/request ID.
- Log at function boundaries, not inside tight loops.
- Use `redact` configuration to mask sensitive fields automatically.

---

## 6. Security & Compliance

### 6.1 OWASP Top 10 Mitigations

| OWASP Risk                     | Mitigation                                                                    |
| ------------------------------ | ----------------------------------------------------------------------------- |
| A01: Broken Access Control     | Enforce RBAC/ABAC at middleware level. Default deny.                          |
| A02: Cryptographic Failures    | Use bcrypt/argon2 for passwords. TLS 1.2+ everywhere.                         |
| A03: Injection                 | Parameterized queries only. Never concatenate user input into queries.        |
| A04: Insecure Design           | Threat model before implementation. Validate at every boundary.               |
| A05: Security Misconfiguration | Harden defaults. Disable debug in production. Remove default credentials.     |
| A06: Vulnerable Components     | Automated dependency scanning (Dependabot, Snyk). Pin versions.               |
| A07: Auth Failures             | MFA support. Account lockout. Secure session management.                      |
| A08: Data Integrity Failures   | Verify signatures. Use SRI for CDN assets. Validate CI/CD pipeline integrity. |
| A09: Logging Failures          | Structured logging. Audit trail for auth events. Tamper-proof log storage.    |
| A10: SSRF                      | Allowlist external URLs. Deny internal network access from user input.        |

### 6.2 Input Validation & Sanitization

**Rule: Validate all input at system boundaries. Reject invalid input; do not attempt to fix it.**

✅ **Do this:**

```typescript
import { z } from "zod";

const CreateUserSchema = z.object({
  name: z.string().trim().min(1).max(100),
  email: z.string().email().toLowerCase(),
  password: z
    .string()
    .min(12)
    .max(128)
    .regex(
      /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])/,
      "Password must contain uppercase, lowercase, digit, and special character",
    ),
  role: z.enum(["admin", "user", "viewer"]).default("user"),
});

// In route handler
app.post("/users", async (req, res) => {
  const parsed = CreateUserSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ errors: parsed.error.flatten().fieldErrors });
  }
  const user = await userService.create(parsed.data);
  res.status(201).json(user);
});
```

```python
from pydantic import BaseModel, Field, EmailStr, field_validator
import re

class CreateUserRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    role: str = Field(default="user", pattern=r"^(admin|user|viewer)$")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v
```

❌ **Avoid this:**

```typescript
app.post("/users", async (req, res) => {
  // No validation — trusting client input directly
  const user = await db.users.create({
    name: req.body.name,
    email: req.body.email,
    password: req.body.password, // Plain text!
    role: req.body.role, // Privilege escalation vulnerability
  });
  res.json(user);
});
```

**Why it matters:** Unvalidated input is the root cause of injection attacks, data corruption, and privilege escalation.

### 6.3 Authentication & Authorization

```typescript
// JWT with refresh token rotation
interface TokenPayload {
  sub: string; // User ID
  role: string; // User role
  iat: number; // Issued at
  exp: number; // Expiration
  jti: string; // Unique token ID (for revocation)
}

// Access token: short-lived (15 minutes)
function generateAccessToken(user: User): string {
  return jwt.sign(
    { sub: user.id, role: user.role, jti: crypto.randomUUID() },
    process.env.JWT_ACCESS_SECRET!,
    { expiresIn: "15m", algorithm: "HS256" },
  );
}

// Refresh token: longer-lived (7 days), stored hashed in DB
function generateRefreshToken(user: User): string {
  return jwt.sign(
    { sub: user.id, jti: crypto.randomUUID() },
    process.env.JWT_REFRESH_SECRET!,
    { expiresIn: "7d", algorithm: "HS256" },
  );
}

// Role-based access control middleware
function requireRole(...allowedRoles: string[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!req.user || !allowedRoles.includes(req.user.role)) {
      throw new ForbiddenError("Insufficient permissions");
    }
    next();
  };
}

// Usage
app.delete("/users/:id", authenticate, requireRole("admin"), deleteUser);
```

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = verify_jwt(credentials.credentials)
    user = await user_repository.find_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user

def require_role(*roles: str):
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return current_user
    return dependency

# Usage
@app.delete("/users/{user_id}")
async def delete_user(user_id: str, user: User = Depends(require_role("admin"))):
    await user_service.delete(user_id)
    return {"status": "deleted"}
```

### 6.4 Environment Variables & Config Management

✅ **Do this:**

```typescript
// config/index.ts — validated at startup, fail fast if missing
import { z } from "zod";

const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "staging", "production"]),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  DATABASE_URL: z.string().url(),
  REDIS_URL: z.string().url(),
  JWT_ACCESS_SECRET: z.string().min(32),
  JWT_REFRESH_SECRET: z.string().min(32),
  CORS_ORIGINS: z.string().transform((s) => s.split(",")),
  LOG_LEVEL: z
    .enum(["error", "warn", "info", "debug", "trace"])
    .default("info"),
});

export const config = EnvSchema.parse(process.env);
```

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    environment: str = "development"
    port: int = 8000
    database_url: str
    redis_url: str
    jwt_secret: str
    cors_origins: list[str] = ["http://localhost:3000"]
    log_level: str = "info"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

❌ **Avoid this:**

```typescript
// Scattered, unvalidated, could be undefined at runtime
const dbUrl = process.env.DATABASE_URL; // Might be undefined
const port = process.env.PORT; // String, not number
```

**Why it matters:** Config validation at startup prevents silent runtime failures caused by missing or malformed environment variables.

### 6.5 Secrets Management

- Never hardcode secrets in source code.
- Use `.env` files for local development only. Never commit `.env` files.
- Use platform-native secret managers in production: AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, HashiCorp Vault.
- Rotate secrets on a defined schedule.
- Audit secret access.

### 6.6 CSRF Protection

**Rule: Any cookie-based session must be protected against Cross-Site Request Forgery. Stateless Bearer token auth is not vulnerable to CSRF.**

✅ **Do this — Double-Submit Cookie + `SameSite=Strict`:**

```typescript
import csrf from "csurf";
import cookieParser from "cookie-parser";

// Express: double-submit cookie pattern
app.use(cookieParser());
app.use(csrf({ cookie: { httpOnly: true, secure: true, sameSite: "strict" } }));

// Inject CSRF token into every HTML response
app.use((req: Request, res: Response, next: NextFunction) => {
  res.locals.csrfToken = req.csrfToken();
  next();
});

// Client must echo the token in a custom header or body field
// X-CSRF-Token: <value from cookie>
```

```python
# FastAPI with itsdangerous CSRF (for cookie-based sessions)
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException, status

csrf_serializer = URLSafeTimedSerializer(settings.secret_key, salt="csrf")

def generate_csrf_token(session_id: str) -> str:
    return csrf_serializer.dumps(session_id)

def validate_csrf_token(token: str, session_id: str, max_age: int = 3600) -> None:
    try:
        value = csrf_serializer.loads(token, max_age=max_age)
        if value != session_id:
            raise ValueError("Session mismatch")
    except Exception:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
```

**SameSite Cookie attribute alone is not sufficient.** Some older browsers do not support it. Always layer `SameSite=Strict` with a CSRF token for defense in depth.

### 6.7 Security Headers

**Rule: Set security headers on every HTTP response. Never rely on framework defaults.**

✅ **Do this (Node.js / Helmet):**

```typescript
import helmet from "helmet";

app.use(
  helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'", "'nonce-{NONCE}'"],   // Use per-request nonces for inline scripts
        styleSrc: ["'self'", "'unsafe-inline'"],     // Prefer nonces over unsafe-inline
        imgSrc: ["'self'", "data:", "https:"],
        connectSrc: ["'self'", "https://api.yourdomain.com"],
        fontSrc: ["'self'", "https://fonts.gstatic.com"],
        objectSrc: ["'none'"],
        upgradeInsecureRequests: [],
      },
    },
    hsts: {
      maxAge: 31_536_000, // 1 year
      includeSubDomains: true,
      preload: true,
    },
    frameguard: { action: "deny" },       // X-Frame-Options: DENY
    noSniff: true,                        // X-Content-Type-Options: nosniff
    xssFilter: true,                      // X-XSS-Protection: 1; mode=block
    referrerPolicy: { policy: "strict-origin-when-cross-origin" },
    permittedCrossDomainPolicies: false,
  }),
);
```

```python
# FastAPI middleware for security headers
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; object-src 'none'; "
            "upgrade-insecure-requests;"
        )
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

### 6.8 Cookie Security Attributes

**Rule: All session and auth cookies must have `HttpOnly`, `Secure`, and `SameSite` attributes set.**

```typescript
// Setting a secure auth cookie
res.cookie("refreshToken", token, {
  httpOnly: true,       // Inaccessible to JavaScript — blocks XSS token theft
  secure: true,         // HTTPS only — never sent over plain HTTP
  sameSite: "strict",   // Not sent on cross-site requests — CSRF mitigation
  maxAge: 7 * 24 * 60 * 60 * 1000, // 7 days in milliseconds
  path: "/api/auth",    // Restrict cookie scope to auth endpoints only
  domain: process.env.COOKIE_DOMAIN, // Never wildcard in production
});
```

```python
from fastapi import Response

def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 3600,
        path="/api/auth",
    )
```

| Attribute | Value | Why |
|-----------|-------|-----|
| `HttpOnly` | `true` | Blocks JS access — prevents XSS-based token theft |
| `Secure` | `true` | HTTPS-only transmission |
| `SameSite` | `Strict` | Blocks cross-origin sends — primary CSRF defense |
| `Path` | Narrow path | Limits exposure to only the routes that need it |
| `Domain` | Explicit | Prevents subdomain leakage |

❌ **Never do this:**

```typescript
res.cookie("session", token); // No attributes — sent over HTTP, readable by JS, CSRF-vulnerable
```

### 6.9 XSS Prevention (Frontend)

**Rule: Never inject untrusted data into the DOM without sanitization. Prefer framework escaping over raw HTML.**

✅ **Do this:**

```tsx
// React escapes content by default — safe
function UserBio({ bio }: { bio: string }) {
  return <p>{bio}</p>; // React auto-escapes — XSS-safe
}

// When rendering HTML from a trusted CMS — sanitize first
import DOMPurify from "dompurify";

function RichContent({ html }: { html: string }) {
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ["p", "b", "i", "em", "strong", "a", "ul", "ol", "li"],
    ALLOWED_ATTR: ["href", "target", "rel"],
    FORCE_BODY: true,
  });
  return <div dangerouslySetInnerHTML={{ __html: clean }} />;
}
```

❌ **Avoid this:**

```tsx
// Unsanitized HTML injection — XSS vulnerability
function UserBio({ bio }: { bio: string }) {
  return <div dangerouslySetInnerHTML={{ __html: bio }} />;
}

// String interpolation into href — XSS via javascript: protocol
function UserLink({ url }: { url: string }) {
  return <a href={url}>Profile</a>; // user could pass href="javascript:alert(1)"
}
```

✅ **Safe href rendering:**

```tsx
function SafeLink({ url, label }: { url: string; label: string }) {
  // Only allow http/https protocols
  const isSafe = /^https?:\/\//.test(url);
  if (!isSafe) return <span>{label}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {label}
    </a>
  );
}
```

**Why it matters:** XSS is the most common web vulnerability. React's default escaping covers most cases, but `dangerouslySetInnerHTML` and dynamic `href`/`src` values require explicit sanitization.

### 6.10 File Upload Security

**Rule: Never trust client-provided MIME types. Validate file content, enforce size limits, and never serve uploads from the same origin as the application.**

```typescript
import multer from "multer";
import { fileTypeFromBuffer } from "file-type";
import path from "path";
import crypto from "crypto";

const ALLOWED_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "application/pdf"]);
const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB

const upload = multer({
  storage: multer.memoryStorage(), // Buffer in memory for validation before writing
  limits: { fileSize: MAX_FILE_SIZE_BYTES },
  fileFilter: (_req, file, cb) => {
    // Reject based on client-provided MIME (first gate — not trusted alone)
    if (!ALLOWED_MIME_TYPES.has(file.mimetype)) {
      return cb(new ValidationError("File type not allowed", { mimetype: file.mimetype }));
    }
    cb(null, true);
  },
});

app.post("/upload", upload.single("file"), async (req, res) => {
  const buffer = req.file!.buffer;

  // Validate actual file signature (magic bytes) — not client header
  const detected = await fileTypeFromBuffer(buffer);
  if (!detected || !ALLOWED_MIME_TYPES.has(detected.mime)) {
    throw new ValidationError("File content does not match declared type");
  }

  // Generate a random, non-guessable filename — prevent path traversal
  const safeExtension = path.extname(req.file!.originalname).toLowerCase().replace(/[^.a-z0-9]/g, "");
  const filename = `${crypto.randomUUID()}${safeExtension}`;

  // Store in isolated object storage (S3, GCS) — never the web root
  const url = await storageService.upload(filename, buffer, detected.mime);

  res.status(201).json({ url });
});
```

```python
from fastapi import UploadFile, HTTPException, status
import magic  # python-magic
import uuid, os

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

@app.post("/upload")
async def upload_file(file: UploadFile, user: User = Depends(get_current_user)):
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    # Validate actual MIME via magic bytes, not Content-Type header
    detected_mime = magic.from_buffer(content, mime=True)
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"File type '{detected_mime}' is not allowed")

    # Randomize filename — prevents path traversal and enumeration
    ext = os.path.splitext(file.filename or "")[1].lower()
    safe_filename = f"{uuid.uuid4()}{ext}"

    url = await storage_service.upload(safe_filename, content, detected_mime)
    return {"url": url}
```

**Key rules:**
- Always validate magic bytes, not `Content-Type` header.
- Randomize stored filenames. Never use client-provided filenames.
- Store uploads in object storage (S3/GCS), never the webserver root.
- Serve uploads from a separate domain/subdomain (e.g., `static.yourdomain.com`) with a strict CSP.
- For sensitive uploads, run async virus scanning (ClamAV, cloud AV) before making files accessible.

---

## 7. Testing Requirements

### 7.1 Testing Pyramid

| Layer             | Coverage Target        | Speed            | Scope                          |
| ----------------- | ---------------------- | ---------------- | ------------------------------ |
| Unit Tests        | 80%+ line coverage     | < 5ms per test   | Single function/class          |
| Integration Tests | Critical paths covered | < 500ms per test | Multiple components, DB, cache |
| E2E Tests         | Critical user journeys | < 30s per test   | Full stack, browser/API        |

### 7.2 Unit Tests

**Rule: Every public function with logic must have unit tests. Pure functions must have 100% branch coverage.**

✅ **Do this:**

```typescript
// user.service.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { UserService } from "./user.service";
import { UserRepository } from "./user.repository";

describe("UserService", () => {
  let service: UserService;
  let repository: vi.Mocked<UserRepository>;

  beforeEach(() => {
    repository = {
      findById: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
    } as any;
    service = new UserService(repository);
  });

  describe("getUserById", () => {
    it("should return user when found", async () => {
      const mockUser = { id: "1", name: "Alice", email: "alice@example.com" };
      repository.findById.mockResolvedValue(mockUser);

      const result = await service.getUserById("1");

      expect(result).toEqual(mockUser);
      expect(repository.findById).toHaveBeenCalledWith("1");
    });

    it("should throw NotFoundError when user does not exist", async () => {
      repository.findById.mockResolvedValue(null);

      await expect(service.getUserById("999")).rejects.toThrow(NotFoundError);
    });
  });
});
```

```python
# test_user_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.user_service import UserService
from errors import NotFoundError

@pytest.fixture
def user_repository():
    return AsyncMock()

@pytest.fixture
def user_service(user_repository):
    return UserService(repository=user_repository)

class TestGetUserById:
    async def test_returns_user_when_found(self, user_service, user_repository):
        expected = {"id": "1", "name": "Alice", "email": "alice@example.com"}
        user_repository.find_by_id.return_value = expected

        result = await user_service.get_user_by_id("1")

        assert result == expected
        user_repository.find_by_id.assert_called_once_with("1")

    async def test_raises_not_found_when_user_missing(self, user_service, user_repository):
        user_repository.find_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await user_service.get_user_by_id("999")
```

❌ **Avoid this:**

```typescript
// Testing implementation details
it("should call repository.findById", async () => {
  await service.getUserById("1");
  expect(repository.findById).toHaveBeenCalledTimes(1); // Tests HOW, not WHAT
});

// No assertion
it("should work", async () => {
  await service.getUserById("1"); // No expect — always passes
});

// Testing trivial code
it("should return name", () => {
  const user = new User("Alice");
  expect(user.name).toBe("Alice"); // Testing a getter — no value
});
```

**Why it matters:** Tests verify behavior contracts. Testing implementation details creates brittle tests that break on valid refactors.

### 7.3 Integration Tests

```typescript
// users.integration.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { createTestApp, TestApp } from "../test-utils";

describe("POST /api/v1/users", () => {
  let app: TestApp;

  beforeAll(async () => {
    app = await createTestApp(); // Spins up app with test DB
  });

  afterAll(async () => {
    await app.teardown();
  });

  it("should create a user and return 201", async () => {
    const response = await app.request
      .post("/api/v1/users")
      .set("Authorization", `Bearer ${app.adminToken}`)
      .send({
        name: "Alice",
        email: "alice@test.com",
        password: "SecureP@ss123!",
      });

    expect(response.status).toBe(201);
    expect(response.body).toMatchObject({
      id: expect.any(String),
      name: "Alice",
      email: "alice@test.com",
    });
    expect(response.body).not.toHaveProperty("password");
  });

  it("should return 400 for invalid email", async () => {
    const response = await app.request
      .post("/api/v1/users")
      .set("Authorization", `Bearer ${app.adminToken}`)
      .send({ name: "Bob", email: "not-an-email", password: "SecureP@ss123!" });

    expect(response.status).toBe(400);
    expect(response.body.errors).toHaveProperty("email");
  });

  it("should return 401 without authentication", async () => {
    const response = await app.request
      .post("/api/v1/users")
      .send({ name: "Eve", email: "eve@test.com", password: "SecureP@ss123!" });

    expect(response.status).toBe(401);
  });
});
```

### 7.4 E2E Tests

```typescript
// login.e2e.test.ts (Playwright)
import { test, expect } from "@playwright/test";

test.describe("Login Flow", () => {
  test("should log in with valid credentials and redirect to dashboard", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("SecureP@ss123!");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page).toHaveURL("/dashboard");
    await expect(page.getByText("Welcome, Admin")).toBeVisible();
  });

  test("should show error for invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("wrongpassword");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByText("Invalid email or password")).toBeVisible();
    await expect(page).toHaveURL("/login");
  });
});
```

### 7.5 Test Naming Convention

Format: `should [expected behavior] when [condition]`

```
✅ should return 404 when user does not exist
✅ should reject enrollment when class is at capacity
✅ should send notification email after successful registration
❌ test1
❌ it works
❌ handles error
```

### 7.6 Test Data Factories

**Rule: Use factories for test data. Never hardcode magic strings. Never share mutable fixtures between tests.**

```typescript
// TypeScript — using @faker-js/faker
import { faker } from "@faker-js/faker";
import type { User, Enrollment } from "../types";

function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: faker.string.uuid(),
    name: faker.person.fullName(),
    email: faker.internet.email().toLowerCase(),
    role: "user",
    isActive: true,
    createdAt: faker.date.past(),
    ...overrides, // Caller controls what matters for the test
  };
}

function buildEnrollment(overrides: Partial<Enrollment> = {}): Enrollment {
  return {
    id: faker.string.uuid(),
    childId: faker.string.uuid(),
    classId: faker.string.uuid(),
    startDate: faker.date.future(),
    status: "active",
    ...overrides,
  };
}

// Usage in tests — each test gets isolated data
it("should reject enrollment when class is at capacity", async () => {
  const fullClass = buildClass({ maxCapacity: 2, enrolledCount: 2 });
  const child = buildUser({ role: "user" });
  await expect(enrollmentService.enroll(child.id, fullClass.id)).rejects.toThrow(CapacityError);
});
```

```python
# Python — using polyfactory or factory_boy
from polyfactory.factories.pydantic_factory import ModelFactory
from schemas.user import UserSchema
from schemas.enrollment import EnrollmentSchema
import faker as Faker

fake = Faker.Faker()

class UserFactory(ModelFactory):
    __model__ = UserSchema

    name = fake.name
    email = fake.email
    role = "user"
    is_active = True

class EnrollmentFactory(ModelFactory):
    __model__ = EnrollmentSchema

# Usage
user = UserFactory.build(role="admin")          # Override specific fields
enrollment = EnrollmentFactory.build(status="pending")
```

**Why it matters:** Hardcoded test data creates invisible coupling between tests. When one test changes a shared fixture, unrelated tests break with no clear reason.

### 7.7 Test Isolation Rules

- Each test must set up and tear down its own data. Never share mutable state between tests.
- Use database transactions that roll back after each integration test.
- Never depend on test execution order.

```typescript
// Integration tests — wrap each in a transaction that rolls back
beforeEach(async () => {
  await db.$executeRaw`BEGIN`;
});

afterEach(async () => {
  await db.$executeRaw`ROLLBACK`;
});
```

```python
# pytest with SQLAlchemy — automatic rollback
@pytest.fixture(autouse=True)
async def auto_rollback(db_session: AsyncSession):
    async with db_session.begin_nested() as savepoint:
        yield db_session
        await savepoint.rollback()
```

---

## 8. API Design Standards

### 8.1 REST API Conventions

| Principle      | Rule                                                                                     |
| -------------- | ---------------------------------------------------------------------------------------- |
| Base URL       | `/api/v{n}/` (e.g., `/api/v1/users`)                                                     |
| Resource Names | Plural nouns, kebab-case (`/user-profiles`, not `/getUserProfile`)                       |
| HTTP Methods   | GET (read), POST (create), PUT (full replace), PATCH (partial update), DELETE (remove)   |
| Status Codes   | Use correct codes: 200, 201, 204, 400, 401, 403, 404, 409, 422, 429, 500                 |
| Pagination     | Cursor-based preferred. Offset-based acceptable. Always include `total`, `next`, `prev`. |
| Filtering      | Query params: `?status=active&role=admin`                                                |
| Sorting        | `?sort=created_at&order=desc`                                                            |
| Versioning     | URL path versioning (`/v1/`, `/v2/`)                                                     |
| Content Type   | `application/json` for request/response bodies                                           |

### 8.2 REST Response Format

✅ **Do this:**

```json
// Success (single resource)
{
  "data": {
    "id": "abc-123",
    "name": "Alice",
    "email": "alice@example.com",
    "createdAt": "2026-04-18T10:30:00Z"
  }
}

// Success (collection with pagination)
{
  "data": [
    { "id": "abc-123", "name": "Alice" },
    { "id": "def-456", "name": "Bob" }
  ],
  "pagination": {
    "total": 42,
    "page": 1,
    "pageSize": 20,
    "totalPages": 3,
    "next": "/api/v1/users?page=2&pageSize=20",
    "prev": null
  }
}

// Error
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": [
      { "field": "email", "message": "Must be a valid email address" },
      { "field": "name", "message": "Must be between 1 and 100 characters" }
    ]
  }
}
```

❌ **Avoid this:**

```json
// Inconsistent structure
{ "success": true, "user": { ... } }
{ "error": true, "msg": "bad request" }

// Leaking internal details
{ "error": "sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: users.email" }
```

**Why it matters:** A consistent response envelope enables clients to build generic error/success handlers, reducing frontend complexity.

### 8.3 GraphQL Standards

```typescript
// Type definitions — strict typing, no generic resolvers
const typeDefs = gql`
  type User {
    id: ID!
    name: String!
    email: String!
    role: UserRole!
    posts(first: Int = 10, after: String): PostConnection!
  }

  enum UserRole {
    ADMIN
    USER
    VIEWER
  }

  type PostConnection {
    edges: [PostEdge!]!
    pageInfo: PageInfo!
  }

  type PostEdge {
    cursor: String!
    node: Post!
  }

  type PageInfo {
    hasNextPage: Boolean!
    endCursor: String
  }

  type Query {
    user(id: ID!): User
    users(first: Int = 20, after: String, filter: UserFilter): UserConnection!
  }

  input UserFilter {
    role: UserRole
    isActive: Boolean
  }

  type Mutation {
    createUser(input: CreateUserInput!): User!
    updateUser(id: ID!, input: UpdateUserInput!): User!
    deleteUser(id: ID!): Boolean!
  }
`;
```

**Rules:**

- Use Relay-style cursor pagination for lists.
- Enforce query depth limits (max 5-7 levels) to prevent abuse.
- Implement query complexity analysis and reject expensive queries.
- Use DataLoader to batch and deduplicate database queries (N+1 prevention).

### 8.4 gRPC Standards

```protobuf
syntax = "proto3";

package user.v1;

service UserService {
  rpc GetUser(GetUserRequest) returns (GetUserResponse);
  rpc ListUsers(ListUsersRequest) returns (ListUsersResponse);
  rpc CreateUser(CreateUserRequest) returns (CreateUserResponse);
  rpc DeleteUser(DeleteUserRequest) returns (DeleteUserResponse);
}

message GetUserRequest {
  string id = 1;
}

message GetUserResponse {
  User user = 1;
}

message User {
  string id = 1;
  string name = 2;
  string email = 3;
  UserRole role = 4;
  google.protobuf.Timestamp created_at = 5;
}

enum UserRole {
  USER_ROLE_UNSPECIFIED = 0;
  USER_ROLE_ADMIN = 1;
  USER_ROLE_USER = 2;
  USER_ROLE_VIEWER = 3;
}
```

**Rules:**

- Version packages: `package service.v1`.
- Always include an `UNSPECIFIED = 0` enum value.
- Use `google.protobuf.Timestamp` for dates, not strings or integers.
- Use field numbers sequentially. Never reuse deleted field numbers.

### 8.5 API Rate Limiting

**Rule: Use a Redis-backed store for rate limiting. In-memory limiters are bypassed trivially in multi-instance deployments.**

```typescript
import rateLimit from "express-rate-limit";
import RedisStore from "rate-limit-redis";
import { redis } from "../config/redis";

// Redis-backed store — shared across all instances
const redisStore = new RedisStore({
  sendCommand: (...args: string[]) => redis.sendCommand(args),
  prefix: "rl:",
});

// Global limiter — keyed by authenticated user ID or IP
const globalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100,
  standardHeaders: true,  // Exposes X-RateLimit-* headers to client
  legacyHeaders: false,
  store: redisStore,
  keyGenerator: (req) => req.user?.id ?? req.ip ?? "anonymous",
  message: {
    error: { code: "RATE_LIMIT_EXCEEDED", message: "Too many requests — retry after the window resets" },
  },
  skip: (req) => req.path === "/health", // Never limit health checks
});

// Strict limiter for auth endpoints — brute-force protection
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  store: new RedisStore({ sendCommand: (...args: string[]) => redis.sendCommand(args), prefix: "rl:auth:" }),
  keyGenerator: (req) => req.body?.email ?? req.ip ?? "anonymous", // Lock per email, not just IP
  message: {
    error: { code: "RATE_LIMIT_EXCEEDED", message: "Too many login attempts — try again in 15 minutes" },
  },
});

app.use("/api/", globalLimiter);
app.use("/api/v1/auth/login", authLimiter);
app.use("/api/v1/auth/forgot-password", authLimiter);
```

```python
# FastAPI — Redis-backed sliding window rate limiter
from fastapi import Request, HTTPException, status
import redis.asyncio as aioredis
import time

cache = aioredis.from_url(settings.redis_url)

async def rate_limit(request: Request, max_requests: int = 100, window_seconds: int = 900):
    user_id = getattr(request.state, "user_id", None)
    key = f"rl:{user_id or request.client.host}"
    now = time.time()
    window_start = now - window_seconds

    pipe = cache.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)   # Remove old entries
    pipe.zadd(key, {str(now): now})               # Add current request
    pipe.zcard(key)                               # Count in window
    pipe.expire(key, window_seconds)
    results = await pipe.execute()

    count = results[2]
    if count > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(window_seconds)},
            detail={"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests"},
        )
```

### 8.6 Idempotency Keys

**Rule: All non-idempotent operations that trigger side effects (payments, emails, notifications, job submissions) must accept an idempotency key. Duplicate requests with the same key must return the same response without re-executing.**

```typescript
// Middleware to enforce and cache idempotent responses
async function idempotencyMiddleware(req: Request, res: Response, next: NextFunction): Promise<void> {
  const idempotencyKey = req.headers["idempotency-key"] as string | undefined;

  if (!idempotencyKey) {
    // Require the header on mutation endpoints
    res.status(400).json({ error: { code: "MISSING_IDEMPOTENCY_KEY", message: "Idempotency-Key header is required" } });
    return;
  }

  const cacheKey = `idempotency:${req.user!.id}:${idempotencyKey}`;
  const cached = await redis.get(cacheKey);

  if (cached) {
    // Replay the stored response — no re-execution
    const { status, body } = JSON.parse(cached);
    res.status(status).json(body);
    return;
  }

  // Intercept the response to cache it
  const originalJson = res.json.bind(res);
  res.json = (body) => {
    if (res.statusCode < 500) {
      // Cache successful responses for 24 hours
      redis.setex(cacheKey, 86_400, JSON.stringify({ status: res.statusCode, body }));
    }
    return originalJson(body);
  };

  next();
}

// Apply only to endpoints that create side effects
app.post("/api/v1/payments", authenticate, idempotencyMiddleware, createPayment);
app.post("/api/v1/enrollments", authenticate, idempotencyMiddleware, createEnrollment);
```

```python
from fastapi import Request, Response
from functools import wraps
import hashlib, json

async def get_idempotent_response(key: str, user_id: str):
    cached = await cache.get(f"idempotency:{user_id}:{key}")
    return json.loads(cached) if cached else None

async def store_idempotent_response(key: str, user_id: str, status_code: int, body: dict):
    payload = json.dumps({"status": status_code, "body": body})
    await cache.setex(f"idempotency:{user_id}:{key}", 86_400, payload)

# Usage in endpoint
@app.post("/api/v1/payments", status_code=201)
async def create_payment(
    request: Request,
    payload: CreatePaymentRequest,
    user: User = Depends(get_current_user),
):
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header required")

    cached = await get_idempotent_response(idempotency_key, user.id)
    if cached:
        return Response(content=json.dumps(cached["body"]), status_code=cached["status"],
                        media_type="application/json")

    result = await payment_service.create(user.id, payload)
    await store_idempotent_response(idempotency_key, user.id, 201, result.dict())
    return result
```

**Client usage:**
```http
POST /api/v1/payments
Idempotency-Key: 7f3a2b91-e4c6-4d1a-b832-9f1c0e2a5d48
Content-Type: application/json

{ "amount": 500, "currency": "USD" }
```

**Rules:**
- Keys must be scoped to `user_id + idempotency_key` — never global keys (prevents cross-user replay attacks).
- Store keys for at least 24 hours after first request.
- Return `409 Conflict` if the same key is used with a different request body.
- Log idempotency cache hits at `info` level for auditing.

---

## 9. Database & Schema Guidelines

### 9.1 Schema Design Principles

- Every table must have a primary key. Prefer UUIDs (`uuid_generate_v4()`) over auto-increment for distributed systems.
- Include `created_at` and `updated_at` timestamps on every table.
- Use soft deletes (`deleted_at`) for auditable data. Hard delete only transient data.
- Normalize to 3NF by default. Denormalize only with measured performance justification.
- Add database indexes for all columns used in WHERE, JOIN, and ORDER BY clauses.
- Use foreign key constraints. Never rely on application code alone for referential integrity.

### 9.2 SQL Injection Prevention

✅ **Do this — parameterized queries only:**

```typescript
// Using an ORM (Prisma)
const user = await prisma.user.findUnique({ where: { id: userId } });

// Raw query with parameterization (pg)
const result = await pool.query(
  "SELECT * FROM users WHERE id = $1 AND role = $2",
  [userId, role],
);
```

```python
# SQLAlchemy ORM
user = await session.execute(select(User).where(User.id == user_id))

# SQLAlchemy raw with parameters
result = await session.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id})
```

❌ **Never do this:**

```typescript
// String concatenation — SQL injection vulnerability
const query = `SELECT * FROM users WHERE id = '${userId}'`;
const result = await pool.query(query);

// Template literals with user input
const result = await pool.query(
  `SELECT * FROM users WHERE name = '${req.body.name}'`,
);
```

**Why it matters:** SQL injection remains the most exploited vulnerability class. Parameterized queries make injection structurally impossible.

### 9.3 ORM Best Practices

```typescript
// Prisma schema
model User {
  id        String   @id @default(uuid())
  email     String   @unique
  name      String
  role      UserRole @default(USER)
  password  String
  isActive  Boolean  @default(true)
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")
  deletedAt DateTime? @map("deleted_at")

  posts     Post[]
  sessions  Session[]

  @@map("users")
  @@index([email])
  @@index([role, isActive])
}

enum UserRole {
  ADMIN
  USER
  VIEWER
}
```

```python
# SQLAlchemy model
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    role = Column(SAEnum("admin", "user", "viewer", name="user_role"), default="user")
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
```

### 9.4 Migration Rules

- Use a migration tool (Alembic, Prisma Migrate, Flyway, Knex).
- Every schema change must be a versioned, reversible migration.
- Never modify production data in migrations. Use separate data scripts.
- Name migrations descriptively: `add_deleted_at_to_users`, not `migration_042`.
- Test migrations against a copy of production data before deploying.

✅ **Do this:**

```python
# Alembic migration
def upgrade():
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

def downgrade():
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_at")
```

❌ **Avoid this:**

```python
def upgrade():
    # Destructive, irreversible
    op.drop_column("users", "legacy_field")
    op.execute("DELETE FROM users WHERE is_active = false")  # Data manipulation in migration
```

#### Expand-Contract Pattern (Zero-Downtime Migrations)

**Rule: Never rename or drop columns in a single deployment. Use the expand-contract pattern to avoid locking tables and breaking running application instances.**

```
Phase 1 — EXPAND: Add the new column (nullable). Deploy app that writes to BOTH old and new columns.
Phase 2 — BACKFILL: Run a background script to copy data from old → new column.
Phase 3 — CONTRACT: Remove reads from old column. Deploy.
Phase 4 — DROP: Remove old column in a separate migration. Deploy.
```

```python
# Phase 1 migration — EXPAND
def upgrade():
    # Add new column as nullable — safe, no lock
    op.add_column("users", sa.Column("full_name", sa.String(200), nullable=True))

# Phase 2 — backfill script (run offline, not in migration)
# UPDATE users SET full_name = first_name || ' ' || last_name WHERE full_name IS NULL;

# Phase 4 migration — CONTRACT (deployed AFTER app no longer reads old columns)
def upgrade():
    op.alter_column("users", "full_name", nullable=False)
    op.drop_column("users", "first_name")
    op.drop_column("users", "last_name")
```

### 9.5 Database Transactions

**Rule: Any operation that modifies multiple tables or rows must run inside a transaction. Partial failures without transactions corrupt data silently.**

```typescript
// Prisma — interactive transaction
async function transferEnrollment(
  childId: string,
  fromClassId: string,
  toClassId: string,
): Promise<void> {
  await prisma.$transaction(async (tx) => {
    // All operations below are atomic
    const fromClass = await tx.class.findUniqueOrThrow({ where: { id: fromClassId } });
    const toClass = await tx.class.findUniqueOrThrow({ where: { id: toClassId } });

    if (toClass.enrolledCount >= toClass.maxCapacity) {
      throw new CapacityError("Target class is at capacity");
    }

    await tx.enrollment.update({
      where: { childId_classId: { childId, classId: fromClassId } },
      data: { status: "withdrawn", endDate: new Date() },
    });

    await tx.enrollment.create({
      data: { childId, classId: toClassId, startDate: new Date(), status: "active" },
    });

    await tx.class.update({ where: { id: fromClassId }, data: { enrolledCount: { decrement: 1 } } });
    await tx.class.update({ where: { id: toClassId }, data: { enrolledCount: { increment: 1 } } });
    // If any step throws, ALL changes roll back automatically
  });
}
```

```python
# SQLAlchemy — async transaction with savepoint
from sqlalchemy.ext.asyncio import AsyncSession

async def transfer_enrollment(
    db: AsyncSession,
    child_id: str,
    from_class_id: str,
    to_class_id: str,
) -> None:
    async with db.begin():  # Transaction wraps all operations
        to_class = await db.get(Class, to_class_id, with_for_update=True)  # Pessimistic lock
        if to_class.enrolled_count >= to_class.max_capacity:
            raise CapacityError("Target class is at capacity")

        await db.execute(
            update(Enrollment)
            .where(Enrollment.child_id == child_id, Enrollment.class_id == from_class_id)
            .values(status="withdrawn", end_date=date.today())
        )
        db.add(Enrollment(child_id=child_id, class_id=to_class_id, status="active"))
        to_class.enrolled_count += 1
        # Commit happens at context manager exit; any exception triggers rollback
```

**Transaction rules:**
- Keep transactions short. Long transactions hold locks that block other operations.
- Use `SELECT ... FOR UPDATE` (pessimistic lock) when reading a value you will modify in the same transaction (e.g., inventory counts, capacity).
- Use optimistic locking (version/etag column) for low-contention data with occasional conflicts.
- Never make network calls (HTTP, email, queue) inside a database transaction.

### 9.6 Connection Pool Configuration

**Rule: Configure pool size deliberately. Too small = slow responses. Too large = database exhaustion.**

```typescript
// Prisma connection pool — set via DATABASE_URL param or datasource config
// DATABASE_URL="postgresql://user:pass@host:5432/db?connection_limit=20&pool_timeout=10"

// pg (node-postgres) explicit pool
import { Pool } from "pg";

const pool = new Pool({
  connectionString: config.databaseUrl,
  max: 20,                  // Max concurrent connections (tune per DB server capacity)
  min: 5,                   // Keep alive minimum connections
  idleTimeoutMillis: 30_000, // Close idle connections after 30s
  connectionTimeoutMillis: 5_000, // Fail fast if pool is exhausted
  statement_timeout: 10_000, // Kill runaway queries after 10s
});

pool.on("error", (err) => {
  logger.error({ err }, "Idle database client error");
});
```

```python
# SQLAlchemy async engine — pool config
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    settings.database_url,
    pool_size=20,           # Max persistent connections
    max_overflow=10,        # Burst connections beyond pool_size (temporary)
    pool_timeout=10,        # Seconds to wait for a connection before raising
    pool_recycle=1800,      # Recycle connections after 30 min (prevents stale connections)
    pool_pre_ping=True,     # Verify connection health before use
    echo=settings.environment == "development",
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

**Sizing formula:** `pool_size = (num_cores × 2) + num_spindles` per application instance. For a 4-core app server: `pool_size ≈ 10`. Always leave headroom on the database server (e.g., PostgreSQL's `max_connections = 100` → cap total across all app instances to 80).

### 9.7 Query Optimization

- Use `EXPLAIN ANALYZE` to verify query plans for any query touching > 1000 rows.
- Avoid SELECT \*. Specify only required columns.
- Use connection pooling (PgBouncer, HikariCP).
- Set query timeouts to prevent runaway queries.

```python
# N+1 problem — AVOID
users = await session.execute(select(User))
for user in users.scalars():
    posts = await session.execute(select(Post).where(Post.user_id == user.id))  # N queries!

# Eager loading — CORRECT
from sqlalchemy.orm import selectinload
users = await session.execute(
    select(User).options(selectinload(User.posts)).where(User.is_active == True)
)
```

---

## 10. Performance & Scalability

### 10.1 Caching Strategies

| Cache Layer          | Tool                         | TTL        | Use Case                                      |
| -------------------- | ---------------------------- | ---------- | --------------------------------------------- |
| Application Cache    | Redis                        | 5-60 min   | Session data, computed results, rate limiting |
| Database Query Cache | Redis / Memcached            | 1-15 min   | Expensive aggregations, dashboard stats       |
| HTTP Cache           | CDN (CloudFront, Cloudflare) | 1-24 hours | Static assets, public API responses           |
| Browser Cache        | Cache-Control headers        | Varies     | JS/CSS bundles, images, fonts                 |

✅ **Do this:**

```typescript
import Redis from "ioredis";

const redis = new Redis(process.env.REDIS_URL);

async function getCachedOrFetch<T>(
  key: string,
  fetchFn: () => Promise<T>,
  ttlSeconds: number = 300,
): Promise<T> {
  const cached = await redis.get(key);
  if (cached) return JSON.parse(cached);

  const data = await fetchFn();
  await redis.setex(key, ttlSeconds, JSON.stringify(data));
  return data;
}

// Usage
const dashboardStats = await getCachedOrFetch(
  `dashboard:${userId}`,
  () => analyticsService.computeStats(userId),
  600, // 10 minutes
);

// Cache invalidation
async function onUserUpdate(userId: string): Promise<void> {
  await redis.del(`user:${userId}`);
  await redis.del(`dashboard:${userId}`);
}
```

```python
import redis.asyncio as redis
import json

cache = redis.from_url(settings.redis_url)

async def get_cached_or_fetch(key: str, fetch_fn, ttl_seconds: int = 300):
    cached = await cache.get(key)
    if cached:
        return json.loads(cached)

    data = await fetch_fn()
    await cache.setex(key, ttl_seconds, json.dumps(data, default=str))
    return data
```

❌ **Avoid this:**

```typescript
// Caching without invalidation strategy — stale data guaranteed
redis.set("users", JSON.stringify(allUsers)); // No TTL, never invalidated

// Caching per-request user-specific data with generic key
redis.set("data", result); // Key collision between users
```

**Why it matters:** Unmanaged caches serve stale data. Every cache entry must have a TTL and an invalidation path.

### 10.2 Frontend Performance

- Lazy-load routes and heavy components.
- Use code splitting per route.
- Optimize images: WebP/AVIF format, responsive `srcset`, lazy loading.
- Minimize bundle size. Audit with `webpack-bundle-analyzer` or `vite-plugin-visualizer`.
- Use `React.memo`, `useMemo`, `useCallback` only when profiling reveals a bottleneck. Do not premature-optimize.

```typescript
// Route-level code splitting (React)
import { lazy, Suspense } from "react";

const Dashboard = lazy(() => import("./features/dashboard/DashboardPage"));
const Reports = lazy(() => import("./features/reports/ReportsPage"));

function App() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/reports" element={<Reports />} />
      </Routes>
    </Suspense>
  );
}
```

### 10.3 Backend Performance

- Use connection pooling for databases and HTTP clients.
- Implement request timeouts at every external call.
- Use streaming for large data exports. Never load entire datasets into memory.
- Profile before optimizing. Use `cProfile` (Python), `clinic.js` (Node.js).
- Use background jobs (Celery, BullMQ) for operations > 500ms.

```python
# Streaming large CSV export — no memory bloat
from fastapi.responses import StreamingResponse
import csv
import io

@app.get("/api/v1/reports/export")
async def export_report(user: User = Depends(require_role("admin"))):
    async def generate():
        yield "id,name,email,created_at\n"
        async for batch in user_repository.stream_all(batch_size=1000):
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            for user in batch:
                writer.writerow([user.id, user.name, user.email, user.created_at])
            yield buffer.getvalue()

    return StreamingResponse(generate(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=users.csv"})
```

### 10.4 Scalability Patterns

| Pattern                      | When to Use                                                  |
| ---------------------------- | ------------------------------------------------------------ |
| Horizontal Scaling           | Stateless services behind a load balancer                    |
| Read Replicas                | Read-heavy workloads with acceptable staleness               |
| Event-Driven / Message Queue | Decoupled services, async processing                         |
| CQRS                         | Separate read and write models for complex domains           |
| Circuit Breaker              | External service calls to prevent cascade failures           |
| Bulkhead                     | Isolate critical paths from non-critical resource contention |

```typescript
// Circuit breaker pattern
class CircuitBreaker {
  private failures = 0;
  private lastFailureTime = 0;
  private state: "closed" | "open" | "half-open" = "closed";

  constructor(
    private readonly threshold: number = 5,
    private readonly resetTimeMs: number = 30_000,
  ) {}

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === "open") {
      if (Date.now() - this.lastFailureTime > this.resetTimeMs) {
        this.state = "half-open";
      } else {
        throw new ServiceUnavailableError("Circuit breaker is open");
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private onSuccess(): void {
    this.failures = 0;
    this.state = "closed";
  }

  private onFailure(): void {
    this.failures++;
    this.lastFailureTime = Date.now();
    if (this.failures >= this.threshold) {
      this.state = "open";
    }
  }
}
```

### 10.5 Cache Stampede (Thundering Herd) Protection

**Problem:** When a cached value expires, hundreds of concurrent requests all miss the cache simultaneously and hammer the database with identical queries. The fix is probabilistic early recomputation or a lock-based pattern.

```typescript
// Lock-based cache repopulation — only one worker recomputes; others wait
async function getCachedWithLock<T>(
  key: string,
  fetchFn: () => Promise<T>,
  ttlSeconds: number = 300,
): Promise<T> {
  const cached = await redis.get(key);
  if (cached) return JSON.parse(cached);

  const lockKey = `lock:${key}`;
  const lockAcquired = await redis.set(lockKey, "1", "NX", "EX", 30); // 30s lock TTL

  if (lockAcquired) {
    try {
      const data = await fetchFn();
      await redis.setex(key, ttlSeconds, JSON.stringify(data));
      return data;
    } finally {
      await redis.del(lockKey);
    }
  } else {
    // Another worker is recomputing — poll briefly then retry
    await new Promise((resolve) => setTimeout(resolve, 100));
    const retried = await redis.get(key);
    if (retried) return JSON.parse(retried);
    return fetchFn(); // Fallback: compute without cache if lock holder is slow
  }
}
```

```python
# Python — probabilistic early expiration (XFetch algorithm)
# Recomputes slightly before expiry with probability proportional to compute cost
import time, math, random

async def get_cached_xfetch(key: str, fetch_fn, ttl_seconds: int = 300, beta: float = 1.0):
    pipe = cache.pipeline()
    pipe.get(key)
    pipe.ttl(key)
    value_raw, remaining_ttl = await pipe.execute()

    if value_raw:
        value, delta = json.loads(value_raw)  # value + last compute time in ms
        # Early recompute probability increases as TTL shrinks
        if remaining_ttl - beta * delta * math.log(random.random()) > 0:
            return value

    start = time.monotonic()
    data = await fetch_fn()
    delta_ms = (time.monotonic() - start) * 1000
    payload = json.dumps([data, delta_ms], default=str)
    await cache.setex(key, ttl_seconds, payload)
    return data
```

### 10.6 Graceful Shutdown & Health Checks

**Rule: Applications must signal health to orchestrators and drain in-flight requests before shutting down. A hard kill during a request causes data corruption and 502 errors.**

```typescript
// Graceful shutdown — Node.js
const server = app.listen(config.port, () => {
  logger.info({ port: config.port }, "Server started");
});

let isShuttingDown = false;

async function shutdown(signal: string): Promise<void> {
  logger.info({ signal }, "Shutdown signal received");
  isShuttingDown = true;

  // Stop accepting new connections
  server.close(async () => {
    try {
      await prisma.$disconnect();
      await redis.quit();
      logger.info("Graceful shutdown complete");
      process.exit(0);
    } catch (err) {
      logger.error({ err }, "Error during shutdown");
      process.exit(1);
    }
  });

  // Force exit if graceful shutdown takes too long
  setTimeout(() => {
    logger.error("Graceful shutdown timeout — forcing exit");
    process.exit(1);
  }, 10_000);
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));

// Health check endpoints (required for Kubernetes liveness/readiness probes)
app.get("/health/live", (_req, res) => {
  // Liveness: is the process alive? If this fails, K8s restarts the pod.
  res.status(200).json({ status: "ok" });
});

app.get("/health/ready", async (_req, res) => {
  // Readiness: can we serve traffic? If this fails, K8s removes pod from load balancer.
  if (isShuttingDown) {
    return res.status(503).json({ status: "shutting_down" });
  }
  try {
    await prisma.$queryRaw`SELECT 1`;
    await redis.ping();
    res.status(200).json({ status: "ok", db: "ok", cache: "ok" });
  } catch (err) {
    logger.warn({ err }, "Readiness check failed");
    res.status(503).json({ status: "degraded", error: (err as Error).message });
  }
});
```

```python
# FastAPI — lifespan-based graceful startup/shutdown
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application starting up")
    await engine.connect()        # Verify DB connectivity at startup
    await cache.ping()            # Verify Redis connectivity at startup
    yield
    # Shutdown — runs after all in-flight requests complete
    logger.info("Application shutting down")
    await engine.dispose()
    await cache.aclose()

app = FastAPI(lifespan=lifespan)

@app.get("/health/live")
async def liveness():
    return {"status": "ok"}

@app.get("/health/ready")
async def readiness():
    try:
        await engine.execute(text("SELECT 1"))
        await cache.ping()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"status": "degraded", "error": str(e)})
```

**Kubernetes probe configuration:**
```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2

terminationGracePeriodSeconds: 30  # Must exceed server.close() timeout
```

---

## 11. Documentation & Examples

### 11.1 Documentation Requirements

| Document                            | Required?                                 | Owner                              |
| ----------------------------------- | ----------------------------------------- | ---------------------------------- |
| README.md                           | Mandatory                                 | Every repository                   |
| API Reference (OpenAPI/Swagger)     | Mandatory                                 | Backend services                   |
| Architecture Decision Records (ADR) | Mandatory for significant decisions       | Lead developer                     |
| CHANGELOG.md                        | Mandatory                                 | Automated via conventional commits |
| CONTRIBUTING.md                     | Mandatory for open-source / team projects | Maintainers                        |
| Inline code comments                | As needed                                 | Author of the code                 |

### 11.2 README.md Template

Every project README must contain these sections:

````markdown
# Project Name

One-sentence description of what this project does.

## Prerequisites

- Node.js >= 20
- PostgreSQL >= 15
- Redis >= 7

## Getting Started

### Installation

\```bash
git clone <repo-url>
cd project
cp .env.example .env
npm install
npm run db:migrate
\```

### Running Locally

\```bash
npm run dev # Start development server
npm run test # Run test suite
npm run test:e2e # Run E2E tests
npm run lint # Run linter
\```

## Architecture

Brief description of the architecture and key design decisions.

## API Documentation

API docs are available at `/docs` when running the development server.

## Environment Variables

| Variable       | Required | Default | Description                  |
| -------------- | -------- | ------- | ---------------------------- |
| `DATABASE_URL` | Yes      | —       | PostgreSQL connection string |
| `REDIS_URL`    | Yes      | —       | Redis connection string      |
| `JWT_SECRET`   | Yes      | —       | Secret key for JWT signing   |
| `PORT`         | No       | 3000    | Server port                  |

## Deployment

Deployment instructions for staging and production environments.
````

### 11.3 Architecture Decision Records

```markdown
# ADR-001: Use PostgreSQL as Primary Database

## Status

Accepted

## Context

We need a relational database that supports JSONB columns, full-text search,
and has strong ecosystem support for our Python/FastAPI backend.

## Decision

Use PostgreSQL 15+ as the primary database.

## Consequences

- Positive: JSONB support for flexible schemas, full-text search, mature tooling.
- Negative: Requires more operational expertise than managed NoSQL alternatives.
- Neutral: Team has existing PostgreSQL experience.
```

### 11.4 API Documentation (OpenAPI)

✅ **Do this — annotate endpoints with full schemas:**

```python
from fastapi import FastAPI, Path, Query

@app.get(
    "/api/v1/users/{user_id}",
    response_model=UserResponse,
    responses={
        404: {"model": ErrorResponse, "description": "User not found"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    },
    summary="Get a user by ID",
    description="Retrieve a single user by their unique identifier.",
    tags=["Users"],
)
async def get_user(
    user_id: str = Path(..., description="The unique user identifier", example="abc-123"),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    ...
```

❌ **Avoid this:**

```python
@app.get("/api/v1/users/{user_id}")
async def get_user(user_id):
    ...  # No type hints, no docs, no error responses documented
```

**Why it matters:** Well-documented APIs reduce integration time for consumers from days to minutes.

---

## 12. Fine-Tuning Instructions for AI Agents

### 12.1 Agent Behavior Rules

1. **Adopt the role.** Act as a senior full-stack developer with 10+ years of experience. Never produce beginner-level code.
2. **Follow this document.** Every code output must comply with every section of this reference. When in conflict, this document takes precedence over general training data.
3. **Ask before assuming.** If the user's requirements are ambiguous, ask clarifying questions. Do not guess technology choices.
4. **Show, don't tell.** Prefer working code examples over textual explanations.
5. **Think in systems.** Consider error handling, edge cases, security, and performance for every code block — not just the happy path.
6. **No placeholder code.** Never use `// TODO`, `pass`, or `...` in production outputs. If a function is requested, implement it fully.
7. **Minimize dependencies.** Do not introduce new libraries unless they solve a problem the standard library cannot.
8. **Explain trade-offs.** When making design decisions, briefly state what was chosen, what was rejected, and why.

### 12.2 Code Generation Protocol

When asked to generate code, follow this sequence:

```
1. UNDERSTAND: Restate the requirement in one sentence.
2. PLAN: Identify files to create/modify and their relationships.
3. VALIDATE: Check for security implications, edge cases, and existing patterns.
4. IMPLEMENT: Write the code following this reference.
5. TEST: Generate corresponding tests.
6. DOCUMENT: Add JSDoc/docstrings for public interfaces.
7. REVIEW: Self-review against this document's rules before presenting.
```

### 12.3 Context Awareness

- Detect the existing tech stack from `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, or project structure.
- Match existing code style: indentation, quote style, semicolons, import ordering.
- Respect existing patterns: if the project uses a repository pattern, do not introduce inline queries.
- Read existing error handling conventions before adding new ones.

### 12.4 Output Format Rules

| Scenario              | Output                                                               |
| --------------------- | -------------------------------------------------------------------- |
| New feature           | Full implementation + tests + types                                  |
| Bug fix               | Minimal change + regression test                                     |
| Refactor              | Explain before/after, maintain behavior, update tests                |
| Code review           | Line-by-line analysis, severity levels (critical/warning/suggestion) |
| Architecture question | Decision matrix with pros/cons                                       |

### 12.5 Prompt Interpretation Rules

| User Says                    | Agent Interprets As                                                          |
| ---------------------------- | ---------------------------------------------------------------------------- |
| "Create a user endpoint"     | Full CRUD with validation, auth, error handling, tests                       |
| "Add authentication"         | JWT access + refresh tokens, middleware, role guards                         |
| "Fix this bug"               | Root cause analysis + fix + regression test                                  |
| "Optimize this"              | Profile first, then apply targeted optimization with benchmarks              |
| "Make this production-ready" | Add error handling, logging, validation, tests, env config, security headers |
| "Review this code"           | Check against all sections of this document                                  |

### 12.6 Language-Specific Fine-Tuning

#### TypeScript Agent Rules

- Always enable strict mode.
- Never use `any`. Use `unknown` and narrow with type guards.
- Prefer `interface` for object shapes, `type` for unions and intersections.
- Use `as const` for literal types.
- Use discriminated unions for state management.

```typescript
// Discriminated union for API response states
type ApiState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: AppError };

// Type guard
function isSuccess<T>(
  state: ApiState<T>,
): state is { status: "success"; data: T } {
  return state.status === "success";
}
```

#### Python Agent Rules

- Use type hints on all function signatures.
- Use `dataclass` or Pydantic `BaseModel` for data structures. Never use plain `dict` for structured data.
- Use `async def` for I/O-bound operations.
- Use `pathlib.Path` instead of `os.path`.
- Use f-strings for string formatting.

```python
# Correct
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True)
class ReportConfig:
    output_dir: Path
    format: str = "pdf"
    include_charts: bool = True
    generated_at: datetime = field(default_factory=datetime.utcnow)
```

#### Go Agent Rules

- Handle every error. Never discard `err` with `_`.
- Use `context.Context` as the first parameter in service functions.
- Use table-driven tests.
- Use `errors.Is` and `errors.As` for error inspection.

```go
func (s *UserService) GetByID(ctx context.Context, id string) (*User, error) {
    user, err := s.repo.FindByID(ctx, id)
    if err != nil {
        if errors.Is(err, ErrNotFound) {
            return nil, fmt.Errorf("user %s: %w", id, ErrNotFound)
        }
        return nil, fmt.Errorf("fetching user %s: %w", id, err)
    }
    return user, nil
}
```

#### Rust Agent Rules

- Use `Result<T, E>` for all fallible operations.
- Derive `Debug`, `Clone` for data types.
- Use `#[must_use]` on functions that return values the caller should not ignore.
- Use `clippy` at pedantic level.

```rust
#[derive(Debug, Clone)]
pub struct User {
    pub id: Uuid,
    pub name: String,
    pub email: String,
    pub role: UserRole,
}

#[must_use]
pub fn validate_email(email: &str) -> Result<(), ValidationError> {
    if !email.contains('@') || email.len() > 254 {
        return Err(ValidationError::InvalidEmail(email.to_string()));
    }
    Ok(())
}
```

---

## 13. Observability & Monitoring

### 13.1 The Three Pillars

| Pillar | Tool | What It Answers |
|--------|------|-----------------|
| **Logs** | Pino, structlog, Loki | What happened and when |
| **Metrics** | Prometheus + Grafana | How the system is behaving over time |
| **Traces** | OpenTelemetry + Jaeger/Tempo | Why a specific request was slow or failed |

**Rule: Instrument every new service with all three pillars before its first production deployment.**

### 13.2 OpenTelemetry Instrumentation

```typescript
// main.ts — initialize tracing before importing anything else
import { NodeSDK } from "@opentelemetry/sdk-node";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { Resource } from "@opentelemetry/resources";
import { SemanticResourceAttributes } from "@opentelemetry/semantic-conventions";

const sdk = new NodeSDK({
  resource: new Resource({
    [SemanticResourceAttributes.SERVICE_NAME]: "kindergarten-api",
    [SemanticResourceAttributes.SERVICE_VERSION]: process.env.APP_VERSION ?? "unknown",
    [SemanticResourceAttributes.DEPLOYMENT_ENVIRONMENT]: process.env.NODE_ENV,
  }),
  traceExporter: new OTLPTraceExporter({ url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT }),
  instrumentations: [getNodeAutoInstrumentations()], // Auto-instruments HTTP, DB, Redis
});

sdk.start();
```

```python
# FastAPI — OpenTelemetry with auto-instrumentation
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)
RedisInstrumentor().instrument()
```

### 13.3 Custom Business Metrics (Prometheus)

```typescript
import { register, Counter, Histogram, Gauge } from "prom-client";

// Define metrics once at module level
export const httpRequestDuration = new Histogram({
  name: "http_request_duration_seconds",
  help: "HTTP request duration in seconds",
  labelNames: ["method", "route", "status_code"],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
});

export const enrollmentCounter = new Counter({
  name: "enrollments_total",
  help: "Total number of enrollment operations",
  labelNames: ["status"],  // 'created' | 'rejected' | 'cancelled'
});

export const activeSessionsGauge = new Gauge({
  name: "active_sessions_total",
  help: "Number of currently active user sessions",
});

// Expose metrics endpoint (scrape target for Prometheus)
app.get("/metrics", async (_req, res) => {
  res.set("Content-Type", register.contentType);
  res.send(await register.metrics());
});

// Middleware to record request duration
app.use((req, res, next) => {
  const end = httpRequestDuration.startTimer({ method: req.method, route: req.route?.path ?? req.path });
  res.on("finish", () => end({ status_code: res.statusCode }));
  next();
});
```

```python
from prometheus_client import Counter, Histogram, Gauge, make_asgi_app
from starlette.routing import Mount

enrollment_counter = Counter("enrollments_total", "Total enrollments", ["status"])
request_duration = Histogram("http_request_duration_seconds", "Request duration", ["method", "route"])
active_sessions = Gauge("active_sessions_total", "Active sessions")

# Mount Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())
```

### 13.4 Structured Alerting Rules

**Rule: Every alert must have an owner, a severity, and a runbook link. Alerts without runbooks are noise.**

```yaml
# Prometheus alerting rules (alerts.yml)
groups:
  - name: api-alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status_code=~"5.."}[5m]) > 0.05
        for: 2m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "Error rate above 5% for 2 minutes"
          runbook: "https://wiki.internal/runbooks/high-error-rate"

      - alert: SlowResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "95th percentile response time above 2s"

      - alert: DatabaseConnectionPoolExhausted
        expr: db_pool_available_connections < 2
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "DB connection pool nearly exhausted — risk of request timeouts"
          runbook: "https://wiki.internal/runbooks/db-pool-exhausted"
```

### 13.5 Distributed Tracing — Adding Custom Spans

```typescript
import { trace, SpanStatusCode } from "@opentelemetry/api";

const tracer = trace.getTracer("user-service");

async function getUserWithEnrollments(userId: string): Promise<UserWithEnrollments> {
  // Creates a child span visible in Jaeger/Tempo waterfall view
  return tracer.startActiveSpan("getUserWithEnrollments", async (span) => {
    span.setAttribute("user.id", userId);
    try {
      const user = await userRepository.findById(userId);
      span.setAttribute("user.found", !!user);

      const enrollments = await enrollmentRepository.findByUserId(userId);
      span.setAttribute("enrollment.count", enrollments.length);

      return { ...user, enrollments };
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}
```

---

## 14. CI/CD Pipeline Standards

### 14.1 Pipeline Stages (Required)

Every repository must have a CI pipeline with these stages in order. A merge to `main` is blocked if any stage fails.

```
1. lint        → ESLint / Ruff / golangci-lint (< 60s)
2. type-check  → tsc --noEmit / mypy (< 90s)
3. unit-test   → Vitest / pytest (< 3 min)
4. build       → Compile/bundle (< 5 min)
5. integration → Test against real DB/cache in Docker (< 10 min)
6. security    → Trivy, Snyk, OWASP dependency-check (< 5 min)
7. e2e         → Playwright / Cypress (< 15 min, on main only)
8. deploy      → Staging (auto) → Production (manual gate)
```

### 14.2 GitHub Actions Pipeline Template

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  NODE_VERSION: "20"
  PYTHON_VERSION: "3.12"

jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: "npm"
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck

  unit-tests:
    runs-on: ubuntu-latest
    needs: lint-and-typecheck
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "${{ env.NODE_VERSION }}", cache: "npm" }
      - run: npm ci
      - run: npm run test:unit -- --coverage
      - uses: codecov/codecov-action@v4
        with: { token: ${{ secrets.CODECOV_TOKEN }} }

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 10s --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    env:
      DATABASE_URL: postgresql://test:test@localhost:5432/test_db
      REDIS_URL: redis://localhost:6379
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "${{ env.NODE_VERSION }}", cache: "npm" }
      - run: npm ci
      - run: npm run db:migrate
      - run: npm run test:integration

  security-scan:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: "fs"
          severity: "CRITICAL,HIGH"
          exit-code: "1"          # Fail the build on critical/high CVEs
      - name: Audit npm dependencies
        run: npm audit --audit-level=high

  deploy-staging:
    runs-on: ubuntu-latest
    needs: [integration-tests, security-scan]
    if: github.ref == 'refs/heads/main'
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to staging
        run: ./scripts/deploy.sh staging
        env:
          DEPLOY_TOKEN: ${{ secrets.STAGING_DEPLOY_TOKEN }}
```

### 14.3 Branch & Merge Rules

| Rule | Rationale |
|------|-----------|
| No direct push to `main` or `develop` | All changes must go through PR + CI |
| Require at least 1 reviewer approval | Four-eyes principle |
| Require all CI checks to pass | No merging broken code |
| Delete branches after merge | Keep repository clean |
| Use conventional commits | Enables automated CHANGELOG generation |
| Sign commits (GPG/SSH) | Provenance and audit trail |

### 14.4 Conventional Commits

```
<type>(<scope>): <subject>

Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert

Examples:
  feat(auth): add refresh token rotation
  fix(enrollment): prevent double-enrollment when request retried
  perf(reports): add index on enrollment.created_at reducing query from 2s to 40ms
  security(upload): validate magic bytes to prevent MIME type spoofing
```

**Commit message rules:**
- Subject line ≤ 72 characters.
- Use imperative mood ("add", not "added" or "adds").
- Reference issue numbers in the body: `Closes #123`.
- Breaking changes must include `BREAKING CHANGE:` in the footer.

---

## 15. Background Jobs & Task Queues

### 15.1 When to Use Background Jobs

**Rule: Any operation that takes > 500ms, triggers external services, or must be retried on failure belongs in a background job — not in the HTTP request/response cycle.**

| Situation | Approach |
|-----------|----------|
| Send email after signup | Background job (fire and forget) |
| Generate a 10k-row PDF report | Background job + polling endpoint |
| Charge a payment (with retry logic) | Background job with idempotency key |
| Sync data to external CRM | Background job with exponential backoff |
| Real-time notification | WebSocket or SSE (not a background job) |

### 15.2 BullMQ (Node.js)

```typescript
import { Queue, Worker, QueueEvents } from "bullmq";
import { redis } from "../config/redis";

// Define a typed queue
const emailQueue = new Queue<EmailJobData>("emails", {
  connection: redis,
  defaultJobOptions: {
    attempts: 3,                  // Retry up to 3 times
    backoff: { type: "exponential", delay: 1000 }, // 1s → 2s → 4s
    removeOnComplete: { count: 1000 }, // Keep last 1000 completed jobs
    removeOnFail: { count: 5000 },     // Keep last 5000 failed jobs for debugging
  },
});

// Producer — add a job (call from API handler)
await emailQueue.add(
  "welcome-email",
  { userId, email, name },
  { jobId: `welcome:${userId}` }, // Deduplication key — prevent duplicate emails
);

// Worker — process jobs (separate process / deployment)
const worker = new Worker<EmailJobData>(
  "emails",
  async (job) => {
    logger.info({ jobId: job.id, userId: job.data.userId }, "Processing email job");
    await emailService.sendWelcome(job.data);
    logger.info({ jobId: job.id }, "Email sent");
  },
  { connection: redis, concurrency: 5 },
);

worker.on("failed", (job, err) => {
  logger.error({ jobId: job?.id, err, attempts: job?.attemptsMade }, "Job failed permanently");
  // Alert after all retries exhausted
  if (job?.attemptsMade === job?.opts.attempts) {
    alertingService.notify(`Email job ${job?.id} failed after all retries`);
  }
});
```

### 15.3 Celery (Python)

```python
# celery_app.py
from celery import Celery
from kombu import Queue

celery_app = Celery(
    "tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,                  # Acknowledge AFTER task completes (not before)
    task_reject_on_worker_lost=True,      # Requeue if worker dies mid-task
    worker_prefetch_multiplier=1,         # Process one task at a time per worker
    task_queues=[
        Queue("high", routing_key="high"),
        Queue("default", routing_key="default"),
        Queue("low", routing_key="low"),
    ],
    task_default_queue="default",
)

# tasks/email_tasks.py
from celery_app import celery_app
import structlog

logger = structlog.get_logger()

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # seconds
    queue="default",
)
def send_welcome_email(self, user_id: str, email: str, name: str) -> None:
    try:
        logger.info("send_welcome_email.started", user_id=user_id)
        email_service.send_welcome(email=email, name=name)
        logger.info("send_welcome_email.completed", user_id=user_id)
    except Exception as exc:
        logger.warning("send_welcome_email.retrying", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)

# Dispatch from API handler
send_welcome_email.apply_async(
    kwargs={"user_id": user.id, "email": user.email, "name": user.name},
    task_id=f"welcome-{user.id}",  # Idempotency key
)
```

### 15.4 Job Queue Rules

- **Always use idempotency keys** when enqueueing jobs that have side effects. Duplicate job submissions must be safe.
- **Use dead letter queues (DLQ)** to capture permanently failed jobs for manual inspection.
- **Never block the HTTP handler** waiting for a job result. Return `202 Accepted` with a job ID; expose a polling endpoint.
- **Monitor queue depth** as a metric. A growing queue signals worker under-provisioning.
- **Use separate queues for different priorities.** A slow low-priority job must not block a time-sensitive high-priority job.

```typescript
// 202 Accepted pattern — async job submission
app.post("/api/v1/reports/generate", authenticate, async (req, res) => {
  const job = await reportQueue.add("generate-report", {
    userId: req.user!.id,
    filters: req.body.filters,
  });

  res.status(202).json({
    jobId: job.id,
    statusUrl: `/api/v1/jobs/${job.id}/status`,
    estimatedDurationSeconds: 30,
  });
});

app.get("/api/v1/jobs/:jobId/status", authenticate, async (req, res) => {
  const job = await reportQueue.getJob(req.params.jobId);
  if (!job) throw new NotFoundError("Job", req.params.jobId);

  const state = await job.getState();
  res.json({
    jobId: job.id,
    status: state,  // 'waiting' | 'active' | 'completed' | 'failed'
    progress: job.progress,
    result: state === "completed" ? job.returnvalue : undefined,
    failReason: state === "failed" ? job.failedReason : undefined,
  });
});
```

---

## Quick Reference Table

| Scenario                                  | Rule                                                              | Section |
| ----------------------------------------- | ----------------------------------------------------------------- | ------- |
| Starting a new function                   | Single responsibility, < 40 lines, typed parameters and return    | §1, §4  |
| Adding an API endpoint                    | Validate input, authenticate, authorize, return standard envelope | §6, §8  |
| Writing a database query                  | Parameterized only, no SELECT \*, use ORM when available          | §9      |
| Handling errors                           | Custom error class, structured logging, no silent catches         | §5      |
| Storing secrets                           | Environment variables validated at startup, never in code         | §6      |
| Caching data                              | Set TTL, define invalidation strategy, namespace keys             | §10     |
| Writing tests                             | Behavior-focused, descriptive names, mock external dependencies   | §7      |
| Creating a new file                       | Follow project structure, feature-based grouping                  | §3      |
| Naming a variable                         | camelCase, intention-revealing, no abbreviations                  | §4      |
| Logging an event                          | Structured, include requestId, appropriate level, redact PII      | §5      |
| Deploying to production                   | Zero warnings, all tests pass, env validated, secrets in vault    | §6, §10 |
| Using `any` in TypeScript                 | Prohibited. Use `unknown` + type guard                            | §2, §12 |
| String concatenation in SQL               | Prohibited. Use parameterized queries                             | §9      |
| Console.log in production                 | Prohibited. Use structured logger                                 | §5      |
| Catching errors generically               | Prohibited. Catch specific types, log context                     | §5      |
| Swallowing errors silently                | Prohibited. Always log or re-throw                                | §5      |
| Committing .env files                     | Prohibited. Use .env.example with placeholder values              | §6      |
| Auto-increment IDs in distributed systems | Prohibited. Use UUIDs                                             | §9      |
| Frontend: class components                | Prohibited in new code. Use functional + hooks                    | §2      |
| Callbacks for async flow                  | Prohibited in new code. Use async/await                           | §2      |
| Adding a side-effect endpoint (payment)   | Require Idempotency-Key header, cache response for 24h            | §8.6    |
| Rendering untrusted HTML                  | Sanitize with DOMPurify before dangerouslySetInnerHTML            | §6.9    |
| Handling file uploads                     | Validate magic bytes, randomize filename, store in object storage | §6.10   |
| Using cookie-based sessions               | Set HttpOnly, Secure, SameSite=Strict; add CSRF token             | §6.6–8  |
| Setting security headers                  | Use Helmet (Node) or SecurityHeadersMiddleware (Python)           | §6.7    |
| Modifying multiple tables atomically      | Wrap in a database transaction; never rely on application-level   | §9.5    |
| Configuring DB connection pool            | Set max/min/timeout; size = (cores × 2) + spindles                | §9.6    |
| Rate limiting in multi-instance deploy    | Use Redis-backed store — in-memory is bypassed across instances   | §8.5    |
| Starting a new service                    | Instrument logs + metrics + traces before first deploy            | §13     |
| Adding a CI pipeline                      | lint → typecheck → unit → build → integration → security → e2e   | §14     |
| Operation taking > 500ms in HTTP handler  | Move to background job; return 202 Accepted + polling URL         | §15     |
| App shutdown (SIGTERM received)           | Drain in-flight requests, close DB pool, exit cleanly             | §10.6   |
| Cache miss causing DB overload            | Use lock-based or XFetch stampede protection                      | §10.5   |
| Renaming a DB column in production        | Use expand-contract pattern across 4 separate deployments         | §9.4    |

---

## Self-Correction Protocol

The AI agent must execute this checklist internally before presenting any code output:

### Pre-Output Validation Checklist

```
□ TYPES: Are all function parameters and return types explicitly typed?
□ VALIDATION: Is all user input validated at the system boundary?
□ SECURITY: Are queries parameterized? Are secrets externalized? Is auth enforced?
□ CSRF: If using cookies, is CSRF protection in place? (§6.6)
□ HEADERS: Are security headers (CSP, HSTS, X-Frame-Options) configured? (§6.7)
□ COOKIES: Are auth cookies HttpOnly + Secure + SameSite=Strict? (§6.8)
□ XSS: Is any HTML rendered with dangerouslySetInnerHTML sanitized via DOMPurify? (§6.9)
□ FILE UPLOADS: Are magic bytes validated? Is filename randomized? Stored outside webroot? (§6.10)
□ IDEMPOTENCY: Do mutation endpoints that cause side effects require an Idempotency-Key? (§8.6)
□ RATE LIMITING: Is the rate limiter Redis-backed (not in-memory) for multi-instance safety? (§8.5)
□ TRANSACTIONS: Do multi-table writes use a database transaction? (§9.5)
□ ERROR HANDLING: Are errors caught, typed, logged, and surfaced correctly?
□ ASYNC ERRORS: Are unhandledRejection / uncaughtException handlers registered at startup? (§5.3)
□ NAMING: Do all identifiers follow the naming conventions in §4?
□ STRUCTURE: Does the code follow the project structure rules in §3?
□ TESTING: Are tests provided or referenced? Do they test behavior, not implementation?
□ TEST DATA: Are test data factories used instead of hardcoded magic strings? (§7.6)
□ LOGGING: Is structured logging used instead of console.log/print?
□ OBSERVABILITY: Are new service functions instrumented with spans/metrics? (§13)
□ PERFORMANCE: Are there N+1 queries, cache stampedes, unbounded loops, or memory leaks?
□ BACKGROUND JOBS: Are operations > 500ms moved to a job queue with retry logic? (§15)
□ HEALTH CHECKS: Do new services expose /health/live and /health/ready endpoints? (§10.6)
□ DOCUMENTATION: Do public interfaces have JSDoc/docstrings?
□ CONSISTENCY: Does the output match the existing codebase's patterns and style?
□ NO PLACEHOLDERS: Are there any TODO, FIXME, pass, or ... in the output?
```

### Deviation Detection

If the agent detects that its output violates any rule in this document:

1. **Stop** generating the current output.
2. **Identify** the violated rule by section number.
3. **Correct** the output to comply.
4. **Note** the correction to the user: "Corrected: [brief description] per §[number]."

### Contradiction Resolution

If two rules in this document appear to conflict:

1. **Security rules (§6) take precedence** over all other rules.
2. **Correctness (§5, §7) takes precedence** over performance (§10).
3. **Readability (§1, §4) takes precedence** over brevity.
4. **Existing project conventions take precedence** over this document's defaults when the project is established and consistent.

---

_End of R_AGENT_REFERENCE v1.1.0_

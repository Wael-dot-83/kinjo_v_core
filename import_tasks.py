"""
Celery tasks for asynchronous CSV data imports.

The triggering endpoint:
  1. Reads and validates the uploaded CSV file synchronously (fast).
  2. Stores the raw CSV bytes in Redis under a job key.
  3. Enqueues this task with the Redis key and user id.
  4. Returns the task id so the caller can poll for results.

This task:
  1. Fetches the CSV bytes from Redis.
  2. Runs the full import pipeline (row-by-row validation + DB writes).
  3. Stores the result summary back in Redis for polling.
"""
import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from celery_app import celery_app
from database import SessionLocal

logger = logging.getLogger(__name__)

_RESULT_TTL_SECONDS = 3600  # 1 hour


def _redis_client():
    from config import settings
    import redis
    return redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)


@celery_app.task(name="import_tasks.process_users_csv", bind=True, max_retries=0)
def process_users_csv(
    self,
    csv_bytes_key: str,
    user_id: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Process a users CSV import from bytes stored in Redis under *csv_bytes_key*.

    Returns a summary dict with keys: total, succeeded, failed, errors.
    The result is also written back to Redis so the caller can poll it.
    """
    result_key = f"import_result:{self.request.id}"
    rc = _redis_client()

    try:
        raw = rc.get(csv_bytes_key)
        if raw is None:
            result = {"error": "csv_data_expired_or_not_found", "task_id": self.request.id}
            rc.setex(result_key, _RESULT_TTL_SECONDS, json.dumps(result))
            return result

        decoded = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded))

        db = SessionLocal()
        try:
            result = _import_users(db, reader, user_id, dry_run)
        finally:
            db.close()

    except Exception as exc:
        logger.exception("CSV import task failed: %s", exc)
        result = {"error": str(exc), "task_id": self.request.id}

    finally:
        try:
            rc.delete(csv_bytes_key)
        except Exception:
            pass

    rc.setex(result_key, _RESULT_TTL_SECONDS, json.dumps(result, default=str))
    return result


def _import_users(db, reader, admin_user_id: int, dry_run: bool) -> Dict[str, Any]:
    """Row-by-row import; mirrors the logic in admin_endpoints import_users_csv."""
    import models
    from admin_security import log_audit_event
    from csv_utils import escape_csv_formula

    required_fields = {"username", "email", "password", "role"}
    header_fields = set(reader.fieldnames or [])
    missing = required_fields - header_fields
    if missing:
        return {"error": f"Missing columns: {', '.join(missing)}"}

    admin_user = db.query(models.User).filter(models.User.id == admin_user_id).first()
    if admin_user is None:
        return {"error": "admin_user_not_found"}

    total = 0
    succeeded: List[int] = []
    failed: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    allowed_roles = {"MANAGER", "SUPERVISOR", "PARENT"}

    for row in reader:
        total += 1
        row_num = total + 1

        sanitized = {k: escape_csv_formula(str(v).strip()) if v else "" for k, v in row.items()}
        role_str = sanitized.get("role", "").upper()
        if role_str not in allowed_roles:
            errors.append({"row": row_num, "field": "role", "code": "INVALID_ROLE", "value": role_str})
            failed.append(row_num)
            continue

        email = sanitized.get("email", "").lower()
        username = sanitized.get("username", "")
        password_plain = sanitized.get("password", "")

        if not email or "@" not in email:
            errors.append({"row": row_num, "field": "email", "code": "INVALID_EMAIL"})
            failed.append(row_num)
            continue

        if not password_plain or len(password_plain) < 8:
            errors.append({"row": row_num, "field": "password", "code": "TOO_SHORT"})
            failed.append(row_num)
            continue

        if not dry_run:
            existing = db.query(models.User).filter(
                (models.User.email == email) | (models.User.username == username)
            ).first()
            if existing:
                errors.append({"row": row_num, "field": "email", "code": "DUPLICATE"})
                failed.append(row_num)
                continue

            from passlib.context import CryptContext
            pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
            hashed = pwd_ctx.hash(password_plain)

            user = models.User(
                username=username,
                email=email,
                hashed_password=hashed,
                role=models.UserRole(role_str),
                status=models.UserStatus.ACTIVE,
            )
            db.add(user)
            try:
                db.flush()
                succeeded.append(user.id)
            except Exception as exc:
                db.rollback()
                errors.append({"row": row_num, "field": "_db", "code": "DB_ERROR", "detail": str(exc)})
                failed.append(row_num)
                continue
        else:
            succeeded.append(row_num)

    if not dry_run and succeeded:
        try:
            log_audit_event(
                db,
                "BULK_USER_IMPORT",
                admin_user,
                "User",
                metadata={"total": total, "succeeded": len(succeeded), "failed": len(failed), "dry_run": dry_run},
            )
            db.commit()
        except Exception:
            db.rollback()

    return {
        "total": total,
        "succeeded": len(succeeded),
        "failed": len(failed),
        "errors": errors,
        "dry_run": dry_run,
    }

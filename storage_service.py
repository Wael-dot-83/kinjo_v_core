"""
Attachment storage helpers (local and S3).
"""
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Tuple

from fastapi import UploadFile

from config import settings

# Allowed file extensions and their MIME types for upload validation
ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".doc": {"application/msword"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xls": {"application/vnd.ms-excel"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".csv": {"text/csv"},
    ".txt": {"text/plain"},
}


def _validate_upload(upload: UploadFile) -> str:
    """Validate file extension and content-type. Returns the safe extension."""
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File type '{ext}' is not allowed. "
            f"Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    declared = (upload.content_type or "").lower()
    if declared and declared not in ALLOWED_EXTENSIONS[ext]:
        raise ValueError(
            f"Content-type '{declared}' does not match extension '{ext}'"
        )
    return ext


def _copy_with_limit(src, dst, max_bytes: int) -> int:
    size = 0
    while True:
        chunk = src.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise ValueError("Attachment exceeds maximum allowed size")
        dst.write(chunk)
    return size


def _save_to_temp(upload: UploadFile, max_bytes: int) -> Tuple[str, int]:
    suffix = Path(upload.filename or "").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        size = _copy_with_limit(upload.file, tmp, max_bytes)
        tmp_path = tmp.name
    upload.file.seek(0)
    return tmp_path, size


def save_attachment(upload: UploadFile) -> Tuple[str, str, int]:
    ext = _validate_upload(upload)
    provider = (settings.STORAGE_PROVIDER or "local").lower()
    max_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
    temp_path, size = _save_to_temp(upload, max_bytes)

    if provider == "s3":
        return _save_to_s3(upload, temp_path, size, ext)

    return _save_to_local(temp_path, size, ext)


def _save_to_local(temp_path: str, size: int, ext: str) -> Tuple[str, str, int]:
    attachments_dir = Path(settings.ATTACHMENTS_DIR).resolve()
    attachments_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4().hex}{ext}"
    final_path = attachments_dir / file_name
    shutil.move(temp_path, final_path)
    storage_key = file_name  # Store relative name, not absolute path
    return "local", storage_key, size


def _save_to_s3(upload: UploadFile, temp_path: str, size: int, ext: str) -> Tuple[str, str, int]:
    import boto3

    bucket = settings.S3_BUCKET
    if not bucket:
        raise ValueError("S3_BUCKET is required when STORAGE_PROVIDER=s3")

    object_key = f"message-attachments/{uuid.uuid4().hex}{ext}"

    session = boto3.session.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION
    )
    client = session.client("s3", endpoint_url=settings.S3_ENDPOINT_URL or None)
    with open(temp_path, "rb") as f:
        client.upload_fileobj(f, bucket, object_key, ExtraArgs={"ContentType": upload.content_type or "application/octet-stream"})

    os.remove(temp_path)
    return "s3", object_key, size


def resolve_attachment_path(storage_key: str) -> Path:
    """Resolve storage key to a safe file path within the attachments directory."""
    base_dir = Path(settings.ATTACHMENTS_DIR).resolve()
    # Reject absolute paths and traversal sequences upfront
    if os.path.isabs(storage_key) or ".." in storage_key:
        raise ValueError("Invalid attachment path")
    file_path = (base_dir / storage_key).resolve()
    # Ensure the resolved path is inside the base directory
    if not str(file_path).startswith(str(base_dir) + os.sep) and file_path != base_dir:
        raise ValueError("Invalid attachment path")
    return file_path


__all__ = ["save_attachment", "resolve_attachment_path"]

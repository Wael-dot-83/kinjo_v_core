"""
Attachment storage helpers (local and S3).
"""
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Tuple

from fastapi import UploadFile

from config import settings
from virus_scan_service import VirusFoundError, VirusScanUnavailable, scan_bytes

logger = logging.getLogger(__name__)

# Images are re-encoded on upload to cap dimensions/size (GWS web-performance
# guidance: keep page weight down). GIFs are skipped to avoid breaking animation.
COMPRESSIBLE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_DIMENSION_PX = 1920
JPEG_WEBP_QUALITY = 82

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


def _sanitize_filename(name: str) -> str:
    """Return a filesystem-safe version of an upload filename.

    GWS C.3.3-069 requires that uploaded file names are free from spaces
    (spaces must be replaced with underscores).  Additionally strips any
    path-separator characters to prevent directory traversal via filename.
    """
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Strip path separators and null bytes
    name = re.sub(r'[/\\:\x00]', "_", name)
    return name


def _validate_upload(upload: UploadFile) -> str:
    """Validate file extension and content-type. Returns the safe extension."""
    raw_name = upload.filename or ""
    safe_name = _sanitize_filename(raw_name)
    if safe_name != raw_name:
        # Update the filename on the upload object so callers see the sanitised name
        upload.filename = safe_name
    ext = Path(safe_name).suffix.lower()
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


def compress_image_in_place(path: str, ext: str) -> int:
    """Re-encode an oversized image in place to cap dimensions and file weight.

    Returns the file's size after the attempt (unchanged on failure).
    Best-effort: any failure (corrupt image, unsupported mode, Pillow
    unavailable) leaves the original file untouched and is logged, never
    raised — a compression problem must not block a valid upload.
    """
    ext = ext.lower()
    if ext not in COMPRESSIBLE_IMAGE_EXTENSIONS:
        return os.path.getsize(path)
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not available; skipping image compression for %s", ext)
        return os.path.getsize(path)

    try:
        with Image.open(path) as img:
            img.load()
            original_format = img.format
            if img.mode in ("RGBA", "P") and ext in (".jpg", ".jpeg"):
                img = img.convert("RGB")

            if max(img.size) > MAX_IMAGE_DIMENSION_PX:
                img.thumbnail((MAX_IMAGE_DIMENSION_PX, MAX_IMAGE_DIMENSION_PX), Image.LANCZOS)

            save_kwargs = {}
            if original_format in ("JPEG", "WEBP"):
                save_kwargs = {"quality": JPEG_WEBP_QUALITY, "optimize": True}
            elif original_format == "PNG":
                save_kwargs = {"optimize": True}

            img.save(path, format=original_format, **save_kwargs)
        return os.path.getsize(path)
    except Exception as exc:  # noqa: BLE001 - never let a compression bug block an upload
        logger.warning("Image compression skipped for upload (%s): %s", ext, exc)
        return os.path.getsize(path)


def _maybe_compress_image(temp_path: str, ext: str, size: int) -> int:
    if ext not in COMPRESSIBLE_IMAGE_EXTENSIONS:
        return size
    return compress_image_in_place(temp_path, ext)


def _scan_or_reject(temp_path: str) -> None:
    """Virus-scan a saved temp file; raise ValueError (caught by callers
    the same way as any other upload-validation failure) if it's infected
    or if scanning is enabled but the scanner can't be reached."""
    try:
        with open(temp_path, "rb") as f:
            scan_bytes(f.read())
    except VirusFoundError as exc:
        os.remove(temp_path)
        raise ValueError(f"File rejected: malicious content detected ({exc.signature})") from exc
    except VirusScanUnavailable as exc:
        os.remove(temp_path)
        raise ValueError("File could not be scanned for viruses; please try again later") from exc


def save_attachment(upload: UploadFile) -> Tuple[str, str, int]:
    ext = _validate_upload(upload)
    provider = (settings.STORAGE_PROVIDER or "local").lower()
    max_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
    temp_path, size = _save_to_temp(upload, max_bytes)
    _scan_or_reject(temp_path)
    size = _maybe_compress_image(temp_path, ext, size)

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


__all__ = ["save_attachment", "resolve_attachment_path", "compress_image_in_place"]

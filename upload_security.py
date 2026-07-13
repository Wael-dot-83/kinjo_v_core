"""Reusable archive guardrails for uploaded Office Open XML workbooks."""

from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException


def validate_xlsx_archive(
    data: bytes,
    *,
    max_compressed_bytes: int,
    max_uncompressed_bytes: int = 100 * 1024 * 1024,
    max_members: int = 1_000,
    max_ratio: int = 100,
) -> None:
    """Reject oversized, encrypted, path-traversing, or expansion-heavy XLSX files."""
    if len(data) > max_compressed_bytes:
        raise HTTPException(status_code=413, detail="Uploaded workbook is too large")
    try:
        with ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > max_members:
                raise HTTPException(status_code=413, detail="Workbook contains too many archive members")
            total_compressed = sum(member.compress_size for member in members)
            total_uncompressed = sum(member.file_size for member in members)
            if total_uncompressed > max_uncompressed_bytes:
                raise HTTPException(status_code=413, detail="Expanded workbook is too large")
            if total_uncompressed > max(total_compressed, 1) * max_ratio:
                raise HTTPException(status_code=413, detail="Workbook compression ratio is unsafe")
            for member in members:
                path = PurePosixPath(member.filename)
                if member.flag_bits & 0x1:
                    raise HTTPException(status_code=400, detail="Encrypted workbooks are not supported")
                if path.is_absolute() or ".." in path.parts:
                    raise HTTPException(status_code=400, detail="Workbook contains an unsafe archive path")
    except BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid XLSX archive") from exc

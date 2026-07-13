from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import HTTPException

from upload_security import validate_xlsx_archive


def _archive(member_name: str, payload: bytes) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(member_name, payload)
    return buffer.getvalue()


def test_xlsx_guard_rejects_invalid_archive():
    with pytest.raises(HTTPException) as exc:
        validate_xlsx_archive(b"not-an-xlsx", max_compressed_bytes=1024)
    assert exc.value.status_code == 400


def test_xlsx_guard_rejects_zip_expansion_limit():
    data = _archive("xl/worksheets/sheet1.xml", b"A" * 50_000)
    with pytest.raises(HTTPException) as exc:
        validate_xlsx_archive(
            data,
            max_compressed_bytes=10_000,
            max_uncompressed_bytes=1_000,
        )
    assert exc.value.status_code == 413


def test_xlsx_guard_rejects_path_traversal_member():
    data = _archive("../payload.xml", b"safe-size")
    with pytest.raises(HTTPException) as exc:
        validate_xlsx_archive(data, max_compressed_bytes=10_000)
    assert exc.value.status_code == 400

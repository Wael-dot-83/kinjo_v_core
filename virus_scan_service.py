"""Pluggable upload virus/malware scanning (ClamAV ``clamd`` protocol).

Disabled by default (``VIRUS_SCAN_ENABLED=False``). When enabled, scanning
fails closed: if the scanner cannot be reached, the upload is rejected
rather than silently treated as clean — in every environment, since turning
this on is itself an explicit operator decision.
"""
from __future__ import annotations

import logging
import socket
import struct

from config import settings

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 4096
_INSTREAM_CMD = b"zINSTREAM\0"


class VirusScanUnavailable(Exception):
    """Raised when scanning is enabled but the scanner cannot be reached or errors."""


class VirusFoundError(Exception):
    """Raised when the scanner reports the content is infected."""

    def __init__(self, signature: str):
        self.signature = signature
        super().__init__(f"Malware signature detected: {signature}")


def scanning_required() -> bool:
    """Whether upload scanning should be enforced for this request.

    Always False under the test suite (TESTING=true), mirroring the existing
    TESTING-bypass pattern used elsewhere (database.py, main.py guards).
    """
    return bool(settings.VIRUS_SCAN_ENABLED) and not settings.TESTING


def scan_bytes(content: bytes) -> None:
    """Scan content with ClamAV's clamd INSTREAM protocol.

    No-op when scanning is disabled or under TESTING. Raises
    ``VirusFoundError`` if infected, ``VirusScanUnavailable`` if the scanner
    can't be reached or errors while scanning is enabled — callers must
    treat both as "reject the upload", never as "treat it as clean".
    """
    if not scanning_required():
        return

    provider = (settings.VIRUS_SCAN_PROVIDER or "clamav").lower()
    if provider != "clamav":
        raise VirusScanUnavailable(f"Unsupported VIRUS_SCAN_PROVIDER: {provider}")

    try:
        with socket.create_connection(
            (settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=10
        ) as sock:
            sock.sendall(_INSTREAM_CMD)
            for offset in range(0, len(content), _CHUNK_SIZE):
                chunk = content[offset : offset + _CHUNK_SIZE]
                sock.sendall(struct.pack(">L", len(chunk)) + chunk)
            sock.sendall(struct.pack(">L", 0))
            response = sock.recv(4096).decode("utf-8", errors="replace").strip()
    except OSError as exc:
        logger.error(
            "Virus scan unavailable: could not reach ClamAV at %s:%s (%s)",
            settings.CLAMAV_HOST, settings.CLAMAV_PORT, exc,
        )
        raise VirusScanUnavailable(str(exc)) from exc

    # clamd responses look like "stream: OK" or "stream: Eicar-Test-Signature FOUND"
    if "FOUND" in response:
        signature = response.split(":", 1)[-1].replace("FOUND", "").strip()
        raise VirusFoundError(signature or "unknown")
    if "ERROR" in response:
        raise VirusScanUnavailable(response)
    # else: clean ("OK")


def scan_error_message(lang: str, infected: bool) -> str:
    if infected:
        if lang == "en":
            return "The file was rejected because it contains malicious content."
        return "تم رفض الملف لاحتوائه على محتوى ضار."
    if lang == "en":
        return "The file could not be scanned for viruses right now; please try again later."
    return "تعذّر فحص الملف من الفيروسات حالياً؛ يرجى المحاولة لاحقاً."


__all__ = [
    "scanning_required",
    "scan_bytes",
    "scan_error_message",
    "VirusScanUnavailable",
    "VirusFoundError",
]

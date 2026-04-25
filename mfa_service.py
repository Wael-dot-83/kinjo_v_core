"""TOTP MFA helpers for privileged KinJo users."""

from __future__ import annotations

import base64
import hashlib
import io
import re
from typing import Optional

import pyotp
import qrcode
from cryptography.fernet import Fernet

from config import settings

MFA_CODE_PATTERN = re.compile(r"^\d{6}$")


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_secret: Optional[str]) -> Optional[str]:
    if not encrypted_secret:
        return None
    return _fernet().decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=settings.MFA_TOTP_ISSUER,
    )


def qr_code_data_url(otpauth_uri: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(otpauth_uri)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def verify_code(secret: str, code: str) -> bool:
    normalized = re.sub(r"\s+", "", str(code or ""))
    if not MFA_CODE_PATTERN.fullmatch(normalized):
        return False
    return bool(pyotp.TOTP(secret).verify(normalized, valid_window=1))


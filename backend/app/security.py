"""
HKY Estates V2 - Kimlik doğrulama ve gizli veri koruma
Parolalar scrypt ile özetlenir; API anahtarı ve proxy şifresi veritabanında şifreli durur.
Oturum httpOnly çerezdedir; değiştiren isteklerde özel başlık zorunludur (CSRF).
"""

import base64
import hashlib
import hmac
import os
import re
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

SESSION_COOKIE = "hky_session"
CSRF_HEADER = "x-hky-csrf"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SENSITIVE_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|password|parola|sifre|şifre|authorization)(['\"\s:=]+)(bearer\s+)?([^\s'\",&]+)"
)
URL_CREDENTIALS = re.compile(r"(?i)\b(https?://)[^/\s:@]+:[^/\s@]+@")


def _secret_bytes() -> bytes:
    secret = get_settings().hky_secret_key
    if len(secret) < 32:
        raise RuntimeError("HKY_SECRET_KEY eksik veya kısa. 'python backend/scripts/init_env.py' komutunu çalıştırın.")
    return secret.encode("utf-8")


def _fernet() -> Fernet:
    key = hashlib.sha256(b"hky-encryption:" + _secret_bytes()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None


def redact(text: object) -> str:
    """Log ve hata mesajlarından anahtar, şifre ve URL içi kimlik bilgilerini çıkarır."""
    cleaned = URL_CREDENTIALS.sub(r"\1***:***@", str(text))
    return SENSITIVE_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}***", cleaned)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, derived_hex = stored.split("$")
    except ValueError:
        return False
    derived = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return hmac.compare_digest(derived.hex(), derived_hex)


def _sign(payload: str) -> str:
    key = hashlib.sha256(b"hky-session:" + _secret_bytes()).digest()
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(user: User) -> str:
    expires = int(time.time()) + get_settings().session_hours * 3600
    payload = f"{user.id}.{user.session_version}.{expires}"
    return f"{payload}.{_sign(payload)}"


def _parse_session_token(token: str) -> Optional[tuple]:
    parts = token.split(".")
    if len(parts) != 4:
        return None
    payload, signature = ".".join(parts[:3]), parts[3]
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        user_id, version, expires = (int(part) for part in parts[:3])
    except ValueError:
        return None
    return (user_id, version) if expires > time.time() else None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    parsed = _parse_session_token(request.cookies.get(SESSION_COOKIE, ""))
    user = db.get(User, parsed[0]) if parsed else None
    if user is None or user.session_version != parsed[1]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Oturum açmanız gerekiyor.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Geçersiz istek kaynağı.")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem için yönetici yetkisi gerekiyor.")
    return user

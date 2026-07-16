"""Password hashing, JWT tokens, API key generation & verification."""
import hashlib
import hmac
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from .config import settings

# ---------- Passwords ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------- JWT ----------

def _create_token(payload: dict[str, Any], expires_delta: timedelta, token_type: str) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + expires_delta
    jti = str(uuid.uuid4())
    to_encode = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "type": token_type,
    }
    token = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, jti, exp


def create_access_token(user_id: str, org_id: str, role: str) -> str:
    token, _, _ = _create_token(
        {"sub": user_id, "org_id": org_id, "role": role},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
    )
    return token


def create_refresh_token(user_id: str, org_id: str, role: str, remember_me: bool = False) -> tuple[str, str, datetime]:
    days = settings.REFRESH_TOKEN_EXPIRE_DAYS if remember_me else max(1, settings.REFRESH_TOKEN_EXPIRE_DAYS // 2)
    token, jti, exp = _create_token(
        {"sub": user_id, "org_id": org_id, "role": role},
        timedelta(days=days),
        "refresh",
    )
    return token, jti, exp


# ---------- Device (agent) JWT ----------

def create_device_access_token(device_id: str, org_id: str) -> tuple[str, datetime]:
    """Short-lived JWT the agent presents on every REST/WS call."""
    token, _, exp = _create_token(
        {"sub": device_id, "org_id": org_id, "kind": "device"},
        timedelta(minutes=settings.DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES),
        "device_access",
    )
    return token, exp


def create_device_refresh_token(device_id: str, org_id: str) -> tuple[str, str, datetime]:
    """Long-lived refresh token so a device offline for weeks can come back."""
    token, jti, exp = _create_token(
        {"sub": device_id, "org_id": org_id, "kind": "device"},
        timedelta(days=settings.DEVICE_REFRESH_TOKEN_EXPIRE_DAYS),
        "device_refresh",
    )
    return token, jti, exp


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# ---------- Device API keys ----------

ALPHABET = string.ascii_uppercase + string.digits


def generate_enrollment_code() -> str:
    """Generate a cryptographically-secure pairing code like DT-8A4P-92KD.

    Format: ``DT-XXXX-XXXX``  (fixed 2-char prefix + two 4-char blocks)
    * Uses ``secrets.choice`` (CSPRNG-backed).
    * Uppercase A-Z + 0-9 alphabet -> 32^8 = ~1.1e12 combinations per org.
    * The ``DT-`` prefix makes codes easy to recognise/paste and lets us
      shortcut-detect obvious typos on the agent side.
    """
    def block(n: int) -> str:
        return "".join(secrets.choice(ALPHABET) for _ in range(n))

    return f"DT-{block(4)}-{block(4)}"


def generate_device_api_key() -> str:
    """Return a URL-safe device API key (secret)."""
    return "dtk_" + secrets.token_urlsafe(40)


def hash_api_key(api_key: str) -> str:
    """Deterministic hash for API key lookup (HMAC-SHA256 with JWT_SECRET as key)."""
    return hmac.new(settings.JWT_SECRET.encode("utf-8"), api_key.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_invitation_token() -> str:
    return secrets.token_urlsafe(32)

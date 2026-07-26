"""
JWT-based auth: password hashing + token issuance/verification, fully
free/local (no external auth provider, no paid service).

Password hashing uses the `bcrypt` package directly rather than
passlib -- passlib 1.7.4 (its last release, project is unmaintained)
is incompatible with bcrypt>=4.1 (it probes a now-removed
`bcrypt.__about__.__version__` attribute and throws), which breaks on
this environment's Python 3.14 + bcrypt 5.x install. Calling bcrypt
directly sidesteps that entirely and is the commonly recommended
workaround.

JWTs are signed with HS256 using JWT_SECRET_KEY from the environment.
If that env var is not set, a random per-process key is generated at
import time -- fine for a single local dev process, but tokens won't
validate across process restarts or multiple workers; set
JWT_SECRET_KEY explicitly for anything beyond local single-process use.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

logger = logging.getLogger(__name__)

_env_secret = os.environ.get("JWT_SECRET_KEY")
if not _env_secret:
    logger.warning(
        "JWT_SECRET_KEY not set -- generating a random per-process signing key. "
        "Tokens will NOT remain valid across process restarts or multiple "
        "workers. Set JWT_SECRET_KEY in the environment for anything beyond "
        "a single local dev process."
    )
JWT_SECRET_KEY = _env_secret or secrets.token_urlsafe(48)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24h default

# bcrypt has a hard 72-byte input limit; truncate defensively rather than
# error on unusually long passwords (matches common bcrypt-wrapper behavior).
_BCRYPT_MAX_BYTES = 72

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    hashed = bcrypt.hashpw(raw, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    raw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash (e.g. legacy/blank) -- treat as non-matching, not a crash.
        return False


def create_access_token(user_id: int, expires_minutes: Optional[int] = None) -> str:
    expire_minutes = expires_minutes if expires_minutes is not None else ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise unauthorized

    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user is None or not user.is_active:
        raise unauthorized
    return user

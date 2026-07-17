"""
auth.py — JWT authentication, password hashing, and RBAC for G-Track.

Issues fixed:
  - Issue 1+2: Duplicate `role` field removed; role is now decoded from JWT payload.
  - Issue 3:   No default JWT secret — startup will fail fast if env var is missing.
  - Issue 13:  Added refresh token support (signed JWT, type="refresh") and
               a reusable `require_role()` dependency factory for clean RBAC.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from pwdlib import PasswordHash


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class AuthSettings(BaseSettings):
    # No default — will raise ValidationError at startup if missing.
    # Set JWT_SECRET_KEY in your .env / Render environment variables.
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = AuthSettings()
password_hasher = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")


# ---------------------------------------------------------------------------
# Token payload schema
# ---------------------------------------------------------------------------

class TokenPayload(BaseModel):
    sub: str
    email: str
    role: str = "user"       # single definition — "user" | "distributor" | "admin"
    token_type: str = "access"   # "access" | "refresh"


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    email: str,
    role: str = "user",
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "token_type": "access",
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    email: str,
    role: str = "user",
) -> str:
    """Long-lived signed JWT used to obtain new access tokens.

    The refresh endpoint validates `token_type == "refresh"` so
    refresh tokens cannot be used as access tokens and vice-versa.
    No database storage is needed — the signature provides authenticity.
    """
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "token_type": "refresh",
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Token decoding
# ---------------------------------------------------------------------------

def decode_token(token: str, expected_type: str = "access") -> TokenPayload:
    """Decode and validate a JWT.  Raises 401 on any failure."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        token_type = payload.get("token_type", "access")
        if token_type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type: expected '{expected_type}'",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return TokenPayload(
            sub=payload["sub"],
            email=payload["email"],
            role=payload.get("role", "user"),   # ← role now decoded from JWT
            token_type=token_type,
        )
    except (InvalidTokenError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenPayload:
    """Dependency: decode access token and return the token payload."""
    return decode_token(token, expected_type="access")


def require_role(*roles: str):
    """Dependency factory for role-based access control.

    Usage in a router:
        current_user: Annotated[TokenPayload, Depends(require_role("admin"))]
        current_user: Annotated[TokenPayload, Depends(require_role("admin", "distributor"))]
    """
    async def _dependency(
        current_user: Annotated[TokenPayload, Depends(get_current_user)],
    ) -> TokenPayload:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: requires role {' or '.join(roles)}",
            )
        return current_user

    return _dependency

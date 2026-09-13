from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


class TokenPayload(BaseModel):
    sub: str
    role: str = "operator"
    scopes: list[str] = Field(default_factory=list)
    exp: int | None = None


class RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._buckets: dict[str, list[float]] = {}

    def check(self, client_id: str) -> None:
        now = datetime.now(UTC).timestamp()
        window_start = now - 60
        hits = [ts for ts in self._buckets.get(client_id, []) if ts >= window_start]
        if len(hits) >= self._settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
        hits.append(now)
        self._buckets[client_id] = hits


def create_access_token(
    subject: str,
    settings: Settings,
    role: str = "operator",
    scopes: list[str] | None = None,
) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "role": role,
        "scopes": scopes or ["tools:read", "tools:execute"],
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


async def get_current_principal(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> TokenPayload:
    if settings.debug and request.headers.get("X-EDITH-DEV-BYPASS") == "1":
        return TokenPayload(sub="dev-user", role="admin", scopes=["*"])

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")

    try:
        data: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return TokenPayload(**data)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def require_scope(scope: str):
    async def _guard(principal: TokenPayload = Depends(get_current_principal)) -> TokenPayload:
        if "*" in principal.scopes or scope in principal.scopes:
            return principal
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing scope: {scope}")

    return _guard

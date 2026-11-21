from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request

from .config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, s.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


class RateLimiter:
    """Small in-memory sliding-window limiter (per client IP + bucket)."""

    def __init__(self, limit: int, window_seconds: int, bucket: str):
        self.limit, self.window, self.bucket = limit, window_seconds, bucket
        self.hits: dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        if get_settings().environment == "test":
            return
        key = f"{self.bucket}:{request.client.host if request.client else 'unknown'}"
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Too many requests. Please wait a moment and try again.")
        q.append(now)

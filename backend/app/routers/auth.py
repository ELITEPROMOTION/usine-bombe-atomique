"""Authentification JWT (stub Bootstrap - a durcir)."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.database import get_pool
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserOut

router = APIRouter()
settings = get_settings()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _create_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: UserCreate) -> UserOut:
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", payload.email)
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, email, password_hash, full_name)
            VALUES ($1, $2, $3, $4)
            RETURNING id, email, full_name, role, is_active, created_at
            """,
            uuid4(), payload.email, pwd_ctx.hash(payload.password), payload.full_name,
        )
    return UserOut(**dict(row))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash, is_active FROM users WHERE email = $1",
            payload.email,
        )
    if not row or not row["is_active"] or not pwd_ctx.verify(payload.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenResponse(
        access_token=_create_token(str(row["id"])),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )

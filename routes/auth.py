"""Authentication endpoints — doctors and admins only.

Patients do NOT log in here. They interact exclusively via WhatsApp and are
identified by their phone number from the webhook payload.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from core.dependencies import get_db
from utils.logger import logger

router = APIRouter(tags=["auth"])


# ── Request / response models ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    role: str
    user_id: str
    name: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db=Depends(get_db)):
    """Authenticate a doctor or admin and return JWT tokens.

    TODO: Add WhatsApp OTP / 2FA for admin accounts before production rollout.
    """
    user = await db.get_user_by_email(body.email)

    if not user or not verify_password(body.password, user.get("password_hash", "")):
        logger.warning(f"Failed login attempt for email={body.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact an administrator.",
        )

    token_data = {"user_id": user["user_id"], "role": user["role"]}
    logger.info(f"Successful login: user_id={user['user_id']} role={user['role']}")

    return LoginResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        role=user["role"],
        user_id=user["user_id"],
        name=user["name"],
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(body: RefreshRequest):
    """Issue a new access token from a valid refresh token."""
    payload = decode_token(body.refresh_token)

    if payload.get("token_type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token",
        )

    token_data = {k: v for k, v in payload.items() if k not in ("exp", "token_type")}
    return AccessTokenResponse(access_token=create_access_token(token_data))

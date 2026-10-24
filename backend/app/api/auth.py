"""
Authentication & User Session Router for EquityVal AI (Firestore + PBKDF2-HMAC-SHA256 + Signed Bearer Tokens).

Supports:
- `POST /api/auth/register`: Create a new compliance analyst / homeowner / loan officer account with
  PBKDF2-HMAC-SHA256 password hashing, persisted in Google Cloud Firestore (`users` collection).
- `POST /api/auth/login`: Authenticate existing account and issue a signed bearer token.
- `GET /api/auth/me`: Return authenticated user's profile and subscription tier.
- `POST /api/auth/sync`: Sync Firebase Auth login into Firestore.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, Field

from app.models.schemas import UserPlan, UserRecord
from app.services.store import DEFAULT_DEMO_USER_ID, db_store

router = APIRouter(prefix="/api/auth", tags=["auth"])

AUTH_SECRET = os.getenv("EQUITYVAL_AUTH_SECRET", "equityval-ai-prod-hmac-secret-key-2026")


class FirebaseSyncRequest(BaseModel):
    email: str = Field(..., min_length=3)
    firebase_uid: Optional[str] = None
    id_token_jwt: Optional[str] = None
    plan: UserPlan = UserPlan.TRIAL


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    full_name: str = Field(default="Fair Lending & ROV Compliance Analyst", min_length=2)
    license_or_nmls_id: Optional[str] = Field(default="NMLS-ROV-884120")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRecord


def _uid_to_uuid(uid_str: str) -> UUID:
    try:
        return UUID(uid_str)
    except ValueError:
        digest = hashlib.md5(uid_str.encode("utf-8")).hexdigest()
        return UUID(digest)


def _hash_password(password: str, email: str) -> str:
    salt = f"equityval:{email.strip().lower()}".encode("utf-8")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return dk.hex()


def _create_signed_token(user_id: UUID) -> str:
    uid_str = str(user_id)
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), uid_str.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"equityval-token-{uid_str}.{sig}"


def _verify_signed_token(token: str) -> Optional[UUID]:
    if not token.startswith("equityval-token-") or "." not in token:
        return None
    body = token[len("equityval-token-") :]
    uid_str, sig = body.rsplit(".", 1)
    expected_sig = hmac.new(AUTH_SECRET.encode("utf-8"), uid_str.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        return UUID(uid_str)
    except ValueError:
        return None


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    x_firebase_email: Optional[str] = Header(default=None),
) -> UserRecord:
    """
    FastAPI dependency resolving the current authenticated user via signed bearer token
    or Firebase ID Token (or defaulting to the seeded demo analyst when unauthenticated).
    """
    if not authorization:
        user = db_store.get_user(DEFAULT_DEMO_USER_ID)
        if user:
            return user
        return db_store.upsert_user(
            UserRecord(id=DEFAULT_DEMO_USER_ID, email="analyst@equityval.ai", plan=UserPlan.PRO_MONTHLY)
        )

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'.",
        )

    token = parts[1].strip()

    # 1. Check EquityVal HMAC-signed session token
    verified_uid = _verify_signed_token(token)
    if verified_uid is not None:
        existing = db_store.get_user(verified_uid)
        if existing:
            return existing
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User session not found.")

    # 2. Check Firebase ID token in production
    firebase_project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if firebase_project_id and not token.startswith("dev-token-"):
        try:
            claims = id_token.verify_firebase_token(
                token,
                google_requests.Request(),
                audience=firebase_project_id,
            )
            uid = _uid_to_uuid(claims.get("sub") or claims.get("user_id", str(DEFAULT_DEMO_USER_ID)))
            email = claims.get("email", x_firebase_email or "analyst@equityval.ai")
            existing = db_store.get_user(uid)
            if existing:
                return existing
            return db_store.upsert_user(UserRecord(id=uid, email=email, plan=UserPlan.TRIAL))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification failed: {exc}",
            ) from exc

    # 3. Local dev / test token handling ("dev-token-<uid>")
    uid = _uid_to_uuid(token.replace("dev-token-", ""))
    existing = db_store.get_user(uid)
    if existing:
        return existing
    return db_store.upsert_user(
        UserRecord(
            id=uid,
            email=x_firebase_email or "analyst@equityval.ai",
            plan=UserPlan.PRO_MONTHLY,
        )
    )


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register_account(req: RegisterRequest) -> AuthTokenResponse:
    """Create a new user account in Firestore and return a signed bearer token."""
    email_norm = req.email.strip().lower()
    existing = db_store.get_user_by_email(email_norm)
    if existing and existing.password_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please sign in.",
        )

    uid = existing.id if existing else _uid_to_uuid(email_norm)
    pw_hash = _hash_password(req.password, email_norm)
    new_user = UserRecord(
        id=uid,
        email=email_norm,
        full_name=req.full_name.strip(),
        license_or_nmls_id=req.license_or_nmls_id,
        password_hash=pw_hash,
        plan=UserPlan.TRIAL,
    )
    saved_user = db_store.upsert_user(new_user)
    token = _create_signed_token(saved_user.id)
    return AuthTokenResponse(access_token=token, user=saved_user)


@router.post("/login", response_model=AuthTokenResponse)
def login_account(req: LoginRequest) -> AuthTokenResponse:
    """Authenticate an existing account with email & password."""
    email_norm = req.email.strip().lower()
    user = db_store.get_user_by_email(email_norm)
    expected_hash = _hash_password(req.password, email_norm)
    if not user or (user.password_hash and not hmac.compare_digest(user.password_hash, expected_hash)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    token = _create_signed_token(user.id)
    return AuthTokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserRecord)
def get_my_profile(current_user: UserRecord = Depends(get_current_user)) -> UserRecord:
    """Return the authenticated user's Firestore profile and active subscription tier."""
    return current_user


@router.post("/sync", response_model=UserRecord)
def sync_firebase_user(req: FirebaseSyncRequest) -> UserRecord:
    """Sync a Firebase Auth user login into the Google Cloud Firestore `users` collection."""
    existing = db_store.get_user_by_email(req.email)
    if existing:
        return existing
    uid = _uid_to_uuid(req.firebase_uid or req.email)
    new_user = UserRecord(
        id=uid,
        email=req.email.strip().lower(),
        plan=req.plan,
    )
    return db_store.upsert_user(new_user)

"""
auth.py — Lightweight user authentication for Buyera AI
=========================================================

Design
------
- Users stored in MongoDB `users` collection
- Passwords hashed with bcrypt (no plaintext ever stored)
- Login returns a signed token: base64(user_id:timestamp:hmac)
  — no JWT library needed, just hashlib + hmac
- Token is passed as X-User-Token header on every request
- FastAPI dependency `get_current_user` validates the token

No third-party auth library required — only `bcrypt` (pip install bcrypt).
"""

import os
import hmac
import hashlib
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

# Secret used for HMAC token signing — set TOKEN_SECRET in .env
_SECRET = os.getenv("TOKEN_SECRET", "buyera-default-secret-change-me").encode()

# Token lifetime in days
TOKEN_DAYS = int(os.getenv("TOKEN_DAYS", "30"))


# ---------------------------------------------------------------------------
# Lazy import of users_collection to avoid circular imports
# ---------------------------------------------------------------------------

def _users_col():
    try:
        from .database import users_collection
    except ImportError:
        from database import users_collection
    return users_collection


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _sign(user_id: str, ts: str) -> str:
    msg = f"{user_id}:{ts}".encode()
    return hmac.new(_SECRET, msg, hashlib.sha256).hexdigest()


def create_token(user_id: str) -> str:
    """Return a URL-safe token string."""
    ts  = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    sig = _sign(user_id, ts)
    raw = f"{user_id}:{ts}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_token(token: str) -> Optional[str]:
    """
    Validate token and return user_id, or None if invalid/expired.
    """
    try:
        raw     = base64.urlsafe_b64decode(token.encode()).decode()
        parts   = raw.split(":")
        if len(parts) != 3:
            return None
        user_id, ts, sig = parts
        # Verify signature
        expected = _sign(user_id, ts)
        if not hmac.compare_digest(sig, expected):
            return None
        # Check expiry
        created = datetime.strptime(ts, "%Y%m%d%H%M%S")
        if datetime.utcnow() - created > timedelta(days=TOKEN_DAYS):
            return None
        return user_id
    except Exception:
        return None


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def register_user(username: str, password: str, email: str = "") -> dict:
    """
    Create a new user. Returns the user doc (without password).
    Raises ValueError if username already exists.
    """
    col = _users_col()
    username = username.strip().lower()
    if not username or len(username) < 3:
        raise ValueError("Username must be at least 3 characters")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    existing = col.find_one({"username": username})
    if existing:
        raise ValueError(f"Username '{username}' already exists")

    user_id = __import__("uuid").uuid4().hex
    doc = {
        "user_id":    user_id,
        "username":   username,
        "email":      email.strip().lower(),
        "password":   hash_password(password),
        "created_at": datetime.utcnow(),
        "role":       "user",           # "admin" role can see all leads
    }
    col.insert_one(doc)
    logger.info("New user registered: %s (%s)", username, user_id)
    return {"user_id": user_id, "username": username, "email": doc["email"]}


def login_user(username: str, password: str) -> dict:
    """
    Validate credentials. Returns {user_id, username, token} or raises ValueError.
    """
    col      = _users_col()
    username = username.strip().lower()
    user     = col.find_one({"username": username})

    if not user or not verify_password(password, user.get("password", "")):
        raise ValueError("Invalid username or password")

    token = create_token(user["user_id"])
    return {
        "user_id":  user["user_id"],
        "username": user["username"],
        "token":    token,
        "role":     user.get("role", "user"),
    }


def get_user_by_id(user_id: str) -> Optional[dict]:
    col  = _users_col()
    user = col.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    return user


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_current_user(x_user_token: str = Header(default="")) -> dict:
    """
    FastAPI dependency — validates X-User-Token header.
    Returns user dict or raises 401.
    """
    if not x_user_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Token header missing",
        )
    user_id = decode_token(x_user_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
        )
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def get_optional_user(x_user_token: str = Header(default="")) -> Optional[dict]:
    """
    Same as get_current_user but returns None instead of raising 401.
    Useful for endpoints that work both with and without auth.
    """
    if not x_user_token:
        return None
    user_id = decode_token(x_user_token)
    if not user_id:
        return None
    return get_user_by_id(user_id)

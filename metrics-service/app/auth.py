"""
JWT Authentication

Verifies tokens issued by the Next.js frontend.
Uses the same secret to ensure interoperability.
"""

import os
from typing import Optional
from fastapi import HTTPException, Header, status
from jose import jwt, JWTError
from pydantic import BaseModel


JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"


class UserPayload(BaseModel):
    """User information extracted from a valid JWT."""
    email: str
    name: str
    role: str


def verify_token(token: str) -> UserPayload:
    """
    Decode and validate a JWT.
    Raises HTTPException if invalid or expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )

    # Validate required fields
    required_fields = {"email", "name", "role"}
    if not required_fields.issubset(payload.keys()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required fields",
        )

    return UserPayload(
        email=payload["email"],
        name=payload["name"],
        role=payload["role"],
    )


def get_current_user(
    authorization: Optional[str] = Header(None),
) -> UserPayload:
    """
    FastAPI dependency: extracts and verifies the user from the
    Authorization header.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'",
        )

    token = authorization[len("Bearer "):]
    return verify_token(token)
"""Unit tests for app.auth — JWT verification + Bearer header parsing.
Pure logic: no Databricks, no network. Uses the same JWT_SECRET the suite sets."""
import os
import time

import pytest
from fastapi import HTTPException
from jose import jwt

from app.auth import verify_token, get_current_user, JWT_ALGORITHM

SECRET = os.environ["JWT_SECRET"]  # set in conftest.py


def _make_token(payload: dict, secret: str = SECRET) -> str:
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def _valid_payload(**over):
    p = {"email": "a@x.com", "name": "Test User", "role": "viewer"}
    p.update(over)
    return p


def test_valid_token_returns_user():
    user = verify_token(_make_token(_valid_payload()))
    assert user.email == "a@x.com"
    assert user.role == "viewer"


def test_admin_role_preserved():
    user = verify_token(_make_token(_valid_payload(role="admin")))
    assert user.role == "admin"


def test_expired_token_rejected():
    token = _make_token(_valid_payload(exp=int(time.time()) - 10))
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401


def test_wrong_signature_rejected():
    token = _make_token(_valid_payload(), secret="a-different-secret")
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401


def test_tampered_token_rejected():
    token = _make_token(_valid_payload())
    with pytest.raises(HTTPException):
        verify_token(token[:-3] + "abc")


@pytest.mark.parametrize("missing", ["email", "name", "role"])
def test_missing_required_field_rejected(missing):
    payload = _valid_payload()
    del payload[missing]
    with pytest.raises(HTTPException) as exc:
        verify_token(_make_token(payload))
    assert exc.value.status_code == 401


def test_get_current_user_missing_header():
    with pytest.raises(HTTPException) as exc:
        get_current_user(authorization=None)
    assert exc.value.status_code == 401


def test_get_current_user_non_bearer():
    with pytest.raises(HTTPException) as exc:
        get_current_user(authorization="Token abc")
    assert exc.value.status_code == 401


def test_get_current_user_happy_path():
    token = _make_token(_valid_payload(role="admin"))
    user = get_current_user(authorization=f"Bearer {token}")
    assert user.role == "admin"
"""Tests for authentication, tokens, API keys and role based access control."""

from __future__ import annotations

import datetime as dt

import pytest

from app.api.security import (
    ROLE_RIGHTS,
    at_least,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    has_right,
    needs_rehash,
    password_strength,
    require_right,
    verify_api_key,
    verify_password,
)
from app.core.errors import AuthenticationError, PermissionDeniedError


# --------------------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------------------
def test_hash_and_verify_round_trip():
    hashed = hash_password("Str0ng-Passw0rd!")
    assert hashed != "Str0ng-Passw0rd!"
    assert verify_password("Str0ng-Passw0rd!", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_hash_is_salted_so_two_hashes_differ():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_handles_a_corrupted_hash():
    assert verify_password("x", "not-a-hash") is False
    assert needs_rehash("not-a-hash") is False


@pytest.mark.parametrize(
    ("password", "valid"),
    [
        ("Str0ng-Passw0rd!", True),
        ("short1!A", False),
        ("alllowercase!!!", False),
        ("ALLUPPERCASE!!!", False),
        ("NoDigitsHere!!", False),
        ("NoSymbols12345", False),
    ],
)
def test_password_strength_gate(password, valid):
    assert password_strength(password)[0] is valid


def test_password_strength_reports_problems():
    valid, problems = password_strength("abc")
    assert not valid and len(problems) >= 3


# --------------------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------------------
def test_access_token_round_trip():
    token = create_access_token(7, role="analyst", email="a@b.com")
    payload = decode_token(token)
    assert payload["sub"] == "7"
    assert payload["role"] == "analyst"
    assert payload["type"] == "access"


def test_refresh_token_cannot_be_used_as_access_token():
    token = create_refresh_token(7)
    assert decode_token(token, expected_type="refresh")["type"] == "refresh"
    with pytest.raises(AuthenticationError):
        decode_token(token, expected_type="access")


def test_expired_token_is_rejected():
    token = create_access_token(1, expires_minutes=-1)
    with pytest.raises(AuthenticationError) as error:
        decode_token(token)
    assert error.value.details.get("reason") == "expired"


def test_garbage_token_is_rejected():
    with pytest.raises(AuthenticationError):
        decode_token("not.a.token")


def test_token_carries_extra_claims():
    token = create_access_token(3, role="admin", extra_claims={"scope": "read"})
    assert decode_token(token)["scope"] == "read"


# --------------------------------------------------------------------------------------
# API keys
# --------------------------------------------------------------------------------------
def test_api_key_generation_is_verifiable_and_prefixed():
    plain, prefix, hashed = generate_api_key()
    assert plain.startswith("pip_")
    assert plain.startswith(prefix)
    assert hashed == hash_api_key(plain)
    assert verify_api_key(plain, hashed) is True
    assert verify_api_key("pip_other", hashed) is False


def test_api_keys_are_unique():
    assert generate_api_key()[0] != generate_api_key()[0]


# --------------------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("role", "right", "allowed"),
    [
        ("viewer", "read", True),
        ("viewer", "write", False),
        ("viewer", "run_pipeline", False),
        ("analyst", "write", True),
        ("analyst", "run_pipeline", True),
        ("analyst", "manage_users", False),
        ("admin", "manage_users", True),
        ("admin", "manage_settings", True),
        ("unknown", "read", False),
    ],
)
def test_has_right_matrix(role, right, allowed):
    assert has_right(role, right) is allowed


def test_require_right_raises_for_missing_permission():
    with pytest.raises(PermissionDeniedError) as error:
        require_right("viewer", "manage_users")
    assert "manage_users" in error.value.details["required"]


def test_require_right_passes_for_granted_permission():
    assert require_right("admin", "manage_users") is None


def test_role_levels_are_ordered():
    assert at_least("admin", "analyst") is True
    assert at_least("analyst", "viewer") is True
    assert at_least("viewer", "analyst") is False


def test_every_role_has_a_permission_set():
    assert set(ROLE_RIGHTS) == {"admin", "analyst", "viewer"}
    assert all(ROLE_RIGHTS.values())

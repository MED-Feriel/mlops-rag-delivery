"""Tests unitaires de l'authentification (token + dépendance principal)."""

import time

import jwt
import pytest
from fastapi import HTTPException

from config.settings import Settings
from src.api import auth


def _settings(**overrides) -> Settings:
    base = dict(
        auth_enabled=True,
        jwt_secret="secret-test-au-moins-32-caracteres!!",
        jwt_algorithm="HS256",
        jwt_expiry_min=60,
        admin_username="admin",
        admin_password="pw",
        api_service_token="svc-token",
    )
    base.update(overrides)
    return Settings(**base)


class _Creds:
    """Simule HTTPAuthorizationCredentials (attribut .credentials)."""

    def __init__(self, token: str):
        self.credentials = token


class _Req:
    """Simule fastapi.Request : headers (dict) + state (objet libre)."""

    def __init__(self, headers=None):
        self.headers = headers or {}
        self.state = type("S", (), {})()


def test_create_and_decode_token_roundtrip():
    s = _settings()
    tok = auth.create_access_token("alice", ["user"], s)
    payload = auth._decode_token(tok, s)
    assert payload["sub"] == "alice"
    assert payload["roles"] == ["user"]
    assert payload["exp"] > time.time()


@pytest.mark.asyncio
async def test_auth_disabled_returns_anonymous(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(auth_enabled=False))
    p = await auth.get_current_principal(_Req(), None)
    assert p.id == "anonymous"
    assert "admin" in p.roles


@pytest.mark.asyncio
async def test_missing_token_raises_401(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings())
    with pytest.raises(HTTPException) as exc:
        await auth.get_current_principal(_Req(), None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_service_token_accepted(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings())
    p = await auth.get_current_principal(_Req(), _Creds("svc-token"))
    assert p.id == "service" and "service" in p.roles


@pytest.mark.asyncio
async def test_api_key_accepted(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: _settings(api_keys={"rag_k": {"name": "svc", "roles": ["service"]}}),
    )
    p = await auth.get_current_principal(_Req({"X-API-Key": "rag_k"}), None)
    assert p.kind == "service" and "service" in p.roles


@pytest.mark.asyncio
async def test_valid_jwt_accepted(monkeypatch):
    s = _settings()
    monkeypatch.setattr(auth, "get_settings", lambda: s)
    tok = auth.create_access_token("bob", ["admin"], s)
    p = await auth.get_current_principal(_Req(), _Creds(tok))
    assert p.id == "bob" and p.roles == ["admin"]


@pytest.mark.asyncio
async def test_invalid_jwt_rejected(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings())
    with pytest.raises(HTTPException) as exc:
        await auth.get_current_principal(_Req(), _Creds("pas-un-jwt"))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_jwt_rejected(monkeypatch):
    s = _settings()
    monkeypatch.setattr(auth, "get_settings", lambda: s)
    now = int(time.time())
    expired = jwt.encode(
        {"sub": "x", "roles": ["user"], "iat": now - 7200, "exp": now - 3600},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    with pytest.raises(HTTPException) as exc:
        await auth.get_current_principal(_Req(), _Creds(expired))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_ok_returns_token(monkeypatch):
    s = _settings()
    monkeypatch.setattr(auth, "get_settings", lambda: s)

    class _Form:
        username = "admin"
        password = "pw"

    out = await auth.login(_Form())
    assert out["token_type"] == "bearer"
    payload = auth._decode_token(out["access_token"], s)
    assert payload["sub"] == "admin" and payload["roles"] == ["admin"]


@pytest.mark.asyncio
async def test_login_bad_credentials_401(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings())

    class _Form:
        username = "admin"
        password = "mauvais"

    with pytest.raises(HTTPException) as exc:
        await auth.login(_Form())
    assert exc.value.status_code == 401

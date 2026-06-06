"""Tests unitaires de l'auth étendue : JWT+rôles, clés API, RBAC (MLOPS-117)."""

from config.settings import Settings
from src.api import auth


def _settings(**kw):
    return Settings(jwt_secret="x" * 32, **kw)


def test_jwt_roundtrip_carries_roles():
    s = _settings()
    token = auth.create_access_token("alice", ["admin"], s)
    payload = auth._decode_token(token, s)
    assert payload["sub"] == "alice"
    assert payload["roles"] == ["admin"]


def test_users_registry_maps_roles():
    s = _settings(
        admin_username="adm",
        admin_password="p1",
        readonly_username="ro",
        readonly_password="p2",
    )
    users = auth._users(s)
    assert users["adm"]["roles"] == ["admin"]
    assert users["ro"]["roles"] == ["user"]


def test_api_key_create_verify_list_revoke():
    s = _settings()
    key, rec = auth.create_api_key("svc-x", ["service"])
    assert key.startswith("rag_")
    assert auth.verify_api_key(key, s)["name"] == "svc-x"
    assert rec["id"] in [k["id"] for k in auth.list_api_keys(s)]
    assert auth.revoke_api_key(rec["id"]) is True
    assert auth.verify_api_key(key, s) is None  # révoquée


def test_api_key_from_settings():
    s = _settings(api_keys={"rag_fixed": {"name": "cfg", "roles": ["service"]}})
    assert auth.verify_api_key("rag_fixed", s)["name"] == "cfg"
    assert auth.verify_api_key("inconnue", s) is None


def test_cors_origins_accepts_csv():
    s = _settings(cors_origins="http://a.local, http://b.local")
    assert s.cors_origins == ["http://a.local", "http://b.local"]

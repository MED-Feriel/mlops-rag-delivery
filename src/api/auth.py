"""Authentification & autorisation de l'API RAG — MLOPS-117.

Étend l'auth PyJWT initiale avec : clés API (en-tête ``X-API-Key``), RBAC par
rôles, rate limiting par identité et audit logging.

Modes d'identification (route protégée) :
  1. **Clé API** — en-tête ``X-API-Key: <clé>`` (service-à-service, rôles définis
     par la clé).
  2. **JWT utilisateur** — ``Authorization: Bearer <token>`` obtenu via
     ``POST /auth/token`` (le token porte les rôles).
  3. **Jeton de service** statique ``API_SERVICE_TOKEN`` → rôle ``service``.

Rôles : ``admin`` (tout), ``user`` (query/chat), ``service`` (machine-to-machine).
Auth désactivée (``AUTH_ENABLED=false``) → principal ``anonymous`` avec tous les
rôles (démo). ``/health`` et ``/metrics`` restent publics.

Prod : changer JWT_SECRET / mots de passe, hacher les mots de passe
(passlib/bcrypt), et persister les clés API (ici : settings + store mémoire).
"""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass, field

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from config.settings import Settings, get_settings
from src.api.audit import log_api_access
from src.api.rate_limit import limit_for_roles, limiter

log = structlog.get_logger()

API_KEY_NAME = "X-API-Key"

# auto_error=False : on gère nous-mêmes l'absence de token (court-circuit si
# l'auth est désactivée, ou si une clé API est fournie à la place).
_bearer = HTTPBearer(auto_error=False)

router = APIRouter(tags=["auth"])


@dataclass
class Principal:
    """Identité authentifiée de l'appelant + ses rôles."""

    id: str
    kind: str  # "user" | "service" | "anonymous"
    roles: list[str] = field(default_factory=list)


# ── Clés API : store mémoire (créées au runtime) + clés du fichier settings ──
_RUNTIME_API_KEYS: dict[str, dict] = {}


def verify_api_key(key: str, settings: Settings) -> dict | None:
    """Retourne {name, roles, id} si la clé est connue, sinon None."""
    rec = _RUNTIME_API_KEYS.get(key) or (settings.api_keys or {}).get(key)
    return rec


def create_api_key(name: str, roles: list[str]) -> tuple[str, dict]:
    """Génère une nouvelle clé API (stockée en mémoire). À persister en prod."""
    key = "rag_" + secrets.token_urlsafe(24)
    rec = {"name": name, "roles": roles or ["service"], "id": key[:12]}
    _RUNTIME_API_KEYS[key] = rec
    return key, rec


def list_api_keys(settings: Settings) -> list[dict]:
    """Liste les clés (sans exposer le secret complet)."""
    out = []
    merged = {**(settings.api_keys or {}), **_RUNTIME_API_KEYS}
    for key, rec in merged.items():
        out.append(
            {
                "id": rec.get("id", key[:12]),
                "name": rec.get("name"),
                "roles": rec.get("roles", []),
                "source": "runtime" if key in _RUNTIME_API_KEYS else "config",
            }
        )
    return out


def revoke_api_key(key_id: str) -> bool:
    """Révoque une clé runtime par son id (ou sa valeur). True si supprimée."""
    for key, rec in list(_RUNTIME_API_KEYS.items()):
        if rec.get("id") == key_id or key == key_id:
            del _RUNTIME_API_KEYS[key]
            return True
    return False


# ── JWT ──────────────────────────────────────────────────────────────────
def create_access_token(subject: str, roles: list[str], settings: Settings) -> str:
    """Crée un JWT signé HS256 avec ``sub``, ``roles`` et expiration."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "roles": roles,
        "iat": now,
        "exp": now + settings.jwt_expiry_min * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str, settings: Settings) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def _users(settings: Settings) -> dict[str, dict]:
    """Registre des utilisateurs autorisés → mot de passe + rôles."""
    return {
        settings.admin_username: {
            "password": settings.admin_password,
            "roles": ["admin"],
        },
        settings.readonly_username: {
            "password": settings.readonly_password,
            "roles": ["user"],
        },
    }


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Résout l'identité de l'appelant (clé API ou Bearer) ou lève 401.

    Pose aussi ``request.state.principal`` pour le middleware d'audit.
    """
    settings = get_settings()

    if not settings.auth_enabled:
        principal = Principal("anonymous", "anonymous", ["admin", "user", "service"])
        request.state.principal = principal
        return principal

    # 1) Clé API (en-tête X-API-Key).
    api_key = request.headers.get(API_KEY_NAME)
    if api_key:
        rec = verify_api_key(api_key, settings)
        if not rec:
            raise _unauthorized("Clé API invalide")
        principal = Principal(
            rec.get("name", "api-key"), "service", rec.get("roles", ["service"])
        )
        request.state.principal = principal
        return principal

    # 2) Bearer (jeton de service statique, ou JWT utilisateur).
    if creds is None or not creds.credentials:
        raise _unauthorized("Authentification manquante")
    token = creds.credentials

    if settings.api_service_token and hmac.compare_digest(
        token, settings.api_service_token
    ):
        principal = Principal("service", "service", ["service"])
        request.state.principal = principal
        return principal

    try:
        payload = _decode_token(token, settings)
        principal = Principal(
            str(payload.get("sub", "user")),
            "user",
            list(payload.get("roles", ["user"])),
        )
        request.state.principal = principal
        return principal
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expiré")
    except jwt.PyJWTError:
        raise _unauthorized("Token invalide")


def require_roles(*required: str):
    """Fabrique une dépendance : auth + RBAC (un des ``required``) + rate-limit.

    Émet un événement d'audit sur refus (403) et applique la limite de débit
    propre au rôle du principal (429 si dépassée).
    """

    async def checker(
        request: Request,
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if required and not any(r in principal.roles for r in required):
            log_api_access(
                request=request,
                user_id=principal.id,
                action="rbac_denied",
                resource=request.url.path,
                status_code=403,
                details={"required": list(required), "roles": principal.roles},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission refusée (rôle insuffisant)",
            )

        settings = get_settings()
        limit = limit_for_roles(principal.roles, settings)
        allowed, retry_after = limiter.check(principal.id, limit)
        if not allowed:
            log_api_access(
                request=request,
                user_id=principal.id,
                action="rate_limited",
                resource=request.url.path,
                status_code=429,
                details={"limit_per_min": limit},
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Limite de débit dépassée ({limit}/min)",
                headers={"Retry-After": str(retry_after)},
            )
        return principal

    return checker


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/token")
async def login(form: LoginRequest) -> dict:
    """Login (username/password JSON) → JWT portant les rôles de l'utilisateur."""
    settings = get_settings()
    users = _users(settings)
    rec = users.get(form.username)
    # Comparaison à temps constant même si l'utilisateur n'existe pas.
    expected = rec["password"] if rec else ""
    ok = rec is not None and hmac.compare_digest(form.password, expected)
    if not ok:
        log.warning("[auth] login échoué", user=form.username)
        raise _unauthorized("Identifiants invalides")
    token = create_access_token(form.username, rec["roles"], settings)
    log.info("[auth] login OK", user=form.username, roles=rec["roles"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expiry_min * 60,
        "roles": rec["roles"],
    }

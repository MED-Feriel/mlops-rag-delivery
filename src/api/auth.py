"""Authentification JWT de l'API RAG — Bearer token + login OAuth2.

Activée via ``AUTH_ENABLED=true`` (désactivée par défaut pour la démo locale et
l'intégration Open WebUI). Deux modes d'identification acceptés sur les routes
protégées (en-tête ``Authorization: Bearer <token>``) :

  1. **JWT utilisateur** — obtenu via ``POST /auth/token`` (login/mot de passe).
  2. **Jeton de service** — valeur statique ``API_SERVICE_TOKEN`` pour les appels
     service-à-service (ex: Open WebUI configuré avec ce jeton comme clé API).

Les routes de monitoring (``/health``, ``/metrics``) restent publiques.
En production : changer ``JWT_SECRET`` et ``AUTH_PASSWORD``, et de préférence
hacher le mot de passe (passlib/bcrypt) plutôt que la comparaison directe.
"""

from __future__ import annotations

import hmac
import time

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from config.settings import Settings, get_settings

log = structlog.get_logger()

# auto_error=False : on gère nous-mêmes le cas "pas de token" pour pouvoir
# court-circuiter quand l'auth est désactivée.
_bearer = HTTPBearer(auto_error=False)

router = APIRouter(tags=["auth"])


def create_access_token(subject: str, settings: Settings) -> str:
    """Crée un JWT signé HS256 avec ``sub`` et expiration."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + settings.jwt_expiry_min * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str, settings: Settings) -> dict:
    """Décode et valide un JWT (lève ``jwt.PyJWTError`` si invalide/expiré)."""
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )


async def get_current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Dépendance FastAPI : renvoie l'identité de l'appelant ou lève 401.

    - Auth désactivée → renvoie ``"anonymous"`` sans contrôle (démo).
    - Jeton == ``api_service_token`` → ``"service"`` (Open WebUI / service).
    - Sinon JWT valide → la valeur de ``sub``.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        return "anonymous"

    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creds.credentials

    # 1) Jeton de service statique (comparaison à temps constant).
    if settings.api_service_token and hmac.compare_digest(
        token, settings.api_service_token
    ):
        return "service"

    # 2) JWT utilisateur.
    try:
        payload = _decode_token(token, settings)
        return str(payload.get("sub", "user"))
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/token")
async def login(form: LoginRequest) -> dict:
    """Login (username/password en JSON) → JWT.

    Corps attendu : ``{"username": "...", "password": "..."}``. Identifiants
    vérifiés en temps constant contre ``AUTH_USERNAME`` / ``AUTH_PASSWORD``.
    Renvoie un ``access_token`` Bearer. (JSON plutôt que form OAuth2 pour éviter
    la dépendance python-multipart.)
    """
    settings = get_settings()
    ok_user = hmac.compare_digest(form.username, settings.auth_username)
    ok_pass = hmac.compare_digest(form.password, settings.auth_password)
    if not (ok_user and ok_pass):
        log.warning("[auth] login échoué", user=form.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(form.username, settings)
    log.info("[auth] login OK", user=form.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expiry_min * 60,
    }

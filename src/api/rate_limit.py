"""Rate limiting par principal (fenêtre fixe en mémoire) — MLOPS-117.

Limite le nombre de requêtes/minute par **identité** (user_id du token ou nom de
la clé API), avec une limite qui dépend du **rôle** (admin > service > user). On
prend la limite la plus permissive parmi les rôles du principal.

Store en mémoire → compteur PAR RÉPLIQUE. Pour un déploiement multi-pods,
remplacer par Redis (INCR + EXPIRE sur une clé par principal/fenêtre).
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, window_sec: int = 60):
        self.window = window_sec
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, now: float | None = None) -> tuple[bool, int]:
        """Incrémente le compteur de ``key`` et dit s'il reste sous ``limit``.

        Retourne ``(autorisé, retry_after_sec)``. ``limit <= 0`` → illimité.
        """
        if limit <= 0:
            return True, 0
        now = time.time() if now is None else now
        with self._lock:
            start, count = self._buckets.get(key, (now, 0))
            if now - start >= self.window:  # fenêtre expirée → reset
                start, count = now, 0
            count += 1
            self._buckets[key] = (start, count)
            if count > limit:
                retry = int(self.window - (now - start)) + 1
                return False, max(retry, 1)
            return True, 0


def limit_for_roles(roles: list[str], settings) -> int:
    """Limite/min applicable = la plus permissive parmi les rôles du principal."""
    mapping = {
        "admin": settings.rate_limit_admin,
        "service": settings.rate_limit_service,
        "user": settings.rate_limit_user,
    }
    applicable = [mapping[r] for r in roles if r in mapping]
    return max(applicable) if applicable else settings.rate_limit_user


# Limiteur partagé par l'API (un par process).
limiter = RateLimiter(window_sec=60)

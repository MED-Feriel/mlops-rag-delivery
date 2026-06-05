"""Cache Redis (synchrone) pour les embeddings de questions.

Principe (cache-aside) :
    clé    = "emb:" + sha256(question.strip().lower())[:16]
    valeur = vecteur sérialisé JSON (liste de 384 floats)
    TTL    = 1h par défaut → les questions récurrentes sont servies sans recompute.

Le hash sha256 normalise casse + espaces (« Quels retards ? » == « quels retards ? »)
et reste court (16 hex) pour des clés Redis légères.

Implémentation **synchrone** : ``RetrievalService.retrieve()`` est synchrone et
``redis-py`` l'est aussi — pas besoin d'``async``/``run_in_executor``. Le cache
est TOUJOURS optionnel : toute erreur Redis retombe silencieusement sur le calcul
direct (jamais d'exception propagée). Les questions vides ou < 3 caractères ne
sont jamais mises en cache.

Stats hit/miss/error stockées dans Redis (hash ``emb:stats``) → partagées entre
tous les workers/pipelines pointant sur le même Redis, exposées via /cache/stats.
"""

from __future__ import annotations

import hashlib
import json

import structlog

log = structlog.get_logger()


class EmbeddingCache:

    KEY_PREFIX = "emb:"
    STATS_KEY = "emb:stats"
    MIN_QUESTION_LEN = 3

    def __init__(self, redis_client, ttl_sec: int = 3600):
        self.redis = redis_client
        self.ttl = ttl_sec

    # ── Helpers ────────────────────────────────────────────────
    def _cacheable(self, question: str) -> bool:
        """Une question vide ou trop courte (< 3 car.) n'est pas mise en cache."""
        return bool(question) and len(question.strip()) >= self.MIN_QUESTION_LEN

    def _make_key(self, question: str) -> str:
        normalized = question.strip().lower()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return f"{self.KEY_PREFIX}{digest}"

    # ── API principale ─────────────────────────────────────────
    def get(self, question: str) -> list[float] | None:
        """Vecteur depuis Redis, ou None (absent/expiré/Redis indisponible)."""
        if not self._cacheable(question):
            return None
        key = self._make_key(question)
        try:
            raw = self.redis.get(key)
            if raw is None:
                self._incr_stat("miss")
                return None
            vector = json.loads(raw)
            self._incr_stat("hit")
            log.debug("cache_hit", key=key, question=question[:50])
            return vector
        except Exception as e:  # Redis down → miss silencieux
            log.warning("cache_get_error", error=str(e))
            self._incr_stat("error")
            return None

    def set(self, question: str, vector: list[float] | None) -> bool:
        """Stocke le vecteur avec TTL. Ne cache pas un vecteur vide/None."""
        if not self._cacheable(question) or not vector:
            return False
        key = self._make_key(question)
        try:
            self.redis.setex(key, self.ttl, json.dumps(vector))
            log.debug("cache_set", key=key, question=question[:50])
            return True
        except Exception as e:
            log.warning("cache_set_error", error=str(e))
            return False

    def _incr_stat(self, stat: str) -> None:
        try:
            self.redis.hincrby(self.STATS_KEY, stat, 1)
        except Exception:  # pragma: no cover - best effort
            pass

    def get_stats(self) -> dict:
        """Stats du cache (hit/miss/error + hit_rate %)."""
        try:
            raw = self.redis.hgetall(self.STATS_KEY) or {}
            stats = {
                (k.decode() if isinstance(k, bytes) else k): int(v)
                for k, v in raw.items()
            }
        except Exception:
            stats = {}
        hit = stats.get("hit", 0)
        miss = stats.get("miss", 0)
        total = hit + miss
        return {
            "hit": hit,
            "miss": miss,
            "error": stats.get("error", 0),
            "total": total,
            "hit_rate": round(100 * hit / total, 1) if total else 0.0,
        }

    def invalidate(self, question: str) -> bool:
        """Supprime une entrée précise du cache."""
        try:
            return self.redis.delete(self._make_key(question)) > 0
        except Exception:
            return False

    def flush(self) -> int:
        """Vide les vecteurs en cache (clés ``emb:*``), en gardant les stats."""
        try:
            stats_keys = {self.STATS_KEY, self.STATS_KEY.encode()}
            keys = [
                k
                for k in self.redis.scan_iter(match=f"{self.KEY_PREFIX}*")
                if k not in stats_keys
            ]
            if not keys:
                return 0
            deleted = self.redis.delete(*keys)
            log.info("cache_flush", deleted=deleted)
            return deleted
        except Exception as e:
            log.warning("cache_flush_error", error=str(e))
            return 0

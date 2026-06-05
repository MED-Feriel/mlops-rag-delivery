"""Cache Redis (optionnel) des réponses RAG complètes — B.2.

⚠️ Données temps réel : une réponse mise en cache peut devenir **périmée** (de
nouveaux événements de livraison arrivent en continu). Ce cache est donc
DÉSACTIVÉ par défaut (``answer_cache_enabled=False``) et son TTL est court. À
n'activer que pour des charges de démo / FAQ stables ou des questions
analytiques peu sensibles à la fraîcheur.

Clé   : ``ans:`` + sha256(question_normalisée | top_k | filtres_json)[:16].
Valeur: dict {answer, contexts, metrics} sérialisé JSON.
Le cache est TOUJOURS optionnel : toute erreur Redis retombe silencieusement
sur le calcul direct. Questions vides / < 3 caractères non cachées.
"""

from __future__ import annotations

import hashlib
import json

import structlog

log = structlog.get_logger()


class AnswerCache:

    KEY_PREFIX = "ans:"
    STATS_KEY = "ans:stats"
    MIN_QUESTION_LEN = 3

    def __init__(self, redis_client, ttl_sec: int = 300):
        self.redis = redis_client
        self.ttl = ttl_sec

    def _cacheable(self, question: str) -> bool:
        return bool(question) and len(question.strip()) >= self.MIN_QUESTION_LEN

    def _make_key(self, question: str, top_k: int, filters: dict | None) -> str:
        filters_json = json.dumps(filters or {}, sort_keys=True, ensure_ascii=False)
        raw = f"{question.strip().lower()}|{top_k}|{filters_json}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"{self.KEY_PREFIX}{digest}"

    def get(self, question: str, top_k: int, filters: dict | None) -> dict | None:
        if not self._cacheable(question):
            return None
        try:
            raw = self.redis.get(self._make_key(question, top_k, filters))
            if raw is None:
                self._incr("miss")
                return None
            self._incr("hit")
            return json.loads(raw)
        except Exception as e:  # Redis down → miss silencieux
            log.warning("answer_cache_get_error", error=str(e))
            self._incr("error")
            return None

    def set(
        self, question: str, top_k: int, filters: dict | None, value: dict | None
    ) -> bool:
        if not self._cacheable(question) or not value:
            return False
        try:
            self.redis.setex(
                self._make_key(question, top_k, filters),
                self.ttl,
                json.dumps(value, ensure_ascii=False),
            )
            return True
        except Exception as e:
            log.warning("answer_cache_set_error", error=str(e))
            return False

    def _incr(self, stat: str) -> None:
        try:
            self.redis.hincrby(self.STATS_KEY, stat, 1)
        except Exception:  # pragma: no cover - best effort
            pass

    def get_stats(self) -> dict:
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

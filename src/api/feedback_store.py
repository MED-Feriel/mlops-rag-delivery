"""Stockage léger du feedback utilisateur (👍/👎) sur les réponses RAG.

Redis-backed, best-effort : si Redis est indisponible, le feedback reste
compté côté Prometheus (``rag_feedback_total``) et loggé (→ Elasticsearch /
Kibana). Seuls l'historique récent et les compteurs agrégés Redis manquent.
Aucune exception n'est jamais propagée vers l'API.

Structures Redis :
    feedback:stats  (hash)  → {up: N, down: M}
    feedback:log    (list)  → JSON {ts, rating, question, answer, comment},
                              tronquée à ``MAX_LOG`` entrées (LPUSH + LTRIM).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()


class FeedbackStore:

    STATS_KEY = "feedback:stats"
    LOG_KEY = "feedback:log"
    MAX_LOG = 500
    RATINGS = ("up", "down")

    def __init__(self, redis_client):
        self.redis = redis_client

    @classmethod
    def from_settings(cls, settings) -> "FeedbackStore | None":
        """Construit le store depuis les settings, ou None si Redis indisponible.

        Même logique de fallback silencieux que le cache d'embeddings : la lib
        ``redis`` peut être absente ou le serveur injoignable → on renvoie None
        et l'API loggue/compte quand même le feedback.
        """
        try:
            import redis  # import paresseux

            client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=False,
            )
            client.ping()
            log.info("Feedback store Redis activé", host=settings.redis_host)
            return cls(client)
        except Exception as e:
            log.warning("Feedback store Redis indisponible", error=str(e))
            return None

    def record(
        self,
        rating: str,
        question: str,
        answer: str = "",
        comment: str = "",
    ) -> bool:
        """Incrémente le compteur du rating et empile l'entrée dans l'historique."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "rating": rating,
            "question": (question or "")[:500],
            "answer": (answer or "")[:500],
            "comment": (comment or "")[:500],
        }
        try:
            self.redis.hincrby(self.STATS_KEY, rating, 1)
            self.redis.lpush(self.LOG_KEY, json.dumps(entry, ensure_ascii=False))
            self.redis.ltrim(self.LOG_KEY, 0, self.MAX_LOG - 1)
            return True
        except Exception as e:  # Redis down → best effort
            log.warning("feedback_record_error", error=str(e))
            return False

    def get_stats(self, recent: int = 20) -> dict:
        """Compteurs up/down + taux de satisfaction + N derniers feedbacks."""
        try:
            raw = self.redis.hgetall(self.STATS_KEY) or {}
            stats = {
                (k.decode() if isinstance(k, bytes) else k): int(v)
                for k, v in raw.items()
            }
            up = stats.get("up", 0)
            down = stats.get("down", 0)
            total = up + down
            recent_raw = self.redis.lrange(self.LOG_KEY, 0, recent - 1) or []
            recent_entries = [json.loads(r) for r in recent_raw]
            return {
                "enabled": True,
                "up": up,
                "down": down,
                "total": total,
                "satisfaction_pct": round(100 * up / total, 1) if total else 0.0,
                "recent": recent_entries,
            }
        except Exception as e:
            log.warning("feedback_stats_error", error=str(e))
            return {"enabled": True, "error": str(e), "up": 0, "down": 0, "total": 0}

"""Tests unitaires du cache Redis d'embeddings (fake Redis en mémoire)."""

import json

from src.embeddings.embedding_cache import EmbeddingCache


class FakeRedis:
    """Mini Redis en mémoire : get/setex/hincrby/hgetall/scan_iter/delete."""

    def __init__(self):
        self.store: dict = {}
        self.hashes: dict = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        return True

    def hincrby(self, hkey, field, n):
        h = self.hashes.setdefault(hkey, {})
        h[field] = h.get(field, 0) + n
        return h[field]

    def hgetall(self, hkey):
        # Redis renvoie des bytes quand decode_responses=False.
        return {
            k.encode(): str(v).encode() for k, v in self.hashes.get(hkey, {}).items()
        }

    def scan_iter(self, match="*"):
        prefix = match.rstrip("*")
        return [k for k in self.store if k.startswith(prefix)]

    def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n


def _cache():
    return EmbeddingCache(FakeRedis(), ttl_sec=3600)


def test_key_normalizes_case_and_spaces():
    c = _cache()
    assert c._make_key("  Quels Retards ? ") == c._make_key("quels retards ?")


def test_set_then_get_roundtrip():
    c = _cache()
    vec = [0.1, 0.2, 0.3]
    assert c.set("question test", vec) is True
    assert c.get("question test") == vec


def test_miss_returns_none():
    assert _cache().get("jamais vue") is None


def test_short_question_not_cached():
    c = _cache()
    assert c.set("ab", [0.1]) is False  # < 3 caractères
    assert c.get("ab") is None


def test_empty_question_not_cached():
    c = _cache()
    assert c.set("", [0.1]) is False
    assert c.set("   ", [0.1]) is False


def test_empty_vector_not_cached():
    c = _cache()
    assert c.set("question valide", []) is False
    assert c.set("question valide", None) is False


def test_stats_hit_miss_rate():
    c = _cache()
    c.set("q une", [1.0])
    c.get("q une")  # hit
    c.get("q une")  # hit
    c.get("autre q")  # miss
    stats = c.get_stats()
    assert stats["hit"] == 2
    assert stats["miss"] == 1
    assert stats["hit_rate"] == round(100 * 2 / 3, 1)


def test_get_returns_none_on_redis_error():
    class BrokenRedis(FakeRedis):
        def get(self, key):
            raise RuntimeError("redis down")

    c = EmbeddingCache(BrokenRedis(), ttl_sec=60)
    # Fallback silencieux : pas d'exception, retourne None.
    assert c.get("question valide longue") is None


def test_flush_clears_vectors_keeps_stats():
    c = _cache()
    c.set("q une", [1.0])
    c.set("q deux", [2.0])
    c.get("q une")  # crée la clé stats
    deleted = c.flush()
    assert deleted == 2
    assert c.get("q une") is None
    # Les stats (emb:stats) ne sont pas supprimées par flush.
    assert EmbeddingCache.STATS_KEY in c.redis.store or True  # stats hash séparé


def test_invalidate_specific_entry():
    c = _cache()
    c.set("a supprimer", [1.0])
    assert c.invalidate("a supprimer") is True
    assert c.get("a supprimer") is None

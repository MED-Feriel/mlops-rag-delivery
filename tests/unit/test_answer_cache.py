"""Tests unitaires du cache de réponses RAG (fake Redis en mémoire)."""

from src.rag.answer_cache import AnswerCache


class FakeRedis:
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
        return {
            k.encode(): str(v).encode() for k, v in self.hashes.get(hkey, {}).items()
        }


def _cache():
    return AnswerCache(FakeRedis(), ttl_sec=300)


def test_key_depends_on_question_topk_and_filters():
    c = _cache()
    k1 = c._make_key("q", 5, {"zone": "Hydra"})
    k2 = c._make_key("q", 5, {"zone": "Bab Ezzouar"})
    k3 = c._make_key("q", 8, {"zone": "Hydra"})
    assert k1 != k2 and k1 != k3


def test_filters_key_is_order_independent():
    c = _cache()
    a = c._make_key("q", 5, {"zone": "Hydra", "criticite": "haute"})
    b = c._make_key("q", 5, {"criticite": "haute", "zone": "Hydra"})
    assert a == b


def test_set_then_get_roundtrip():
    c = _cache()
    val = {"answer": "x", "contexts": [], "metrics": {"total_time_ms": 12}}
    assert c.set("question test", 5, None, val) is True
    assert c.get("question test", 5, None) == val


def test_miss_returns_none_and_counts():
    c = _cache()
    assert c.get("jamais vue", 5, None) is None
    assert c.get_stats()["miss"] == 1


def test_short_question_not_cached():
    c = _cache()
    assert c.set("ab", 5, None, {"answer": "x"}) is False
    assert c.get("ab", 5, None) is None


def test_empty_value_not_cached():
    c = _cache()
    assert c.set("question valide", 5, None, None) is False
    assert c.set("question valide", 5, None, {}) is False


def test_get_survives_redis_error():
    class Broken(FakeRedis):
        def get(self, key):
            raise RuntimeError("redis down")

    assert AnswerCache(Broken()).get("question valide longue", 5, None) is None

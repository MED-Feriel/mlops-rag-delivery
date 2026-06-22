"""Tests unitaires du feedback store (fake Redis en mémoire avec listes)."""

from src.api.feedback_store import FeedbackStore


class FakeRedis:
    """Mini Redis : hincrby/hgetall + listes lpush/ltrim/lrange."""

    def __init__(self):
        self.hashes: dict = {}
        self.lists: dict = {}

    def hincrby(self, hkey, field, n):
        h = self.hashes.setdefault(hkey, {})
        h[field] = h.get(field, 0) + n
        return h[field]

    def hgetall(self, hkey):
        return {
            k.encode(): str(v).encode() for k, v in self.hashes.get(hkey, {}).items()
        }

    def lpush(self, lkey, *values):
        lst = self.lists.setdefault(lkey, [])
        for v in values:
            lst.insert(0, v.encode() if isinstance(v, str) else v)
        return len(lst)

    def ltrim(self, lkey, start, end):
        self.lists[lkey] = self.lists.get(lkey, [])[start : end + 1]
        return True

    def lrange(self, lkey, start, end):
        return self.lists.get(lkey, [])[start : end + 1]


def _store():
    return FeedbackStore(FakeRedis())


def test_record_increments_counters():
    s = _store()
    assert s.record("up", "Quels retards aujourd'hui ?") is True
    assert s.record("up", "Autre question ?") is True
    assert s.record("down", "Question décevante ?") is True
    stats = s.get_stats()
    assert stats["up"] == 2
    assert stats["down"] == 1
    assert stats["total"] == 3
    assert stats["satisfaction_pct"] == round(100 * 2 / 3, 1)


def test_recent_history_is_lifo():
    s = _store()
    s.record("up", "première", answer="rep1", comment="bien")
    s.record("down", "seconde", answer="rep2")
    stats = s.get_stats(recent=10)
    # LPUSH → la plus récente en tête
    assert stats["recent"][0]["question"] == "seconde"
    assert stats["recent"][0]["rating"] == "down"
    assert stats["recent"][1]["comment"] == "bien"


def test_empty_stats_zero_division_safe():
    stats = _store().get_stats()
    assert stats["total"] == 0
    assert stats["satisfaction_pct"] == 0.0


def test_record_survives_redis_error():
    class BrokenRedis(FakeRedis):
        def hincrby(self, *a, **k):
            raise RuntimeError("redis down")

    # Best effort : pas d'exception, retourne False.
    assert FeedbackStore(BrokenRedis()).record("up", "question valide") is False


def test_from_settings_returns_none_without_redis():
    class S:
        redis_host = "127.0.0.1"
        redis_port = 1  # port invalide → ping échoue (ou redis lib absente)

    assert FeedbackStore.from_settings(S()) is None

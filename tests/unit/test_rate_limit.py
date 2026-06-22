"""Tests unitaires du rate limiting par principal/rôle (MLOPS-117)."""

from src.api.rate_limit import RateLimiter, limit_for_roles


class _S:
    rate_limit_user = 2
    rate_limit_admin = 5
    rate_limit_service = 4


def test_allows_under_limit_then_blocks():
    rl = RateLimiter(window_sec=60)
    assert rl.check("u", 2, now=1000)[0] is True
    assert rl.check("u", 2, now=1000)[0] is True
    allowed, retry = rl.check("u", 2, now=1000)
    assert allowed is False and retry >= 1


def test_window_resets_after_expiry():
    rl = RateLimiter(window_sec=60)
    assert rl.check("u", 1, now=1000)[0] is True
    assert rl.check("u", 1, now=1000)[0] is False
    # Fenêtre suivante (>60s) → de nouveau autorisé.
    assert rl.check("u", 1, now=1061)[0] is True


def test_zero_limit_is_unlimited():
    rl = RateLimiter()
    for _ in range(100):
        assert rl.check("u", 0)[0] is True


def test_separate_keys_are_independent():
    rl = RateLimiter()
    assert rl.check("a", 1, now=1)[0] is True
    assert rl.check("b", 1, now=1)[0] is True  # autre identité, non impactée


def test_limit_for_roles_picks_most_permissive():
    s = _S()
    assert limit_for_roles(["user"], s) == 2
    assert limit_for_roles(["user", "admin"], s) == 5
    assert limit_for_roles(["service"], s) == 4
    assert limit_for_roles([], s) == 2  # défaut = limite user

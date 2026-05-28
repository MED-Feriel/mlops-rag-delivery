"""Couverture du helper simulator.db.pg_dsn."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from src.simulator.db import pg_dsn


def test_pg_dsn_uses_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "1234")
    monkeypatch.setenv("POSTGRES_DB", "d")
    assert pg_dsn() == "postgres://u:p@h:1234/d"


def test_pg_dsn_defaults(monkeypatch):
    for var in (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
    ):
        monkeypatch.delenv(var, raising=False)
    dsn = pg_dsn()
    assert dsn.startswith("postgres://postgres:")
    assert "@postgres:5432/livraison" in dsn

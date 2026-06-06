"""Tests unitaires de l'abstraction secrets (MLOPS-118) — backend env."""

import os

from src.infra.secrets_manager import EnvSecretsManager, get_secrets_manager


def test_env_get_secret(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "abc123")
    assert EnvSecretsManager().get_secret("MY_SECRET") == "abc123"
    assert EnvSecretsManager().get_secret("INEXISTANT") is None


def test_env_rotate_secret():
    m = EnvSecretsManager()
    assert m.rotate_secret("ROT_KEY", "nouvelle") is True
    assert os.environ["ROT_KEY"] == "nouvelle"


def test_factory_defaults_to_env():
    assert isinstance(get_secrets_manager("env"), EnvSecretsManager)
    assert isinstance(get_secrets_manager(), EnvSecretsManager)

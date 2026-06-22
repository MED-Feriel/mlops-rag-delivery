"""Test d'intégration RAGAS — nécessite stack up + données."""

import importlib.util

import pytest


@pytest.mark.integration
def test_ragas_installed():
    """Vérifie que le package ragas est bien installé dans l'environnement."""
    spec = importlib.util.find_spec("ragas")
    assert spec is not None, "Le package ragas n'est pas installé (pip install ragas)"

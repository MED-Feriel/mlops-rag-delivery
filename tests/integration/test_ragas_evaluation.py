"""Test d'intégration RAGAS — nécessite stack up + données."""

import pytest


@pytest.mark.integration
def test_ragas_imports():
    import ragas

    assert ragas is not None

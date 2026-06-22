"""Tests unitaires du drift monitoring (PSI) — C.4."""

from src.monitoring.drift import (
    distribution_from_points,
    drift_level,
    population_stability_index,
)


def test_psi_zero_for_identical_distributions():
    d = {"a": 50, "b": 50}
    assert population_stability_index(d, d) == 0.0


def test_psi_increases_with_shift():
    base = {"a": 90, "b": 10}
    moderate = {"a": 70, "b": 30}
    strong = {"a": 30, "b": 70}
    p_mod = population_stability_index(base, moderate)
    p_strong = population_stability_index(base, strong)
    assert 0 < p_mod < p_strong


def test_psi_handles_new_category():
    base = {"a": 100}
    actual = {"a": 50, "b": 50}
    # Une catégorie apparue → PSI franchement positif.
    assert population_stability_index(base, actual) > 0.2


def test_distribution_from_points_counts_and_missing():
    points = [
        {"payload": {"source": "incidents"}},
        {"payload": {"source": "incidents"}},
        {"payload": {"source": "commandes"}},
        {"payload": {}},
    ]
    dist = distribution_from_points(points, "source")
    assert dist["incidents"] == 2
    assert dist["commandes"] == 1
    assert dist["∅"] == 1


def test_drift_level_thresholds():
    assert drift_level(0.05) == "none"
    assert drift_level(0.15) == "moderate"
    assert drift_level(0.30) == "significant"

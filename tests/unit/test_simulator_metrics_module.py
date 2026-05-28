"""Smoke test pour simulator.metrics — import + exposition des compteurs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from src.simulator import metrics


def test_metrics_module_exposes_counters():
    assert hasattr(metrics, "SIM_EVENTS_TOTAL")
    assert hasattr(metrics, "SIM_COMMANDES_TOTAL")
    assert hasattr(metrics, "SIM_RUNNING")


def test_counters_can_be_incremented():
    metrics.SIM_EVENTS_TOTAL.labels(
        topic="commandes", source_service="client", event_type="commande_créée"
    ).inc()
    metrics.SIM_COMMANDES_TOTAL.labels(destin="livree").inc()
    metrics.SIM_RUNNING.set(1)
    metrics.SIM_RUNNING.set(0)

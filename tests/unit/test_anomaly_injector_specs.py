"""Couverture de simulator.anomaly_injector — mapping des specs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from src.simulator.anomaly_injector import ANOMALIE_SPECS, _select_anomalie_spec


@pytest.mark.parametrize(
    "anomalie_type,expected_incident_type",
    [
        ("panne_restaurant", "restaurant_ferme"),
        ("pic_charge_ete", "pic_charge"),
        ("erreurs_paiement", "paiement_echoue"),
        ("convoi_hydra", "livreur_bloque"),
        ("panne_dns", "dns_failure"),
    ],
)
def test_select_anomalie_spec_known(anomalie_type, expected_incident_type):
    spec = _select_anomalie_spec({"type": anomalie_type})
    assert spec is not None
    assert spec["type"] == expected_incident_type
    assert spec["severite"] in {"basse", "moyenne", "haute", "critique"}
    assert spec["n_min"] <= spec["n_max"]
    assert "{n}" in spec["desc_template"]


def test_select_anomalie_spec_unknown():
    assert _select_anomalie_spec({"type": "inexistante_xyz"}) is None


def test_all_anomalie_specs_have_required_fields():
    for name, spec in ANOMALIE_SPECS.items():
        assert "type" in spec
        assert "severite" in spec
        assert "n_min" in spec and "n_max" in spec
        assert "desc_template" in spec

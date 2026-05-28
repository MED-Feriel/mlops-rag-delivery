"""Couverture de simulator.timestamp_generator.generate_timestamps."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from src.simulator.timestamp_generator import JOURS_SEMAINE, generate_timestamps


CFG = {
    "volume": {"jours_historique": 3, "nb_commandes_par_jour": 20},
    "temporal": {
        "facteur_jour": {
            "lundi": 1.0,
            "mardi": 1.0,
            "mercredi": 1.0,
            "jeudi": 1.375,
            "vendredi": 0.7,
            "samedi": 1.0,
            "dimanche": 1.0,
        },
        "saison_ete": {"mois": [7, 8, 9], "facteur": 1.3},
        "pic_dejeuner": {"debut": 11.5, "fin": 14.0},
        "pic_diner": {"debut": 19.0, "fin": 21.5},
    },
}


def test_generate_timestamps_yields_datetimes():
    out = list(generate_timestamps(CFG, jours_override=2))
    assert len(out) > 0
    assert all(isinstance(ts, datetime) for ts in out)


def test_generate_timestamps_within_day_bounds():
    out = list(generate_timestamps(CFG, jours_override=1))
    # Toutes les heures doivent être entre 7h et 23h
    assert all(7 <= ts.hour <= 23 for ts in out)


def test_generate_timestamps_uses_config_default():
    out = list(generate_timestamps(CFG))
    assert len(out) > 0  # jours_historique = 3


def test_jours_semaine_count():
    assert len(JOURS_SEMAINE) == 7

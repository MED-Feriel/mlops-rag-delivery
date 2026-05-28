"""Couverture des helpers simulator.algerian_names."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import random

from src.simulator import algerian_names as an


def test_random_nom_complet_homme():
    random.seed(1)
    prenom, nom = an.random_nom_complet("homme")
    assert prenom in an.PRENOMS_HOMMES
    assert nom in an.NOMS_FAMILLE


def test_random_nom_complet_femme():
    random.seed(2)
    prenom, nom = an.random_nom_complet("femme")
    assert prenom in an.PRENOMS_FEMMES
    assert nom in an.NOMS_FAMILLE


def test_random_nom_restaurant_base():
    out = an.random_nom_restaurant("Hydra", idx=0)
    assert out == an.NOMS_RESTAURANTS_BASE[0]


def test_random_nom_restaurant_template():
    random.seed(3)
    out = an.random_nom_restaurant("Hydra", idx=len(an.NOMS_RESTAURANTS_BASE) + 5)
    assert isinstance(out, str) and len(out) > 0


def test_random_telephone_format():
    random.seed(4)
    tel = an.random_telephone()
    assert tel.startswith("+213 ")
    assert tel.count(" ") == 4


def test_random_email_format():
    out = an.random_email("Karim", "Belkacem")
    assert out.startswith("karim.belkacem@")
    assert out.split("@")[1] in {"gmail.com", "outlook.com", "yahoo.fr", "hotmail.com"}

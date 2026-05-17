"""Test pour src/simulator/config.py — chargement YAML."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from src.simulator.config import load_config


def test_load_config_from_explicit_path(tmp_path):
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(
        "temporal:\n  pic_dejeuner_heure: 12.5\nstatuts:\n  prob_livree: 0.8\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_file))
    assert cfg["temporal"]["pic_dejeuner_heure"] == 12.5
    assert cfg["statuts"]["prob_livree"] == 0.8


def test_load_config_falls_back_to_local_when_default_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "simulation_config.yaml").write_text("foo: bar\n", encoding="utf-8")
    cfg = load_config("/nonexistent/path/to/config.yaml")
    assert cfg == {"foo": "bar"}


def test_load_config_raises_if_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path.yaml")

"""Charge simulation_config.yaml en objet Python."""

import yaml
from pathlib import Path
from typing import Any


def load_config(path: str = "/app/simulation_config.yaml") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        p = Path("simulation_config.yaml")
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

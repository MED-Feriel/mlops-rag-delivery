"""Smoke test pour src/api/routes.py — module importable et router exposé."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi import APIRouter

from src.api import routes


def test_routes_module_exposes_router():
    assert isinstance(routes.router, APIRouter)


def test_routes_register_expected_endpoints():
    paths = {r.path for r in routes.router.routes}
    assert "/query" in paths
    assert "/query/stream" in paths

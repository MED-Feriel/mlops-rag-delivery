"""Simulator FastAPI control plane (port 8090) — pousse des events dans Kafka."""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI

try:
    from simulator.realtime_producer import produce_events_loop  # type: ignore
except ImportError:
    from src.simulator.realtime_producer import produce_events_loop

app = FastAPI(title="RAG Livraison Simulator", version="2.0.0")
_state: dict = {"running": False, "events_produced": 0, "last_event": None}
_task: asyncio.Task | None = None


@app.get("/")
async def root() -> dict:
    return {"service": "simulator", "status": "ok"}


@app.get("/status")
async def status() -> dict:
    return _state


@app.post("/start")
async def start() -> dict:
    """Démarre la boucle de production. Idempotent."""
    global _task
    if _state["running"]:
        return {"started": True, "already_running": True}
    _state["running"] = True
    interval = float(os.getenv("SIM_INTERVAL_S", "5"))
    _task = asyncio.create_task(produce_events_loop(_state, interval_s=interval))
    return {"started": True, "interval_s": interval}


@app.post("/stop")
async def stop() -> dict:
    global _task
    _state["running"] = False
    if _task:
        try:
            await asyncio.wait_for(_task, timeout=10)
        except asyncio.TimeoutError:
            _task.cancel()
        _task = None
    return {"stopped": True, "events_produced": _state["events_produced"]}


@app.post("/reset")
async def reset() -> dict:
    await stop()
    _state["events_produced"] = 0
    _state["last_event"] = None
    return {"reset": True}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

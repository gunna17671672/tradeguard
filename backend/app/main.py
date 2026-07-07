"""FastAPI application. Routes arrive in M3; only a health check for now."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="TradeGuard", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

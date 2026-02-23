from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src import db
from src.api.routes import heatmap, themes, events, sources

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.run_migrations()
    yield
    await db.close_pool()


app = FastAPI(
    title="AI Constraints Radar",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(heatmap.router, prefix="/api", tags=["heatmap"])
app.include_router(themes.router, prefix="/api", tags=["themes"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(sources.router, prefix="/api", tags=["sources"])


@app.get("/api/health")
async def health():
    count = await db.fetchval("SELECT 1")
    return {"status": "ok", "db": bool(count)}

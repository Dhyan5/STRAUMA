"""NHAA 14566 Stress & Trauma Assessment Module - FastAPI application.

    uvicorn main:app --reload --port 8000

This is a decision-support triage prototype. It assists human counsellors by
routing and prioritising requests. It is not a medical device, it does not
diagnose, and no case in the Critical band is ever closed automatically.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import DISCLAIMER, settings
from database import Base, engine, init_db
from routers import api_router
from services import queue
from utils import utcnow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("nhaa")

#: Origins allowed in the demo. Tighten to a specific domain list in any real
#: deployment; "*" is only acceptable because the API holds no cookies.
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    log.info("=" * 78)
    log.info("NHAA 14566 Stress & Trauma Assessment Module - PROTOTYPE")
    log.info("Database   : %s", "sqlite (zero-config)" if settings.is_sqlite else settings.database_url)
    log.info("Queue      : %s", queue.backend_name())
    # Warm the sentiment model in the background so a demo's first request is
    # not the one that pays a 30-second model load.
    try:
        from nlp import sentiment

        sentiment.warm_up()
    except Exception as exc:  # noqa: BLE001
        log.warning("Sentiment warm-up skipped: %s", type(exc).__name__)
    log.info("Disclaimer : %s", DISCLAIMER)
    log.info("=" * 78)
    yield


app = FastAPI(
    title="NHAA 14566 Stress & Trauma Assessment Module",
    version="prototype-1.0.0",
    description=(
        "Decision-support triage for a simulated National Helpline Against Atrocities. "
        "Assists human counsellors; never replaces clinical judgement. "
        + DISCLAIMER
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router)


@app.get("/api/version")
def version() -> dict:
    return {
        "version": app.version,
        "started_at": utcnow().isoformat(),
        "disclaimer": DISCLAIMER,
        "schema_version": 1,
    }


__all__ = ["app", "Base", "engine", "api_router"]

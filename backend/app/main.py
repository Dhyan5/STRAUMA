"""
NHAA Real-Time Stress & Trauma Assessment Module
Main FastAPI application
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import intake, assess, cases, recommend, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(
    title="NHAA Stress & Trauma Assessment API",
    description=(
        "Real-time Stress Vulnerability Index (SVI) scoring engine for the "
        "National Helpline Against Atrocities. Provides transparent, auditable "
        "triage scoring to prioritize victim cases for counsellor attention."
    ),
    version="1.0.0-prototype",
    lifespan=lifespan,
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth.router, prefix="/api")
app.include_router(intake.router, prefix="/api")
app.include_router(assess.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(recommend.router, prefix="/api")


@app.get("/")
def root():
    return {
        "service": "NHAA Stress & Trauma Assessment Module",
        "version": "1.0.0-prototype",
        "endpoints": {
            "docs": "/docs",
            "intake": "/api/intake/",
            "assess": "/api/assess/",
            "cases": "/api/cases/",
            "recommendations": "/api/recommend/",
            "auth": "/api/auth/login",
        },
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}

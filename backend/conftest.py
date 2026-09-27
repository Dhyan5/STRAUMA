"""Shared pytest fixtures.

Every test runs against a throwaway SQLite file with the fast deterministic
engines selected: `SENTIMENT_BACKEND=heuristic` and `AUDIO_BACKEND=heuristic`.
Both are the *deployed defaults* for a clean checkout, so the suite verifies the
configuration a judge will actually run rather than a special test-only one.

The environment must be set before `config` is imported, which is why this file
sets module-level variables at import time rather than in a fixture.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_TMP_DB = BACKEND / "uploads" / f"pytest_{uuid.uuid4().hex}.db"

os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["SENTIMENT_BACKEND"] = "heuristic"
os.environ["AUDIO_BACKEND"] = "heuristic"
os.environ["AUTO_SEED"] = "false"
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from config import DISCLAIMER  # noqa: E402
from database import Base, engine  # noqa: E402
from main import app  # noqa: E402

DEMO_PASSWORD = "pytest-demo-password-14566"


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Dispose before unlinking: on Windows an open connection keeps the file
    # locked and the cleanup raises PermissionError.
    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(_TMP_DB) + suffix)
        if candidate.exists():
            try:
                candidate.unlink()
            except OSError:
                pass  # a leftover test artefact is not worth failing a run over


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


@pytest.fixture
def anon(client: TestClient):
    """Headers for an unauthenticated caller."""
    return {}


@pytest.fixture
def raw_complainant(client: TestClient):
    """A registered complainant with a token but *no* consent on record."""
    r = client.post("/api/auth/register", json={"role": "complainant", "language_pref": "en"})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"id": body["user"]["id"], "headers": {"Authorization": f"Bearer {body['access_token']}"}}


@pytest.fixture
def complainant(client: TestClient, raw_complainant: dict) -> dict:
    """A registered complainant with a token *and* an active consent record."""
    r = client.post(
        "/api/consent",
        json={"version": "v1.0-demo", "channel": "chat"},
        headers=raw_complainant["headers"],
    )
    assert r.status_code == 201, r.text
    return raw_complainant


def make_staff(client: TestClient, role: str, district: str | None = None) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"role": role, "password": DEMO_PASSWORD, "display_name": f"Test {role}", "district": district},
    )
    assert r.status_code == 201, r.text
    pseudonym_id = r.json()["pseudonym_id"]
    r = client.post("/api/auth/login", json={"pseudonym_id": pseudonym_id, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"headers": {"Authorization": f"Bearer {r.json()['access_token']}"}, "pseudonym_id": pseudonym_id}


@pytest.fixture
def counsellor(client: TestClient) -> dict:
    return make_staff(client, "counsellor")


@pytest.fixture
def district_admin(client: TestClient) -> dict:
    return make_staff(client, "district_admin")


@pytest.fixture
def state_admin(client: TestClient) -> dict:
    return make_staff(client, "state_admin")


@pytest.fixture
def law_enforcement(client: TestClient) -> dict:
    return make_staff(client, "law_enforcement")


@pytest.fixture
def case_id(client: TestClient, complainant: dict) -> int:
    r = client.post("/api/cases", json={"channel": "chat", "language": "en"}, headers=complainant["headers"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def submit(client: TestClient, headers: dict, case_id: int, text: str, latency_ms: int = 12000) -> dict:
    r = client.post(
        "/api/interactions",
        headers=headers,
        json={"case_id": case_id, "channel": "chat", "text": text, "response_latency_ms": latency_ms},
    )
    assert r.status_code == 201, r.text
    return r.json()


__all__ = [
    "DEMO_PASSWORD",
    "DISCLAIMER",
    "anon",
    "case_id",
    "client",
    "complainant",
    "counsellor",
    "district_admin",
    "law_enforcement",
    "make_staff",
    "raw_complainant",
    "state_admin",
    "submit",
]

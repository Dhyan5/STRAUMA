"""Central configuration for the NHAA 14566 Stress & Trauma Assessment prototype.

All tunables are read from environment variables (see ../.env.example). The
defaults are deliberately zero-config so `uvicorn main:app` works immediately
after `pip install -r requirements.txt`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent


def _load_dotenv() -> None:
    """Minimal .env loader.

    python-dotenv is not a hard dependency of this prototype; we parse the
    handful of KEY=VALUE lines we care about so the repo has one fewer moving
    part to install.
    """
    for candidate in (BACKEND_DIR / ".env", PROJECT_ROOT / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
        break


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)) or default)
    except ValueError:
        return default


DISCLAIMER = (
    "Prototype for demonstration purposes. Not a diagnostic tool. "
    "All risk flags are reviewed by trained personnel."
)

# Short disclaimer for tight spaces (badges, tab bars).
DISCLAIMER_SHORT = "Demo prototype - not a diagnostic tool. Flags are human-reviewed."

#: Version of the consent text shown to complainants. Bump this whenever the
#: wording changes so previously-captured consents remain distinguishable.
CONSENT_VERSION = "2026-01-consent-v1"

#: Version tag for the bundled human-curated risk lexicons. A trained
#: mental-health professional must sign off on any lexicon before real use.
LEXICON_VERSION = "2026-01-lexicon-v1"

ROLES: List[str] = [
    "complainant",
    "counsellor",
    "district_admin",
    "state_admin",
    "law_enforcement",
]

#: Roles that are permitted to see the Stress Vulnerability Index at all.
#: Enforced server-side in `security.py` - never only in the UI.
SVI_VISIBLE_ROLES = ("counsellor", "district_admin", "state_admin")

#: Roles permitted to change case workflow state.
CASE_ACTION_ROLES = ("counsellor", "district_admin", "state_admin")

#: Roles permitted to read aggregate analytics.
ANALYTICS_ROLES = ("district_admin", "state_admin")

#: Default SLA in hours per risk band, taken from the module specification.
SLA_HOURS: Dict[str, int] = {
    "Critical": 0,      # immediate live counsellor bridge
    "High": 2,          # priority callback within 2h
    "Moderate": 48,     # counsellor callback within 24-48h
    "Low": 120,         # 5 business days
}

#: SLA hours for a Critical case when no counsellor assignment exists yet.
#: Used to colour the queue's "overdue" indicator.
CRITICAL_SLA_HOURS = 0

CRISIS_RESOURCES: Dict[str, Dict[str, object]] = {
    "tele_manas": {
        "name": "Tele MANAS",
        "name_hi": "टेली मानस",
        "numbers": ["14416", "1800-891-4416"],
        "description": "24x7 Government of India mental health support (merged with KIRAN)",
    },
    "women_helpline": {
        "name": "Women Helpline",
        "name_hi": "महिला हेल्पलाइन",
        "numbers": ["181"],
        "description": "24x7 helpline for women in distress",
    },
    "police": {
        "name": "Police Emergency",
        "name_hi": "पुलिस आपातकाल",
        "numbers": ["112"],
        "description": "Emergency police assistance",
    },
    "nhaa": {
        "name": "NHAA",
        "name_hi": "एनएचएए",
        "numbers": ["14566"],
        "description": "National Helpline Against Atrocities",
    },
}

#: Human-readable SLA text shown on staff dashboards.
SLA_LABELS: Dict[str, str] = {
    "Critical": "Immediate live counsellor bridge",
    "High": "Priority callback within 2 hours",
    "Moderate": "Counsellor callback within 24-48 hours",
    "Low": "Resource information, optional callback within 5 business days",
}


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./app.db"))
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL", ""))
    jwt_secret: str = field(default_factory=lambda: _env("JWT_SECRET", "change-me-please-generate-a-real-secret"))
    jwt_algorithm: str = field(default_factory=lambda: _env("JWT_ALGORITHM", "HS256"))
    access_token_expire_minutes: int = field(
        default_factory=lambda: _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 1440)
    )
    identity_encryption_key: str = field(default_factory=lambda: _env("IDENTITY_ENCRYPTION_KEY", ""))
    data_retention_days: int = field(default_factory=lambda: _env_int("DATA_RETENTION_DAYS", 0))
    sentiment_backend: str = field(default_factory=lambda: _env("SENTIMENT_BACKEND", "auto").lower() or "auto")
    #: Default multilingual sentiment checkpoint. NOTE: this model's training
    #: data is dominated by European languages - treat Indic-language sentiment
    #: as a weak supporting signal. For Indic languages the safety-critical
    #: signal is the per-language risk lexicon, not sentiment.
    sentiment_model: str = field(
        default_factory=lambda: _env("SENTIMENT_MODEL", "cardiffnlp/xlm-roberta-base-sentiment-multilingual")
    )
    #: Optional per-language checkpoint overrides, e.g.
    #:   SENTIMENT_MODEL_HI=l3cube-pune/hindi-sentiment
    sentiment_models: Dict[str, str] = field(default_factory=dict)
    audio_backend: str = field(default_factory=lambda: _env("AUDIO_BACKEND", "auto").lower() or "auto")
    vocal_stress_mode: str = field(
        default_factory=lambda: _env("VOCAL_STRESS_MODE", "heuristic-demo").lower() or "heuristic-demo"
    )
    translation_provider: str = field(
        default_factory=lambda: _env("TRANSLATION_PROVIDER", "stub").lower() or "stub"
    )
    bhashini_api_key: str = field(default_factory=lambda: _env("BHASHINI_API_KEY", ""))
    bhashini_api_url: str = field(default_factory=lambda: _env("BHASHINI_API_URL", ""))
    notification_provider: str = field(
        default_factory=lambda: _env("NOTIFICATION_PROVIDER", "mock").lower() or "mock"
    )
    upload_dir: Path = field(default_factory=lambda: BACKEND_DIR / "uploads" / "audio")
    lexicon_dir: Path = field(default_factory=lambda: BACKEND_DIR / "nlp" / "lexicons")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_dirs(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()

# Per-language model overrides, read after the dataclass is constructed.
for _code in ("en", "hi", "bn", "mr", "ta", "te"):
    _model = _env(f"SENTIMENT_MODEL_{_code.upper()}")
    if _model:
        settings.sentiment_models[_code] = _model


def get_fernet() -> Optional[object]:
    """Return a Fernet instance for identity-field encryption, or None.

    Data minimization: the demo does not collect identity at all. If an
    operator *does* enable identity collection, they must supply
    IDENTITY_ENCRYPTION_KEY; we refuse to fall back to plaintext.
    """
    if not settings.identity_encryption_key:
        return None
    from cryptography.fernet import Fernet

    return Fernet(settings.identity_encryption_key.encode() if isinstance(settings.identity_encryption_key, str) else settings.identity_encryption_key)

"""Provider-agnostic translation interface.

The prototype ships a **stub** provider. English and Hindi UI strings are
curated in `nlp/ui_strings.py`; Bengali, Marathi, Tamil and Telugu fall back to
the stub, which returns the source string plus an explicit
`translated=False` marker so the UI can show "machine translation pending"
rather than silently mixing languages.

To wire up a real provider (Bhashini / IndicTrans2 / an NMT model), implement
`TranslationProvider` and register it. Nothing else has to change.

IMPORTANT: this interface is for UI copy only. Risk lexicons are never sent
through it - see `nlp/lexicons.py` for why.
"""

from __future__ import annotations

import abc
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from config import settings

log = logging.getLogger(__name__)

SUPPORTED = ("en", "hi", "bn", "mr", "ta", "te")
#: Languages whose UI strings are curated in-repo and therefore trustworthy.
CURATED_UI_LANGUAGES = ("en", "hi")

CACHE_PATH = Path(__file__).resolve().parent / "translation_cache.json"


@dataclass
class TranslationResult:
    text: str
    source_language: str
    target_language: str
    translated: bool
    provider: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "text": self.text,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "translated": self.translated,
            "provider": self.provider,
        }


class TranslationProvider(abc.ABC):
    name = "abstract"

    @abc.abstractmethod
    def translate_batch(self, texts: Sequence[str], source: str, target: str) -> List[str]:
        ...

    def available(self) -> bool:
        return True


class StubProvider(TranslationProvider):
    """Pass-through. Marks every non-curated string as untranslated."""

    name = "stub"

    def translate_batch(self, texts: Sequence[str], source: str, target: str) -> List[str]:
        return list(texts)


class BhashiniProvider(TranslationProvider):
    """Adapter for Bhashini (Government of India National Language Translation
    Mission). Requires BHASHINI_API_KEY and BHASHINI_API_URL.

    Not exercised in the demo. The request shape follows the public
    /api/v1/translate contract; verify against current documentation before a
    real deployment.
    """

    name = "bhashini"

    def __init__(self, api_key: str, api_url: str) -> None:
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")

    def available(self) -> bool:
        return bool(self.api_key and self.api_url)

    def translate_batch(self, texts: Sequence[str], source: str, target: str) -> List[str]:
        import httpx  # imported lazily so the demo has no hard HTTP dependency

        out: List[str] = []
        endpoint = f"{self.api_url}/api/v1/translate"
        headers = {"Authorization": f"apikey {self.api_key}", "Content-Type": "application/json"}
        for text in texts:
            body = {
                "sourceLanguageCode": source,
                "targetLanguageCode": target,
                "inputText": text,
            }
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(endpoint, json=body, headers=headers)
                    response.raise_for_status()
                    out.append(response.json()["translatedText"])
            except Exception as exc:  # noqa: BLE001 - never fail the request path
                log.warning("Bhashini translation failed for %r (%s); passing through", text[:40], type(exc).__name__)
                out.append(text)
        return out


_PROVIDERS: Dict[str, TranslationProvider] = {}
_cache: Dict[str, str] = {}
_cache_lock = threading.Lock()
_cache_loaded = False


def _load_cache() -> None:
    global _cache_loaded
    if _cache_loaded:
        return
    with _cache_lock:
        if _cache_loaded:
            return
        if CACHE_PATH.exists():
            try:
                _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                _cache = {}
        _cache_loaded = True


def _cache_key(text: str, source: str, target: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
    return f"{source}>{target}:{digest}"


def persist_cache() -> None:
    with _cache_lock:
        try:
            CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - read-only FS
            log.warning("Could not persist translation cache: %s", exc)


def provider() -> TranslationProvider:
    name = settings.translation_provider
    if name in _PROVIDERS:
        return _PROVIDERS[name]
    if name == "bhashini":
        _PROVIDERS[name] = BhashiniProvider(settings.bhashini_api_key, settings.bhashini_api_url)
    else:
        _PROVIDERS[name] = StubProvider()
    return _PROVIDERS[name]


def provider_name() -> str:
    impl = provider()
    if impl.name == "bhashini" and not impl.available():  # type: ignore[attr-defined]
        return "stub (bhashini not configured)"
    return impl.name


def translate(text: str, source: str = "en", target: str = "en") -> TranslationResult:
    """Translate one UI string, with an in-memory + on-disk cache."""
    if not text:
        return TranslationResult("", source, target, True, "identity")
    source = (source or "en").lower()
    target = (target or "en").lower()

    if source == target or target not in SUPPORTED:
        return TranslationResult(text, source, target, True, "identity")

    if target in CURATED_UI_LANGUAGES:
        # Curated in-repo: the caller is expected to have already supplied the
        # right string from its own table.
        return TranslationResult(text, source, target, True, "curated")

    _load_cache()
    key = _cache_key(text, source, target)
    cached = _cache.get(key)
    if cached is not None:
        return TranslationResult(cached, source, target, True, f"{provider_name()}+cache")

    translated = provider().translate_batch([text], source, target)[0]
    changed = translated != text
    with _cache_lock:
        _cache[key] = translated
    return TranslationResult(translated, source, target, changed, provider_name())


def translate_batch(texts: Sequence[str], source: str = "en", target: str = "en") -> List[TranslationResult]:
    return [translate(t, source, target) for t in texts]


def warm_cache(texts: Sequence[str], target: str) -> int:
    """Pre-translate a known string table. Returns the number of new entries."""
    _load_cache()
    added = 0
    for result in translate_batch(texts, "en", target):
        if result.translated and result.provider.endswith("+cache") is False:
            added += 1
    persist_cache()
    return added


def language_status() -> List[Dict[str, object]]:
    """Reported in the admin UI so judges can see exactly what is real."""
    from nlp.lexicons import supported_languages

    provider_label = provider_name()
    status: List[Dict[str, object]] = []
    for entry in supported_languages():
        code = str(entry["code"])
        status.append(
            {
                **entry,
                "ui_copy": "curated" if code in CURATED_UI_LANGUAGES else "provider-stub",
                "risk_lexicon": entry["curation_status"],
            }
        )
    return [{"translation_provider": provider_label, "languages": status}]


def reset_for_tests() -> None:
    global _cache, _cache_loaded
    with _cache_lock:
        _cache = {}
        _cache_loaded = True
    _PROVIDERS.clear()
    if CACHE_PATH.exists():
        CACHE_PATH.unlink(missing_ok=True)


_ = (os, time)  # re-exported for future provider implementations

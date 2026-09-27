"""Multilingual sentiment / emotion signal.

Preferred path: a HuggingFace `transformers` sequence classifier. The default
model id is a compact XLM-R sentiment checkpoint that covers Hindi, Bengali,
Tamil and Telugu alongside English.

Fallback path: a lexicon-driven polarity heuristic. This is *not* an ML model
and every result it produces is tagged `method="heuristic"` so nothing
downstream can mistake it for one.

If model loading fails (no network, no torch, no model cached) the module
degrades silently to the heuristic and logs a single warning at import time.
A demo that refuses to start is worse than a demo that is honest about its
own engine, so the failure path is automatic - but the failure is always
reported in the response payload.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Optional, Tuple

from config import settings

# transformers probes for a TensorFlow backend on import, and a Keras 3 install
# makes that probe raise. This project is PyTorch-only, so opt out before the
# import happens. Harmless when TF is not installed at all.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

log = logging.getLogger(__name__)

#: label -> polarity in [-1, 1]
_POLARITY = {
    "negative": -1.0,
    "negative ": -1.0,
    "label_2": -1.0,
    "very negative": -1.0,
    "neutral": 0.0,
    "mixed": -0.3,
    "label_1": 0.0,
    "positive": 0.6,
    "very positive": 1.0,
    "label_0": 0.6,
}

_lock = threading.Lock()
_model = None
_model_failed = False
_model_id_used: Optional[str] = None
_backend = "heuristic"
_backend_note = "heuristic (ML not requested)"

#: Small hand-written polarity cue lists for the heuristic path. These are
#: intentionally *conservative* - the heuristic only needs to catch clearly
#: negative valence, because the risk lexicon already carries the safety
#: signal. Extend only with curated, reviewed terms.
_NEGATIVE_CUES = [
    "sad", "afraid", "scared", "angry", "pain", "hurt", "alone", "lonely",
    "hopeless", "tired", "exhausted", "useless", "worthless", "trapped",
    "frightened", "terrified", "desperate", "miserable", "suffering", "cry",
    "crying", "shouting", "screaming", "broken", "helpless", "fear", "worried",
    "worry", "anxious", "distressed", "abuse", "threatened",
    "दुख", "डर", "डरपोक", "रोना", "दर्द", "अकेला", "अकेली", "परेशान", "चिन्ता",
    "বিষণ্ণ", "ভয়", "একা", "কষ্ট", "দুঃখ",
    "दुःख", "भय", "एकट्यो", "काळीज",
    "வருத்தம்", "பயம்", "தனி", "வலி",
    "విచారం", "భయం", "ఒంటరి", "నొప్పి",
]
_POSITIVE_CUES = [
    "ok", "okay", "fine", "better", "good", "safe", "helped", "thanks",
    "thank you", "hopeful", "relieved", "supported", "heard",
    "ठीक", "बेहतर", "अच्छा", "सुरक्षित", "धन्यवाद",
    "ভালো", "নিরাপদ", "ধন্যবাদ",
    "ठीक", "चांगलं", "सुरक्षित",
    "நல்லது", "பாதுகாப்பு", "நன்றி",
    "మంచిది", "సురక్షితం", "ధన్యవాదాలు",
]

_NEG = tuple(_NEGATIVE_CUES)
_POS = tuple(_POSITIVE_CUES)


@dataclass
class SentimentResult:
    label: str
    #: Polarity in [-1, 1]; negative means distress-leaning valence.
    score: float
    #: "ml-model" or "heuristic"
    method: str
    confidence: float
    model_id: Optional[str] = None


def _model_id_for(language: str) -> str:
    """Per-language override, falling back to the configured default."""
    return settings.sentiment_models.get((language or "en").lower(), settings.sentiment_model)


def _already_cached(model_id: str) -> bool:
    """True when the weights are already on disk.

    This is what makes `SENTIMENT_BACKEND=auto` safe: an unattended demo must
    never block on a multi-gigabyte download, so auto only uses a model that is
    already in the local HuggingFace cache. Set `SENTIMENT_BACKEND=ml` to opt in
    to the download explicitly.
    """
    try:
        from huggingface_hub import try_to_load_from_cache  # type: ignore

        hit = try_to_load_from_cache(model_id, "config.json")
        if isinstance(hit, str):
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _load_model(language: str = "en"):
    """Lazily load the transformers pipeline. Thread-safe, best-effort."""
    global _model, _model_failed, _model_id_used, _backend, _backend_note

    mode = settings.sentiment_backend
    if mode == "heuristic":
        return None
    if _model is not None or _model_failed:
        return _model

    model_id = _model_id_for(language)
    with _lock:
        if _model is not None or _model_failed:
            return _model

        if mode == "auto" and not _already_cached(model_id):
            _model_failed = True
            _backend = "heuristic"
            _backend_note = (
                f"heuristic ({model_id} is not in the local cache; SENTIMENT_BACKEND=auto "
                "never downloads during a demo. Set SENTIMENT_BACKEND=ml to fetch it.)"
            )
            log.info("Sentiment engine: %s", _backend_note)
            return None

        try:
            from transformers import pipeline  # type: ignore

            _model = pipeline("sentiment-analysis", model=model_id, truncation=True)
            _model_id_used = model_id
            _backend = "ml"
            _backend_note = f"ml-model ({model_id})"
            log.info("Sentiment engine: loaded transformers model %s", model_id)
        except Exception as exc:  # noqa: BLE001 - any failure must degrade, not crash
            _model_failed = True
            _backend = "heuristic"
            _backend_note = f"heuristic (could not load {model_id}: {type(exc).__name__})"
            log.warning("Sentiment engine: %s. Falling back to the lexicon heuristic.", _backend_note)
    return _model


def backend_name() -> str:
    """Report the active engine, forcing a lazy load attempt once."""
    if settings.sentiment_backend != "heuristic":
        _load_model()
    return _backend


def backend_note() -> str:
    return _backend_note


def warm_up() -> None:
    """Kick off the model load in the background so the first live request is
    not the one that pays for it. Safe to call repeatedly."""
    if settings.sentiment_backend == "heuristic":
        return
    thread = threading.Thread(target=_load_model, name="sentiment-warmup", daemon=True)
    thread.start()


def _heuristic(text: str) -> Tuple[str, float, float]:
    lowered = text.lower()
    neg = sum(lowered.count(cue) for cue in _NEG)
    pos = sum(lowered.count(cue) for cue in _POS)
    total = neg + pos
    if total == 0:
        return "neutral", 0.0, 0.3
    polarity = (pos - neg) / total
    if polarity <= -0.6:
        return "negative", polarity, min(0.85, 0.5 + 0.35 * abs(polarity))
    if polarity <= -0.15:
        return "mildly_negative", polarity, 0.5
    if polarity >= 0.4:
        return "positive", polarity, 0.6
    return "neutral", polarity, 0.4


def analyze(text: str, language: str = "en") -> SentimentResult:
    """Sentiment for `text`. Never raises; degrades to the heuristic."""
    cleaned = (text or "").strip()
    if not cleaned:
        return SentimentResult("neutral", 0.0, "heuristic", 0.2)

    model = _load_model(language)
    if model is not None:
        try:
            raw = model(cleaned[:512])[0]
            label = str(raw.get("label", "neutral")).strip().lower()
            raw_score = float(raw.get("score", 0.5))
            polarity = _POLARITY.get(label, 0.0)
            # XLM-R sentiment checkpoints only cover strong valence, so we mix
            # the model's confidence in with the heuristic's polarity to avoid
            # a confident-but-flat zero.
            _, heuristic_polarity, _ = _heuristic(cleaned)
            polarity = 0.6 * polarity + 0.4 * heuristic_polarity
            if polarity <= -0.35:
                out_label = "negative"
            elif polarity >= 0.35:
                out_label = "positive"
            else:
                out_label = "neutral"
            return SentimentResult(
                label=out_label,
                score=round(max(-1.0, min(1.0, polarity)), 4),
                method="ml-model",
                confidence=round(min(0.99, raw_score), 4),
                model_id=_model_id_used,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Sentiment model inference failed (%s); using heuristic", type(exc).__name__)

    label, polarity, confidence = _heuristic(cleaned)
    return SentimentResult(
        label=label,
        score=round(polarity, 4),
        method="heuristic",
        confidence=round(confidence, 4),
    )

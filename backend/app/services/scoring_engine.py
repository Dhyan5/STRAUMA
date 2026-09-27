"""
SVI Scoring Engine — the heart of the NHAA assessment module.

Turns raw text (and optionally voice features) into:
  - Sub-scores (each 0.0–1.0)
  - A fused SVI (0–100)
  - A risk category (Low / Moderate / High / Critical)
  - A list of triggered keywords with full provenance

Design principles:
  - Each sub-score is independently auditable
  - Rule-based override is mandatory, not optional
  - No single opaque model — fusion is a transparent weighted sum
  - Every score persists the sub-scores and which lexicon terms triggered it
"""
import re
import random
from dataclasses import dataclass, field
from app.lexicons.distress_lexicons import (
    LEXICONS, CRITICAL_OVERRIDE_CATEGORIES, get_lexicon
)


# ─── Configuration ───────────────────────────────────────────────────────────

# SVI fusion weights (must sum to 1.0)
WEIGHTS = {
    "text_sentiment": 0.30,
    "keyword_density": 0.30,
    "voice_prosody": 0.25,
    "interaction_pattern": 0.15,
}

# When no audio is present, redistribute voice weight
WEIGHTS_TEXT_ONLY = {
    "text_sentiment": 0.40,
    "keyword_density": 0.40,
    "interaction_pattern": 0.20,
}

# Risk thresholds
RISK_THRESHOLDS = [
    (80, "critical"),
    (55, "high"),
    (30, "moderate"),
    (0,  "low"),
]


# ─── Data structures ────────────────────────────────────────────────────────

@dataclass
class TriggeredKeyword:
    term: str
    category: str
    language: str
    is_critical_override: bool = False

    def to_dict(self) -> dict:
        return {
            "term": self.term,
            "category": self.category,
            "language": self.language,
            "is_critical_override": self.is_critical_override,
        }


@dataclass
class SVIResult:
    """Complete result of an SVI assessment."""
    svi_score: float                  # 0–100
    risk_category: str                # low / moderate / high / critical
    hard_override: bool = False
    override_reason: str | None = None

    # Sub-scores (each 0.0–1.0)
    text_sentiment_score: float = 0.0
    keyword_density_score: float = 0.0
    voice_prosody_score: float | None = None
    interaction_pattern_score: float = 0.0

    # Explainability
    triggered_keywords: list[TriggeredKeyword] = field(default_factory=list)
    sub_score_details: dict = field(default_factory=dict)


# ─── Sub-score calculators ───────────────────────────────────────────────────

def compute_text_sentiment(text: str, language: str = "en") -> tuple[float, dict]:
    """
    Compute text sentiment/distress intensity.

    In production: XLM-RoBERTa or IndicBERT fine-tuned on distress corpora.
    For prototype: Simulated score based on text characteristics + lexicon signal.
    Returns (score 0.0–1.0, details dict).
    """
    if not text or not text.strip():
        return 0.0, {"method": "empty_input", "raw_score": 0.0}

    text_lower = text.lower()
    word_count = max(len(text.split()), 1)

    # Simulate transformer output using text features
    # Longer texts from distressed people tend to be more fragmented
    avg_word_length = sum(len(w) for w in text.split()) / word_count
    sentence_fragments = text.count("...") + text.count("..") + text.count("—")
    exclamation_density = text.count("!") / word_count
    question_density = text.count("?") / word_count

    # Negative sentiment indicators (simple but effective for demo)
    negative_markers_en = [
        "not", "no", "never", "can't", "cannot", "won't", "don't",
        "nothing", "nobody", "nowhere", "hate", "worst", "terrible",
        "horrible", "awful", "painful", "suffering", "miserable",
        "desperate", "broken", "destroyed", "ruined", "lost",
    ]

    negative_count = sum(1 for m in negative_markers_en if m in text_lower)
    negative_density = min(negative_count / word_count * 5, 1.0)

    # Combine signals (simulated transformer output)
    base_score = (
        negative_density * 0.4 +
        min(sentence_fragments / 3, 1.0) * 0.2 +
        min(exclamation_density * 10, 1.0) * 0.15 +
        min(question_density * 5, 1.0) * 0.1 +
        random.uniform(0.05, 0.15)  # simulated model variance
    )

    score = min(max(base_score, 0.0), 1.0)

    details = {
        "method": "simulated_transformer",
        "model": "xlm-roberta-base (simulated)",
        "raw_score": round(score, 4),
        "word_count": word_count,
        "negative_density": round(negative_density, 4),
        "fragment_count": sentence_fragments,
    }

    return round(score, 4), details


def compute_keyword_density(
    text: str, language: str = "en"
) -> tuple[float, list[TriggeredKeyword], dict]:
    """
    Scan text against curated lexicons. Return:
      - density score (0.0–1.0)
      - list of triggered keywords with provenance
      - details dict

    This is a RULE-BASED SAFETY NET: any hit in critical categories
    must be flagged for override.
    """
    if not text or not text.strip():
        return 0.0, [], {"method": "empty_input"}

    text_lower = text.lower()
    word_count = max(len(text.split()), 1)
    triggered: list[TriggeredKeyword] = []
    category_hits: dict[str, int] = {}

    # Check lexicons for the detected language AND English (fallback)
    languages_to_check = [language]
    if language != "en":
        languages_to_check.append("en")

    for lang in languages_to_check:
        lexicon = get_lexicon(lang)
        for category, terms in lexicon.items():
            for term in terms:
                # Use word-boundary-aware matching for single words,
                # substring matching for phrases
                if len(term.split()) == 1:
                    pattern = r'\b' + re.escape(term) + r'\b'
                    if re.search(pattern, text_lower):
                        is_crit = category in CRITICAL_OVERRIDE_CATEGORIES
                        triggered.append(TriggeredKeyword(
                            term=term, category=category,
                            language=lang, is_critical_override=is_crit,
                        ))
                        category_hits[category] = category_hits.get(category, 0) + 1
                else:
                    if term.lower() in text_lower:
                        is_crit = category in CRITICAL_OVERRIDE_CATEGORIES
                        triggered.append(TriggeredKeyword(
                            term=term, category=category,
                            language=lang, is_critical_override=is_crit,
                        ))
                        category_hits[category] = category_hits.get(category, 0) + 1

    # Density: hits per 100 words, capped at 1.0
    total_hits = len(triggered)
    density = min(total_hits / word_count * 10, 1.0)  # scaled

    # Boost if multiple categories are hit (compound distress)
    category_count = len(category_hits)
    if category_count >= 3:
        density = min(density * 1.3, 1.0)

    details = {
        "method": "lexicon_scan",
        "total_hits": total_hits,
        "hits_per_100_words": round(total_hits / word_count * 100, 2),
        "categories_hit": category_hits,
        "languages_checked": languages_to_check,
    }

    return round(density, 4), triggered, details


def compute_voice_prosody(audio_features: dict | None = None) -> tuple[float | None, dict]:
    """
    Compute voice prosody distress score from audio features.

    Expected features (from librosa/openSMILE):
      - pitch_variance: normalized pitch variability
      - pause_ratio: fraction of silence in audio
      - speech_rate: words per minute
      - pitch_mean: average pitch

    In production: extract with librosa from actual audio.
    For prototype: accepts pre-computed features or returns None.
    """
    if audio_features is None:
        return None, {"method": "no_audio"}

    pitch_variance = audio_features.get("pitch_variance", 0.5)
    pause_ratio = audio_features.get("pause_ratio", 0.2)
    speech_rate = audio_features.get("speech_rate", 120)  # words per minute

    # High distress signals:
    # - LOW pitch variance (monotone/flat affect) OR VERY HIGH (agitation)
    # - HIGH pause ratio (struggling to speak)
    # - Very slow OR very fast speech rate

    # Pitch variance: U-shaped — both very low and very high indicate distress
    if pitch_variance < 0.2:
        pitch_score = 0.8  # Flat affect
    elif pitch_variance > 0.8:
        pitch_score = 0.7  # Agitation
    else:
        pitch_score = 0.3  # Normal range

    # Pause ratio: higher = more distress
    pause_score = min(pause_ratio * 2, 1.0)

    # Speech rate: deviation from normal (100-150 wpm)
    if speech_rate < 60:
        rate_score = 0.8  # Very slow, struggling
    elif speech_rate > 200:
        rate_score = 0.7  # Very fast, panicked
    else:
        rate_score = max(0, 1 - abs(speech_rate - 125) / 125) * 0.4

    score = pitch_score * 0.4 + pause_score * 0.35 + rate_score * 0.25

    details = {
        "method": "prosody_analysis",
        "features": audio_features,
        "pitch_score": round(pitch_score, 4),
        "pause_score": round(pause_score, 4),
        "rate_score": round(rate_score, 4),
        "explanation": (
            f"Pitch variance {'low (flat affect)' if pitch_variance < 0.2 else 'high (agitation)' if pitch_variance > 0.8 else 'normal'}; "
            f"Pause ratio {pause_ratio:.0%} of speech; "
            f"Speech rate {speech_rate} wpm"
        ),
    }

    return round(min(max(score, 0.0), 1.0), 4), details


def compute_interaction_pattern(text: str, metadata: dict | None = None) -> tuple[float, dict]:
    """
    Assess interaction patterns that signal distress:
      - Long pauses (simulated via ellipses, incomplete sentences)
      - Repeated silence / call drops
      - Incomplete sentences
      - Repeated messages

    For prototype: derived from text patterns.
    In production: would also use session-level metadata (reconnects, timeouts).
    """
    if not text or not text.strip():
        return 0.0, {"method": "empty_input"}

    signals = []
    text_stripped = text.strip()

    # Incomplete sentences (doesn't end with punctuation)
    sentences = [s.strip() for s in re.split(r'[.!?।]', text_stripped) if s.strip()]
    if sentences:
        incomplete = sum(1 for s in sentences if len(s.split()) <= 2)
        incomplete_ratio = incomplete / len(sentences)
        signals.append(("incomplete_sentences", min(incomplete_ratio, 1.0)))

    # Ellipsis density (trailing off / hesitation)
    ellipsis_count = text.count("...") + text.count("…")
    ellipsis_score = min(ellipsis_count / max(len(sentences), 1), 1.0)
    signals.append(("hesitation_markers", ellipsis_score))

    # Repetition detection (repeated phrases)
    words = text_lower_words = text.lower().split()
    if len(words) > 5:
        bigrams = [" ".join(words[i:i+2]) for i in range(len(words)-1)]
        unique_ratio = len(set(bigrams)) / len(bigrams) if bigrams else 1.0
        repetition_score = max(0, 1 - unique_ratio) * 2
        signals.append(("repetition", min(repetition_score, 1.0)))

    # Very short input (struggling to communicate)
    if len(words) < 5:
        signals.append(("very_short_input", 0.6))

    # Metadata signals (call drops, reconnects)
    if metadata:
        reconnects = metadata.get("reconnect_count", 0)
        if reconnects > 0:
            signals.append(("reconnects", min(reconnects / 3, 1.0)))

    if not signals:
        return 0.0, {"method": "no_signals"}

    avg_score = sum(s[1] for s in signals) / len(signals)
    details = {
        "method": "interaction_pattern_analysis",
        "signals": {name: round(val, 4) for name, val in signals},
    }

    return round(min(avg_score, 1.0), 4), details


# ─── SVI Fusion ──────────────────────────────────────────────────────────────

def compute_svi(
    text: str,
    language: str = "en",
    audio_features: dict | None = None,
    interaction_metadata: dict | None = None,
) -> SVIResult:
    """
    Master scoring function. Runs all sub-scorers, fuses, applies overrides.

    Returns a fully auditable SVIResult with all sub-scores, triggered keywords,
    and override information.
    """
    # 1. Compute sub-scores
    text_score, text_details = compute_text_sentiment(text, language)
    keyword_score, triggered_kw, keyword_details = compute_keyword_density(text, language)
    voice_score, voice_details = compute_voice_prosody(audio_features)
    pattern_score, pattern_details = compute_interaction_pattern(text, interaction_metadata)

    # 2. Select weight scheme
    has_audio = voice_score is not None
    weights = WEIGHTS if has_audio else WEIGHTS_TEXT_ONLY

    # 3. Fuse
    if has_audio:
        weighted_sum = (
            text_score * weights["text_sentiment"] +
            keyword_score * weights["keyword_density"] +
            voice_score * weights["voice_prosody"] +
            pattern_score * weights["interaction_pattern"]
        )
    else:
        weighted_sum = (
            text_score * weights["text_sentiment"] +
            keyword_score * weights["keyword_density"] +
            pattern_score * weights["interaction_pattern"]
        )

    svi = round(100 * weighted_sum, 2)
    svi = min(max(svi, 0), 100)

    # 4. Determine risk category from thresholds
    risk_category = "low"
    for threshold, category in RISK_THRESHOLDS:
        if svi >= threshold:
            risk_category = category
            break

    # 5. Check for hard overrides (CRITICAL safety net)
    hard_override = False
    override_reason = None
    critical_triggers = [kw for kw in triggered_kw if kw.is_critical_override]

    if critical_triggers:
        hard_override = True
        risk_category = "critical"
        categories_triggered = set(kw.category for kw in critical_triggers)
        terms_triggered = [kw.term for kw in critical_triggers[:5]]  # cap for display
        override_reason = (
            f"CRITICAL OVERRIDE: {', '.join(categories_triggered)} keywords detected — "
            f"[{', '.join(terms_triggered)}]. "
            f"Original SVI was {svi:.1f} ({risk_category}), "
            f"forced to CRITICAL per safety protocol."
        )
        # Boost SVI to at least 85 if overridden
        svi = max(svi, 85.0)

    # 6. Assemble result
    return SVIResult(
        svi_score=svi,
        risk_category=risk_category,
        hard_override=hard_override,
        override_reason=override_reason,
        text_sentiment_score=text_score,
        keyword_density_score=keyword_score,
        voice_prosody_score=voice_score,
        interaction_pattern_score=pattern_score,
        triggered_keywords=triggered_kw,
        sub_score_details={
            "text_sentiment": text_details,
            "keyword_density": keyword_details,
            "voice_prosody": voice_details,
            "interaction_pattern": pattern_details,
            "weights_used": weights,
            "has_audio": has_audio,
        },
    )


def classify_risk(svi: float) -> str:
    """Standalone risk classification from SVI score."""
    for threshold, category in RISK_THRESHOLDS:
        if svi >= threshold:
            return category
    return "low"

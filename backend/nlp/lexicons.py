"""Loader and matcher for the human-curated per-language risk lexicons.

Why JSON files and not a live translation call
---------------------------------------------
Mistranslating a suicide-risk phrase is a *safety* bug, not a cosmetic bug. So
risk patterns are always read from a checked-in, versioned, human-curated file
per language, and never machine-translated at runtime. Languages we do not yet
have a signed-off file for fall back to "no patterns + low confidence", and
the UI says so explicitly.

Every lexicon also carries a `curation_status`:
  "PROTOTYPE" - hand-authored, broad, still needs professional sign-off
  "STUB"      - partial coverage; critical-tier hits are advisory only
"""

from __future__ import annotations

import functools
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import LEXICON_VERSION, settings

log = logging.getLogger(__name__)

TIER_CRITICAL = "critical"
TIER_HIGH = "high"
TIER_MODERATE = "moderate"
TIER_LOW = "low"

TIER_ORDER = {TIER_CRITICAL: 0, TIER_HIGH: 1, TIER_MODERATE: 2, TIER_LOW: 3}

#: Unicode block ranges used for script detection.
_SCRIPT_RANGES: List[Tuple[str, Tuple[int, int]]] = [
    ("bn", (0x0980, 0x09FF)),   # Bengali
    ("hi", (0x0900, 0x097F)),   # Devanagari (Hindi / Marathi)
    ("ta", (0x0B80, 0x0BFF)),   # Tamil
    ("te", (0x0C00, 0x0C7F)),   # Telugu
]

_LATIN_RE = re.compile(r"[A-Za-z]")

#: Zero-width and bidi control characters that must be stripped before matching.
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff\u2060]")


@dataclass
class FlagHit:
    flag: str
    tier: str
    weight: float
    label: str
    #: Short redacted excerpt of what matched, for the counsellor only.
    excerpt: str
    lexicon_language: str
    curated: bool

    def as_dict(self) -> Dict[str, object]:
        return {
            "flag": self.flag,
            "tier": self.tier,
            "weight": round(self.weight, 1),
            "label": self.label,
            "excerpt": self.excerpt,
            "lexicon_language": self.lexicon_language,
            "curated": self.curated,
        }


@dataclass
class Lexicon:
    language: str
    display_name: str
    native_name: str
    version: str
    curation_status: str
    flags: Dict[str, Dict[str, object]] = field(default_factory=dict)
    #: flag -> list of compiled patterns
    compiled: Dict[str, List[re.Pattern]] = field(default_factory=dict)
    absolutist: List[re.Pattern] = field(default_factory=list)
    negation: List[re.Pattern] = field(default_factory=list)
    hedge: List[re.Pattern] = field(default_factory=list)
    disfluent: List[re.Pattern] = field(default_factory=list)
    load_errors: List[str] = field(default_factory=list)
    #: The parsed file, kept so cue groups can be compiled alongside `flags`.
    _raw: Dict[str, object] = field(default_factory=dict, repr=False)

    @property
    def is_curated(self) -> bool:
        """True when coverage is good enough to trust for critical detection."""
        return self.curation_status != "STUB"

    def compile_all(self) -> None:
        self.compiled = {}
        for name, spec in self.flags.items():
            patterns: List[re.Pattern] = []
            for raw in spec.get("patterns", []) or []:
                try:
                    patterns.append(re.compile(raw, re.IGNORECASE | re.UNICODE))
                except re.error as exc:  # pragma: no cover - defensive
                    self.load_errors.append(f"{self.language}/{name}: {exc}")
            if patterns:
                self.compiled[name] = patterns

        def _compile_group(entries: object) -> List[re.Pattern]:
            out: List[re.Pattern] = []
            for raw in entries or []:  # type: ignore[union-attr]
                try:
                    out.append(re.compile(raw, re.IGNORECASE | re.UNICODE))
                except re.error as exc:  # pragma: no cover - defensive
                    self.load_errors.append(f"{self.language}/cue: {exc}")
            return out

        # Cue groups (absolutist terms, negation, hedging, disfluency) live at
        # the top level of the lexicon file, not inside `flags`.
        self.absolutist = _compile_group(self._raw.get("absolutist_terms"))
        self.negation = _compile_group(self._raw.get("negation_cues"))
        self.hedge = _compile_group(self._raw.get("hedge_cues"))
        self.disfluent = _compile_group(self._raw.get("disfluent_cues"))

    def match(self, text: str) -> List[FlagHit]:
        hits: List[FlagHit] = []
        for name, patterns in self.compiled.items():
            spec = self.flags[name]
            for pattern in patterns:
                m = pattern.search(text)
                if not m:
                    continue
                hits.append(
                    FlagHit(
                        flag=name,
                        tier=str(spec.get("tier", TIER_LOW)),
                        weight=float(spec.get("weight", 0)),  # type: ignore[arg-type]
                        label=str(spec.get("label", name)),
                        excerpt=_excerpt(text, m.start(), m.end()),
                        lexicon_language=self.language,
                        curated=self.is_curated,
                    )
                )
                break  # one hit per flag keeps the score interpretable
        hits.sort(key=lambda h: (TIER_ORDER.get(h.tier, 9), -h.weight))
        return hits

    def count_cues(self, patterns: List[re.Pattern], text: str) -> int:
        return sum(len(p.findall(text)) for p in patterns)


def _excerpt(text: str, start: int, end: int, pad: int = 34) -> str:
    """A short window around a match, collapsed to one line and length-capped."""
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    snippet = re.sub(r"\s+", " ", text[left:right]).strip()
    if left > 0:
        snippet = "..." + snippet
    if right < len(text):
        snippet = snippet + "..."
    return snippet[:140]


@functools.lru_cache(maxsize=1)
def _load_all() -> Dict[str, Lexicon]:
    directory: Path = settings.lexicon_dir
    lexicons: Dict[str, Lexicon] = {}
    if not directory.exists():
        log.warning("Lexicon directory %s not found - no risk patterns will match", directory)
        return lexicons

    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            log.error("Skipping malformed lexicon %s: %s", path.name, exc)
            continue
        lex = Lexicon(
            language=raw.get("language", path.stem),
            display_name=raw.get("display_name", path.stem),
            native_name=raw.get("native_name", path.stem),
            version=raw.get("version", LEXICON_VERSION),
            curation_status=raw.get("curation_status", "STUB"),
            flags=raw.get("flags", {}) or {},
            _raw=raw,
        )
        lex.compile_all()
        if lex.load_errors:
            log.warning("Lexicon %s had %d unusable pattern(s): %s", lex.language, len(lex.load_errors), lex.load_errors)
        lexicons[lex.language] = lex
    log.info("Loaded %d risk lexicons: %s", len(lexicons), ", ".join(sorted(lexicons)))
    return lexicons


def all_lexicons() -> Dict[str, Lexicon]:
    return _load_all()


def get_lexicon(language: str) -> Optional[Lexicon]:
    return _load_all().get((language or "en").lower())


def supported_languages() -> List[Dict[str, str]]:
    """Language metadata for the UI language switcher."""
    order = ["en", "hi", "bn", "mr", "ta", "te"]
    lexicons = _load_all()
    out: List[Dict[str, str]] = []
    for code in order:
        lex = lexicons.get(code)
        if lex is None:
            continue
        out.append(
            {
                "code": code,
                "display_name": lex.display_name,
                "native_name": lex.native_name,
                "curation_status": lex.curation_status,
            }
        )
    return out


def normalize(text: str) -> str:
    """NFKC-normalise, strip invisibles, collapse whitespace, lowercase."""
    if not text:
        return ""
    cleaned = _INVISIBLE_RE.sub("", text)
    cleaned = unicodedata.normalize("NFKC", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def detect_script_language(text: str) -> str:
    """Return the lexicon's expected language for a piece of text.

    Only counts letters, so punctuation/digits do not skew detection. Falls
    back to English for Latin script, which also covers Romanised Hindi
    ('Hinglish') input.
    """
    if not text:
        return "en"
    counts: Dict[str, int] = {}
    for ch in text:
        code = ord(ch)
        for lang, (low, high) in _SCRIPT_RANGES:
            if low <= code <= high:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if counts:
        return max(counts.items(), key=lambda kv: kv[1])[0]
    if _LATIN_RE.search(text):
        return "en"
    return "en"


def match(text: str, languages: Optional[List[str]] = None) -> Tuple[List[FlagHit], List[str], str]:
    """Match normalised `text` against one or more lexicons.

    Returns `(hits, languages_used, detected_script)`. When more than one
    language is consulted (e.g. English + a stub language) hits keep their
    `lexicon_language` so the UI can show which file fired.
    """
    normalized = normalize(text)
    if not normalized:
        return [], [], "en"

    detected = detect_script_language(normalized)
    lexicon_set = _load_all()

    if languages is None:
        languages = [detected]
        # Latin script may be Romanised Hindi/Marathi, so English patterns are
        # always applied as a backstop for Latin input.
        if detected == "en":
            languages = ["en"]
    else:
        languages = [lang for lang in languages if lang in lexicon_set] or [detected]

    hits: List[FlagHit] = []
    seen: set = set()
    for lang in languages:
        lex = lexicon_set.get(lang)
        if not lex:
            continue
        for hit in lex.match(normalized):
            key = (hit.flag, hit.lexicon_language)
            if key in seen:
                continue
            seen.add(key)
            hits.append(hit)

    hits.sort(key=lambda h: (TIER_ORDER.get(h.tier, 9), -h.weight))
    return hits, languages, detected

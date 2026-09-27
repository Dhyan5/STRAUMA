"""
Language detection service.

Auto-detects the language of victim input rather than asking them to
pick from a dropdown — distressed people often won't stop to select.

For prototype: Uses Unicode script detection heuristics.
For production: Would use fastText langid or Bhashini API.
"""
import re
from collections import Counter


# Unicode script ranges for major Indian languages
SCRIPT_RANGES = {
    "hi": [  # Devanagari (Hindi, Marathi, Sanskrit)
        (0x0900, 0x097F),  # Devanagari
    ],
    "bn": [  # Bengali
        (0x0980, 0x09FF),
    ],
    "ta": [  # Tamil
        (0x0B80, 0x0BFF),
    ],
    "te": [  # Telugu
        (0x0C00, 0x0C7F),
    ],
    "mr": [  # Marathi uses Devanagari — disambiguated by lexicon check
        (0x0900, 0x097F),
    ],
}

# Marathi-specific markers to distinguish from Hindi (both use Devanagari)
MARATHI_MARKERS = [
    "आहे", "नाही", "करतो", "करते", "आहेत", "होतं", "होता",
    "मला", "तुला", "त्याला", "तिला", "आम्ही", "तुम्ही",
    "काय", "कसं", "कुठे", "केव्हा", "का",
]


def detect_language(text: str) -> str:
    """
    Detect the primary language of input text.

    Returns ISO 639-1 language code: en, hi, te, ta, mr, bn
    Falls back to 'en' if uncertain.
    """
    if not text or not text.strip():
        return "en"

    # Count characters by script
    script_counts: Counter = Counter()
    latin_count = 0
    total_alpha = 0

    for char in text:
        cp = ord(char)
        if char.isalpha():
            total_alpha += 1

            # Check Latin (English)
            if (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):
                latin_count += 1
                continue

            # Check Indic scripts
            for lang, ranges in SCRIPT_RANGES.items():
                for start, end in ranges:
                    if start <= cp <= end:
                        script_counts[lang] += 1
                        break

    if total_alpha == 0:
        return "en"

    # If mostly Latin characters, it's English
    if latin_count / total_alpha > 0.7:
        return "en"

    # Find dominant Indic script
    if not script_counts:
        return "en"

    dominant_lang, dominant_count = script_counts.most_common(1)[0]

    # Disambiguate Hindi vs Marathi (both Devanagari)
    if dominant_lang in ("hi", "mr"):
        text_lower = text.lower()
        marathi_hits = sum(1 for m in MARATHI_MARKERS if m in text)
        if marathi_hits >= 2:
            return "mr"
        return "hi"

    return dominant_lang


def get_language_name(code: str) -> str:
    """Return human-readable language name."""
    names = {
        "en": "English",
        "hi": "Hindi",
        "te": "Telugu",
        "ta": "Tamil",
        "mr": "Marathi",
        "bn": "Bengali",
    }
    return names.get(code, "Unknown")

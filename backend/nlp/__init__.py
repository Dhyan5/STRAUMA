"""NLP and speech analytics for the NHAA 14566 Stress & Trauma Assessment module.

Sub-modules:
    lexicons       per-language, human-curated risk lexicons
    sentiment      multilingual sentiment (transformers, with honest fallback)
    text_analyzer  lexicon matching + linguistic markers -> text risk score
    audio_analyzer vocal-stress features (librosa, numpy fallback)
    translator     provider-agnostic translation interface (UI copy only)
    ui_strings     curated complainant-facing copy (English + Hindi)
"""

__all__ = [
    "lexicons",
    "sentiment",
    "text_analyzer",
    "audio_analyzer",
    "translator",
    "ui_strings",
]

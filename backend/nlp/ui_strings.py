"""Curated UI copy for the victim-facing portal (English + Hindi).

Two hard rules encoded here:

1. No string in this file may contain a number, a score, or the words
   "risk", "score", "category", "SVI" or "vulnerability index". A complainant
   never sees their own numeric assessment. `assert_no_score_leakage` enforces
   that at test time.
2. Every string is written to be read out loud by someone in distress: short
   sentences, second person, no clinical jargon, no blame.

Bengali / Marathi / Tamil / Telugu fall through `nlp.translator`, which
returns them untranslated and flagged, rather than guessing.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from nlp import translator

EN: Dict[str, str] = {
    "app.title": "Support Portal",
    "app.subtitle": "A safe place to tell us what is happening",
    "disclaimer": "Prototype for demonstration purposes. Not a diagnostic tool. All risk flags are reviewed by trained personnel.",
    "quick_exit": "Quick exit",
    "quick_exit_hint": "Leave this page now",
    "language.label": "Language",
    "landing.heading": "You are not alone. We are listening.",
    "landing.body": "You can tell us what is happening in your own words, in your language. You can stop at any time. You do not have to give your name.",
    "cta.start": "Start",
    "cta.continue": "Continue",
    "cta.submit": "Send",
    "cta.back": "Back",
    "cta.skip_optional": "Skip this question",
    "consent.heading": "Before you begin",
    "consent.point_record": "We will record what you type or say, so a counsellor can read it later.",
    "consent.point_analyse": "A computer will look for signs that you may need urgent help. It only sorts requests. A trained person makes every decision.",
    "consent.point_share": "Only the counsellors handling your request will see it. We do not share your name because we never ask for it.",
    "consent.point_retention": "We keep this for a limited time, then delete it.",
    "consent.point_stop": "You can stop at any moment and nothing will be sent.",
    "consent.checkbox": "I understand and I agree to continue.",
    "consent.need_help_now": "I need help right now",
    "channel.label": "How would you like to tell us?",
    "channel.chat": "Type it",
    "channel.voice": "Say it",
    "channel.ivrs": "Phone menu",
    "chat.prompt_one": "In your own words, what is happening?",
    "chat.prompt_more": "Is there anything else you want to add?",
    "chat.placeholder": "Type here, in any language",
    "voice.record": "Hold the button and speak",
    "voice.stop": "Stop recording",
    "voice.re_record": "Record again",
    "voice.use_demo": "No microphone? Use a practice recording",
    "voice.demo_note": "This is a computer-generated practice clip, not a recording of you.",
    "voice.heard": "Thank you. We have what you said.",
    "ivrs.heading": "Phone menu",
    "ivrs.hint": "Use the numbers below, like a phone menu.",
    "ivrs.press": "Press",
    "ivrs.option_language": "for language",
    "ivrs.option_talk": "to tell us what is happening",
    "ivrs.option_helpline": "for helpline numbers",
    "ivrs.option_emergency": "if you need help right now",
    "selfreport.heading": "A few quick questions",
    "selfreport.note": "These are not a test and nothing is scored. Answer only what you want to.",
    "selfreport.q_safety": "How safe do you feel right now?",
    "selfreport.q_support": "Is there someone you trust nearby?",
    "selfreport.q_heard": "Do you feel heard by the people around you?",
    "selfreport.q_rest": "Have you been able to rest?",
    "selfreport.q_urgent": "Do you need someone to reach you soon?",
    "option.a_lot": "A lot",
    "option.some": "Somewhat",
    "option.a_little": "Only a little",
    "option.not_at_all": "Not at all",
    "option.yes": "Yes",
    "option.no": "No",
    "option.prefer_not": "I would rather not say",
    "done.heading": "Thank you for telling us.",
    "done.body": "A counsellor will read this and contact you. You do not need to explain again.",
    "done.reference": "Your reference",
    "done.what_next": "What happens next",
    "done.bridge_live": "A counsellor is being connected to you now. Stay on this screen if you can.",
    "done.callback": "A counsellor will call you. Keep your phone nearby.",
    "done.resources": "You can call any of these at any time, free of charge.",
    "done.save_reference": "Write down your reference number so you can quote it.",
    "resources.heading": "Free helplines, any time",
    "resources.tele_manas": "Tele MANAS",
    "resources.women_helpline": "Women Helpline",
    "resources.police": "Police emergency",
    "resources.nhaa": "NHAA",
    "error.generic": "Something went wrong. Please try again.",
    "error.network": "We could not reach the service. Please try again, or call the helplines above.",
    "footer.prototype": "Prototype for demonstration purposes. Not a diagnostic tool.",
}

HI: Dict[str, str] = {
    "app.title": "सहायता पोर्टल",
    "app.subtitle": "यहाँ आप बता सकते हैं कि क्या हो रहा है",
    "disclaimer": "यह एक डेमो प्रोटोटाइप है, निदान का उपकरण नहीं। सभी संकेत योग्य प्रशिक्षित व्यक्ति देखते हैं।",
    "quick_exit": "तुरंत बाहर निकलें",
    "quick_exit_hint": "अभी यह पेज छोड़ें",
    "language.label": "भाषा",
    "landing.heading": "आप अकेली नहीं हैं। हम सुन रहे हैं।",
    "landing.body": "आप अपनी भाषा में, अपने शब्दों में बता सकते हैं कि क्या हो रहा है। आप कभी भी रुक सकते हैं। अपना नाम देना ज़रूरी नहीं है।",
    "cta.start": "शुरू करें",
    "cta.continue": "आगे बढ़ें",
    "cta.submit": "भेजें",
    "cta.back": "पीछे",
    "cta.skip_optional": "यह सवाल छोड़ें",
    "consent.heading": "शुरू करने से पहले",
    "consent.point_record": "आप जो लिखेंगी या बोलेंगे, वह रिकॉर्ड होगा, ताकि बाद में एक काउंसलर पढ़ सके।",
    "consent.point_analyse": "एक कंप्यूटर यह देखेगा कि आपको तुरंत मदद चाहिए या नहीं। वह केवल क्रम तय करता है। हर निर्णय प्रशिक्षित व्यक्ति करते हैं।",
    "consent.point_share": "आपके मामले को संभालने वाले काउंसलर ही इसे देखते हैं। हम नाम नहीं माँगते, इसलिए साझा नहीं करते।",
    "consent.point_retention": "हम इसे सीमित समय तक रखते हैं, फिर हटा देते हैं।",
    "consent.point_stop": "आप कभी भी रुक सकते हैं, कुछ भी नहीं भेजा जाएगा।",
    "consent.checkbox": "मैं समझती/समझता हूँ और आगे बढ़ने के लिए सहमत हूँ।",
    "consent.need_help_now": "मुझे अभी मदद चाहिए",
    "channel.label": "आप कैसे बताना चाहेंगे?",
    "channel.chat": "लिखकर बताएँ",
    "channel.voice": "बोलकर बताएँ",
    "channel.ivrs": "फ़ोन मेन्यू",
    "chat.prompt_one": "अपने शब्दों में बताएँ, क्या हो रहा है?",
    "chat.prompt_more": "क्या आप कुछ और जानाना चाहेंगे?",
    "chat.placeholder": "यहाँ लिखें, किसी भी भाषा में",
    "voice.record": "बटन दबाए रखें और बोलें",
    "voice.stop": "रिकॉर्डिंग रोकें",
    "voice.re_record": "दोबारा रिकॉर्ड करें",
    "voice.use_demo": "माइक्रोफ़ोन नहीं है? अभ्यास रिकॉर्डिंग चलाएँ",
    "voice.demo_note": "यह कंप्यूटर से बनी अभ्यास रिकॉर्डिंग है, आपकी नहीं।",
    "voice.heard": "धन्यवाद। आपकी बात हमें मिल गई।",
    "ivrs.heading": "फ़ोन मेन्यू",
    "ivrs.hint": "फ़ोन मेन्यू की तरह नीचे दिए अंक दबाएँ।",
    "ivrs.press": "दबाएँ",
    "ivrs.option_language": "भाषा के लिए",
    "ivrs.option_talk": "क्या हो रहा है बताने के लिए",
    "ivrs.option_helpline": "हेल्पलाइन नंबर के लिए",
    "ivrs.option_emergency": "अभी मदद चाहिए तो",
    "selfreport.heading": "कुछ छोटे सवाल",
    "selfreport.note": "यह कोई परीक्षा नहीं है और कुछ भी गिना नहीं जाता। जो चाहें उत्तर दें।",
    "selfreport.q_safety": "आप इस समय कितना सुरक्षित महसूस कर रहे हैं?",
    "selfreport.q_support": "क्या आपके पास कोई भरोसेमंद व्यक्ति है?",
    "selfreport.q_heard": "क्या आपको लगता है आपकी बात लोग सुनते हैं?",
    "selfreport.q_rest": "क्या आप आराम कर पाए?",
    "selfreport.q_urgent": "क्या आपको जल्दी कोई संपर्क चाहिए?",
    "option.a_lot": "बहुत",
    "option.some": "कुछ हद तक",
    "option.a_little": "बहुत कम",
    "option.not_at_all": "बिल्कुल नहीं",
    "option.yes": "हाँ",
    "option.no": "नहीं",
    "option.prefer_not": "कहना नहीं चाहती/चाहता",
    "done.heading": "यह बताकर धन्यवाद।",
    "done.body": "एक काउंसलर इसे पढ़कर आपसे संपर्क करेगा। आपको दोबारा कुछ नहीं बताना होगा।",
    "done.reference": "आपका संदर्भ नंबर",
    "done.what_next": "आगे क्या होगा",
    "done.bridge_live": "एक काउंसलर को अभी आपसे जोड़ा जा रहा है। हो सके तो इसी स्क्रीन पर रहें।",
    "done.callback": "एक काउंसलर आपको फ़ोन करेगा। फ़ोन पास रखें।",
    "done.resources": "आप इनमें से किसी भी नंबर पर कभी भी, मुफ़्त कॉल कर सकते हैं।",
    "done.save_reference": "अपना संदर्भ नंबर लिख लें ताकि आप बाद में बता सकें।",
    "resources.heading": "मुफ़्त हेल्पलाइन, कभी भी",
    "resources.tele_manas": "टेली मानस",
    "resources.women_helpline": "महिला हेल्पलाइन",
    "resources.police": "पुलिस आपातकाल",
    "resources.nhaa": "एनएचएए",
    "error.generic": "कुछ गड़बड़ हुई। कृपया दोबारा कोशिश करें।",
    "error.network": "हम सेवा तक नहीं पहुँच सके। कृपया दोबारा कोशिश करें, या ऊपर दिए नंबर पर कॉल करें।",
    "footer.prototype": "यह डेमो प्रोटोटाइप है, निदान का उपकरण नहीं।",
}

TABLES: Dict[str, Dict[str, str]] = {"en": EN, "hi": HI}

#: Terms that must never appear in complainant-facing copy.
FORBIDDEN_IN_VICTIM_COPY = [
    r"\bscore\b", r"\brisk\b", r"\bcategor", r"\bsvi\b", r"\bindex\b",
    r"\bvulnerab", r"\bdiagnos", r"\bdepress", r"\bsuicid", r"\bdiagnostic\b",
    r"\d{1,3}\s*(?:/|out of)\s*100",
]
_FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_IN_VICTIM_COPY), re.IGNORECASE)


def _approved_boilerplate() -> frozenset:
    """Strings that are *required* to mention the words the checker forbids.

    The mandated disclaimer has to say "Not a diagnostic tool" and "All risk
    flags are reviewed by trained personnel", so it necessarily trips
    `\\bdiagnos` and `\\brisk`. The brief requires that text verbatim, and it is
    the opposite of a leak. The exemption is an exact-match allowlist of that
    boilerplate plus its translations - not a weakening of the patterns, so any
    *other* string that mentions risk or diagnosis still fails the check.
    """
    return frozenset(
        value for value in (EN.get("disclaimer"), HI.get("disclaimer"), EN.get("footer.prototype"), HI.get("footer.prototype")) if value
    )


APPROVED_BOILERPLATE = _approved_boilerplate()


def assert_no_score_leakage(table_name: str, table: Dict[str, str]) -> List[str]:
    """Return a list of leaks. Empty list == safe. Called by the test suite."""
    leaks: List[str] = []
    for key, value in table.items():
        if value in APPROVED_BOILERPLATE:
            continue
        match = _FORBIDDEN_RE.search(value)
        if match:
            leaks.append(f"{table_name}:{key} -> {match.group(0)!r}")
    return leaks


def t(key: str, language: str = "en", **kwargs: object) -> str:
    """Look up a UI string, falling back: target table -> English -> key."""
    language = (language or "en").lower()
    table = TABLES.get(language)
    if table and key in table:
        return _format(table[key], kwargs)
    english = EN.get(key)
    if english is not None:
        if language not in CURATED and language in translator.SUPPORTED:
            result = translator.translate(english, "en", language)
            return _format(result.text, kwargs)
        return _format(english, kwargs)
    return key


def _format(template: str, kwargs: dict) -> str:
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def available_languages() -> List[Dict[str, str]]:
    from nlp.lexicons import supported_languages

    out: List[Dict[str, str]] = []
    for entry in supported_languages():
        code = str(entry["code"])
        out.append(
            {
                "code": code,
                "label": TABLES.get(code, {}).get("app.title", entry["display_name"]),
                "native_name": entry["native_name"],
                "curated_ui": "true" if code in TABLES else "false",
            }
        )
    return out


def has_curated_copy(language: str) -> bool:
    return (language or "en").lower() in TABLES


def t_opt(key: str, language: str = "en", default: Optional[str] = None, **kwargs: object) -> str:
    value = t(key, language, **kwargs)
    return value if value != key else (default or key)

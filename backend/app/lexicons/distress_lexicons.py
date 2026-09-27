"""
Curated multilingual lexicons for keyword/pattern-based distress detection.

These lexicons serve as a RULE-BASED SAFETY NET that overrides ML scores:
- Any match in the CRITICAL_OVERRIDE categories forces risk = CRITICAL
- Density of matches in other categories contributes to the keyword_density sub-score

Categories:
  - self_harm:       Suicidal ideation, self-injury language
  - immediate_threat: Active violence, ongoing assault, life in danger
  - violence:        Physical/sexual violence references
  - fear:            Expressions of fear, helplessness, entrapment
  - isolation:       Social isolation, being cut off from support
  - discrimination:  Caste-based slurs, untouchability, exclusion

CRITICAL_OVERRIDE categories: self_harm, immediate_threat
"""

# Categories that force an immediate CRITICAL override regardless of SVI score
CRITICAL_OVERRIDE_CATEGORIES = {"self_harm", "immediate_threat"}

LEXICONS: dict[str, dict[str, list[str]]] = {
    # ─── English ──────────────────────────────────────────────────────────
    "en": {
        "self_harm": [
            "want to die", "kill myself", "end my life", "suicide",
            "no reason to live", "better off dead", "can't go on",
            "want to end it", "take my own life", "self harm",
            "cut myself", "hurt myself", "overdose", "hang myself",
            "jump off", "slit my wrist", "no point living",
            "wish i was dead", "wish i were dead", "don't want to live",
            "life is not worth", "ending it all", "pills",
        ],
        "immediate_threat": [
            "he is hitting me", "she is hitting me", "being beaten",
            "right now", "help me now", "going to kill me",
            "he has a weapon", "knife", "gun", "locked me in",
            "can't escape", "won't let me leave", "choking me",
            "strangling", "burning me", "pouring acid",
            "beating me right now", "attacking me", "please send help",
            "emergency", "he's here", "they're coming",
        ],
        "violence": [
            "beat me", "hit me", "slapped", "punched", "kicked",
            "raped", "sexual assault", "molested", "forced me",
            "stripped", "burnt", "acid attack", "stab",
            "assault", "attacked", "tortured", "abuse",
            "domestic violence", "marital rape", "dowry",
            "thrashed", "threw me", "dragged",
        ],
        "fear": [
            "scared", "terrified", "afraid", "frightened", "helpless",
            "hopeless", "trapped", "nowhere to go", "no one to help",
            "alone", "abandoned", "can't breathe", "panic",
            "nightmare", "can't sleep", "fear for my life",
            "they will find me", "threatened to kill",
            "blackmail", "threatening", "stalking",
        ],
        "isolation": [
            "no one believes me", "no one will help", "all alone",
            "family won't support", "thrown out", "disowned",
            "nowhere to go", "cut off", "no money", "no phone",
            "took my documents", "won't let me work",
            "locked inside", "not allowed to leave",
            "social boycott", "ostracized", "excommunicated",
        ],
        "discrimination": [
            "untouchable", "lower caste", "dalit", "chamar",
            "bhangi", "dom", "musahar", "caste abuse",
            "refused entry", "separate glass", "cannot use well",
            "denied access", "caste discrimination",
            "atrocity", "social boycott", "honor killing",
            "inter-caste", "manual scavenging",
        ],
    },

    # ─── Hindi ────────────────────────────────────────────────────────────
    "hi": {
        "self_harm": [
            "मरना चाहता हूं", "मरना चाहती हूं", "जीने का मन नहीं",
            "आत्महत्या", "खुद को मार डालना", "ज़हर खा लूंगा",
            "ज़हर खा लूंगी", "जीना नहीं चाहता", "जीना नहीं चाहती",
            "मर जाऊंगा", "मर जाऊंगी", "जान दे दूंगा", "जान दे दूंगी",
            "फांसी लगा लूंगा", "नींद की गोलियां", "कलाई काट",
        ],
        "immediate_threat": [
            "मार रहा है", "पीट रहा है", "अभी मदद चाहिए",
            "जान से मार देगा", "चाकू", "बंदूक", "बंद कर दिया है",
            "बाहर नहीं निकलने दे रहा", "गला दबा रहा है",
            "तेजाब", "जला रहा है", "मदद भेजो", "वो यहां है",
            "मार डालेगा", "जान का खतरा",
        ],
        "violence": [
            "मारपीट", "पिटाई", "थप्पड़", "लात", "मुक्का",
            "बलात्कार", "छेड़छाड़", "यौन शोषण", "जबरदस्ती",
            "कपड़े उतारे", "जलाया", "तेजाब", "हमला",
            "प्रताड़ना", "घरेलू हिंसा", "दहेज", "मारा",
        ],
        "fear": [
            "डर लगता है", "डरी हुई हूं", "बेबस", "लाचार",
            "फंसी हुई हूं", "कहीं जाने की जगह नहीं",
            "कोई मदद नहीं", "अकेली", "सो नहीं पाती",
            "जान से मारने की धमकी", "ब्लैकमेल",
            "पीछा कर रहा है", "धमकी दे रहा है",
        ],
        "isolation": [
            "कोई विश्वास नहीं करता", "अकेली हूं", "घर से निकाल दिया",
            "कहीं जाने की जगह नहीं", "पैसे नहीं हैं", "फोन छीन लिया",
            "कागजात ले लिए", "काम नहीं करने देता",
            "बाहर नहीं जाने देता", "सामाजिक बहिष्कार",
        ],
        "discrimination": [
            "अछूत", "नीची जाति", "दलित", "चमार", "भंगी",
            "डोम", "मुसहर", "जातिगत भेदभाव", "प्रवेश नहीं दिया",
            "अलग बर्तन", "कुआं नहीं छूने दिया", "अत्याचार",
            "सामाजिक बहिष्कार", "ऑनर किलिंग", "हाथ से मैला",
        ],
    },

    # ─── Telugu ───────────────────────────────────────────────────────────
    "te": {
        "self_harm": [
            "చనిపోవాలని ఉంది", "ఆత్మహత్య", "బతకడం ఇష్టం లేదు",
            "నన్ను నేను చంపుకుంటాను", "విషం తాగుతాను",
            "బతకడం వల్ల ప్రయోజనం లేదు",
        ],
        "immediate_threat": [
            "కొడుతున్నాడు", "ఇప్పుడు సహాయం కావాలి",
            "చంపేస్తాడు", "కత్తి", "తుపాకి", "బంధించాడు",
            "బయటకు వెళ్ళనివ్వడం లేదు", "సహాయం పంపండి",
        ],
        "violence": [
            "కొట్టాడు", "చెంపదెబ్బ", "తన్నాడు", "అత్యాచారం",
            "లైంగిక వేధింపు", "బలవంతంగా", "కాల్చాడు",
            "యాసిడ్ దాడి", "హింస", "గృహ హింస",
        ],
        "fear": [
            "భయంగా ఉంది", "నిస్సహాయంగా", "చిక్కుకున్నాను",
            "ఎక్కడికి వెళ్ళాలో తెలియదు", "ఎవరూ సహాయం చేయరు",
            "బెదిరిస్తున్నాడు", "వెంటాడుతున్నాడు",
        ],
        "isolation": [
            "ఎవరూ నమ్మరు", "ఒంటరిగా", "ఇంటి నుండి వెళ్ళగొట్టారు",
            "డబ్బులు లేవు", "ఫోన్ లాక్కున్నాడు",
            "సామాజిక బహిష్కరణ",
        ],
        "discrimination": [
            "అంటరానివాడు", "కింది కులం", "దళితుడు",
            "కులవివక్ష", "ప్రవేశం నిరాకరించారు",
            "అత్యాచారం", "సామాజిక బహిష్కరణ",
        ],
    },

    # ─── Tamil ────────────────────────────────────────────────────────────
    "ta": {
        "self_harm": [
            "சாகணும்", "தற்கொலை", "உயிரை மாய்ச்சுக்கணும்",
            "வாழ பிடிக்கல", "விஷம் குடிக்கணும்",
        ],
        "immediate_threat": [
            "அடிக்கிறான்", "இப்ப உதவி வேணும்",
            "கொன்னுடுவான்", "கத்தி", "துப்பாக்கி",
            "பூட்டி வச்சிருக்கான்", "உதவி அனுப்புங்க",
        ],
        "violence": [
            "அடிச்சான்", "உதைச்சான்", "பலாத்காரம்",
            "பாலியல் வன்கொடுமை", "கட்டாயப்படுத்தினான்",
            "ஆசிட் தாக்குதல்", "வன்முறை", "குடும்ப வன்முறை",
        ],
        "fear": [
            "பயமா இருக்கு", "நிலையில்லாம", "சிக்கிக்கிட்டேன்",
            "எங்க போவதென்று தெரியல", "யாரும் உதவ மாட்டாங்க",
            "மிரட்டுகிறான்", "பின்தொடர்கிறான்",
        ],
        "isolation": [
            "யாரும் நம்ப மாட்டாங்க", "தனியா", "வீட்டை விட்டு துரத்தினாங்க",
            "பணம் இல்ல", "போன் பறிச்சான்",
            "சமூக புறக்கணிப்பு",
        ],
        "discrimination": [
            "தீண்டாமை", "கீழ் சாதி", "தலித்",
            "சாதி பாகுபாடு", "நுழைய விடல",
            "கொடுமை", "சமூக புறக்கணிப்பு",
        ],
    },

    # ─── Marathi ──────────────────────────────────────────────────────────
    "mr": {
        "self_harm": [
            "मला मरायचं आहे", "आत्महत्या", "जगायचं नाही",
            "विष खाईन", "जीव देईन", "फास लावीन",
        ],
        "immediate_threat": [
            "मारतोय", "आत्ता मदत हवी", "जीवे मारेल",
            "सुरी", "बंदूक", "कोंडून ठेवलंय",
            "बाहेर जाऊ देत नाही", "मदत पाठवा",
        ],
        "violence": [
            "मारहाण", "थप्पड", "लाथ", "बलात्कार",
            "लैंगिक अत्याचार", "जबरदस्ती", "जाळलं",
            "ॲसिड हल्ला", "हिंसा", "कौटुंबिक हिंसा",
        ],
        "fear": [
            "भीती वाटते", "असहाय", "अडकले आहे",
            "कुठे जायचं कळत नाही", "कोणी मदत करत नाही",
            "धमकी देतोय", "पाठलाग करतोय",
        ],
        "isolation": [
            "कोणी विश्वास ठेवत नाही", "एकटी", "घरातून काढलं",
            "पैसे नाहीत", "फोन काढून घेतला",
            "सामाजिक बहिष्कार",
        ],
        "discrimination": [
            "अस्पृश्य", "खालची जात", "दलित",
            "जातीय भेदभाव", "प्रवेश नाकारला",
            "अत्याचार", "सामाजिक बहिष्कार",
        ],
    },

    # ─── Bengali ──────────────────────────────────────────────────────────
    "bn": {
        "self_harm": [
            "মরে যেতে চাই", "আত্মহত্যা", "বাঁচতে চাই না",
            "বিষ খাব", "প্রাণ দেব", "গলায় দড়ি দেব",
        ],
        "immediate_threat": [
            "মারছে", "এখনই সাহায্য চাই", "মেরে ফেলবে",
            "ছুরি", "বন্দুক", "বন্ধ করে রেখেছে",
            "বেরোতে দিচ্ছে না", "সাহায্য পাঠাও",
        ],
        "violence": [
            "মারধোর", "চড়", "লাথি", "ধর্ষণ",
            "যৌন নির্যাতন", "জোর করে", "পুড়িয়ে দিয়েছে",
            "অ্যাসিড আক্রমণ", "হিংসা", "পারিবারিক হিংসা",
        ],
        "fear": [
            "ভয় লাগছে", "অসহায়", "আটকে আছি",
            "কোথায় যাব বুঝতে পারছি না", "কেউ সাহায্য করবে না",
            "হুমকি দিচ্ছে", "পিছু নিচ্ছে",
        ],
        "isolation": [
            "কেউ বিশ্বাস করে না", "একা", "বাড়ি থেকে তাড়িয়ে দিয়েছে",
            "টাকা নেই", "ফোন কেড়ে নিয়েছে",
            "সামাজিক বয়কট",
        ],
        "discrimination": [
            "অস্পৃশ্য", "নীচু জাত", "দলিত",
            "জাতি বৈষম্য", "প্রবেশ দেওয়া হয়নি",
            "অত্যাচার", "সামাজিক বয়কট",
        ],
    },
}


def get_all_languages() -> list[str]:
    """Return list of supported language codes."""
    return list(LEXICONS.keys())


def get_lexicon(language: str) -> dict[str, list[str]]:
    """Get lexicon for a language, falling back to English."""
    return LEXICONS.get(language, LEXICONS["en"])

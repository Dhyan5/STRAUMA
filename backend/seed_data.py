"""
Seed script — populates the database with realistic synthetic cases
for demo purposes. Each case demonstrates a different risk scenario.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_db, SessionLocal
from app.models.database import Case, ChannelSource, CaseStatus
from app.services.scoring_engine import compute_svi
from app.services.language_detection import detect_language
from app.models.database import Assessment, RiskCategory, AuditLog
from datetime import datetime, timezone, timedelta
import random


SAMPLE_CASES = [
    # CRITICAL — self-harm ideation
    {
        "text": "I can't take this anymore. Every day they come to our house and threaten us. They threw acid on my brother last month. I want to die. There is no point living like this. The police won't file our FIR. Nobody helps us. I want to end it all.",
        "channel": "chat",
        "hours_ago": 0.5,
    },
    # CRITICAL — immediate threat (Hindi)
    {
        "text": "वो मुझे मार रहा है अभी मदद चाहिए। उसके पास चाकू है। मुझे बाहर नहीं जाने दे रहा। बच्चे डर गए हैं। प्लीज मदद भेजो जल्दी।",
        "channel": "voice",
        "hours_ago": 1,
    },
    # HIGH — ongoing violence, fear
    {
        "text": "They beat my husband in front of the whole village because he went to the upper-caste well. He is injured badly. They said if we go to police they will burn our house. I am scared and helpless. We have nowhere to go. They have done social boycott of our family.",
        "channel": "chat",
        "hours_ago": 2,
    },
    # HIGH — Telugu, discrimination + violence
    {
        "text": "మా ఊళ్ళో మాకు దేవాలయంలో ప్రవేశం నిరాకరించారు. నిన్న రాత్రి వాళ్ళు మా ఇంటికి వచ్చి కొట్టారు. మా పిల్లలకు భయంగా ఉంది. పోలీసులు ఏమీ చేయరు. సహాయం కావాలి.",
        "channel": "portal",
        "hours_ago": 3,
    },
    # MODERATE — threats and discrimination
    {
        "text": "I am a Dalit teacher in a government school. The upper caste teachers refuse to eat with me. They have filed a false complaint against me to get me transferred. The headmaster supports them. I feel isolated and don't know what to do. My family depends on this job.",
        "channel": "chat",
        "hours_ago": 5,
    },
    # MODERATE — property dispute with caste angle
    {
        "text": "They occupied our ancestral land. When we protested, they said lower castes have no right to own land in this village. The revenue officer is also from their caste and refuses to help. We have been living in fear for two months now.",
        "channel": "portal",
        "hours_ago": 8,
    },
    # LOW — informational query
    {
        "text": "I want to know about the SC/ST Prevention of Atrocities Act. What protection does it provide? Can I file a complaint if someone denied me entry to a temple because of my caste? What documents do I need?",
        "channel": "chat",
        "hours_ago": 12,
    },
    # LOW — follow-up on existing case
    {
        "text": "I filed a complaint last month about caste discrimination at my workplace. Case number was given. I want to check the status of my complaint. The officer said they would investigate but I haven't heard back.",
        "channel": "portal",
        "hours_ago": 24,
    },
    # HIGH — Marathi, domestic violence + caste
    {
        "text": "माझ्या नवऱ्याच्या घरचे मला मारतात कारण मी खालच्या जातीची आहे. दहेज मागतात. मला जीवे मारेल अशी धमकी देतोय. मला बाहेर जाऊ देत नाही. मला मदत हवी. एकटी आहे. कोणी विश्वास ठेवत नाही.",
        "channel": "voice",
        "hours_ago": 4,
    },
    # CRITICAL — Bengali, assault in progress
    {
        "text": "ওরা আমাদের বাড়িতে আগুন লাগিয়ে দিয়েছে। আমরা দলিত বলে। পুলিশ আসছে না। আমার বাবা গুরুতর আহত। এখনই সাহায্য চাই। জীবনের ভয়ে আছি। সাহায্য পাঠাও।",
        "channel": "voice",
        "hours_ago": 0.2,
    },
    # MODERATE — Tamil, social boycott
    {
        "text": "எங்கள் குடும்பத்தை கிராமத்தில் இருந்து சமூக புறக்கணிப்பு செய்கிறார்கள். கடைகளில் பொருள் விற்க மறுக்கிறார்கள். பிள்ளைகளை பள்ளிக்கு அனுப்ப பயமா இருக்கு. என்ன செய்வதென்று தெரியவில்லை.",
        "channel": "chat",
        "hours_ago": 6,
    },
    # HIGH — witness intimidation
    {
        "text": "I witnessed an atrocity against a Scheduled Tribe family. I gave my statement to the police. Now the accused are threatening to kill me if I don't take back my statement. They came to my house yesterday and said they would destroy my family. I am terrified. I need witness protection.",
        "channel": "portal",
        "hours_ago": 3,
    },
]


def seed_database():
    """Create sample cases and run assessments on each."""
    init_db()
    db = SessionLocal()

    try:
        # Check if already seeded
        existing = db.query(Case).count()
        if existing > 0:
            print(f"Database already has {existing} cases. Skipping seed.")
            return

        print("Seeding database with sample cases...")

        for i, sample in enumerate(SAMPLE_CASES):
            text = sample["text"]
            channel = ChannelSource(sample["channel"])
            lang = detect_language(text)

            # Create case
            case = Case(
                channel=channel,
                language_detected=lang,
                consent_given=True,
                consent_timestamp=datetime.now(timezone.utc) - timedelta(hours=sample["hours_ago"]),
                raw_text=text,
                created_at=datetime.now(timezone.utc) - timedelta(hours=sample["hours_ago"]),
                status=CaseStatus.NEW,
            )
            db.add(case)
            db.flush()

            # Run assessment
            result = compute_svi(text=text, language=lang)
            risk_enum = RiskCategory(result.risk_category)

            assessment = Assessment(
                case_id=case.id,
                text_sentiment_score=result.text_sentiment_score,
                keyword_density_score=result.keyword_density_score,
                voice_prosody_score=result.voice_prosody_score,
                interaction_pattern_score=result.interaction_pattern_score,
                svi_score=result.svi_score,
                risk_category=risk_enum,
                hard_override=result.hard_override,
                override_reason=result.override_reason,
                triggered_keywords=[kw.to_dict() for kw in result.triggered_keywords],
                sub_score_details=result.sub_score_details,
                created_at=case.created_at,
            )
            db.add(assessment)

            # Assign counsellors to high/critical cases
            if risk_enum in (RiskCategory.HIGH, RiskCategory.CRITICAL):
                case.status = CaseStatus.ASSIGNED
                case.assigned_to = random.choice(["usr-counsellor-001", "usr-counsellor-002"])

            # Audit
            audit = AuditLog(
                case_id=case.id,
                action="CASE_CREATED",
                timestamp=case.created_at,
                details={"channel": sample["channel"], "language": lang, "seeded": True},
            )
            db.add(audit)

            override_txt = " [!OVERRIDE]" if result.hard_override else ""
            print(
                f"  [{i+1}/{len(SAMPLE_CASES)}] Case {case.id[:8]}... | "
                f"Lang: {lang} | SVI: {result.svi_score:.1f} | "
                f"Risk: {result.risk_category.upper()}{override_txt}"
            )

        db.commit()
        print(f"\n[OK] Seeded {len(SAMPLE_CASES)} cases successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()

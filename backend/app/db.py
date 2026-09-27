"""
Database session management and initialization.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.database import Base, RecommendationRule, User, RiskCategory, UserRole
from passlib.context import CryptContext

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nhaa.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db():
    """FastAPI dependency — yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and seed default data."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_recommendation_rules(db)
        _seed_demo_users(db)
        db.commit()
    finally:
        db.close()


def _seed_recommendation_rules(db: Session):
    """Insert default recommendation rules if not present."""
    existing = db.query(RecommendationRule).count()
    if existing > 0:
        return

    rules = [
        RecommendationRule(
            risk_category=RiskCategory.LOW,
            actions=[
                "Log case in system",
                "Schedule standard follow-up call within 48 hours",
                "Send informational resources via SMS/email",
            ],
            response_window="48 hours",
            notify_roles=["counsellor"],
        ),
        RecommendationRule(
            risk_category=RiskCategory.MODERATE,
            actions=[
                "Assign counsellor callback within 24 hours",
                "Share legal aid information and helpline numbers",
                "Send nearest protection officer contact details",
                "Document case for district-level review",
            ],
            response_window="24 hours",
            notify_roles=["counsellor"],
        ),
        RecommendationRule(
            risk_category=RiskCategory.HIGH,
            actions=[
                "Immediate counsellor assignment",
                "Legal aid referral — connect with district legal services authority",
                "Medical referral if injuries reported",
                "Flag to district SC/ST welfare officer",
                "Notify protection officer for follow-up visit",
            ],
            response_window="4 hours",
            notify_roles=["counsellor", "district_admin"],
        ),
        RecommendationRule(
            risk_category=RiskCategory.CRITICAL,
            actions=[
                "EMERGENCY: Real-time alert to on-duty counsellor",
                "Alert local police liaison / PCR van dispatch",
                "Push emergency helpline number (112, 181) to victim",
                "Initiate witness protection protocol notification",
                "Notify district magistrate office",
                "Medical emergency services alert if physical harm indicated",
            ],
            response_window="Immediate",
            notify_roles=["counsellor", "district_admin", "super_admin"],
        ),
    ]
    db.add_all(rules)


def _seed_demo_users(db: Session):
    """Create demo users for the prototype."""
    existing = db.query(User).count()
    if existing > 0:
        return

    demo_users = [
        User(
            id="usr-admin-001",
            username="admin",
            hashed_password=pwd_context.hash("admin123"),
            full_name="System Administrator",
            role=UserRole.SUPER_ADMIN,
            district="National",
        ),
        User(
            id="usr-counsellor-001",
            username="priya.sharma",
            hashed_password=pwd_context.hash("demo123"),
            full_name="Dr. Priya Sharma",
            role=UserRole.COUNSELLOR,
            district="Delhi",
        ),
        User(
            id="usr-counsellor-002",
            username="rajesh.kumar",
            hashed_password=pwd_context.hash("demo123"),
            full_name="Rajesh Kumar",
            role=UserRole.COUNSELLOR,
            district="Maharashtra",
        ),
        User(
            id="usr-district-001",
            username="dist.admin",
            hashed_password=pwd_context.hash("demo123"),
            full_name="District Welfare Officer",
            role=UserRole.DISTRICT_ADMIN,
            district="Maharashtra",
        ),
    ]
    db.add_all(demo_users)

import re
from datetime import datetime, timedelta

from fastapi import Request, HTTPException
from sqlalchemy.orm import Session

from app.models import Learner, LoginAttempt
from app.config import RATE_LIMIT_PER_MINUTE
from app.import_data import clean_phone, clean_email


def normalize_login_input(raw: str) -> tuple:
    raw = raw.strip()
    if "@" in raw:
        return "email", clean_email(raw)
    digits = re.sub(r"[^\d]", "", raw)
    if digits.startswith("976") and len(digits) == 11:
        digits = digits[3:]
    if len(digits) >= 8:
        return "phone", digits[:8]
    return "email", clean_email(raw)


def check_rate_limit(db: Session, ip: str) -> bool:
    cutoff = datetime.utcnow() - timedelta(minutes=1)
    count = db.query(LoginAttempt).filter(
        LoginAttempt.ip == ip,
        LoginAttempt.attempted_at > cutoff,
    ).count()
    return count < RATE_LIMIT_PER_MINUTE


def record_login_attempt(db: Session, ip: str, success: bool):
    attempt = LoginAttempt(ip=ip, success=success)
    db.add(attempt)
    db.commit()


def find_learner(db: Session, login_input: str, track: str | None = None) -> Learner | None:
    field_type, value = normalize_login_input(login_input)
    if not value:
        return None
    q = db.query(Learner)
    if track:
        from app.models import TrackEnum
        try:
            q = q.filter(Learner.track == TrackEnum(track))
        except ValueError:
            pass
    if field_type == "phone":
        return q.filter(Learner.phone == value).first()
    else:
        return q.filter(Learner.email == value).first()


def get_current_learner(request: Request, db: Session) -> Learner | None:
    learner_id = request.session.get("learner_id")
    if not learner_id:
        return None
    return db.query(Learner).filter(Learner.id == learner_id).first()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

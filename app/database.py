from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import DATABASE_URL

_is_sqlite = "sqlite" in DATABASE_URL

connect_args = {"check_same_thread": False} if _is_sqlite else {}
pool_args = {} if _is_sqlite else {"pool_size": 5, "max_overflow": 10, "pool_pre_ping": True}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    **pool_args,
)


if _is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import (  # noqa: F401
        Learner, Team, LeaderVote, Task, PresentationSlot,
        WeeklyUpdate, Announcement, AuditLog, LoginAttempt,
    )
    Base.metadata.create_all(bind=engine)
    _migrate_add_columns()


def _migrate_add_columns():
    new_columns = [
        ("teams", "project_before_state", "TEXT"),
        ("teams", "project_ai_tools", "VARCHAR(500)"),
        ("teams", "project_ai_level", "INTEGER"),
        ("teams", "project_measurement_plan", "TEXT"),
        ("teams", "project_target_audience", "TEXT"),
        ("teams", "result_summary", "TEXT"),
        ("teams", "result_time_saved", "VARCHAR(500)"),
        ("teams", "result_output_change", "VARCHAR(500)"),
        ("teams", "result_quality_change", "VARCHAR(500)"),
        ("teams", "result_cost_change", "VARCHAR(500)"),
        ("teams", "result_outcome_change", "VARCHAR(500)"),
        ("teams", "result_key_insight", "TEXT"),
        ("teams", "presentation_slide_link", "VARCHAR(500)"),
        ("teams", "presentation_demo_video_link", "VARCHAR(500)"),
    ]
    with engine.connect() as conn:
        for table, col, col_type in new_columns:
            try:
                if _is_sqlite:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"
                    ))
                else:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
                    ))
                conn.commit()
            except Exception:
                conn.rollback()

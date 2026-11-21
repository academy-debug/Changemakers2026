import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    Enum, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class TrackEnum(str, enum.Enum):
    professionals = "professionals"
    students = "students"


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    number = Column(Integer, nullable=False)
    track = Column(Enum(TrackEnum), nullable=False)
    topic = Column(String(500), default="")
    shared_goal = Column(Text, default="")

    leader_id = Column(Integer, ForeignKey("learners.id"), nullable=True)

    project_name = Column(String(300), nullable=True)
    project_description = Column(Text, nullable=True)
    project_ai_solution = Column(Text, nullable=True)
    project_before_state = Column(Text, nullable=True)
    project_ai_tools = Column(String(500), nullable=True)
    project_ai_level = Column(Integer, nullable=True)
    project_measurement_plan = Column(Text, nullable=True)
    project_target_audience = Column(Text, nullable=True)
    problem_statement = Column(Text, nullable=True)
    problem_who = Column(Text, nullable=True)
    problem_why = Column(Text, nullable=True)

    result_summary = Column(Text, nullable=True)
    result_time_saved = Column(String(500), nullable=True)
    result_output_change = Column(String(500), nullable=True)
    result_quality_change = Column(String(500), nullable=True)
    result_cost_change = Column(String(500), nullable=True)
    result_outcome_change = Column(String(500), nullable=True)
    result_key_insight = Column(Text, nullable=True)

    presentation_slide_link = Column(String(500), nullable=True)
    presentation_demo_video_link = Column(String(500), nullable=True)

    meeting_link = Column(String(500), nullable=True)
    meeting_datetime = Column(String(200), nullable=True)
    meeting_done = Column(Boolean, default=False)

    slot_id = Column(Integer, ForeignKey("presentation_slots.id"), nullable=True)
    slot_confirmed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = relationship("Learner", back_populates="team", foreign_keys="Learner.team_id")
    leader = relationship("Learner", foreign_keys=[leader_id], post_update=True)
    votes = relationship("LeaderVote", back_populates="team", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="team", cascade="all, delete-orphan")
    weekly_updates = relationship("WeeklyUpdate", back_populates="team", cascade="all, delete-orphan")
    slot = relationship("PresentationSlot", back_populates="bookings")

    __table_args__ = (
        UniqueConstraint("number", "track", name="uq_team_number_track"),
    )

    @property
    def display_name(self):
        return f"{self.number}-р баг"

    @property
    def current_step(self):
        members_logged = any(m.last_login_at for m in self.members)
        if not members_logged:
            return 1
        if not self.meeting_done:
            return 2
        if not self.leader_id:
            return 3
        if not self.problem_statement:
            return 4
        if not self.project_name:
            return 5
        tasks_with_assignee = [t for t in self.tasks if t.assignee_id]
        if len(tasks_with_assignee) < 3:
            return 6
        if not self.slot_id:
            return 7
        if self.slot_confirmed_at:
            return 9
        return 8

    @property
    def task_progress(self):
        if not self.tasks:
            return 0
        done = sum(1 for t in self.tasks if t.status == TaskStatus.done)
        return int(done / len(self.tasks) * 100)

    @property
    def last_activity(self):
        dates = []
        for m in self.members:
            if m.last_login_at:
                dates.append(m.last_login_at)
        for u in self.weekly_updates:
            dates.append(u.created_at)
        if self.updated_at:
            dates.append(self.updated_at)
        return max(dates) if dates else None


class Learner(Base):
    __tablename__ = "learners"

    id = Column(Integer, primary_key=True)
    code = Column(String(100), nullable=False)
    track = Column(Enum(TrackEnum), nullable=False)
    surname = Column(String(200), default="")
    first_name = Column(String(200), default="")
    workplace = Column(String(300), nullable=True)
    position = Column(String(300), nullable=True)
    experience = Column(String(50), nullable=True)
    language_score = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(300), nullable=True)
    origin = Column(String(200), nullable=True)

    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    team_reason = Column(Text, nullable=True)

    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="members", foreign_keys=[team_id])

    __table_args__ = (
        UniqueConstraint("code", "track", name="uq_learner_code_track"),
        Index("ix_learner_phone", "phone"),
        Index("ix_learner_email", "email"),
    )

    @property
    def full_name(self):
        parts = []
        if self.surname:
            parts.append(self.surname)
        if self.first_name:
            parts.append(self.first_name)
        return " ".join(parts) if parts else self.code


class LeaderVote(Base):
    __tablename__ = "leader_votes"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    voter_id = Column(Integer, ForeignKey("learners.id"), nullable=False)
    candidate_id = Column(Integer, ForeignKey("learners.id"), nullable=False)
    voted_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="votes")
    voter = relationship("Learner", foreign_keys=[voter_id])
    candidate = relationship("Learner", foreign_keys=[candidate_id])

    __table_args__ = (
        UniqueConstraint("team_id", "voter_id", name="uq_one_vote_per_member"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    title = Column(String(500), nullable=False)
    assignee_id = Column(Integer, ForeignKey("learners.id"), nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.todo)
    created_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="tasks")
    assignee = relationship("Learner")


class PresentationSlot(Base):
    __tablename__ = "presentation_slots"

    id = Column(Integer, primary_key=True)
    track = Column(Enum(TrackEnum), nullable=False)
    slot_date = Column(Date, nullable=False)
    time_start = Column(String(10), nullable=False)
    time_end = Column(String(10), nullable=False)
    session_name = Column(String(300), default="")
    capacity = Column(Integer, default=5)
    deadline = Column(DateTime, nullable=True)

    bookings = relationship("Team", back_populates="slot")

    @property
    def booked_count(self):
        return len(self.bookings)

    @property
    def is_full(self):
        return self.booked_count >= self.capacity

    @property
    def is_demo_day(self):
        return "demo day" in self.session_name.lower()


class WeeklyUpdate(Base):
    __tablename__ = "weekly_updates"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    content = Column(Text, nullable=False)
    repo_link = Column(String(500), nullable=True)
    demo_link = Column(String(500), nullable=True)
    slide_link = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_id = Column(Integer, ForeignKey("learners.id"), nullable=True)

    team = relationship("Team", back_populates="weekly_updates")
    created_by = relationship("Learner")


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    learner_id = Column(Integer, ForeignKey("learners.id"), nullable=True)
    action = Column(String(200), nullable=False)
    detail = Column(Text, nullable=True)
    ip = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    learner = relationship("Learner")


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True)
    ip = Column(String(50), nullable=False)
    attempted_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_login_attempt_ip_time", "ip", "attempted_at"),
    )

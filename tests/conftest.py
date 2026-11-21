import os
import pytest
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///test_capstone.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_PASSWORD"] = "testadmin"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


engine = create_engine("sqlite:///test_capstone.db", connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    TestSession.close_all()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_data(db):
    from app.models import Team, Learner, PresentationSlot, TrackEnum
    from datetime import date

    team = Team(number=1, track=TrackEnum.professionals, topic="Тест сэдэв", shared_goal="Тест зорилго")
    db.add(team)
    db.flush()

    learner1 = Learner(
        code="YP001", track=TrackEnum.professionals,
        surname="Бат", first_name="Болд",
        phone="99112233", email="bold@test.com",
        workplace="Тест ХХК", position="Инженер",
        team_id=team.id,
    )
    learner2 = Learner(
        code="YP002", track=TrackEnum.professionals,
        surname="Дорж", first_name="Ганаа",
        phone="99445566", email="ganaa@test.com",
        workplace="Тест2 ХХК", position="Менежер",
        team_id=team.id,
    )
    learner3 = Learner(
        code="YP003", track=TrackEnum.professionals,
        surname="Оюун", first_name="Сараа",
        phone="88778899", email="saraa@test.com",
        team_id=team.id,
    )
    db.add_all([learner1, learner2, learner3])
    db.flush()

    other_team = Team(number=2, track=TrackEnum.professionals, topic="Өөр сэдэв")
    db.add(other_team)
    db.flush()
    other_learner = Learner(
        code="YP010", track=TrackEnum.professionals,
        surname="Тэмүүлэн", first_name="Нар",
        phone="77889900", email="nar@test.com",
        team_id=other_team.id,
    )
    db.add(other_learner)

    slot1 = PresentationSlot(
        track=TrackEnum.professionals,
        slot_date=date(2026, 12, 17),
        time_start="19:00", time_end="20:30",
        session_name="Session 19. 5 Баг rehearsal",
        capacity=2,
    )
    slot2 = PresentationSlot(
        track=TrackEnum.professionals,
        slot_date=date(2026, 12, 21),
        time_start="19:00", time_end="20:30",
        session_name="Session 20. 5 Баг rehearsal",
        capacity=5,
    )
    db.add_all([slot1, slot2])
    db.commit()

    return {
        "team": team,
        "learner1": learner1,
        "learner2": learner2,
        "learner3": learner3,
        "other_team": other_team,
        "other_learner": other_learner,
        "slot1": slot1,
        "slot2": slot2,
    }

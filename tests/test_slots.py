import threading


def login_as(client, phone):
    client.post("/login", data={"credential": phone}, follow_redirects=False)


def test_cannot_select_full_slot(client, sample_data, db):
    from app.models import Team
    team = sample_data["team"]
    team.project_name = "Тест"
    team.leader_id = sample_data["learner1"].id
    db.commit()

    other = sample_data["other_team"]
    other.slot_id = sample_data["slot1"].id
    other.project_name = "Other"
    other.leader_id = sample_data["other_learner"].id
    db.commit()

    team2_copy = Team(number=3, track=team.track, topic="3-р баг")
    team2_copy.slot_id = sample_data["slot1"].id
    team2_copy.project_name = "Third"
    db.add(team2_copy)
    db.commit()

    login_as(client, "99112233")
    resp = client.post("/select-slot", data={"slot_id": sample_data["slot1"].id}, follow_redirects=False)
    assert resp.status_code == 409


def test_select_slot_success(client, sample_data, db):
    team = sample_data["team"]
    team.project_name = "Тест"
    team.leader_id = sample_data["learner1"].id
    db.commit()

    login_as(client, "99112233")
    resp = client.post("/select-slot", data={"slot_id": sample_data["slot2"].id}, follow_redirects=False)
    assert resp.status_code == 302


def test_slot_without_project_allowed(client, sample_data, db):
    login_as(client, "99112233")
    resp = client.post("/select-slot", data={"slot_id": sample_data["slot2"].id}, follow_redirects=False)
    assert resp.status_code == 302


def test_leader_vote_majority(client, sample_data, db):
    login_as(client, "99112233")
    client.post("/vote-leader", data={"candidate_id": sample_data["learner1"].id}, follow_redirects=False)

    login_as(client, "99445566")
    client.post("/vote-leader", data={"candidate_id": sample_data["learner1"].id}, follow_redirects=False)

    db.expire_all()
    from app.models import Team
    team = db.query(Team).filter_by(number=1).first()
    assert team.leader_id == sample_data["learner1"].id

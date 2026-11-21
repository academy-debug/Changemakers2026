def login_as(client, phone):
    resp = client.post("/login", data={"credential": phone}, follow_redirects=False)
    return resp


def test_cannot_see_other_team_contact(client, sample_data):
    login_as(client, "99112233")
    resp = client.get("/my-team")
    assert "77889900" not in resp.text
    assert "nar@test.com" not in resp.text


def test_can_see_own_team_contact(client, sample_data):
    login_as(client, "99112233")
    resp = client.get("/my-team")
    assert "99445566" in resp.text or "ganaa@test.com" in resp.text


def test_no_essay_in_response(client, sample_data):
    login_as(client, "99112233")
    resp = client.get("/my-team")
    text = resp.text.lower()
    assert "асуулт 2" not in text
    assert "асуулт 3" not in text
    assert "асуулт 5" not in text
    assert "мотиваци" not in text


def test_project_registration_leader_only(client, sample_data, db):
    from app.models import Team
    team = db.query(Team).filter_by(number=1).first()
    team.leader_id = sample_data["learner1"].id
    db.commit()

    login_as(client, "99445566")
    resp = client.post("/project", data={
        "project_name": "Тест төсөл",
        "project_description": "Тайлбар",
        "project_ai_solution": "AI шийдэл",
    }, follow_redirects=False)
    assert resp.status_code == 403

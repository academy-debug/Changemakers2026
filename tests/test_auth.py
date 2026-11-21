def test_login_with_phone(client, sample_data):
    resp = client.post("/login", data={"credential": "99112233"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/my-team" in resp.headers["location"]


def test_login_with_phone_formatted(client, sample_data):
    resp = client.post("/login", data={"credential": "9911 2233"}, follow_redirects=False)
    assert resp.status_code == 302


def test_login_with_phone_plus976(client, sample_data):
    resp = client.post("/login", data={"credential": "+97699112233"}, follow_redirects=False)
    assert resp.status_code == 302


def test_login_with_email(client, sample_data):
    resp = client.post("/login", data={"credential": "bold@test.com"}, follow_redirects=False)
    assert resp.status_code == 302


def test_login_with_email_uppercase(client, sample_data):
    resp = client.post("/login", data={"credential": "BOLD@TEST.COM"}, follow_redirects=False)
    assert resp.status_code == 302


def test_login_invalid(client, sample_data):
    resp = client.post("/login", data={"credential": "00000000"}, follow_redirects=False)
    assert resp.status_code == 404


def test_my_team_requires_login(client, sample_data):
    resp = client.get("/my-team", follow_redirects=False)
    assert resp.status_code == 302


def test_admin_login(client):
    resp = client.post("/admin/login", data={"password": "testadmin"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin" in resp.headers["location"]


def test_admin_login_wrong(client):
    resp = client.post("/admin/login", data={"password": "wrong"})
    assert "буруу" in resp.text.lower()

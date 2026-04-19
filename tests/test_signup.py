def test_signup_page_loads(client):
    resp = client.get("/signup")
    assert resp.status_code == 200
    assert b"Store Name" in resp.data or b"store_name" in resp.data

def test_signup_redirects_to_dashboard(client):
    resp = client.post("/signup", data={
        "store_name": "New Test Store",
        "email": "newowner@example.com",
        "password": "securepass1!",
        "phone": "555-1234"
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]

def test_signup_creates_store_in_db(client):
    client.post("/signup", data={
        "store_name": "DB Check Store",
        "email": "dbcheck@example.com",
        "password": "securepass1!",
        "phone": ""
    })
    with client.application.app_context():
        from app import Store, User
        s = Store.query.filter_by(email="dbcheck@example.com").first()
        assert s is not None
        assert s.plan == "trial"
        assert s.trial_ends_at is not None
        assert s.grace_ends_at is not None
        u = User.query.filter_by(username="dbcheck@example.com").first()
        assert u is not None
        assert u.role == "admin"
        assert u.store_id == s.id

def test_signup_rejects_duplicate_email(client):
    data = {"store_name": "First", "email": "dup@example.com",
            "password": "securepass1!", "phone": ""}
    client.post("/signup", data=data)
    resp = client.post("/signup", data={**data, "store_name": "Second"})
    assert resp.status_code == 200
    assert b"already exists" in resp.data.lower()

def test_signup_rejects_short_password(client):
    resp = client.post("/signup", data={
        "store_name": "Short Pass", "email": "short@example.com",
        "password": "abc", "phone": ""
    })
    assert resp.status_code == 200
    assert b"8" in resp.data

def test_signup_rejects_missing_store_name(client):
    resp = client.post("/signup", data={
        "store_name": "", "email": "noname@example.com",
        "password": "securepass1!", "phone": ""
    })
    assert resp.status_code == 200
    assert b"required" in resp.data.lower() or b"store name" in resp.data.lower()

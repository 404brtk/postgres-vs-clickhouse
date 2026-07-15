from src import config


def test_api_key_required(client):
    res = client.get("/api/analytics/properties")
    assert res.status_code == 401

    res = client.get(
        "/api/analytics/properties",
        headers={"Authorization": "Bearer invalid-key"},
    )
    assert res.status_code == 401


def test_api_key_authorized(client):
    res = client.get(
        "/api/analytics/properties",
        headers={"Authorization": f"Bearer {config.ANALYTICS_API_KEY}"},
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_auth_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "AUTH_DISABLED", True)

    res = client.get("/api/analytics/properties")
    assert res.status_code == 200


def test_ingest_is_public(client):
    payload = {"event_type": "pageview", "pathname": "/home"}
    res = client.post("/api/analytics/ingest", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

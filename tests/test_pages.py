def test_dashboard_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Analytics Console" in res.text


def test_tracker_demo_page(client):
    res = client.get("/demo")
    assert res.status_code == 200
    assert "Event Tracker" in res.text

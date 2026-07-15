import pytest
from src import config

pytestmark = pytest.mark.usefixtures("clear_events_table")

HEADERS = {"Authorization": f"Bearer {config.ANALYTICS_API_KEY}"}


def test_ingest_anonymous(client):
    payload = {
        "event_type": "pageview",
        "device": "desktop",
        "pathname": "/home",
        "referrer": "google.com",
        "duration_sec": 15,
        "custom_metric": "value1",
    }
    res = client.post("/api/analytics/ingest", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["count"] == 1


def test_ingest_batch(client):
    payload = [
        {"event_type": "pageview", "pathname": "/home"},
        {"event_type": "click", "pathname": "/home"},
        {"event_type": "share", "pathname": "/about"},
    ]
    res = client.post("/api/analytics/ingest", json=payload)
    assert res.status_code == 200
    assert res.json()["count"] == 3


def test_analytics_overview(client):
    events = [
        {
            "event_type": "pageview",
            "device": "desktop",
            "pathname": "/home",
            "duration_sec": 10,
            "user_id": 1,
        },
        {
            "event_type": "pageview",
            "device": "mobile",
            "pathname": "/home",
            "duration_sec": 20,
            "user_id": 1,
        },
        {
            "event_type": "click",
            "device": "mobile",
            "pathname": "/home",
            "duration_sec": 0,
            "user_id": 1,
        },
        {
            "event_type": "pageview",
            "device": "tablet",
            "pathname": "/about",
            "duration_sec": 30,
            "user_id": 2,
        },
    ]
    client.post("/api/analytics/ingest", json=events)

    res = client.get("/api/analytics/overview", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()

    summary = data["summary"]
    assert summary["total_views"] == 3
    assert summary["total_events"] == 4
    assert summary["avg_duration"] == 20.0
    assert summary["unique_visitors"] == 2

    devices = {d["device"]: d["views"] for d in data["devices"]}
    assert devices.get("desktop") == 1
    assert devices.get("mobile") == 2
    assert devices.get("tablet") == 1


def test_custom_query_aggregations(client):
    events = [
        {"event_type": "click", "device": "desktop", "price": "100.50"},
        {"event_type": "click", "device": "mobile", "price": "200.00"},
        {"event_type": "click", "device": "desktop", "price": "50.50"},
    ]
    client.post("/api/analytics/ingest", json=events)

    query = {
        "metrics": [
            {"type": "count", "alias": "clicks"},
            {"type": "sum", "field": "properties.price", "alias": "total_sales"},
            {"type": "avg", "field": "properties.price", "alias": "average_sale"},
        ],
        "group_by": ["device"],
    }
    res = client.post("/api/analytics/query", json=query, headers=HEADERS)
    assert res.status_code == 200
    rows = res.json()

    desktop_row = next(r for r in rows if r["device"] == "desktop")
    mobile_row = next(r for r in rows if r["device"] == "mobile")

    assert desktop_row["clicks"] == 2
    assert desktop_row["total_sales"] == 151.0
    assert desktop_row["average_sale"] == 75.5
    assert mobile_row["clicks"] == 1
    assert mobile_row["total_sales"] == 200.0


def test_custom_query_filters(client):
    events = [
        {"event_type": "click", "device": "desktop", "user_group": "admin"},
        {"event_type": "click", "device": "mobile", "user_group": "member"},
        {"event_type": "click", "device": "tablet", "user_group": "member"},
    ]
    client.post("/api/analytics/ingest", json=events)

    query = {
        "metrics": [{"type": "count", "alias": "count"}],
        "filters": [
            {"field": "properties.user_group", "operator": "eq", "value": "member"}
        ],
    }
    res = client.post("/api/analytics/query", json=query, headers=HEADERS)
    assert res.status_code == 200
    rows = res.json()
    assert rows[0]["count"] == 2


def test_properties_listing(client):
    events = [
        {"event_type": "click", "custom_prop_a": "1", "custom_prop_b": "2"},
    ]
    client.post("/api/analytics/ingest", json=events)

    res = client.get("/api/analytics/properties", headers=HEADERS)
    assert res.status_code == 200
    props = res.json()
    assert "custom_prop_a" in props
    assert "custom_prop_b" in props


def test_clear_analytics_data(client):
    events = [
        {"event_type": "pageview", "pathname": "/home"},
    ]
    client.post("/api/analytics/ingest", json=events)

    res = client.post("/api/analytics/clear", headers=HEADERS)
    assert res.status_code == 200

    overview = client.get("/api/analytics/overview", headers=HEADERS).json()
    assert overview["summary"]["total_events"] == 0


def test_custom_query_more_metrics_and_limit(client):
    events = [
        {"event_type": "click", "device": "desktop", "score": "10", "user_id": 101},
        {"event_type": "click", "device": "desktop", "score": "50", "user_id": 102},
        {"event_type": "click", "device": "mobile", "score": "30", "user_id": 101},
    ]
    client.post("/api/analytics/ingest", json=events)

    query = {
        "metrics": [
            {"type": "uniq", "field": "user_id", "alias": "unique_users"},
            {"type": "min", "field": "properties.score", "alias": "min_score"},
            {"type": "max", "field": "properties.score", "alias": "max_score"},
        ],
        "group_by": ["device"],
        "limit": 1,
    }
    res = client.post("/api/analytics/query", json=query, headers=HEADERS)
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    row = rows[0]
    assert "unique_users" in row
    assert "min_score" in row
    assert "max_score" in row
    if row["device"] == "desktop":
        assert row["unique_users"] == 2
        assert row["min_score"] == 10.0
        assert row["max_score"] == 50.0


def test_custom_query_operators(client):
    events = [
        {
            "event_type": "click",
            "pathname": "/home",
            "status": "active",
            "score": "100",
        },
        {
            "event_type": "click",
            "pathname": "/about",
            "status": "pending",
            "score": "200",
        },
        {
            "event_type": "click",
            "pathname": "/contact",
            "status": "closed",
            "score": "300",
        },
    ]
    client.post("/api/analytics/ingest", json=events)

    query = {
        "metrics": [{"type": "count", "alias": "count"}],
        "filters": [
            {"field": "properties.status", "operator": "neq", "value": "closed"},
            {"field": "properties.score", "operator": "gt", "value": "150"},
        ],
    }
    res = client.post("/api/analytics/query", json=query, headers=HEADERS)
    assert res.status_code == 200
    assert res.json()[0]["count"] == 1

    query2 = {
        "metrics": [{"type": "count", "alias": "count"}],
        "filters": [
            {"field": "pathname", "operator": "like", "value": "/%o%"},
            {
                "field": "properties.status",
                "operator": "in",
                "value": ["active", "pending"],
            },
        ],
    }
    res2 = client.post("/api/analytics/query", json=query2, headers=HEADERS)
    assert res2.status_code == 200
    assert res2.json()[0]["count"] == 2


def test_custom_query_date_filtering(client):
    events = [
        {"event_type": "pageview", "pathname": "/home"},
    ]
    client.post("/api/analytics/ingest", json=events)

    res = client.get(
        "/api/analytics/overview?start_date=2020-01-01&end_date=2030-01-01",
        headers=HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["summary"]["total_events"] == 1

    res_empty = client.get(
        "/api/analytics/overview?start_date=2020-01-01&end_date=2020-01-02",
        headers=HEADERS,
    )
    assert res_empty.status_code == 200
    assert res_empty.json()["summary"]["total_events"] == 0

    query = {
        "metrics": [{"type": "count", "alias": "count"}],
        "start_date": "2020-01-01",
        "end_date": "2030-01-01",
    }
    res_query = client.post("/api/analytics/query", json=query, headers=HEADERS)
    assert res_query.json()[0]["count"] == 1


def test_custom_query_error_handling(client):
    query_no_metrics = {
        "metrics": [],
    }
    res = client.post("/api/analytics/query", json=query_no_metrics, headers=HEADERS)
    assert res.status_code in (400, 422)

    query_missing_field = {
        "metrics": [{"type": "sum", "alias": "total"}],
    }
    res2 = client.post(
        "/api/analytics/query", json=query_missing_field, headers=HEADERS
    )
    assert res2.status_code in (400, 422)


def test_analytics_history_basic(client):
    events = [
        {"event_type": "pageview", "pathname": "/home", "duration_sec": 10},
        {"event_type": "click", "pathname": "/home", "duration_sec": 0},
    ]
    client.post("/api/analytics/ingest", json=events)

    res = client.get("/api/analytics/history", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    row = data[0]
    assert "day" in row
    assert "views" in row
    assert "visitors" in row
    assert "events" in row
    assert "duration" in row


def test_analytics_history_intervals_and_filters(client):
    events = [
        {"event_type": "pageview", "pathname": "/home", "duration_sec": 10},
        {"event_type": "click", "pathname": "/home", "duration_sec": 0},
    ]
    client.post("/api/analytics/ingest", json=events)

    res_hour = client.get("/api/analytics/history?interval=hour", headers=HEADERS)
    assert res_hour.status_code == 200
    data_hour = res_hour.json()
    assert len(data_hour) >= 1
    assert "T" in data_hour[0]["day"]
    assert data_hour[0]["events"] == 2

    res_min = client.get("/api/analytics/history?interval=minute", headers=HEADERS)
    assert res_min.status_code == 200
    data_min = res_min.json()
    assert len(data_min) >= 1
    assert "T" in data_min[0]["day"]

    res_filter = client.get(
        "/api/analytics/history?event_type=pageview", headers=HEADERS
    )
    assert res_filter.status_code == 200
    data_filter = res_filter.json()
    assert len(data_filter) >= 1
    assert data_filter[0]["views"] == 1
    assert data_filter[0]["events"] == 1


def test_analytics_history_auth_enforced(client):
    res = client.get("/api/analytics/history")
    assert res.status_code == 401

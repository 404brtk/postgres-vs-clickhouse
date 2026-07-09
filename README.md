# Generic Analytics Microservice (Postgres vs ClickHouse)

A lightweight, schema-less event tracking and analytics microservice that records telemetry in parallel to **PostgreSQL** and **ClickHouse** and exposes a dynamic SQL query compiler.

---

## How to Run

1. Start the databases:
    ```bash
    docker-compose up -d
    ```
2. Install dependencies:
    ```bash
    uv sync
    ```
3. Run the server:
    ```bash
    uv run uvicorn main:app --reload
    ```

Open **`http://127.0.0.1:8000/`** to access the Analytics Console dashboard.

---

## Live Tracker Demo

The repository includes a lightweight, no-code JavaScript tracker (`tracker.js`) and an interactive console (`tracker_demo.html`). To view the live tracking logs, navigate to **`http://127.0.0.1:8000/demo`** in your browser.

---

## Benchmark Results

### 1. Analytical Queries (OLAP)

For heavy read queries that scan millions of rows and aggregate data, ClickHouse runs significantly faster.

| Query / Operation                                                      | PostgreSQL (ms) | ClickHouse (ms) |         Speedup          |
| :--------------------------------------------------------------------- | :-------------: | :-------------: | :----------------------: |
| **Count all records** <br> `SELECT COUNT(*) FROM user_events;`         |    194.36 ms    |     0.95 ms     | **204.82x** (ClickHouse) |
| **Mobile revenue/commissions** <br> `SELECT SUM(commission), AVG...`   |    571.82 ms    |    65.13 ms     |  **8.78x** (ClickHouse)  |
| **Total commission & count grouped** <br> `SELECT device, category...` |    945.49 ms    |    117.41 ms    |  **8.05x** (ClickHouse)  |
| **Hourly breakdown of count/commission** <br> `SELECT extract(hour...` |   6740.33 ms    |    41.65 ms     | **161.83x** (ClickHouse) |
| **Top 10 users by total commission** <br> `SELECT user_id, SUM...`     |   2705.58 ms    |    120.15 ms    | **22.52x** (ClickHouse)  |
| **Distinct users on tablet in April** <br> `SELECT COUNT(DISTINCT...`  |    370.57 ms    |    25.86 ms     | **14.33x** (ClickHouse)  |

### 2. Single Row Operations (OLTP)

For operations on single rows, updates, and deletes, PostgreSQL excels due to its B-tree indexing.

_(Note: ClickHouse updates/deletes in this test are run with `mutations_sync = 1` to wait for the operation to complete synchronously)._

| Operation / Button                                                | PostgreSQL (ms) | ClickHouse (ms) |        Speedup         |
| :---------------------------------------------------------------- | :-------------: | :-------------: | :--------------------: |
| **Insert Event** <br> `INSERT INTO user_events ...`               |    11.71 ms     |    11.96 ms     | **1.02x** (PostgreSQL) |
| **Fetch Event** <br> `SELECT * FROM ... WHERE event_id = X;`      |     8.24 ms     |    10.81 ms     | **1.31x** (PostgreSQL) |
| **Update Event** <br> `UPDATE ... SET duration_sec = Y WHERE ...` |     7.21 ms     |    15.24 ms     | **2.11x** (PostgreSQL) |
| **Delete Event** <br> `DELETE FROM ... WHERE event_id = X;`       |     6.37 ms     |    13.71 ms     | **2.15x** (PostgreSQL) |

### 3. Batch Ingestion Operations

For bulk data loading, ClickHouse's column-oriented design scales significantly better than PostgreSQL.

| Batch Size                          | PostgreSQL (ms) | ClickHouse (ms) |        Speedup         |
| :---------------------------------- | :-------------: | :-------------: | :--------------------: |
| **Insert Batch (10,000 events)**    |    36.44 ms     |    72.18 ms     | **2.00x** (PostgreSQL) |
| **Insert Batch (50,000 events)**    |    169.89 ms    |    66.19 ms     | **2.57x** (ClickHouse) |
| **Insert Batch (100,000 events)**   |    294.65 ms    |    96.24 ms     | **3.06x** (ClickHouse) |
| **Insert Batch (1,000,000 events)** |   2851.14 ms    |    838.35 ms    | **3.40x** (ClickHouse) |

---

## Querying Dynamic Aggregations (cURL Examples)

You can query dynamic metrics, filters, and groupings directly from external business applications via `POST /api/analytics/query` or `POST /api/analytics/compare`.

### Example 1: Basic Pageviews & Unique Visitors

Count all `pageview` events grouped by URL pathname:

```bash
curl -X POST http://127.0.0.1:8000/api/analytics/query \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      { "type": "count", "field": "event_id", "alias": "total_views" },
      { "type": "uniq", "field": "user_id", "alias": "unique_visitors" }
    ],
    "group_by": ["pathname"],
    "filters": [
      { "field": "event_type", "operator": "eq", "value": "pageview" }
    ]
  }'
```

### Example 2: Aggregate Dynamic Properties

Aggregate custom properties (such as `scroll_depth` or `commission`) stored inside the database map columns:

```bash
curl -X POST http://127.0.0.1:8000/api/analytics/query \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      { "type": "avg", "field": "properties.scroll_depth", "alias": "avg_scroll_pct" },
      { "type": "sum", "field": "properties.commission", "alias": "total_commissions" }
    ],
    "group_by": ["device"],
    "filters": []
  }'
```

### Example 3: Compare Database Speed

Measure execution times between Postgres and ClickHouse for custom analytics queries:

```bash
curl -X POST http://127.0.0.1:8000/api/analytics/compare \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      { "type": "avg", "field": "duration_sec", "alias": "avg_session_duration" }
    ],
    "group_by": ["pathname"],
    "filters": [
      { "field": "event_type", "operator": "eq", "value": "exit" }
    ]
  }'
```

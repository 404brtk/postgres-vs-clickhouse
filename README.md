# Postgres 18 vs ClickHouse Benchmark Results

This repository contains benchmark results comparing **PostgreSQL 18** and **ClickHouse** on a generated dataset of user events.

---

## How to Run

```bash
docker-compose up -d
uv sync
uv run python generate-data.py
uv run uvicorn api:app --reload
```

Open **`http://127.0.0.1:8000/`** in your browser to view the web dashboard.

Alternatively, you can run the entire benchmark suite from the command line and save the results to a file:
```bash
uv run python run_benchmark_cli.py
```

---

## Benchmark Results

### 1. Analytical Queries (OLAP)
For heavy read queries that scan millions of rows and aggregate data, ClickHouse runs significantly faster.

| Query / Operation | PostgreSQL (ms) | ClickHouse (ms) | Speedup |
| :--- | :---: | :---: | :---: |
| **Count all records** <br> `SELECT COUNT(*) FROM user_events;` | 194.36 ms | 0.95 ms | **204.82x** (ClickHouse) |
| **Mobile revenue/commissions** <br> `SELECT SUM(commission), AVG...` | 571.82 ms | 65.13 ms | **8.78x** (ClickHouse) |
| **Total commission & count grouped** <br> `SELECT device, category...` | 945.49 ms | 117.41 ms | **8.05x** (ClickHouse) |
| **Hourly breakdown of count/commission** <br> `SELECT extract(hour...` | 6740.33 ms | 41.65 ms | **161.83x** (ClickHouse) |
| **Top 10 users by total commission** <br> `SELECT user_id, SUM...` | 2705.58 ms | 120.15 ms | **22.52x** (ClickHouse) |
| **Distinct users on tablet in April** <br> `SELECT COUNT(DISTINCT...` | 370.57 ms | 25.86 ms | **14.33x** (ClickHouse) |

### 2. Single Row Operations (OLTP)
For operations on single rows, updates, and deletes, PostgreSQL excels due to its B-tree indexing.

*(Note: ClickHouse updates/deletes in this test are run with `mutations_sync = 1` to wait for the operation to complete synchronously).*

| Operation / Button | PostgreSQL (ms) | ClickHouse (ms) | Speedup |
| :--- | :---: | :---: | :---: |
| **Insert Event** <br> `INSERT INTO user_events ...` | 11.71 ms | 11.96 ms | **1.02x** (PostgreSQL) |
| **Fetch Event** <br> `SELECT * FROM ... WHERE event_id = X;` | 8.24 ms | 10.81 ms | **1.31x** (PostgreSQL) |
| **Update Event** <br> `UPDATE ... SET duration_sec = Y WHERE ...` | 7.21 ms | 15.24 ms | **2.11x** (PostgreSQL) |
| **Delete Event** <br> `DELETE FROM ... WHERE event_id = X;` | 6.37 ms | 13.71 ms | **2.15x** (PostgreSQL) |

### 3. Batch Ingestion Operations
For bulk data loading, ClickHouse's column-oriented design scales significantly better than PostgreSQL.

| Batch Size | PostgreSQL (ms) | ClickHouse (ms) | Speedup |
| :--- | :---: | :---: | :---: |
| **Insert Batch (10,000 events)** | 36.44 ms | 72.18 ms | **2.00x** (PostgreSQL) |
| **Insert Batch (50,000 events)** | 169.89 ms | 66.19 ms | **2.57x** (ClickHouse) |
| **Insert Batch (100,000 events)** | 294.65 ms | 96.24 ms | **3.06x** (ClickHouse) |
| **Insert Batch (1,000,000 events)** | 2851.14 ms | 838.35 ms | **3.40x** (ClickHouse) |

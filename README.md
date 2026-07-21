# Analytics Microservice

A lightweight, schema-less event tracking and analytics microservice that records telemetry to **ClickHouse** and exposes a dynamic SQL query compiler.

---

## How to Run

1. Start the database:
    ```bash
    docker-compose up -d
    ```
2. Install dependencies:
    ```bash
    uv sync
    ```
3. Run the server:
    ```bash
    uv run uvicorn src.main:app --reload
    ```

Open **`http://127.0.0.1:8000/`** to access the Analytics Console dashboard.

---

## Client Integration (tracker.js)

The project includes a drop-in JavaScript tracker (`static/tracker.js`) to record browser telemetry.

### 1. Embed the Script

Include the script at the bottom of your HTML pages. Using the `defer` attribute ensures the script does not block HTML parsing. By default, it sends events to the same host at `/api/analytics/ingest` (you only need to provide `data-endpoint` if hosting the API on a separate domain):

```html
<!-- Same-domain tracking (default) -->
<script src="http://127.0.0.1:8000/static/tracker.js" defer></script>

<!-- Cross-domain tracking (optional) -->
<script
    src="http://127.0.0.1:8000/static/tracker.js"
    data-endpoint="https://analytics.example.com/api/analytics/ingest"
    defer
></script>
```

### 2. Auto-Track Clicks & Attributes

Adding a `data-event` attribute to any interactive element will automatically track click events. Any additional `data-*` attributes will be dynamically included as custom properties (converted to snake_case):

```html
<button
    data-event="btn_click"
    data-target-id="premium_signup"
    data-price="49.99"
>
    Sign Up
</button>
```

_Clicking this button automatically triggers an ingestion payload with `event_type: "btn_click"` and custom properties `{"target_id": "premium_signup", "price": "49.99"}`._

### 3. Interactive Demo Page

An interactive event simulator and log console is served directly at **`http://127.0.0.1:8000/demo`** to test integrations and verify page tracking.

---

## API Examples (cURL)

### 1. Ingest Events

Send telemetry data from external websites or server-side applications. Ingestion is **public** and does not require credentials.

```bash
curl -X POST http://127.0.0.1:8000/api/analytics/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "purchase",
    "device": "mobile",
    "pathname": "/checkout/success",
    "referrer": "google.com",
    "duration_sec": 45,
    "product_id": "99",
    "price": "49.99"
  }'
```

### 2. Query Aggregations (Secure)

Query custom metrics, groupings, and filters. This endpoint requires passing the authorization API key.

```bash
curl -X POST http://127.0.0.1:8000/api/analytics/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer demo-api-key" \
  -d '{
    "metrics": [
      { "type": "count", "field": "event_id", "alias": "total_sales" },
      { "type": "sum", "field": "properties.price", "alias": "total_revenue" }
    ],
    "group_by": ["pathname"],
    "filters": [
      { "field": "event_type", "operator": "eq", "value": "purchase" }
    ]
  }'
```

---

## Database Backups & Disaster Recovery (Cloudflare R2)

Database backups are managed using the official `altinity/clickhouse-backup` Docker service with `zstd` level 3 compression and direct streaming to Cloudflare R2.

### 1. Configuration Setup

Copy `.env.example` to `.env` and fill in your Cloudflare R2 credentials:

```env
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_BUCKET_NAME=your_r2_bucket_name
R2_ACCESS_KEY_ID=your_r2_access_key_id
R2_SECRET_ACCESS_KEY=your_r2_secret_access_key
```

---

### 2. Manual Backup Management

#### Monthly Full Baseline Backup (1st of every month)

```bash
docker compose exec clickhouse-backup clickhouse-backup create_remote --delete full_$(date +%Y_%m)
```

#### Daily Incremental Backup (Every night)

```bash
docker compose exec clickhouse-backup clickhouse-backup create_remote --diff-from-remote=full_$(date +%Y_%m) --delete inc_$(date +%Y_%m_%d)
```

#### List Remote Backups stored in Cloudflare R2

```bash
docker compose exec clickhouse-backup clickhouse-backup list remote
```

#### Delete a Remote Backup

```bash
docker compose exec clickhouse-backup clickhouse-backup delete remote <backup_name>
```

---

### 3. Disaster Recovery (Restoring Data)

To restore a backup from Cloudflare R2 into ClickHouse:

```bash
docker compose exec clickhouse-backup clickhouse-backup restore_remote --rm --restore-database-mapping default:default <backup_name>
```

> **Note**: Pass `--restore-database-mapping default:default` when restoring to generate fresh Atomic table UUIDs, preventing directory collisions with ClickHouse's background drop queue. Pass `--rm` to automatically drop pre-existing schema tables before restoring.

---

### 4. Automated Hands-Free Scheduler (`watch` Mode)

To enable automatic background backups, set `command: [- watch]` for `clickhouse-backup` in `docker-compose.yml` and set `WATCH_SCHEDULES` in `.env`:

```env
WATCH_SCHEDULES="name=monthly,full=0 0 1 * *,increment=0 2 * * *"
```

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

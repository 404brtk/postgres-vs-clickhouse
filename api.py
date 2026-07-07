import time
import subprocess
import os
from datetime import datetime, timedelta
from typing import Union
from pydantic import BaseModel
import io
import random
from fastapi import FastAPI, HTTPException, Query, Response, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg
import clickhouse_connect

app = FastAPI(title="Database Benchmark API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSV_FILE = "user_events.csv"
PG_DSN = "host=localhost dbname=benchmark_db user=postgres password=postgres_password"
CH_HOST = "localhost"
CH_PORT = 8123
CH_USER = "default"
CH_PASSWORD = "clickhouse_password"
CH_DB = "default"

QUERIES = [
    {
        "id": "q1",
        "name": "Count all records",
        "sql": "SELECT COUNT(*) FROM user_events;"
    },
    {
        "id": "q2",
        "name": "Mobile revenue/commissions",
        "sql": "SELECT SUM(commission), AVG(commission) FROM user_events WHERE device = 'mobile' AND event_type IN ('click', 'share');"
    },
    {
        "id": "q3",
        "name": "Total commission & count grouped by device and category",
        "sql": "SELECT device, category_id, SUM(commission), COUNT(*) FROM user_events GROUP BY device, category_id ORDER BY device, category_id;"
    },
    {
        "id": "q4",
        "name": "Hourly breakdown of count and commission",
        "sql": "SELECT extract(hour from event_time) as hr, COUNT(*), SUM(commission) FROM user_events GROUP BY hr ORDER BY hr;"
    },
    {
        "id": "q5",
        "name": "Top 10 users by total commission generated",
        "sql": "SELECT user_id, SUM(commission) as total_comm FROM user_events GROUP BY user_id ORDER BY total_comm DESC LIMIT 10;"
    },
    {
        "id": "q6",
        "name": "Distinct users who liked something on tablet in April",
        "sql": "SELECT COUNT(DISTINCT user_id) FROM user_events WHERE device = 'tablet' AND is_liked = 1 AND event_time >= '2026-04-01 00:00:00' AND event_time < '2026-05-01 00:00:00';"
    }
]


@app.get("/api/queries")
def get_queries():
    return QUERIES

@app.get("/api/status")
def get_status():
    pg_count = 0
    ch_count = 0
    
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'user_events'
                    );
                """)
                exists = cur.fetchone()[0]
                if exists:
                    cur.execute("SELECT COUNT(*) FROM user_events;")
                    pg_count = cur.fetchone()[0]
    except Exception:
        pass

    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        exists = ch_client.command("EXISTS TABLE user_events;")
        if exists:
            ch_count = ch_client.command("SELECT COUNT(*) FROM user_events;")
        ch_client.close()
    except Exception:
        pass

    return {
        "postgres_count": pg_count,
        "clickhouse_count": ch_count,
        "is_ready": pg_count > 0 and ch_count > 0
    }

@app.post("/api/import")
def run_import():
    if not os.path.exists(CSV_FILE):
        raise HTTPException(status_code=400, detail="CSV file not found. Please run generate-data.py first.")
        
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS user_events;")
                cur.execute("""
                    CREATE TABLE user_events (
                        event_id BIGINT,
                        user_id INT,
                        target_id INT,
                        category_id INT,
                        event_type VARCHAR(10),
                        duration_sec INT,
                        is_liked INT,
                        event_time TIMESTAMP,
                        device VARCHAR(10),
                        commission NUMERIC(10, 2)
                    );
                    CREATE INDEX idx_user_events_event_id ON user_events (event_id);
                """)
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset Postgres schema: {str(e)}")

    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.command("DROP TABLE IF EXISTS user_events;")
        ch_client.command("""
            CREATE TABLE user_events (
                event_id Int64,
                user_id Int32,
                target_id Int32,
                category_id Int8,
                event_type LowCardinality(String),
                duration_sec Int32,
                is_liked Int8,
                event_time DateTime,
                device LowCardinality(String),
                commission Decimal(10, 2)
            ) ENGINE = MergeTree()
            ORDER BY (category_id, event_time, user_id);
        """)
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset ClickHouse schema: {str(e)}")

    start_pg = time.perf_counter()
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                with open(CSV_FILE, "r") as f:
                    with cur.copy("COPY user_events (event_id, user_id, target_id, category_id, event_type, duration_sec, is_liked, event_time, device, commission) FROM STDIN WITH (FORMAT CSV, HEADER true)") as copy:
                        while data := f.read(1024 * 1024):
                            copy.write(data)
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres import failed: {str(e)}")
    elapsed_pg = time.perf_counter() - start_pg

    start_ch = time.perf_counter()
    try:
        cmd = [
            "docker", "exec", "-i", "benchmark-clickhouse",
            "clickhouse-client",
            "--password", CH_PASSWORD,
            "--database", CH_DB,
            "-q", "INSERT INTO user_events FORMAT CSVWithNames"
        ]
        with open(CSV_FILE, "rb") as f:
            subprocess.run(cmd, stdin=f, check=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ClickHouse import failed: {str(e)}")
    elapsed_ch = time.perf_counter() - start_ch

    return {
        "status": "success",
        "postgres_import_seconds": round(elapsed_pg, 2),
        "clickhouse_import_seconds": round(elapsed_ch, 2),
        "import_speedup": round(elapsed_pg / elapsed_ch, 2) if elapsed_ch > 0 else 0
    }

class EventPayload(BaseModel):
    user_id: int | None = None
    target_id: int | None = 0
    category_id: int | None = 0
    event_type: str
    duration_sec: int | None = 0
    is_liked: int | None = 0
    device: str | None = "desktop"
    commission: float | None = 0.0

@app.post("/api/events")
def create_events(payload: Union[EventPayload, list[EventPayload]], request: Request):
    import hashlib
    events = [payload] if isinstance(payload, EventPayload) else payload
    
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    session_str = f"{client_ip}-{user_agent}-{today_str}"
    md5_hex = hashlib.md5(session_str.encode('utf-8')).hexdigest()
    session_hash = int(md5_hex[:8], 16) % 100000 + 1
    
    prepared_rows = []
    for ev in events:
        event_id = random.randint(1000000000, 9999999999)
        event_time = datetime.now()
        user_id = ev.user_id if ev.user_id is not None else session_hash
        commission = ev.commission if ev.commission is not None else 0.0
        prepared_rows.append((
            event_id, user_id, ev.target_id or 0, ev.category_id or 0,
            ev.event_type, ev.duration_sec or 0, ev.is_liked or 0, event_time,
            ev.device or "desktop", commission
        ))
        
    start_pg = time.perf_counter()
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO user_events (event_id, user_id, target_id, category_id, event_type, duration_sec, is_liked, event_time, device, commission)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    prepared_rows
                )
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres insert failed: {str(e)}")
    elapsed_pg = (time.perf_counter() - start_pg) * 1000
    
    start_ch = time.perf_counter()
    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.insert(
            "user_events",
            data=prepared_rows,
            column_names=["event_id", "user_id", "target_id", "category_id", "event_type", "duration_sec", "is_liked", "event_time", "device", "commission"]
        )
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clickhouse insert failed: {str(e)}")
    elapsed_ch = (time.perf_counter() - start_ch) * 1000
    
    return {
        "status": "success",
        "count": len(events),
        "timings_ms": {
            "postgres": round(elapsed_pg, 2),
            "clickhouse": round(elapsed_ch, 2),
            "speedup": round(elapsed_pg / elapsed_ch, 2) if elapsed_ch > 0 else 0
        }
    }

@app.post("/api/events/random")
def add_event_random():
    event_id = random.randint(1000000000, 9999999999)
    user_id = random.randint(1, 100000)
    target_id = random.randint(1, 50000)
    category_id = random.randint(1, 20)
    event_type = random.choice(['view', 'click', 'scroll', 'share'])
    duration_sec = random.randint(2, 600)
    is_liked = random.choice([0, 0, 0, 1])
    event_time = datetime.now()
    device = random.choice(['mobile', 'desktop', 'tablet'])
    
    if event_type == 'click':
        commission = round(random.uniform(0.05, 2.50), 2)
    elif event_type == 'share':
        commission = round(random.uniform(0.50, 5.00), 2)
    else:
        commission = 0.00

    start_pg = time.perf_counter()
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_events (event_id, user_id, target_id, category_id, event_type, duration_sec, is_liked, event_time, device, commission)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (event_id, user_id, target_id, category_id, event_type, duration_sec, is_liked, event_time, device, commission)
                )
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres insert failed: {str(e)}")
    elapsed_pg = (time.perf_counter() - start_pg) * 1000

    start_ch = time.perf_counter()
    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.insert(
            "user_events",
            data=[[event_id, user_id, target_id, category_id, event_type, duration_sec, is_liked, event_time, device, commission]],
            column_names=["event_id", "user_id", "target_id", "category_id", "event_type", "duration_sec", "is_liked", "event_time", "device", "commission"]
        )
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clickhouse insert failed: {str(e)}")
    elapsed_ch = (time.perf_counter() - start_ch) * 1000

    return {
        "status": "success",
        "event_id": event_id,
        "timings_ms": {
            "postgres": round(elapsed_pg, 2),
            "clickhouse": round(elapsed_ch, 2),
            "speedup": round(elapsed_ch / elapsed_pg, 2) if elapsed_pg > 0 else 0
        }
    }

@app.get("/api/events/lookup")
def lookup_event(event_id: int = Query(...)):
    start_pg = time.perf_counter()
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM user_events WHERE event_id = %s;", (event_id,))
                row_pg = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres lookup failed: {str(e)}")
    elapsed_pg = (time.perf_counter() - start_pg) * 1000

    start_ch = time.perf_counter()
    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.query("SELECT * FROM user_events WHERE event_id = %(event_id)s", {"event_id": event_id})
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clickhouse lookup failed: {str(e)}")
    elapsed_ch = (time.perf_counter() - start_ch) * 1000

    return {
        "status": "success",
        "found": row_pg is not None,
        "timings_ms": {
            "postgres": round(elapsed_pg, 2),
            "clickhouse": round(elapsed_ch, 2),
            "speedup": round(elapsed_ch / elapsed_pg, 2) if elapsed_pg > 0 else 0
        }
    }

@app.put("/api/events/update")
def update_event(event_id: int = Query(...)):
    new_duration = random.randint(2, 600)
    
    start_pg = time.perf_counter()
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE user_events SET duration_sec = %s WHERE event_id = %s;", (new_duration, event_id))
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres update failed: {str(e)}")
    elapsed_pg = (time.perf_counter() - start_pg) * 1000

    start_ch = time.perf_counter()
    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.command(
            "ALTER TABLE user_events UPDATE duration_sec = %(duration)s WHERE event_id = %(event_id)s",
            {"duration": new_duration, "event_id": event_id},
            settings={"mutations_sync": "1"}
        )
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clickhouse update failed: {str(e)}")
    elapsed_ch = (time.perf_counter() - start_ch) * 1000

    return {
        "status": "success",
        "new_duration": new_duration,
        "timings_ms": {
            "postgres": round(elapsed_pg, 2),
            "clickhouse": round(elapsed_ch, 2),
            "speedup": round(elapsed_ch / elapsed_pg, 2) if elapsed_pg > 0 else 0
        }
    }

@app.delete("/api/events/delete")
def delete_event(event_id: int = Query(...)):
    start_pg = time.perf_counter()
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_events WHERE event_id = %s;", (event_id,))
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres delete failed: {str(e)}")
    elapsed_pg = (time.perf_counter() - start_pg) * 1000

    start_ch = time.perf_counter()
    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.command(
            "ALTER TABLE user_events DELETE WHERE event_id = %(event_id)s",
            {"event_id": event_id},
            settings={"mutations_sync": "1"}
        )
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clickhouse delete failed: {str(e)}")
    elapsed_ch = (time.perf_counter() - start_ch) * 1000

    return {
        "status": "success",
        "timings_ms": {
            "postgres": round(elapsed_pg, 2),
            "clickhouse": round(elapsed_ch, 2),
            "speedup": round(elapsed_ch / elapsed_pg, 2) if elapsed_pg > 0 else 0
        }
    }

@app.post("/api/events/batch")
def add_events_batch(count: int = Query(10000)):
    start_id = random.randint(100000000, 900000000)
    start_date = datetime(2026, 1, 1)
    
    rows = []
    for i in range(count):
        event_time = start_date + timedelta(seconds=random.randint(0, 15552000))
        event_type = random.choice(['view', 'click', 'scroll', 'share'])
        if event_type == 'click':
            commission = round(random.uniform(0.05, 2.50), 2)
        elif event_type == 'share':
            commission = round(random.uniform(0.50, 5.00), 2)
        else:
            commission = 0.00
        device = random.choice(['mobile', 'desktop', 'tablet'])
        
        rows.append((
            start_id + i,
            random.randint(1, 100000),
            random.randint(1, 50000),
            random.randint(1, 20),
            event_type,
            random.randint(2, 600),
            random.choice([0, 0, 0, 1]),
            event_time,
            device,
            commission
        ))
        
    start_pg = time.perf_counter()
    try:
        csv_buffer = io.StringIO()
        for r in rows:
            dt_str = r[7].strftime('%Y-%m-%d %H:%M:%S')
            csv_buffer.write(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]},{dt_str},{r[8]},{r[9]}\n")
        csv_buffer.seek(0)
        
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                with cur.copy("COPY user_events (event_id, user_id, target_id, category_id, event_type, duration_sec, is_liked, event_time, device, commission) FROM STDIN WITH (FORMAT CSV)") as copy:
                    copy.write(csv_buffer.read())
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres batch insert failed: {str(e)}")
    elapsed_pg = (time.perf_counter() - start_pg) * 1000
    
    start_ch = time.perf_counter()
    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.insert(
            "user_events",
            data=rows,
            column_names=["event_id", "user_id", "target_id", "category_id", "event_type", "duration_sec", "is_liked", "event_time", "device", "commission"]
        )
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clickhouse batch insert failed: {str(e)}")
    elapsed_ch = (time.perf_counter() - start_ch) * 1000
    
    return {
        "status": "success",
        "rows_inserted": count,
        "timings_ms": {
            "postgres": round(elapsed_pg, 2),
            "clickhouse": round(elapsed_ch, 2),
            "speedup": round(elapsed_pg / elapsed_ch, 2) if elapsed_ch > 0 else 0
        }
    }

@app.get("/api/commission")
def calculate_commission(
    device: str = Query(None),
    event_type: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    user_id: int = Query(None)
):
    where_parts = []
    params = []
    
    if device:
        where_parts.append("device = %s")
        params.append(device)
    if event_type:
        where_parts.append("event_type = %s")
        params.append(event_type)
    if start_date:
        where_parts.append("event_time >= %s")
        params.append(start_date)
    if end_date:
        where_parts.append("event_time <= %s")
        params.append(end_date)
    if user_id:
        where_parts.append("user_id = %s")
        params.append(user_id)
        
    where_clause = ""
    if where_parts:
        where_clause = "WHERE " + " AND ".join(where_parts)

    sql_pg = f"SELECT SUM(commission), AVG(commission), COUNT(*) FROM user_events {where_clause};"

    start_pg = time.perf_counter()
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_pg, params)
                row_pg = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres execution failed: {str(e)}")
    elapsed_pg = (time.perf_counter() - start_pg) * 1000

    ch_where_parts = []
    ch_params = {}
    
    if device:
        ch_where_parts.append("device = %(device)s")
        ch_params["device"] = device
    if event_type:
        ch_where_parts.append("event_type = %(event_type)s")
        ch_params["event_type"] = event_type
    if start_date:
        ch_where_parts.append("event_time >= %(start_date)s")
        ch_params["start_date"] = start_date
    if end_date:
        ch_where_parts.append("event_time <= %(end_date)s")
        ch_params["end_date"] = end_date
    if user_id:
        ch_where_parts.append("user_id = %(user_id)s")
        ch_params["user_id"] = user_id
        
    ch_where_clause = ""
    if ch_where_parts:
        ch_where_clause = "WHERE " + " AND ".join(ch_where_parts)

    sql_ch = f"SELECT SUM(commission), AVG(commission), COUNT(*) FROM user_events {ch_where_clause};"

    start_ch = time.perf_counter()
    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
        ch_client.query(sql_ch, ch_params)
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ClickHouse execution failed: {str(e)}")
    elapsed_ch = (time.perf_counter() - start_ch) * 1000

    total_comm = float(row_pg[0]) if row_pg and row_pg[0] is not None else 0.0
    avg_comm = float(row_pg[1]) if row_pg and row_pg[1] is not None else 0.0
    count = int(row_pg[2]) if row_pg and row_pg[2] is not None else 0

    return {
        "filters": {
            "device": device,
            "event_type": event_type,
            "start_date": start_date,
            "end_date": end_date,
            "user_id": user_id
        },
        "results": {
            "total_commission": round(total_comm, 2),
            "average_commission": round(avg_comm, 4),
            "matching_events_count": count
        },
        "timings_ms": {
            "postgres": round(elapsed_pg, 2),
            "clickhouse": round(elapsed_ch, 2),
            "speedup": round(elapsed_pg / elapsed_ch, 2) if elapsed_ch > 0 else 0
        }
    }

@app.get("/api/benchmark")
def run_benchmark():
    try:
        pg_conn = psycopg.connect(PG_DSN)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Postgres: {str(e)}")

    try:
        ch_client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DB
        )
    except Exception as e:
        pg_conn.close()
        raise HTTPException(status_code=500, detail=f"Failed to connect to ClickHouse: {str(e)}")

    results = []
    
    for query in QUERIES:
        name = query["name"]
        sql = query["sql"]
        
        try:
            with pg_conn.cursor() as cur:
                cur.execute(sql)
                cur.fetchall()
        except Exception as e:
            pg_conn.rollback()
            pg_conn.close()
            ch_client.close()
            raise HTTPException(status_code=500, detail=f"Postgres query failed during warm-up: {str(e)}")
            
        pg_times = []
        for _ in range(3):
            t0 = time.perf_counter()
            with pg_conn.cursor() as cur:
                cur.execute(sql)
                cur.fetchall()
            t1 = time.perf_counter()
            pg_times.append((t1 - t0) * 1000)
            
        pg_min = min(pg_times)
        pg_avg = sum(pg_times) / len(pg_times)

        try:
            ch_client.query(sql)
        except Exception as e:
            pg_conn.close()
            ch_client.close()
            raise HTTPException(status_code=500, detail=f"ClickHouse query failed during warm-up: {str(e)}")
            
        ch_times = []
        for _ in range(3):
            t0 = time.perf_counter()
            ch_client.query(sql)
            t1 = time.perf_counter()
            ch_times.append((t1 - t0) * 1000)
            
        ch_min = min(ch_times)
        ch_avg = sum(ch_times) / len(ch_times)
        
        results.append({
            "query_name": name,
            "sql": sql,
            "postgres": {
                "min_ms": round(pg_min, 2),
                "avg_ms": round(pg_avg, 2)
            },
            "clickhouse": {
                "min_ms": round(ch_min, 2),
                "avg_ms": round(ch_avg, 2)
            },
            "speedup": round(pg_min / ch_min, 2) if ch_min > 0 else 0
        })
        
    pg_conn.close()
    ch_client.close()
    
    return {
        "benchmark_results": results
    }

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    with open("index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/tracker.js")
def get_tracker():
    with open("tracker.js", "r") as f:
        return Response(content=f.read(), media_type="application/javascript")

@app.get("/demo", response_class=HTMLResponse)
def get_tracker_demo():
    with open("tracker_demo.html", "r") as f:
        return HTMLResponse(content=f.read())

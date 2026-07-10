import time
import random
from datetime import datetime
from typing import Union
from fastapi import APIRouter, HTTPException, Request
from config import generate_user_hash
from database import get_ch_client, execute_sql
from models import GenericEvent, QuerySpec

router = APIRouter()

def resolve_field(field_name: str, for_numeric_aggregation: bool = False) -> str:
    standard_cols = {"event_id", "user_id", "event_type", "event_time", "device", "pathname", "referrer", "duration_sec"}
    if field_name in standard_cols:
        return field_name
        
    if field_name.startswith("properties."):
        prop_key = field_name.split(".", 1)[1]
        clean_key = "".join(c for c in prop_key if c.isalnum() or c == "_")
        return f"toFloat64OrNull(properties['{clean_key}'])" if for_numeric_aggregation else f"properties['{clean_key}']"

    raise ValueError(f"Invalid field name: {field_name}")

@router.post("/api/analytics/ingest")
def create_events(payload: Union[GenericEvent, list[GenericEvent]], request: Request):
    events = [payload] if isinstance(payload, GenericEvent) else payload
    
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")
    user_id = generate_user_hash(client_ip, user_agent)
    
    prepared_rows = []
    for ev in events:
        event_id = random.randint(1000000000, 9999999999)
        event_time = datetime.now()
        
        extra = ev.model_extra or {}
        custom_user_id = extra.pop("user_id", None)
        try:
            ev_user_id = int(custom_user_id) if custom_user_id is not None else user_id
        except Exception:
            ev_user_id = user_id
            
        properties = {k: str(v) for k, v in extra.items()}
        
        prepared_rows.append((
            event_id, ev_user_id, ev.event_type, event_time,
            ev.device or "desktop", ev.pathname, ev.referrer, ev.duration_sec or 0, properties
        ))
        
    start_ch = time.perf_counter()
    try:
        ch_client = get_ch_client()
        ch_client.insert(
            "events",
            data=prepared_rows,
            column_names=["event_id", "user_id", "event_type", "event_time", "device", "pathname", "referrer", "duration_sec", "properties"]
        )
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert into ClickHouse: {str(e)}")
        
    elapsed_ch = (time.perf_counter() - start_ch) * 1000
    
    return {
        "status": "success",
        "count": len(events),
        "timings_ms": {
            "clickhouse": round(elapsed_ch, 2)
        }
    }

@router.post("/api/analytics/clear")
def clear_analytics_data():
    try:
        ch_client = get_ch_client()
        ch_client.command("TRUNCATE TABLE events;")
        ch_client.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear database: {str(e)}")
    return {"status": "success", "message": "All generic events cleared."}

def compile_sql_query(spec: QuerySpec) -> tuple[str, dict]:
    if not spec.metrics and not spec.group_by:
        raise ValueError("At least one metric or group-by column must be specified.")

    select_parts = []
    group_by_cols = []
    
    if spec.group_by:
        for gb in spec.group_by:
            resolved = resolve_field(gb)
            select_parts.append(f"{resolved} AS {gb.replace('.', '_')}")
            group_by_cols.append(resolved)
            
    for m in spec.metrics:
        alias = m.alias or f"{m.type}_{m.field or 'all'}"
        clean_alias = "".join(c for c in alias if c.isalnum() or c == "_")
        
        is_numeric = m.type in ("sum", "avg")
        
        if m.field:
            resolved = resolve_field(m.field, for_numeric_aggregation=is_numeric)
            if m.type == "count":
                expr = f"COUNT({resolved})" if m.field != "*" else "COUNT(*)"
            elif m.type == "uniq":
                expr = f"uniq({resolved})"
            elif m.type in ("sum", "avg", "min", "max"):
                expr = f"{m.type.upper()}({resolved})"
            else:
                raise ValueError(f"Unsupported metric type: {m.type}")
        else:
            if m.type == "count":
                expr = "COUNT(*)"
            else:
                raise ValueError(f"{m.type} metric requires a field")
                
        select_parts.append(f"{expr} AS {clean_alias}")
        
    where_parts = []
    params = {}
    
    if spec.start_date:
        where_parts.append("event_time >= %(start_date)s")
        params["start_date"] = spec.start_date
            
    if spec.end_date:
        where_parts.append("event_time <= %(end_date)s")
        params["end_date"] = spec.end_date
            
    if spec.filters:
        for idx, f in enumerate(spec.filters):
            resolved_field = resolve_field(f.field)
            
            op_map = {
                "eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
                "in": "IN", "like": "LIKE"
            }
            if f.operator not in op_map:
                raise ValueError(f"Unsupported operator: {f.operator}")
                
            sql_op = op_map[f.operator]
            param_key = f"filter_val_{idx}"
            
            if f.operator == "in":
                if not isinstance(f.value, list):
                    raise ValueError("IN operator requires a list value")
                where_parts.append(f"{resolved_field} {sql_op} %({param_key})s")
                params[param_key] = tuple(f.value)
            else:
                where_parts.append(f"{resolved_field} {sql_op} %({param_key})s")
                params[param_key] = f.value
                    
    select_clause = ", ".join(select_parts)
    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    group_by_clause = f"GROUP BY {', '.join(group_by_cols)}" if group_by_cols else ""
    limit_clause = f"LIMIT {int(spec.limit)}" if spec.limit is not None else ""
    
    query_sql = f"SELECT {select_clause} FROM events {where_clause} {group_by_clause} {limit_clause};"
    return query_sql, params

@router.post("/api/analytics/query")
def query_analytics_events(spec: QuerySpec):
    try:
        sql, params = compile_sql_query(spec)
        results = execute_sql(sql, params)
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@router.get("/api/analytics/properties")
def get_available_properties():
    keys = set()
    try:
        ch_client = get_ch_client()
        res = ch_client.query("SELECT DISTINCT arrayJoin(mapKeys(properties)) AS key FROM events;")
        for row in res.result_rows:
            keys.add(row[0])
        ch_client.close()
    except Exception:
        pass
    return sorted(list(keys))

@router.get("/api/analytics/overview")
def get_analytics_overview(
    start_date: datetime | None = None,
    end_date: datetime | None = None
):
    try:
        where_parts = []
        params = {}

        if start_date:
            where_parts.append("event_time >= %(start_date)s")
            params["start_date"] = start_date

        if end_date:
            where_parts.append("event_time <= %(end_date)s")
            params["end_date"] = end_date

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        q_summary = f"""
            SELECT 
                countIf(event_type = 'pageview') AS total_views,
                uniq(user_id) AS unique_visitors,
                COUNT(*) AS total_events,
                avgIf(duration_sec, duration_sec > 0) AS avg_duration
            FROM events
            {where_clause}
        """
        q_pages = f"""
            SELECT pathname, COUNT(*) AS views, uniq(user_id) AS unique_visitors
            FROM events
            {where_clause}
            GROUP BY pathname
            ORDER BY views DESC
            LIMIT 10
        """
        q_referrers = f"""
            SELECT referrer, COUNT(*) AS views
            FROM events
            {where_clause}
            GROUP BY referrer
            ORDER BY views DESC
            LIMIT 10
        """
        q_devices = f"""
            SELECT device, COUNT(*) AS views
            FROM events
            {where_clause}
            GROUP BY device
            ORDER BY views DESC
        """

        summary_rows = execute_sql(q_summary, params)
        summary = summary_rows[0] if summary_rows else {"total_views": 0, "unique_visitors": 0, "total_events": 0}

        top_pages = execute_sql(q_pages, params)
        top_referrers = execute_sql(q_referrers, params)
        devices = execute_sql(q_devices, params)

        return {
            "summary": summary,
            "top_pages": top_pages,
            "top_referrers": top_referrers,
            "devices": devices
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

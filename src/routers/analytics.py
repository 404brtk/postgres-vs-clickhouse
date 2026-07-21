import time
import logging
from datetime import datetime
from typing import Union
from fastapi import APIRouter, Depends, HTTPException, Request
from src.config import generate_user_hash
from src.database import execute_sql, get_ch_client
from src.models import GenericEvent, QuerySpec
from src.auth import verify_api_key

router = APIRouter()


def resolve_field(field_name: str, for_numeric_aggregation: bool = False) -> str:
    standard_cols = {
        "event_id",
        "user_id",
        "event_type",
        "event_time",
        "device",
        "pathname",
        "referrer",
        "duration_sec",
    }
    if field_name in standard_cols:
        return field_name

    if field_name.startswith("properties."):
        prop_key = field_name.split(".", 1)[1]
        clean_key = "".join(c for c in prop_key if c.isalnum() or c == "_")
        if not clean_key:
            raise ValueError(f"Invalid field name: {field_name}")
        return (
            f"toFloat64OrNull(properties['{clean_key}'])"
            if for_numeric_aggregation
            else f"properties['{clean_key}']"
        )

    raise ValueError(f"Invalid field name: {field_name}")


@router.post("/api/analytics/ingest")
def create_events(
    payload: Union[GenericEvent, list[GenericEvent]],
    request: Request,
    ch_client=Depends(get_ch_client),
):
    events = [payload] if isinstance(payload, GenericEvent) else payload

    # TODO: once reverse proxy is set up, configure uvicorn's --proxy-headers
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")
    user_id = generate_user_hash(client_ip, user_agent)

    prepared_rows = []
    for ev in events:
        event_time = datetime.now()

        extra = ev.model_extra or {}
        custom_user_id = extra.pop("user_id", None)

        try:
            ev_user_id = int(custom_user_id) if custom_user_id is not None else user_id
        except (ValueError, TypeError):
            ev_user_id = user_id

        properties = {k: str(v) for k, v in extra.items()}

        prepared_rows.append(
            (
                ev_user_id,
                ev.event_type,
                event_time,
                ev.device or "desktop",
                ev.pathname,
                ev.referrer,
                ev.duration_sec or 0,
                properties,
            )
        )

    start_ch = time.perf_counter()
    try:
        ch_client.insert(
            "events",
            data=prepared_rows,
            column_names=[
                "user_id",
                "event_type",
                "event_time",
                "device",
                "pathname",
                "referrer",
                "duration_sec",
                "properties",
            ],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write events to ClickHouse: {str(e)}",
        )
    elapsed_ch = (time.perf_counter() - start_ch) * 1000

    return {
        "status": "success",
        "count": len(events),
        "timings_ms": {"clickhouse": round(elapsed_ch, 2)},
    }


@router.post("/api/analytics/clear")
def clear_analytics_data(
    ch_client=Depends(get_ch_client),
    _=Depends(verify_api_key),
):
    try:
        ch_client.command("TRUNCATE TABLE events")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clear database: {str(e)}"
        )
    return {
        "status": "success",
        "message": "All events cleared from database.",
    }


def _build_where_clause(spec: QuerySpec) -> tuple[str, dict]:
    where_parts = []
    params = {}

    if spec.start_date:
        where_parts.append("event_time >= %(start_date)s")
        params["start_date"] = spec.start_date.strftime("%Y-%m-%d %H:%M:%S")

    if spec.end_date:
        where_parts.append("event_time <= %(end_date)s")
        params["end_date"] = spec.end_date.strftime("%Y-%m-%d %H:%M:%S")

    if spec.filters:
        op_map = {
            "eq": "=",
            "neq": "!=",
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
            "in": "IN",
            "like": "LIKE",
        }
        for idx, f in enumerate(spec.filters):
            resolved_f = resolve_field(f.field)
            param_name = f"filter_val_{idx}"
            where_parts.append(f"{resolved_f} {op_map[f.operator]} %({param_name})s")
            params[param_name] = f.value

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return where_clause, params


def _compile_standard_query(
    spec: QuerySpec, where_clause: str, limit_clause: str
) -> str:
    select_parts = []
    group_by_cols = []

    if spec.group_by:
        for gb in spec.group_by:
            resolved = resolve_field(gb)
            select_parts.append(f"{resolved} AS `{gb}`")
            group_by_cols.append(resolved)

    for idx, m in enumerate(spec.metrics):
        alias = m.alias if m.alias else f"metric_{idx}"
        alias_escaped = f"`{alias}`"
        if m.type == "count":
            select_parts.append(f"COUNT(*) AS {alias_escaped}")
        else:
            if not m.field:
                raise ValueError(f"Field is required for metric type {m.type}")
            resolved_field = resolve_field(m.field, for_numeric_aggregation=True)
            func_name = {
                "uniq": "uniq",
                "sum": "sum",
                "avg": "avg",
                "min": "min",
                "max": "max",
            }[m.type]
            select_parts.append(f"{func_name}({resolved_field}) AS {alias_escaped}")

    select_clause = ", ".join(select_parts)
    group_clause = f"GROUP BY {', '.join(group_by_cols)}" if group_by_cols else ""
    order_clause = (
        f"ORDER BY {group_by_cols[0]} ASC" if group_by_cols else "ORDER BY 1 ASC"
    )

    return f"""
        SELECT {select_clause}
        FROM events
        {where_clause}
        {group_clause}
        {order_clause}
        {limit_clause}
    """


def _compile_bounce_query(spec: QuerySpec, where_clause: str, limit_clause: str) -> str:
    gb_resolved = [resolve_field(gb) for gb in (spec.group_by or [])]
    gb_select = [
        f"{resolved} AS `{gb}`"
        for gb, resolved in zip(spec.group_by or [], gb_resolved)
    ]
    inner_gb = [f"`{gb}`" for gb in (spec.group_by or [])]

    inner_cols = [
        "user_id",
        "countIf(event_type = 'pageview') AS `_pv_cnt`",
        "countIf(event_type NOT IN ('pageview', 'exit')) AS `_interact_cnt`",
    ] + gb_select
    inner_group = ["user_id"] + gb_resolved

    outer_select = []
    if spec.group_by:
        for gb in spec.group_by:
            outer_select.append(f"`{gb}`")

    for idx, m in enumerate(spec.metrics):
        alias = m.alias if m.alias else f"metric_{idx}"
        alias_escaped = f"`{alias}`"
        if m.type == "bounce_rate":
            outer_select.append(
                f"round(if(count() = 0, 0.0, countIf(`_pv_cnt` = 1 AND `_interact_cnt` = 0) * 100.0 / count()), 2) AS {alias_escaped}"
            )
        elif m.type == "count":
            outer_select.append(f"sum(`_pv_cnt` + `_interact_cnt`) AS {alias_escaped}")
        elif m.type == "uniq":
            outer_select.append(f"count() AS {alias_escaped}")
        else:
            if not m.field:
                raise ValueError(f"Field is required for metric type {m.type}")
            resolved_field = resolve_field(m.field, for_numeric_aggregation=True)
            outer_select.append(f"{m.type}({resolved_field}) AS {alias_escaped}")

    outer_group = f"GROUP BY {', '.join(inner_gb)}" if inner_gb else ""
    order_clause = f"ORDER BY {inner_gb[0]} ASC" if inner_gb else "ORDER BY 1 ASC"

    return f"""
        WITH user_sessions AS (
            SELECT {", ".join(inner_cols)}
            FROM events
            {where_clause}
            GROUP BY {", ".join(inner_group)}
        )
        SELECT {", ".join(outer_select)}
        FROM user_sessions
        {outer_group}
        {order_clause}
        {limit_clause}
    """


def compile_sql_query(spec: QuerySpec) -> tuple[str, dict]:
    if not spec.metrics and not spec.group_by:
        raise ValueError("At least one metric or group-by column must be specified.")

    where_clause, params = _build_where_clause(spec)
    limit_clause = f"LIMIT {spec.limit}" if spec.limit else ""

    if any(m.type == "bounce_rate" for m in spec.metrics):
        query_sql = _compile_bounce_query(spec, where_clause, limit_clause)
    else:
        query_sql = _compile_standard_query(spec, where_clause, limit_clause)

    return query_sql, params


@router.post("/api/analytics/query")
def query_analytics_events(
    spec: QuerySpec,
    ch_client=Depends(get_ch_client),
    _=Depends(verify_api_key),
):
    try:
        sql, params = compile_sql_query(spec)
        results = execute_sql(ch_client, sql, params)
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.get("/api/analytics/properties")
def get_available_properties(
    ch_client=Depends(get_ch_client),
    _=Depends(verify_api_key),
):
    keys = set()
    try:
        res = ch_client.query(
            "SELECT DISTINCT arrayJoin(mapKeys(properties)) AS key FROM events"
        )
        for row in res.result_rows:
            keys.add(row[0])
    except Exception as e:
        logging.error(f"Failed to fetch available properties: {e}")
    return sorted(list(keys))


@router.get("/api/analytics/overview")
def get_analytics_overview(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    ch_client=Depends(get_ch_client),
    _=Depends(verify_api_key),
):
    try:
        where_parts = []
        params: dict = {}

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
        q_bounce = f"""
            WITH user_sessions AS (
                SELECT
                    user_id,
                    countIf(event_type = 'pageview') AS pageview_count,
                    countIf(event_type NOT IN ('pageview', 'exit')) AS interaction_count
                FROM events
                {where_clause}
                GROUP BY user_id
            )
            SELECT round(if(count() = 0, 0.0, countIf(pageview_count = 1 AND interaction_count = 0) * 100.0 / count()), 1) AS bounce_rate
            FROM user_sessions
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

        summary_rows = execute_sql(ch_client, q_summary, params)
        bounce_rows = execute_sql(ch_client, q_bounce, params)
        summary = (
            summary_rows[0]
            if summary_rows
            else {
                "total_views": 0,
                "unique_visitors": 0,
                "total_events": 0,
                "avg_duration": 0,
            }
        )
        summary["bounce_rate"] = bounce_rows[0]["bounce_rate"] if bounce_rows else 0.0

        top_pages = execute_sql(ch_client, q_pages, params)
        top_referrers = execute_sql(ch_client, q_referrers, params)
        devices = execute_sql(ch_client, q_devices, params)

        return {
            "summary": summary,
            "top_pages": top_pages,
            "top_referrers": top_referrers,
            "devices": devices,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/analytics/history")
def get_analytics_history(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    event_type: str | None = None,
    interval: str | None = None,
    ch_client=Depends(get_ch_client),
    _=Depends(verify_api_key),
):
    try:
        where_parts = []
        params: dict = {}

        if start_date:
            where_parts.append("event_time >= %(start_date)s")
            params["start_date"] = start_date

        if end_date:
            where_parts.append("event_time <= %(end_date)s")
            params["end_date"] = end_date

        if event_type:
            where_parts.append("event_type = %(event_type)s")
            params["event_type"] = event_type

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        time_expr = "toDate(event_time)"
        if interval == "hour":
            time_expr = (
                "formatDateTime(toStartOfHour(event_time), '%%Y-%%m-%%dT%%H:00:00Z')"
            )
        elif interval == "minute":
            time_expr = (
                "formatDateTime(toStartOfMinute(event_time), '%%Y-%%m-%%dT%%H:%%i:00Z')"
            )

        q_history = f"""
            SELECT
                {time_expr} AS day,
                countIf(event_type = 'pageview') AS views,
                uniq(user_id) AS visitors,
                COUNT(*) AS events,
                avgIf(duration_sec, duration_sec > 0) AS duration
            FROM events
            {where_clause}
            GROUP BY day
            ORDER BY day ASC
            LIMIT 100
        """
        q_bounce_history = f"""
            WITH user_sessions AS (
                SELECT
                    {time_expr} AS day,
                    user_id,
                    countIf(event_type = 'pageview') AS pageview_count,
                    countIf(event_type NOT IN ('pageview', 'exit')) AS interaction_count
                FROM events
                {where_clause}
                GROUP BY day, user_id
            )
            SELECT
                day,
                round(if(count() = 0, 0.0, countIf(pageview_count = 1 AND interaction_count = 0) * 100.0 / count()), 1) AS bounce
            FROM user_sessions
            GROUP BY day
        """
        history_rows = execute_sql(ch_client, q_history, params)
        bounce_rows = execute_sql(ch_client, q_bounce_history, params)
        bounce_map = {r["day"]: r["bounce"] for r in bounce_rows}
        for h in history_rows:
            h["bounce"] = bounce_map.get(h["day"], 0.0)

        return history_rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

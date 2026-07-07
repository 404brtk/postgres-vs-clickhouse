import urllib.request
import json
from datetime import datetime

API_BASE = "http://127.0.0.1:8000"

def make_request(path, method="GET"):
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Request failed for {path}: {e}")
        return None

def main():
    import_choice = input("Do you want to reset databases and import user_events.csv first? (y/n): ").strip().lower()
    if import_choice == 'y':
        print("Importing...")
        import_data = make_request("/api/import", method="POST")
        if not import_data:
            print("Import failed. Make sure FastAPI server is running.")
            return

    print("Running benchmarks...")
    olap_data = make_request("/api/benchmark")
    if not olap_data:
        print("OLAP benchmark failed.")
        return
        
    insert_res = make_request("/api/events/random", method="POST")
    if not insert_res:
        print("OLTP benchmark failed.")
        return
    event_id = insert_res["event_id"]
    
    fetch_res = make_request(f"/api/events/lookup?event_id={event_id}")
    update_res = make_request(f"/api/events/update?event_id={event_id}", method="PUT")
    delete_res = make_request(f"/api/events/delete?event_id={event_id}", method="DELETE")
    
    batch_results = {}
    for size in [10000, 50000, 100000, 1000000]:
        batch_res = make_request(f"/api/events/batch?count={size}", method="POST")
        if batch_res:
            batch_results[size] = batch_res["timings_ms"]
            
    report_lines = []
    report_lines.append("=====================================================================")
    report_lines.append("                 POSTGRES VS CLICKHOUSE BENCHMARK REPORT             ")
    report_lines.append(f"                 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}       ")
    report_lines.append("=====================================================================\n")
    
    report_lines.append("1. Analytical Queries (OLAP)")
    report_lines.append("---------------------------------------------------------------------")
    report_lines.append(f"{'Query / Operation':<40} | {'Postgres':<12} | {'ClickHouse':<12} | {'Speedup':<15}")
    report_lines.append("---------------------------------------------------------------------")
    for r in olap_data["benchmark_results"]:
        speedup_str = f"{r['speedup']:.2f}x (ClickHouse)"
        report_lines.append(f"{r['query_name']:<40} | {r['postgres']['min_ms']:>8.2f} ms | {r['clickhouse']['min_ms']:>8.2f} ms | {speedup_str:<15}")
    report_lines.append("---------------------------------------------------------------------\n")
    
    report_lines.append("2. Single Row Operations (OLTP)")
    report_lines.append("---------------------------------------------------------------------")
    report_lines.append(f"{'Operation / Button':<40} | {'Postgres':<12} | {'ClickHouse':<12} | {'Speedup':<15}")
    report_lines.append("---------------------------------------------------------------------")
    
    oltp_ops = [
        ("Insert Event", insert_res["timings_ms"]),
        ("Fetch Event", fetch_res["timings_ms"] if fetch_res else None),
        ("Update Event", update_res["timings_ms"] if update_res else None),
        ("Delete Event", delete_res["timings_ms"] if delete_res else None)
    ]
    
    for name, timings in oltp_ops:
        if timings:
            speedup = timings["speedup"]
            speedup_str = f"{speedup:.2f}x (PostgreSQL)" if speedup >= 1 else f"{1/speedup:.2f}x (ClickHouse)"
            report_lines.append(f"{name:<40} | {timings['postgres']:>8.2f} ms | {timings['clickhouse']:>8.2f} ms | {speedup_str:<15}")
    report_lines.append("---------------------------------------------------------------------\n")
    
    report_lines.append("3. Batch Ingestion Operations")
    report_lines.append("---------------------------------------------------------------------")
    report_lines.append(f"{'Batch Size':<40} | {'Postgres':<12} | {'ClickHouse':<12} | {'Speedup':<15}")
    report_lines.append("---------------------------------------------------------------------")
    for size, timings in batch_results.items():
        speedup = timings["speedup"]
        speedup_str = f"{speedup:.2f}x (ClickHouse)" if speedup >= 1 else f"{1/speedup:.2f}x (PostgreSQL)"
        label = f"Insert Batch ({size:,} events)"
        report_lines.append(f"{label:<40} | {timings['postgres']:>8.2f} ms | {timings['clickhouse']:>8.2f} ms | {speedup_str:<15}")
    report_lines.append("---------------------------------------------------------------------\n")
    
    report_text = "\n".join(report_lines)
    
    print("\n" + report_text)
    
    with open("benchmark_results.txt", "w") as f:
        f.write(report_text)
        
    print("Done! Report written to benchmark_results.txt.")

if __name__ == "__main__":
    main()

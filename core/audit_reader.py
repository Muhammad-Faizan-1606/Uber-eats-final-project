import sqlite3, json
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any

def _connect(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con

def _row_to_item(r: sqlite3.Row) -> Dict[str,Any]:
    return {
        "id": r["id"],
        "ts": r["ts"],
        "order_id": r["order_id"],
        "decision": r["decision"],
        "source": r["source"],
        "confidence": r["confidence"],
        "rule_id": r["rule_id"],
        "category": r["category"],
        "reason": r["reason"],
        "case_json": r["case_json"],
        "case": json.loads(r["case_json"] or "{}"),
    }

def query_audit(db_path: str, page: int = 1, page_size: int = 50) -> Tuple[List[Dict], int]:
    con = _connect(db_path)
    try:
        total = con.execute("SELECT COUNT(*) AS c FROM audit").fetchone()["c"]
        offset = max(0, (page-1)*page_size)
        rows = con.execute("""            SELECT * FROM audit ORDER BY id DESC LIMIT ? OFFSET ?
        """, [page_size, offset]).fetchall()
        return [ _row_to_item(r) for r in rows ], total
    finally:
        con.close()

def compute_stats(db_path: str, days: int = 14) -> Dict[str,Any]:
    con = _connect(db_path)
    try:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        rows = con.execute("SELECT * FROM audit WHERE ts >= ?", [since]).fetchall()
        items = [ _row_to_item(r) for r in rows ]
        total = len(items)
        by_decision, by_source = {}, {}
        by_day = {}
        for it in items:
            by_decision[it["decision"]] = by_decision.get(it["decision"],0) + 1
            by_source[it["source"]] = by_source.get(it["source"],0) + 1
            day = (it["ts"] or "")[:10]
            by_day[day] = by_day.get(day,0) + 1
        by_day_list = [{"day":k,"count":v} for k,v in sorted(by_day.items())]
        return {"total": total, "by_decision": by_decision, "by_source": by_source, "by_day": by_day_list}
    finally:
        con.close()

def export_csv_rows(db_path: str) -> List[Dict[str,Any]]:
    con = _connect(db_path)
    try:
        rows = con.execute("SELECT * FROM audit ORDER BY id DESC").fetchall()
        return [ dict(r) for r in rows ]
    finally:
        con.close()

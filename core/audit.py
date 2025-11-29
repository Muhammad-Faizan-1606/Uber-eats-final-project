import sqlite3, json
from pathlib import Path
from typing import Dict, Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL DEFAULT (datetime('now')),
  order_id TEXT NOT NULL,
  decision TEXT,
  source TEXT,
  confidence REAL,
  rule_id TEXT,
  category TEXT,
  reason TEXT,
  case_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit(ts);
CREATE INDEX IF NOT EXISTS ix_audit_order ON audit(order_id);
"""

class Audit:
    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = Path(db_path).parent
        if parent.as_posix() not in (".",""):
            parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self):
        con = sqlite3.connect(self.db_path)
        try:
            con.executescript(SCHEMA)
            con.commit()
        finally:
            con.close()

    def log(self, order_id: str, outcome: Dict[str,Any], case: Dict[str,Any]):
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("""                INSERT INTO audit (order_id, decision, source, confidence, rule_id, category, reason, case_json)
                VALUES (?,?,?,?,?,?,?,?)
            """, [
                order_id,
                outcome.get("decision"),
                outcome.get("source"),
                float(outcome.get("confidence", 0)) if outcome.get("confidence") is not None else None,
                outcome.get("rule_id"),
                outcome.get("category"),
                outcome.get("reason"),
                json.dumps(case, ensure_ascii=False),
            ])
            con.commit()
        finally:
            con.close()

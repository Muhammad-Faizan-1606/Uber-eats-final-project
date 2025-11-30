"""
Audit Database Module
SQLite-based storage for complaints, feedback, and analytics.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class AuditDB:
    """
    SQLite database for complaint tracking and analytics.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
        self._init_schema()
    
    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_schema(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS complaints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    complaint_id TEXT UNIQUE,
                    order_id TEXT,
                    customer_id TEXT,
                    timestamp TEXT,
                    decision TEXT,
                    confidence REAL,
                    source TEXT,
                    rule_id TEXT,
                    severity TEXT,
                    categories TEXT,
                    root_cause TEXT,
                    fraud_risk TEXT,
                    fraud_score REAL,
                    sla_deadline TEXT,
                    resolved_at TEXT,
                    case_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    complaint_id TEXT,
                    original_decision TEXT,
                    corrected_decision TEXT,
                    reason TEXT,
                    agent TEXT,
                    timestamp TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    email TEXT,
                    total_complaints INTEGER DEFAULT 0,
                    total_refunds INTEGER DEFAULT 0,
                    total_denials INTEGER DEFAULT 0,
                    fraud_flags INTEGER DEFAULT 0,
                    lifetime_value REAL DEFAULT 0,
                    risk_tier TEXT DEFAULT 'normal',
                    first_seen TEXT,
                    last_seen TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_complaints_customer ON complaints(customer_id);
                CREATE INDEX IF NOT EXISTS idx_complaints_timestamp ON complaints(timestamp);
                CREATE INDEX IF NOT EXISTS idx_complaints_decision ON complaints(decision);
                CREATE INDEX IF NOT EXISTS idx_complaints_severity ON complaints(severity);
                CREATE INDEX IF NOT EXISTS idx_feedback_complaint ON feedback(complaint_id);
            """)
            conn.commit()
            logger.info(f"Database initialized: {self.db_path}")
    
    def is_healthy(self) -> bool:
        """Check if database is accessible."""
        try:
            with self._get_conn() as conn:
                conn.execute("SELECT 1")
            return True
        except:
            return False
    
    def log_complaint(self, result: Dict[str, Any], case: Dict[str, Any]):
        """Log a complaint and its classification result."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO complaints 
                (complaint_id, order_id, customer_id, timestamp, decision, confidence,
                 source, rule_id, severity, categories, root_cause, fraud_risk, 
                 fraud_score, sla_deadline, case_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.get("complaint_id"),
                result.get("order_id"),
                case.get("customer_id", "anonymous"),
                result.get("timestamp"),
                result.get("decision"),
                result.get("confidence"),
                result.get("source"),
                result.get("rule_id"),
                result.get("severity"),
                json.dumps(result.get("categories", [])),
                result.get("root_cause"),
                result.get("fraud_risk"),
                result.get("fraud_score"),
                result.get("sla_deadline"),
                json.dumps(case)
            ))
            
            # Update customer record
            self._update_customer(conn, case.get("customer_id"), result)
            conn.commit()
    
    def _update_customer(self, conn, customer_id: str, result: Dict):
        """Update customer statistics."""
        if not customer_id or customer_id == "anonymous":
            return
        
        now = datetime.utcnow().isoformat()
        
        conn.execute("""
            INSERT INTO customers (customer_id, first_seen, last_seen, total_complaints)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(customer_id) DO UPDATE SET
                total_complaints = total_complaints + 1,
                last_seen = ?,
                total_refunds = total_refunds + CASE WHEN ? = 'refund' THEN 1 ELSE 0 END,
                total_denials = total_denials + CASE WHEN ? = 'deny' THEN 1 ELSE 0 END,
                fraud_flags = fraud_flags + CASE WHEN ? IN ('high', 'critical') THEN 1 ELSE 0 END
        """, (customer_id, now, now, now, result.get("decision"), result.get("decision"), result.get("fraud_risk")))
    
    def log_feedback(self, feedback: Dict[str, Any]):
        """Log agent feedback on a decision."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO feedback 
                (complaint_id, original_decision, corrected_decision, reason, agent, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                feedback.get("complaint_id"),
                feedback.get("original_decision"),
                feedback.get("corrected_decision"),
                feedback.get("reason"),
                feedback.get("agent"),
                feedback.get("timestamp")
            ))
            conn.commit()
    
    def get_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get aggregated statistics for dashboard."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        with self._get_conn() as conn:
            # Total complaints
            total = conn.execute(
                "SELECT COUNT(*) FROM complaints WHERE timestamp >= ?", (cutoff,)
            ).fetchone()[0]
            
            # By decision
            by_decision = dict(conn.execute("""
                SELECT decision, COUNT(*) FROM complaints 
                WHERE timestamp >= ? GROUP BY decision
            """, (cutoff,)).fetchall())
            
            # By severity
            by_severity = dict(conn.execute("""
                SELECT severity, COUNT(*) FROM complaints 
                WHERE timestamp >= ? GROUP BY severity
            """, (cutoff,)).fetchall())
            
            # By category (need to unpack JSON)
            categories_raw = conn.execute("""
                SELECT categories FROM complaints WHERE timestamp >= ?
            """, (cutoff,)).fetchall()
            
            category_counts = {}
            for row in categories_raw:
                try:
                    cats = json.loads(row[0]) if row[0] else []
                    for cat in cats:
                        category_counts[cat] = category_counts.get(cat, 0) + 1
                except:
                    pass
            
            # By source
            by_source = dict(conn.execute("""
                SELECT source, COUNT(*) FROM complaints 
                WHERE timestamp >= ? GROUP BY source
            """, (cutoff,)).fetchall())
            
            # Average confidence
            avg_conf = conn.execute("""
                SELECT AVG(confidence) FROM complaints WHERE timestamp >= ?
            """, (cutoff,)).fetchone()[0] or 0
            
            # Fraud flagged
            fraud_count = conn.execute("""
                SELECT COUNT(*) FROM complaints 
                WHERE timestamp >= ? AND fraud_risk IN ('high', 'critical')
            """, (cutoff,)).fetchone()[0]
            
            # Daily trend
            daily = conn.execute("""
                SELECT DATE(timestamp) as day, COUNT(*) as count
                FROM complaints WHERE timestamp >= ?
                GROUP BY DATE(timestamp) ORDER BY day
            """, (cutoff,)).fetchall()
            
            return {
                "total": total,
                "by_decision": by_decision,
                "by_severity": by_severity,
                "by_category": category_counts,
                "by_source": by_source,
                "avg_confidence": round(avg_conf, 3),
                "fraud_flagged": fraud_count,
                "sla_compliance": 0.95,  # Placeholder
                "daily_trend": [{"day": r[0], "count": r[1]} for r in daily]
            }
    
    def get_timeseries(self, days: int = 30, metric: str = "volume") -> Dict:
        """Get time-series data for charts."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        with self._get_conn() as conn:
            if metric == "volume":
                data = conn.execute("""
                    SELECT DATE(timestamp) as day, COUNT(*) as value
                    FROM complaints WHERE timestamp >= ?
                    GROUP BY DATE(timestamp) ORDER BY day
                """, (cutoff,)).fetchall()
                return {"labels": [r[0] for r in data], "values": [r[1] for r in data]}
            
            elif metric == "decision":
                data = conn.execute("""
                    SELECT DATE(timestamp) as day, decision, COUNT(*) as value
                    FROM complaints WHERE timestamp >= ?
                    GROUP BY DATE(timestamp), decision ORDER BY day
                """, (cutoff,)).fetchall()
                # Pivot data
                result = {"labels": [], "datasets": {}}
                for row in data:
                    if row[0] not in result["labels"]:
                        result["labels"].append(row[0])
                    if row[1] not in result["datasets"]:
                        result["datasets"][row[1]] = []
                return result
            
            elif metric == "severity":
                data = conn.execute("""
                    SELECT severity, COUNT(*) as value
                    FROM complaints WHERE timestamp >= ?
                    GROUP BY severity
                """, (cutoff,)).fetchall()
                return {"labels": [r[0] for r in data], "values": [r[1] for r in data]}
            
            elif metric == "fraud":
                data = conn.execute("""
                    SELECT DATE(timestamp) as day, 
                           SUM(CASE WHEN fraud_risk IN ('high', 'critical') THEN 1 ELSE 0 END) as flagged,
                           COUNT(*) as total
                    FROM complaints WHERE timestamp >= ?
                    GROUP BY DATE(timestamp) ORDER BY day
                """, (cutoff,)).fetchall()
                return {
                    "labels": [r[0] for r in data],
                    "flagged": [r[1] for r in data],
                    "total": [r[2] for r in data]
                }
        
        return {}
    
    def get_root_cause_stats(self, days: int = 30) -> Dict:
        """Get root cause analysis data."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        with self._get_conn() as conn:
            data = conn.execute("""
                SELECT root_cause, COUNT(*) as count
                FROM complaints WHERE timestamp >= ? AND root_cause IS NOT NULL
                GROUP BY root_cause ORDER BY count DESC
            """, (cutoff,)).fetchall()
            
            return {
                "causes": [{"cause": r[0], "count": r[1]} for r in data]
            }
    
    def get_recent(self, limit: int = 10) -> List[Dict]:
        """Get recent complaints."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT complaint_id, order_id, timestamp, decision, severity, 
                       categories, confidence, source
                FROM complaints ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_complaints(self, page: int = 1, limit: int = 20, 
                       status: str = "all", severity: str = "all") -> Dict:
        """Get paginated complaints list."""
        offset = (page - 1) * limit
        
        with self._get_conn() as conn:
            where_clauses = []
            params = []
            
            if status != "all":
                where_clauses.append("decision = ?")
                params.append(status)
            
            if severity != "all":
                where_clauses.append("severity = ?")
                params.append(severity)
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            total = conn.execute(f"""
                SELECT COUNT(*) FROM complaints WHERE {where_sql}
            """, params).fetchone()[0]
            
            # Get page
            rows = conn.execute(f"""
                SELECT * FROM complaints WHERE {where_sql}
                ORDER BY timestamp DESC LIMIT ? OFFSET ?
            """, params + [limit, offset]).fetchall()
            
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "page": page,
                "pages": (total + limit - 1) // limit
            }
    
    def get_customer_complaints(self, customer_id: str, page: int = 1, limit: int = 20) -> Dict:
        """Get complaints for a specific customer."""
        offset = (page - 1) * limit
        
        with self._get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM complaints WHERE customer_id = ?", (customer_id,)
            ).fetchone()[0]
            
            rows = conn.execute("""
                SELECT * FROM complaints WHERE customer_id = ?
                ORDER BY timestamp DESC LIMIT ? OFFSET ?
            """, (customer_id, limit, offset)).fetchall()
            
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "page": page
            }
    
    def get_feedback_for_training(self, limit: int = 1000) -> List[Dict]:
        """Get feedback data for model retraining."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT f.*, c.case_data
                FROM feedback f
                JOIN complaints c ON f.complaint_id = c.complaint_id
                ORDER BY f.timestamp DESC LIMIT ?
            """, (limit,)).fetchall()
            
            return [dict(row) for row in rows]

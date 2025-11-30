# core/fraud_detector.py

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class FraudDetector:
    """
    Simple, defensive fraud / abuse scoring engine.
    """

    DEFAULT_THRESHOLDS = {
        "complaints_30d": 3,
        "complaints_24h": 2,
        "refund_rate": 0.6,
        "account_age_days_min": 7,
    }

    DEFAULT_WEIGHTS = {
        "excessive_complaints": 25,
        "burst_activity": 20,
        "high_refund_rate": 25,
        "very_new_account": 15,
        "high_value_pattern": 15,
    }

    def __init__(
        self,
        db_path: str,
        thresholds: Optional[Dict[str, Any]] = None,
        weights: Optional[Dict[str, int]] = None,
    ) -> None:
        self.db_path = db_path
        self.THRESHOLDS = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.WEIGHTS = {**self.DEFAULT_WEIGHTS, **(weights or {})}

    def assess(
        self,
        customer_id: Optional[str],
        intelligence: Optional[Dict[str, Any]] = None,
        decision: Optional[Dict[str, Any]] = None,
        order_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Main entrypoint.
        """
        # Defensive: Return clean empty structure if no customer_id
        if not customer_id:
            return {
                "score": 0,
                "label": "normal",
                "flags": [],
                "history": {},
            }

        # 1. Fetch History
        history = self._get_customer_history(customer_id)
        flags: List[Dict[str, Any]] = []
        score = 0

        # 2. Extract Variables SAFELY (Fix for TypeError)
        # We use (value or 0) to ensure None becomes 0 immediately
        total_complaints = int(history.get("total_complaints") or 0)
        complaints_30d = int(history.get("complaints_30d") or 0)
        complaints_24h = int(history.get("complaints_24h") or 0)
        refund_rate = float(history.get("refund_rate") or 0.0)
        account_age_days = int(history.get("account_age_days") or 0)

        # 3. Handle Order Value (Fix for signature mismatch with main.py)
        # main.py passes 'case' dict as the 2nd argument (intelligence)
        # We try to find order_value there if not passed explicitly.
        current_order_val = order_value
        if current_order_val is None and isinstance(intelligence, dict):
            current_order_val = intelligence.get("order_value")
        
        safe_order_value = self._safe_float(current_order_val)

        # --- RULE 1: Excessive complaints in 30 days ---
        if complaints_30d >= self.THRESHOLDS["complaints_30d"]:
            flags.append({
                "type": "excessive_complaints",
                "description": f"{complaints_30d} complaints in last 30 days",
                "severity": "high",
            })
            score += self.WEIGHTS["excessive_complaints"]

        # --- RULE 2: Burst activity (24h) ---
        if complaints_24h >= self.THRESHOLDS["complaints_24h"]:
            flags.append({
                "type": "burst_activity",
                "description": f"{complaints_24h} complaints in last 24 hours",
                "severity": "high",
            })
            score += self.WEIGHTS["burst_activity"]

        # --- RULE 3: High refund rate ---
        if total_complaints >= 3 and refund_rate >= self.THRESHOLDS["refund_rate"]:
            percent = round(refund_rate * 100, 1)
            flags.append({
                "type": "high_refund_rate",
                "description": f"Refund rate {percent}% over {total_complaints} complaints",
                "severity": "high",
            })
            score += self.WEIGHTS["high_refund_rate"]

        # --- RULE 4: Very new account ---
        if account_age_days < self.THRESHOLDS["account_age_days_min"] and total_complaints > 0:
            flags.append({
                "type": "very_new_account",
                "description": f"Account age {account_age_days} days with {total_complaints} complaints",
                "severity": "medium",
            })
            score += self.WEIGHTS["very_new_account"]

        # --- RULE 5: High-value pattern ---
        if safe_order_value >= 50: # Example threshold, adjust as needed
            flags.append({
                "type": "high_value_order",
                "description": f"High-value complaint (${safe_order_value})",
                "severity": "medium",
            })
            score += self.WEIGHTS["high_value_pattern"]

        # Cap score
        score = max(0, min(100, score))
        label = self._classify_label(score)

        return {
            "score": score,
            "label": label,
            "flags": flags,
            "history": history,
        }

    def _get_customer_history(self, customer_id: str) -> Dict[str, Any]:
        """
        Pull basic stats from SQLite. Returns dict with guaranteed zero-values on error.
        """
        # Default empty structure
        default_history = {
            "total_complaints": 0,
            "total_refunds": 0,
            "complaints_30d": 0,
            "complaints_24h": 0,
            "refund_rate": 0.0,
            "account_age_days": 0,
            "first_seen": None
        }

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            now = datetime.utcnow()
            cutoff_30d = (now - timedelta(days=30)).isoformat()
            cutoff_24h = (now - timedelta(hours=24)).isoformat()

            # Check if table exists first to avoid crash on fresh DB
            check_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit';").fetchone()
            if not check_table:
                conn.close()
                return default_history

            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_complaints,
                    SUM(CASE WHEN decision = 'refund' THEN 1 ELSE 0 END) AS total_refunds,
                    SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END) AS complaints_30d,
                    SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END) AS complaints_24h,
                    MIN(timestamp) AS first_seen
                FROM audit
                WHERE customer_id = ?
                """,
                (cutoff_30d, cutoff_24h, customer_id),
            ).fetchone()

            conn.close()

            if not row:
                return default_history

            # Convert Row to dict and safely process
            data = dict(row)
            
            history = {
                "total_complaints": self._safe_int(data.get("total_complaints")),
                "total_refunds": self._safe_int(data.get("total_refunds")),
                "complaints_30d": self._safe_int(data.get("complaints_30d")),
                "complaints_24h": self._safe_int(data.get("complaints_24h")),
                "first_seen": data.get("first_seen")
            }

            # Calc Rate
            if history["total_complaints"] > 0:
                history["refund_rate"] = history["total_refunds"] / history["total_complaints"]
            else:
                history["refund_rate"] = 0.0

            # Calc Age
            history["account_age_days"] = 0
            if history["first_seen"]:
                try:
                    cleaned = str(history["first_seen"]).replace("Z", "+00:00")
                    first_dt = datetime.fromisoformat(cleaned)
                    if first_dt.tzinfo is not None:
                        first_dt = first_dt.astimezone(tz=None).replace(tzinfo=None)
                    history["account_age_days"] = (now - first_dt).days
                except Exception:
                    pass

            return history

        except Exception as e:
            logger.error(f"Error fetching history for {customer_id}: {e}")
            return default_history

    def _classify_label(self, score: int) -> str:
        if score >= 70: return "high_risk"
        elif score >= 40: return "suspicious"
        elif score >= 20: return "watch"
        else: return "normal"

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            if value is None: return 0
            return int(value)
        except:
            return 0

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            if value is None: return 0.0
            return float(value)
        except:
            return 0.0
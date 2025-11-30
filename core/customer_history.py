"""
Customer History Module
Tracks and analyzes customer complaint patterns.
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class CustomerHistory:
    """
    Customer history tracking and analysis.
    """
    
    # Risk tier thresholds
    RISK_TIERS = {
        "vip": {"min_orders": 50, "max_complaint_rate": 0.02},
        "trusted": {"min_orders": 20, "max_complaint_rate": 0.05},
        "normal": {"min_orders": 0, "max_complaint_rate": 0.15},
        "watch": {"min_orders": 0, "max_complaint_rate": 0.30},
        "flagged": {"min_orders": 0, "max_complaint_rate": 1.0}
    }
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_summary(self, customer_id: str) -> Dict[str, Any]:
        """Get quick customer summary for classification context."""
        if not customer_id or customer_id == "anonymous":
            return {
                "total_complaints": 0,
                "recent_complaints": 0,
                "refund_rate": 0.0,
                "lifetime_value": 0.0,
                "risk_tier": "unknown"
            }
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            cutoff_30d = (datetime.utcnow() - timedelta(days=30)).isoformat()
            
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total_complaints,
                    SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END) as recent_complaints,
                    SUM(CASE WHEN decision = 'refund' THEN 1 ELSE 0 END) as refunds
                FROM complaints WHERE customer_id = ?
            """, (cutoff_30d, customer_id)).fetchone()
            
            if row:
                total = row["total_complaints"] or 0
                refunds = row["refunds"] or 0
                recent = row["recent_complaints"] or 0
                
                refund_rate = refunds / total if total > 0 else 0
                risk_tier = self._calculate_risk_tier(total, refund_rate)
                
                conn.close()
                
                return {
                    "total_complaints": total,
                    "recent_complaints": recent,
                    "refund_rate": round(refund_rate, 3),
                    "lifetime_value": total * 25,  # Placeholder LTV calculation
                    "risk_tier": risk_tier
                }
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error getting customer summary: {e}")
        
        return {
            "total_complaints": 0,
            "recent_complaints": 0,
            "refund_rate": 0.0,
            "lifetime_value": 0.0,
            "risk_tier": "normal"
        }
    
    def get_full_history(self, customer_id: str) -> Dict[str, Any]:
        """Get complete customer history for detail view."""
        if not customer_id:
            return {"error": "No customer ID provided"}
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Get customer record
            customer = conn.execute("""
                SELECT * FROM customers WHERE customer_id = ?
            """, (customer_id,)).fetchone()
            
            # Get complaint stats
            stats = conn.execute("""
                SELECT 
                    COUNT(*) as total_complaints,
                    SUM(CASE WHEN decision = 'refund' THEN 1 ELSE 0 END) as refunds,
                    SUM(CASE WHEN decision = 'deny' THEN 1 ELSE 0 END) as denials,
                    SUM(CASE WHEN decision = 'escalate' THEN 1 ELSE 0 END) as escalations,
                    AVG(confidence) as avg_confidence,
                    MIN(timestamp) as first_complaint,
                    MAX(timestamp) as last_complaint
                FROM complaints WHERE customer_id = ?
            """, (customer_id,)).fetchone()
            
            # Get category breakdown
            categories = conn.execute("""
                SELECT categories, COUNT(*) as count
                FROM complaints WHERE customer_id = ?
                GROUP BY categories
            """, (customer_id,)).fetchall()
            
            # Get severity breakdown
            severities = conn.execute("""
                SELECT severity, COUNT(*) as count
                FROM complaints WHERE customer_id = ?
                GROUP BY severity
            """, (customer_id,)).fetchall()
            
            # Get recent complaints
            recent = conn.execute("""
                SELECT complaint_id, order_id, timestamp, decision, severity, categories
                FROM complaints WHERE customer_id = ?
                ORDER BY timestamp DESC LIMIT 10
            """, (customer_id,)).fetchall()
            
            # Get fraud flags history
            fraud_flags = conn.execute("""
                SELECT fraud_risk, COUNT(*) as count
                FROM complaints WHERE customer_id = ?
                GROUP BY fraud_risk
            """, (customer_id,)).fetchall()
            
            conn.close()
            
            total = stats["total_complaints"] if stats else 0
            refunds = stats["refunds"] if stats else 0
            refund_rate = refunds / total if total > 0 else 0
            
            return {
                "customer_id": customer_id,
                "profile": dict(customer) if customer else {},
                "stats": {
                    "total_complaints": total,
                    "refunds": refunds,
                    "denials": stats["denials"] if stats else 0,
                    "escalations": stats["escalations"] if stats else 0,
                    "refund_rate": round(refund_rate, 3),
                    "avg_confidence": round(stats["avg_confidence"] or 0, 3),
                    "first_complaint": stats["first_complaint"] if stats else None,
                    "last_complaint": stats["last_complaint"] if stats else None
                },
                "risk_tier": self._calculate_risk_tier(total, refund_rate),
                "categories": {r["categories"]: r["count"] for r in categories},
                "severities": {r["severity"]: r["count"] for r in severities},
                "fraud_history": {r["fraud_risk"]: r["count"] for r in fraud_flags},
                "recent_complaints": [dict(r) for r in recent]
            }
            
        except Exception as e:
            logger.error(f"Error getting customer history: {e}")
            return {"error": str(e)}
    
    def _calculate_risk_tier(self, total_complaints: int, refund_rate: float) -> str:
        """Calculate customer risk tier based on behavior."""
        if total_complaints == 0:
            return "normal"
        
        if refund_rate > 0.5 and total_complaints >= 5:
            return "flagged"
        elif refund_rate > 0.3:
            return "watch"
        elif refund_rate < 0.1 and total_complaints >= 10:
            return "trusted"
        elif refund_rate < 0.05 and total_complaints >= 20:
            return "vip"
        
        return "normal"
    
    def get_top_complainers(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """Get customers with most complaints."""
        try:
            conn = sqlite3.connect(self.db_path)
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            rows = conn.execute("""
                SELECT 
                    customer_id,
                    COUNT(*) as complaints,
                    SUM(CASE WHEN decision = 'refund' THEN 1 ELSE 0 END) as refunds,
                    SUM(CASE WHEN fraud_risk IN ('high', 'critical') THEN 1 ELSE 0 END) as fraud_flags
                FROM complaints 
                WHERE timestamp >= ? AND customer_id != 'anonymous'
                GROUP BY customer_id
                ORDER BY complaints DESC
                LIMIT ?
            """, (cutoff, limit)).fetchall()
            
            conn.close()
            
            return [{
                "customer_id": r[0],
                "complaints": r[1],
                "refunds": r[2],
                "refund_rate": r[2] / r[1] if r[1] > 0 else 0,
                "fraud_flags": r[3]
            } for r in rows]
            
        except Exception as e:
            logger.error(f"Error getting top complainers: {e}")
            return []
    
    def update_customer_profile(self, customer_id: str, updates: Dict):
        """Update customer profile data."""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Build update query
            set_clauses = []
            params = []
            for key, value in updates.items():
                if key in ["risk_tier", "lifetime_value", "email"]:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
            
            if set_clauses:
                params.append(customer_id)
                conn.execute(f"""
                    UPDATE customers SET {', '.join(set_clauses)}
                    WHERE customer_id = ?
                """, params)
                conn.commit()
            
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error updating customer: {e}")
            return False

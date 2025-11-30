"""
Hybrid Decision Engine - Combines policy rules with ML classification.
"""

import os
import json
import logging
import numpy as np
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class HybridEngine:
    """
    Decision engine that combines:
    1. Policy rules (checked first)
    2. ML model predictions
    3. Default escalation fallback
    """
    
    def __init__(self, rules_path: str, model_path: str):
        self.rules = self._load_rules(rules_path)
        self.model = self._load_model(model_path)
        self._ready = True
    
    def _load_rules(self, path: str) -> List[Dict]:
        """Load policy rules from JSON file."""
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    rules = data.get("rules", data) if isinstance(data, dict) else data
                    logger.info(f"Loaded {len(rules)} rules from {path}")
                    return rules
        except Exception as e:
            logger.error(f"Error loading rules: {e}")
        return []
    
    def _load_model(self, path: str):
        """Load ML model from pickle file."""
        try:
            if os.path.exists(path):
                import joblib
                model = joblib.load(path)
                logger.info(f"Loaded ML model from {path}")
                return model
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
        return None
    
    def is_ready(self) -> bool:
        return self._ready
    
    def predict(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a decision on a complaint case.
        
        Priority:
        1. Check policy rules
        2. Use ML model
        3. Default to escalate
        """
        # Try policy rules first
        rule_result = self._apply_rules(case)
        if rule_result:
            return rule_result
        
        # Try ML model
        if self.model:
            ml_result = self._apply_ml(case)
            if ml_result:
                return ml_result
        
        # Default fallback
        return {
            "decision": "escalate",
            "confidence": 0.5,
            "source": "system",
            "reason": "No matching rule or model prediction - escalating for review",
            "rule_id": None,
            "category": case.get("order_status", "unknown")
        }
    
    def _apply_rules(self, case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check case against policy rules."""
        for rule in self.rules:
            if self._rule_matches(rule, case):
                logger.info(f"Rule matched: {rule.get('id')}")
                return {
                    "decision": rule.get("decision", "escalate"),
                    "confidence": rule.get("confidence", 0.85),
                    "source": "policy",
                    "reason": rule.get("reason", "Policy rule applied"),
                    "rule_id": rule.get("id"),
                    "category": rule.get("category", case.get("order_status"))
                }
        return None
    
    def _rule_matches(self, rule: Dict, case: Dict) -> bool:
        """Check if a rule matches the case."""
        conditions = rule.get("conditions", {})
        
        for field, expected in conditions.items():
            actual = case.get(field)
            
            # Handle different comparison types
            if isinstance(expected, dict):
                op = expected.get("op", "eq")
                val = expected.get("value")
                
                if op == "eq" and actual != val:
                    return False
                elif op == "ne" and actual == val:
                    return False
                elif op == "gt" and not (actual is not None and actual > val):
                    return False
                elif op == "gte" and not (actual is not None and actual >= val):
                    return False
                elif op == "lt" and not (actual is not None and actual < val):
                    return False
                elif op == "lte" and not (actual is not None and actual <= val):
                    return False
                elif op == "in" and actual not in val:
                    return False
                elif op == "contains" and val not in str(actual):
                    return False
            else:
                # Simple equality check
                if actual != expected:
                    return False
        
        return True
    
    def _apply_ml(self, case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Apply ML model to case."""
        try:
            import pandas as pd
            
            # Prepare features
            features = pd.DataFrame([{
                "order_status": case.get("order_status", "unknown"),
                "refund_history_30d": int(case.get("refund_history_30d", 0)),
                "handoff_photo": bool(case.get("handoff_photo", False)),
                "courier_rating": float(case.get("courier_rating", 4.5)),
            }])
            
            # Get prediction
            prediction = self.model.predict(features)[0]
            probabilities = self.model.predict_proba(features)[0]
            confidence = float(max(probabilities))
            
            logger.info(f"ML prediction: {prediction} ({confidence:.0%})")
            
            return {
                "decision": prediction,
                "confidence": confidence,
                "source": "ml",
                "reason": f"ML classification ({confidence:.0%} confidence)",
                "rule_id": None,
                "category": case.get("order_status", "unknown")
            }
            
        except Exception as e:
            logger.error(f"ML prediction error: {e}")
            return None
    
    def explain(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Provide explainable reasoning for a decision.
        """
        result = self.predict(case)
        
        explanation = {
            "decision": result["decision"],
            "factors": [],
            "confidence_breakdown": {}
        }
        
        # Add factor explanations
        if case.get("refund_history_30d", 0) >= 3:
            explanation["factors"].append({
                "factor": "High refund history",
                "value": case["refund_history_30d"],
                "impact": "negative",
                "description": "Multiple refund requests in last 30 days"
            })
        
        if not case.get("handoff_photo"):
            explanation["factors"].append({
                "factor": "No delivery photo",
                "value": False,
                "impact": "positive" if case.get("order_status") == "missing_delivery" else "neutral",
                "description": "No proof of delivery available"
            })
        
        if case.get("courier_rating", 5) < 4.0:
            explanation["factors"].append({
                "factor": "Low courier rating",
                "value": case["courier_rating"],
                "impact": "positive",
                "description": "Courier has below-average rating"
            })
        
        return explanation

import json, os
from typing import Dict, Any, Optional
import joblib

class HybridEngine:
    def __init__(self, rules_path: str, model_path: str):
        self.rules_path = rules_path
        self.model_path = model_path
        self.rules = self._load_rules(rules_path)
        self.model = self._load_model(model_path)

    def _load_rules(self, path: str):
        if not os.path.exists(path):
            return {"version":"1.0","rules":[]}
        with open(path,"r",encoding="utf-8") as f:
            return json.load(f)

    def _load_model(self, path: str):
        try:
            if os.path.exists(path):
                return joblib.load(path)
        except Exception:
            pass
        return None

    def _match(self, case: Dict[str, Any], cond: Dict[str, Any]) -> bool:
        for k,v in cond.items():
            if isinstance(v, bool):
                if bool(case.get(k)) != v: return False
            elif isinstance(v, (int,float,str)) and not (isinstance(v,str) and v[:1] in "><"):
                if str(case.get(k)) != str(v): return False
        for k,v in cond.items():
            if isinstance(v,str) and v.startswith((">=","<=","<",">") ):
                try:
                    lhs = float(case.get(k,0))
                    op  = v[:2] if v[:2] in (">=","<=") else v[0]
                    rhs = float(v[2:]) if op in (">=","<=") else float(v[1:])
                    if   op == ">=" and not (lhs >= rhs): return False
                    elif op == "<=" and not (lhs <= rhs): return False
                    elif op == ">"  and not (lhs >  rhs): return False
                    elif op == "<"  and not (lhs <  rhs): return False
                except Exception:
                    return False
        return True

    def _policy_decide(self, case: Dict[str,Any]) -> Optional[Dict[str,Any]]:
        for r in self.rules.get("rules",[]):
            if self._match(case, r.get("if", {})):
                return {
                    "decision": r["then"]["decision"],
                    "reason":   r["then"]["reason"],
                    "source":   "policy",
                    "confidence": r.get("confidence", 0.75),
                    "rule_id":  r.get("id"),
                    "category": r["then"].get("category")
                }
        return None

    def _ml_decide(self, case: Dict[str,Any]) -> Optional[Dict[str,Any]]:
        if self.model is None:
            return None
        try:
            X = [{
                "order_status": case.get("order_status"),
                "refund_history_30d": int(case.get("refund_history_30d",0)),
                "handoff_photo": bool(case.get("handoff_photo",False)),
                "courier_rating": float(case.get("courier_rating",4.7)),
            }]
            proba = self.model.predict_proba(X)[0]
            import numpy as np
            pred_idx = int(np.argmax(proba))
            classes = list(self.model.classes_)
            decision = classes[pred_idx]
            return {
                "decision": decision,
                "confidence": float(proba[pred_idx]),
                "reason": "ML pipeline prediction",
                "source": "ml",
                "rule_id": None,
                "category": None
            }
        except Exception as e:
            return {"decision": "escalate", "confidence": 0.4,
                    "reason": f"ML error: {e}", "source":"system"}

    def predict(self, case: Dict[str,Any]) -> Dict[str,Any]:
        pol = self._policy_decide(case)
        if pol: return pol
        ml = self._ml_decide(case)
        if ml: return ml
        return {"decision":"escalate","confidence":0.4,"reason":"No ML model present; escalate.","source":"system"}

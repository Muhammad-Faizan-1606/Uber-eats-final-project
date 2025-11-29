import os, hmac
from functools import wraps
from datetime import datetime
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, Response
from core.hybrid_engine import HybridEngine
from core.audit import Audit
from core.audit_reader import query_audit, export_csv_rows, compute_stats
from core.mailer import maybe_send_decision_email
from dotenv import load_dotenv
load_dotenv()


RULES_PATH = os.getenv("RULES_PATH", "policies/policy_rules_base.json")
MODEL_PATH = os.getenv("MODEL_PATH", "models/refund_classifier.pkl")
DB_PATH    = os.getenv("DB_PATH", "audit.db")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key  = os.getenv("FLASK_SECRET_KEY", "dev-change-this")

ADMIN_USER      = os.getenv("ADMIN_USER", "Admin")
ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD", "admin123")

engine = HybridEngine(RULES_PATH, MODEL_PATH)
audit  = Audit(DB_PATH)

def _coerce(d: dict) -> dict:
    return {
        "order_id": str(d.get("order_id","")).strip(),
        "order_status": str(d.get("order_status","")).strip().lower().replace(" ","_").replace("-", "_"),
        "refund_history_30d": int(d.get("refund_history_30d",0)),
        "handoff_photo": str(d.get("handoff_photo","")).lower() in ("1","true","yes","y","t"),
        "courier_rating": float(d.get("courier_rating",4.7)),
        "email": (d.get("email") or "").strip(),
    }

def admin_required(fn):
    @wraps(fn)
    def _wrap(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return _wrap

@app.get("/api/health/")
def health():
    return jsonify({"status": "ok"}), 200

@app.post("/api/decide/")
def decide():
    data = request.get_json(silent=True) or {}
    required = {"order_id","order_status","refund_history_30d","handoff_photo","courier_rating"}
    if not required.issubset(data.keys()):
        return jsonify({"error": f"missing fields: {list(required - set(data.keys()))}"}), 400
    case = _coerce(data)
    out = engine.predict(case)
    audit.log(case["order_id"], out, case)
    if case.get("email"):
        maybe_send_decision_email(case.get("email"), case, out)
    if out.get("source") == "system" and "No ML model" in (out.get("reason") or ""):
        out["reason"] += f" (looked for: {MODEL_PATH})"
    return jsonify(out), 200

@app.post("/api/decide")
def decide_alias():
    return decide()

@app.get("/api/audit/")
@admin_required
def api_audit_list():
    page = int(request.args.get("page", "1"))
    page_size = int(request.args.get("page_size", "50"))
    items, total = query_audit(DB_PATH, page=page, page_size=page_size)
    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size})

@app.get("/api/audit/stats")
@admin_required
def api_audit_stats():
    days = int(request.args.get("days", "14"))
    return jsonify(compute_stats(DB_PATH, days=days))

@app.get("/api/audit/export.csv")
@admin_required
def api_audit_export_csv():
    rows = export_csv_rows(DB_PATH)
    def gen():
        yield "id,ts,order_id,decision,source,confidence,rule_id,category,reason,case_json\n"
        for r in rows:
            def esc(x):
                if x is None: return ""
                s = str(x).replace('"','""')
                return f'"{s}"'
            yield ",".join([
                esc(r["id"]), esc(r["ts"]), esc(r["order_id"]),
                esc(r["decision"]), esc(r["source"]), esc(r["confidence"]),
                esc(r["rule_id"]), esc(r["category"]), esc(r["reason"]),
                esc(r["case_json"]),
            ]) + "\n"
    fname = f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(gen(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})

@app.get("/admin/login")
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_home"))
    next_url = request.args.get("next") or url_for("admin_home")
    return render_template("admin_login.html", next_url=next_url, error=None)

@app.post("/admin/login")
def admin_login_post():
    user = (request.form.get("username") or "").strip()
    pw   = (request.form.get("password") or "").strip()
    next_url = request.form.get("next_url") or url_for("admin_home")
    import hmac
    ok_user = hmac.compare_digest(user, ADMIN_USER)
    ok_pass = hmac.compare_digest(pw, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        return render_template("admin_login.html", next_url=next_url, error="Invalid credentials")
    session["is_admin"] = True
    session["admin_user"] = user
    return redirect(next_url)

@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.get("/")
def ui_home():
    return render_template("index.html")

@app.get("/audit")
@admin_required
def ui_audit():
    return render_template("audit.html")

@app.get("/admin")
@admin_required
def admin_home():
    return render_template("admin.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

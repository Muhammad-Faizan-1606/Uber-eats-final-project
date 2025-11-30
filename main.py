"""
Uber Eats Complaint AI - Enterprise Complaint Management System
Full-featured complaint classification with ML, fraud detection, and admin operations.
"""

import os
import re
import json
import csv
import uuid
import hashlib
import logging
from functools import wraps
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Optional, Dict, Any, List, Tuple
from io import StringIO

from flask import (
    Flask, jsonify, request, render_template, redirect,
    url_for, session, Response, send_from_directory, g
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import core modules
from core.hybrid_engine import HybridEngine
from core.intelligence import ComplaintIntelligence
from core.audit import AuditDB
from core.mailer import send_decision_email, test_smtp_connection
from core.fraud_detector import FraudDetector
from core.customer_history import CustomerHistory

# ============================================================================
# Configuration
# ============================================================================

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('logs', exist_ok=True)

# Initialize components
RULES_PATH = os.getenv("RULES_PATH", "policies/policy_rules_base.json")
MODEL_PATH = os.getenv("MODEL_PATH", "models/complaint_classifier.pkl")
DB_PATH = os.getenv("DB_PATH", "data/complaints.db")

engine = HybridEngine(RULES_PATH, MODEL_PATH)
intelligence = ComplaintIntelligence()
audit_db = AuditDB(DB_PATH)
fraud_detector = FraudDetector(DB_PATH)
customer_history = CustomerHistory(DB_PATH)

# User roles
USERS = {
    os.getenv("ADMIN_USER", "admin"): {
        "password": os.getenv("ADMIN_PASSWORD", "admin123"),
        "role": "admin",
        "name": "Administrator"
    },
    "agent": {
        "password": "agent123",
        "role": "agent",
        "name": "Support Agent"
    },
    "viewer": {
        "password": "viewer123",
        "role": "viewer",
        "name": "Read Only User"
    }
}

# SLA Configuration (in minutes)
SLA_CONFIG = {
    "critical": 30,
    "high": 120,
    "medium": 480,
    "low": 1440
}

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'webp'}

# ============================================================================
# Sample Data
# ============================================================================

DUMMY_ORDERS = [
    {"id": "UE-10021", "restaurant": "McDonald's", "title": "Big Mac Meal", "total": 12.99, "status": "Delivered", "time_ago": "32 min", "date": "2025-01-15"},
    {"id": "UE-10022", "restaurant": "Domino's Pizza", "title": "Large Pepperoni", "total": 18.50, "status": "Delivered", "time_ago": "2 hours", "date": "2025-01-15"},
    {"id": "UE-10023", "restaurant": "KFC", "title": "Zinger Box Meal", "total": 14.99, "status": "Delivered", "time_ago": "Yesterday", "date": "2025-01-14"},
    {"id": "UE-10024", "restaurant": "Subway", "title": "Footlong Italian BMT", "total": 11.49, "status": "Delivered", "time_ago": "2 days ago", "date": "2025-01-13"},
]

COMPLAINT_TEMPLATES = [
    {"id": "late", "title": "Late Delivery", "icon": "🕐", "template": "My order arrived {delay} late. The estimated delivery time was {eta} but it arrived at {actual}."},
    {"id": "missing", "title": "Missing Items", "icon": "📦", "template": "Items missing from my order: {items}. I paid for these items but they were not in my delivery bag."},
    {"id": "wrong", "title": "Wrong Order", "icon": "❌", "template": "I received the wrong order. I ordered {ordered} but received {received} instead."},
    {"id": "quality", "title": "Food Quality", "icon": "🍔", "template": "The food quality was poor: {issue}. The food was {condition} when it arrived."},
    {"id": "spilled", "title": "Spilled/Damaged", "icon": "💧", "template": "My order was damaged during delivery: {description}. {items} were affected."},
    {"id": "driver", "title": "Driver Issue", "icon": "🚗", "template": "I had an issue with the delivery driver: {issue}."},
]

# ============================================================================
# Decorators & Middleware
# ============================================================================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.is_json:
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                if request.is_json:
                    return jsonify({"error": "Insufficient permissions"}), 403
                return render_template("error.html", message="You don't have permission to access this page."), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def rate_limit(max_requests=100, window=60):
    """Simple in-memory rate limiter"""
    requests = defaultdict(list)
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            ip = request.remote_addr
            now = datetime.now()
            # Clean old requests
            requests[ip] = [t for t in requests[ip] if (now - t).seconds < window]
            if len(requests[ip]) >= max_requests:
                return jsonify({"error": "Rate limit exceeded"}), 429
            requests[ip].append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator

@app.before_request
def before_request():
    g.start_time = datetime.now()
    g.request_id = str(uuid.uuid4())[:8]

@app.after_request
def after_request(response):
    if hasattr(g, 'start_time'):
        duration = (datetime.now() - g.start_time).total_seconds() * 1000
        logger.info(f"[{g.request_id}] {request.method} {request.path} - {response.status_code} ({duration:.1f}ms)")
    return response

# ============================================================================
# Authentication Routes
# ============================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        if username in USERS and USERS[username]["password"] == password:
            session["logged_in"] = True
            session["username"] = username
            session["role"] = USERS[username]["role"]
            session["name"] = USERS[username]["name"]
            logger.info(f"User logged in: {username} ({USERS[username]['role']})")
            
            next_url = request.args.get("next", url_for("admin_dashboard"))
            return redirect(next_url)
        else:
            error = "Invalid username or password"
            logger.warning(f"Failed login attempt: {username}")
    
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    username = session.get("username", "unknown")
    session.clear()
    logger.info(f"User logged out: {username}")
    return redirect(url_for("login"))

# ============================================================================
# Public Routes
# ============================================================================

@app.route("/")
def home():
    return render_template("index.html", 
                          orders=DUMMY_ORDERS, 
                          templates=COMPLAINT_TEMPLATES)

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "version": "3.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "engine": engine.is_ready(),
            "database": audit_db.is_healthy(),
            "fraud_detector": True
        }
    })

# ============================================================================
# Core Complaint API
# ============================================================================

@app.route("/api/classify", methods=["POST"])
@rate_limit(max_requests=60, window=60)
def classify_complaint():
    """
    Main complaint classification endpoint.
    Accepts structured data or free text.
    """
    data = request.get_json(silent=True) or {}
    
    # Extract fields
    order_id = data.get("order_id", f"COMP-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    complaint_text = data.get("complaint_text", "")
    issue_type = data.get("issue_type", "")
    customer_email = data.get("email", "")
    customer_id = data.get("customer_id", hashlib.md5(customer_email.encode()).hexdigest()[:12] if customer_email else "anonymous")
    
    # Structured fields (handle None explicitly)
    handoff_photo = str(data.get("handoff_photo") or "unknown").lower() in ("true", "yes", "1")
    refund_history = int(data.get("refund_history_30d") or 0)
    courier_rating = float(data.get("courier_rating") or 4.5)
    order_value = float(data.get("order_value") or 15.0)
    
    # Evidence files
    evidence_files = data.get("evidence_files", [])
    
    # Build case for engine
    case = {
        "order_id": order_id,
        "order_status": issue_type or intelligence.detect_issue_type(complaint_text),
        "complaint_text": complaint_text,
        "refund_history_30d": refund_history,
        "handoff_photo": handoff_photo,
        "courier_rating": courier_rating,
        "order_value": order_value,
        "customer_id": customer_id,
        "evidence_count": len(evidence_files)
    }
    
    # Get base decision from engine
    result = engine.predict(case)
    
    # Enhance with intelligence layer
    intelligence_result = intelligence.analyze(complaint_text, case)
    
    # Fraud detection
    fraud_result = fraud_detector.assess(customer_id, case)
    
    # Customer history
    history = customer_history.get_summary(customer_id)
    
    # Calculate severity and SLA
    severity = intelligence_result.get("severity", "medium")
    sla_minutes = SLA_CONFIG.get(severity, 480)
    sla_deadline = datetime.now() + timedelta(minutes=sla_minutes)
    
    # Build comprehensive response
    response = {
        "complaint_id": str(uuid.uuid4())[:12].upper(),
        "order_id": order_id,
        "timestamp": datetime.utcnow().isoformat(),
        
        # Decision
        "decision": result.get("decision", "escalate"),
        "confidence": result.get("confidence", 0.5),
        "source": result.get("source", "system"),
        "rule_id": result.get("rule_id"),
        
        # Intelligence
        "severity": severity,
        "sla_deadline": sla_deadline.isoformat(),
        "sla_minutes": sla_minutes,
        "categories": intelligence_result.get("categories", [case["order_status"]]),
        "root_cause": intelligence_result.get("root_cause", "unknown"),
        "sentiment": intelligence_result.get("sentiment", "neutral"),
        "explanation": intelligence_result.get("explanation", result.get("reason", "")),
        "suggested_actions": intelligence_result.get("suggested_actions", []),
        
        # Fraud
        "fraud_risk": fraud_result.get("risk_level", "low"),
        "fraud_score": fraud_result.get("score", 0.0),
        "fraud_flags": fraud_result.get("flags", []),
        
        # Customer context
        "customer_history": {
            "total_complaints": history.get("total_complaints", 0),
            "recent_complaints": history.get("recent_complaints", 0),
            "refund_rate": history.get("refund_rate", 0.0),
            "lifetime_value": history.get("lifetime_value", 0.0),
            "risk_tier": history.get("risk_tier", "normal")
        },
        
        # Agent copilot
        "agent_summary": _build_agent_summary(case, result, intelligence_result, fraud_result),
        "response_templates": _get_response_templates(result.get("decision"), severity),
        "alternative_decisions": _get_alternatives(result, case)
    }
    
    # Log to audit
    audit_db.log_complaint(response, case)
    
    # Send email if provided
    email_sent = False
    if customer_email:
        email_sent = send_decision_email(
            to_email=customer_email,
            order_id=order_id,
            decision=response["decision"],
            confidence=response["confidence"],
            reason=response["explanation"],
            category=response["categories"][0] if response["categories"] else "general",
            source=response["source"],
            severity=severity,
            sla_deadline=sla_deadline.strftime("%Y-%m-%d %H:%M")
        )
    response["email_sent"] = email_sent
    
    return jsonify(response), 200


def _build_agent_summary(case, result, intelligence, fraud):
    """Build structured summary for agent copilot."""
    return {
        "headline": f"{result.get('decision', 'escalate').upper()} - {intelligence.get('severity', 'medium').upper()} priority",
        "key_facts": [
            f"Order: {case.get('order_id')}",
            f"Issue: {case.get('order_status', 'unknown').replace('_', ' ').title()}",
            f"Refund history: {case.get('refund_history_30d', 0)} in 30 days",
            f"Photo proof: {'Yes' if case.get('handoff_photo') else 'No'}",
            f"Fraud risk: {fraud.get('risk_level', 'low').upper()}"
        ],
        "recommendation": result.get("reason", "Review case manually"),
        "confidence_level": "High" if result.get("confidence", 0) > 0.8 else "Medium" if result.get("confidence", 0) > 0.6 else "Low"
    }


def _get_response_templates(decision, severity):
    """Get one-click response templates for agents."""
    templates = {
        "refund": [
            {"id": "full_refund", "title": "Full Refund", "text": "We apologize for the inconvenience. A full refund of ${amount} has been processed to your original payment method. Please allow 3-5 business days for it to appear."},
            {"id": "partial_refund", "title": "Partial Refund", "text": "We've processed a partial refund of ${amount} for the affected items. The amount will appear in your account within 3-5 business days."},
            {"id": "credit", "title": "Account Credit", "text": "We've added ${amount} in Uber Eats credit to your account as compensation. This credit will be automatically applied to your next order."}
        ],
        "deny": [
            {"id": "policy", "title": "Policy Explanation", "text": "After reviewing your request, we're unable to process a refund at this time as the order was delivered as described. If you have additional information, please share it with us."},
            {"id": "abuse_warning", "title": "Account Warning", "text": "We've noticed multiple refund requests from your account recently. Please note that misuse of our refund policy may result in account restrictions."}
        ],
        "escalate": [
            {"id": "escalate_ack", "title": "Escalation Acknowledgment", "text": "Your case has been escalated to our senior support team for further review. You'll receive an update within 24-48 hours."},
            {"id": "more_info", "title": "Request More Info", "text": "To help us resolve your issue, could you please provide additional details or photos of the problem?"}
        ]
    }
    return templates.get(decision, templates["escalate"])


def _get_alternatives(result, case):
    """Get alternative decision options with reasoning."""
    decision = result.get("decision", "escalate")
    alternatives = []
    
    if decision != "refund":
        alternatives.append({
            "decision": "refund",
            "reason": "Customer has good history and issue seems legitimate",
            "confidence_impact": -0.1
        })
    if decision != "deny":
        alternatives.append({
            "decision": "deny",
            "reason": "Pattern suggests potential abuse or policy violation",
            "confidence_impact": -0.15
        })
    if decision != "escalate":
        alternatives.append({
            "decision": "escalate",
            "reason": "Case complexity requires human review",
            "confidence_impact": 0
        })
    
    return alternatives

# ============================================================================
# Batch Processing
# ============================================================================

@app.route("/api/batch/classify", methods=["POST"])
@login_required
@role_required("admin", "agent")
def batch_classify():
    """Process CSV file of complaints."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        return jsonify({"error": "Invalid file. Please upload a CSV."}), 400
    
    try:
        content = file.read().decode('utf-8')
        reader = csv.DictReader(StringIO(content))
        
        results = []
        for row in reader:
            case = {
                "order_id": row.get("order_id", ""),
                "order_status": row.get("issue_type", row.get("order_status", "")),
                "complaint_text": row.get("complaint_text", row.get("text", "")),
                "refund_history_30d": int(row.get("refund_history_30d", 0)),
                "handoff_photo": row.get("handoff_photo", "").lower() in ("true", "yes", "1"),
                "courier_rating": float(row.get("courier_rating", 4.5)),
            }
            
            result = engine.predict(case)
            intel = intelligence.analyze(case.get("complaint_text", ""), case)
            
            results.append({
                "order_id": case["order_id"],
                "decision": result.get("decision"),
                "confidence": result.get("confidence"),
                "severity": intel.get("severity"),
                "categories": intel.get("categories", [])
            })
        
        return jsonify({
            "processed": len(results),
            "results": results
        }), 200
        
    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# Evidence Upload
# ============================================================================

@app.route("/api/upload/evidence", methods=["POST"])
@rate_limit(max_requests=20, window=60)
def upload_evidence():
    """Upload evidence files for a complaint."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    complaint_id = request.form.get("complaint_id", str(uuid.uuid4())[:12])
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400
    
    # Generate secure filename
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{complaint_id}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    file.save(filepath)
    logger.info(f"Evidence uploaded: {filename} for complaint {complaint_id}")
    
    return jsonify({
        "success": True,
        "filename": filename,
        "url": f"/static/uploads/{filename}",
        "complaint_id": complaint_id
    }), 200

# ============================================================================
# Feedback & Retraining
# ============================================================================

@app.route("/api/feedback", methods=["POST"])
@login_required
def submit_feedback():
    """Submit human feedback on a decision."""
    data = request.get_json(silent=True) or {}
    
    complaint_id = data.get("complaint_id")
    original_decision = data.get("original_decision")
    corrected_decision = data.get("corrected_decision")
    feedback_reason = data.get("reason", "")
    agent = session.get("username", "unknown")
    
    if not all([complaint_id, original_decision, corrected_decision]):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Log feedback
    audit_db.log_feedback({
        "complaint_id": complaint_id,
        "original_decision": original_decision,
        "corrected_decision": corrected_decision,
        "reason": feedback_reason,
        "agent": agent,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    logger.info(f"Feedback logged: {complaint_id} {original_decision} -> {corrected_decision} by {agent}")
    
    return jsonify({"success": True, "message": "Feedback recorded"}), 200

# ============================================================================
# Analytics API
# ============================================================================

@app.route("/api/analytics/overview", methods=["GET"])
@login_required
def analytics_overview():
    """Get dashboard overview stats."""
    days = int(request.args.get("days", 30))
    stats = audit_db.get_stats(days=days)
    
    return jsonify({
        "total_complaints": stats.get("total", 0),
        "by_decision": stats.get("by_decision", {}),
        "by_severity": stats.get("by_severity", {}),
        "by_category": stats.get("by_category", {}),
        "by_source": stats.get("by_source", {}),
        "avg_confidence": stats.get("avg_confidence", 0),
        "fraud_flagged": stats.get("fraud_flagged", 0),
        "sla_compliance": stats.get("sla_compliance", 0),
        "trend": stats.get("daily_trend", [])
    }), 200

@app.route("/api/analytics/timeseries", methods=["GET"])
@login_required
def analytics_timeseries():
    """Get time-series data for charts."""
    days = int(request.args.get("days", 30))
    metric = request.args.get("metric", "volume")  # volume, decision, severity, fraud
    
    data = audit_db.get_timeseries(days=days, metric=metric)
    return jsonify(data), 200

@app.route("/api/analytics/root-causes", methods=["GET"])
@login_required
def analytics_root_causes():
    """Get root cause analysis data."""
    days = int(request.args.get("days", 30))
    data = audit_db.get_root_cause_stats(days=days)
    return jsonify(data), 200

# ============================================================================
# Customer History
# ============================================================================

@app.route("/api/customer/<customer_id>", methods=["GET"])
@login_required
def get_customer(customer_id):
    """Get customer complaint history."""
    history = customer_history.get_full_history(customer_id)
    return jsonify(history), 200

@app.route("/api/customer/<customer_id>/complaints", methods=["GET"])
@login_required
def get_customer_complaints(customer_id):
    """Get customer's complaint list."""
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    
    complaints = audit_db.get_customer_complaints(customer_id, page=page, limit=limit)
    return jsonify(complaints), 200

# ============================================================================
# Admin Routes
# ============================================================================

@app.route("/admin")
@login_required
def admin_dashboard():
    """Main admin dashboard."""
    stats = audit_db.get_stats(days=30)
    recent = audit_db.get_recent(limit=10)
    
    return render_template("admin/dashboard.html", 
                          stats=stats, 
                          recent=recent,
                          sla_config=SLA_CONFIG)

@app.route("/admin/complaints")
@login_required
def admin_complaints():
    """Complaint management page."""
    page = int(request.args.get("page", 1))
    status = request.args.get("status", "all")
    severity = request.args.get("severity", "all")
    
    complaints = audit_db.get_complaints(page=page, status=status, severity=severity)
    return render_template("admin/complaints.html", complaints=complaints)

@app.route("/admin/analytics")
@login_required
def admin_analytics():
    """Analytics dashboard."""
    return render_template("admin/analytics.html")

@app.route("/admin/customers")
@login_required
def admin_customers():
    """Customer management page."""
    return render_template("admin/customers.html")

@app.route("/admin/batch")
@login_required
@role_required("admin", "agent")
def admin_batch():
    """Batch processing page."""
    return render_template("admin/batch.html")

@app.route("/admin/settings")
@login_required
@role_required("admin")
def admin_settings():
    """System settings page."""
    smtp_status = test_smtp_connection()
    return render_template("admin/settings.html", smtp_status=smtp_status)

# ============================================================================
# SMTP Test
# ============================================================================

@app.route("/api/smtp/test", methods=["POST"])
@login_required
@role_required("admin")
def api_test_smtp():
    """Test SMTP connection and optionally send test email."""
    data = request.get_json(silent=True) or {}
    test_email = data.get("email", "")
    
    result = test_smtp_connection()
    
    if test_email and result.get("connection_ok"):
        sent = send_decision_email(
            to_email=test_email,
            order_id="TEST-001",
            decision="refund",
            confidence=0.95,
            reason="This is a test email from Uber Eats Complaint AI",
            category="test",
            source="test",
            severity="low",
            sla_deadline=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        result["test_email_sent"] = sent
    
    return jsonify(result), 200

# ============================================================================
# Rewrite Complaint
# ============================================================================

@app.route("/api/rewrite", methods=["POST"])
@rate_limit(max_requests=30, window=60)
def rewrite_complaint():
    """Rewrite complaint to be more clear and professional."""
    data = request.get_json(silent=True) or {}
    original = data.get("text", "")
    
    if not original:
        return jsonify({"error": "No text provided"}), 400
    
    rewritten = intelligence.rewrite_complaint(original)
    
    return jsonify({
        "original": original,
        "rewritten": rewritten,
        "improvements": intelligence.get_improvements(original, rewritten)
    }), 200

# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    if request.is_json:
        return jsonify({"error": "Not found"}), 404
    return render_template("error.html", message="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    if request.is_json:
        return jsonify({"error": "Internal server error"}), 500
    return render_template("error.html", message="Something went wrong"), 500

# ============================================================================
# Main
# ============================================================================

# Original startup block removed to ensure port 8081 is used at the end of file

# ============================================================================
# Additional API Endpoints
# ============================================================================

@app.route("/api/audit/", methods=["GET"])
def api_audit_list():
    """Get paginated audit list."""
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    status = request.args.get("status", "all")
    severity = request.args.get("severity", "all")
    
    data = audit_db.get_complaints(page=page, limit=limit, status=status, severity=severity)
    return jsonify(data), 200


@app.route("/api/audit/export.csv", methods=["GET"])
def api_audit_export():
    """Export audit data as CSV."""
    complaints = audit_db.get_complaints(page=1, limit=10000)
    
    output = "complaint_id,order_id,decision,severity,confidence,timestamp\n"
    for c in complaints.get("items", []):
        output += f"{c.get('complaint_id','')},{c.get('order_id','')},{c.get('decision','')},{c.get('severity','')},{c.get('confidence','')},{c.get('timestamp','')}\n"
    
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=complaints_export.csv"})


@app.route("/api/customers/top", methods=["GET"])
def api_top_customers():
    """Get top complaining customers."""
    days = int(request.args.get("days", 30))
    limit = int(request.args.get("limit", 20))
    
    customers = customer_history.get_top_complainers(days=days, limit=limit)
    return jsonify({"customers": customers}), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8081))
    logger.info(f'Starting Uber Eats Complaint AI v3.0 on port {port}')
    app.run(host='0.0.0.0', port=port, debug=False)

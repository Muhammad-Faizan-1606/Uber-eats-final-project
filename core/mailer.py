"""
Email Notification Module - Sends HTML emails with decision summaries.
"""

import os
import ssl
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

def _get_smtp_config():
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "465")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASS", ""),
        "from_email": os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")),
        "from_name": os.getenv("SMTP_FROM_NAME", "Uber Eats Support"),
        "timeout": int(os.getenv("SMTP_TIMEOUT", "30")),
    }

def _get_decision_style(decision):
    styles = {
        "refund": {"bg": "#dcfce7", "border": "#22c55e", "text": "#166534", "icon": "✅", "title": "Refund Approved", "message": "Your refund request has been approved."},
        "deny": {"bg": "#fee2e2", "border": "#ef4444", "text": "#991b1b", "icon": "❌", "title": "Request Declined", "message": "We are unable to process a refund for this order."},
        "escalate": {"bg": "#fef3c7", "border": "#f59e0b", "text": "#92400e", "icon": "⏳", "title": "Under Review", "message": "Your case has been escalated for manual review."}
    }
    return styles.get(decision.lower(), styles["escalate"])

def send_decision_email(to_email, order_id, decision, confidence, reason, category, source, severity="medium", sla_deadline="", rule_id=None, additional_info=""):
    if not to_email:
        return False
    config = _get_smtp_config()
    if not config["user"] or not config["password"]:
        logger.warning("SMTP not configured")
        return False
    try:
        style = _get_decision_style(decision)
        timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        category_display = category.replace("_", " ").title() if category else "General"
        confidence_pct = f"{confidence * 100:.0f}%" if confidence else "N/A"
        
        html = f'''<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,sans-serif;background:#f3f4f6">
<table width="100%" style="padding:40px 20px"><tr><td align="center">
<table width="600" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)">
<tr><td style="background:linear-gradient(135deg,#000,#1f2937);padding:40px;text-align:center">
<h1 style="margin:0;font-size:32px"><span style="color:#fff">Uber</span><span style="color:#22c55e">Eats</span></h1>
<p style="margin:10px 0 0;color:#9ca3af;font-size:14px">Complaint Resolution Center</p></td></tr>
<tr><td style="padding:40px">
<table width="100%" style="background:{style['bg']};border:2px solid {style['border']};border-radius:16px">
<tr><td style="padding:32px;text-align:center">
<div style="font-size:56px;margin-bottom:16px">{style['icon']}</div>
<h2 style="margin:0;font-size:28px;color:{style['text']}">{style['title']}</h2>
<p style="margin:12px 0 0;color:{style['text']}">{style['message']}</p></td></tr></table></td></tr>
<tr><td style="padding:0 40px 32px">
<h3 style="margin:0 0 20px;border-bottom:2px solid #e5e7eb;padding-bottom:12px">📋 Details</h3>
<table width="100%" style="font-size:15px">
<tr><td style="padding:14px 0;border-bottom:1px solid #f3f4f6;color:#6b7280">Order ID</td><td style="padding:14px 0;border-bottom:1px solid #f3f4f6;font-weight:600">{order_id}</td></tr>
<tr><td style="padding:14px 0;border-bottom:1px solid #f3f4f6;color:#6b7280">Category</td><td style="padding:14px 0;border-bottom:1px solid #f3f4f6;font-weight:600">{category_display}</td></tr>
<tr><td style="padding:14px 0;border-bottom:1px solid #f3f4f6;color:#6b7280">Priority</td><td style="padding:14px 0;border-bottom:1px solid #f3f4f6"><span style="background:{'#dc2626' if severity=='critical' else '#ea580c' if severity=='high' else '#ca8a04' if severity=='medium' else '#16a34a'};color:white;padding:4px 12px;border-radius:12px;font-size:12px">{severity.upper()}</span></td></tr>
<tr><td style="padding:14px 0;border-bottom:1px solid #f3f4f6;color:#6b7280">Confidence</td><td style="padding:14px 0;border-bottom:1px solid #f3f4f6;font-weight:600">{confidence_pct}</td></tr>
<tr><td style="padding:14px 0;color:#6b7280">Processed</td><td style="padding:14px 0">{timestamp}</td></tr></table></td></tr>
<tr><td style="padding:0 40px 32px">
<div style="background:#f8fafc;border-radius:12px;padding:20px;border-left:4px solid {style['border']}">
<h4 style="margin:0 0 10px;font-size:14px;color:#374151">💬 Reason</h4>
<p style="margin:0;font-size:15px;color:#4b5563;line-height:1.7">{reason}</p></div></td></tr>
<tr><td style="background:#f9fafb;padding:32px 40px;border-top:1px solid #e5e7eb">
<p style="margin:0;font-size:12px;color:#6b7280">Reference: {order_id} • {timestamp}</p></td></tr>
</table></td></tr></table></body></html>'''

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Uber Eats: {decision.upper()} - Order {order_id}"
        msg["From"] = f"{config['from_name']} <{config['from_email']}>"
        msg["To"] = to_email
        msg.attach(MIMEText(f"Decision: {decision.upper()}\nOrder: {order_id}\nReason: {reason}", "plain"))
        msg.attach(MIMEText(html, "html"))
        
        if config["port"] == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(config["host"], config["port"], context=ctx, timeout=config["timeout"]) as s:
                s.login(config["user"], config["password"])
                s.sendmail(config["from_email"], to_email, msg.as_string())
        else:
            with smtplib.SMTP(config["host"], config["port"], timeout=config["timeout"]) as s:
                s.starttls()
                s.login(config["user"], config["password"])
                s.sendmail(config["from_email"], to_email, msg.as_string())
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

def test_smtp_connection():
    config = _get_smtp_config()
    result = {"configured": bool(config["user"] and config["password"]), "host": config["host"], "port": config["port"], "connection_ok": False, "error": None}
    if not result["configured"]:
        result["error"] = "SMTP not configured"
        return result
    try:
        if config["port"] == 465:
            with smtplib.SMTP_SSL(config["host"], config["port"], context=ssl.create_default_context(), timeout=10) as s:
                s.login(config["user"], config["password"])
                result["connection_ok"] = True
        else:
            with smtplib.SMTP(config["host"], config["port"], timeout=10) as s:
                s.starttls()
                s.login(config["user"], config["password"])
                result["connection_ok"] = True
    except Exception as e:
        result["error"] = str(e)
    return result

# core/mailer.py
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Dict, Any, Optional
from html import escape

def _smtp_config():
    """Read SMTP config from env with sane Gmail defaults."""
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))  # 465=SSL, 587=STARTTLS
    user = os.getenv("SMTP_USER")              # your Gmail address
    pwd  = os.getenv("SMTP_PASS")              # your Gmail App Password
    from_email = os.getenv("SMTP_FROM", user or "")
    from_name  = os.getenv("SMTP_FROM_NAME", "Support Decisions")
    reply_to   = os.getenv("SMTP_REPLY_TO", from_email)
    timeout    = float(os.getenv("SMTP_TIMEOUT", "15"))
    return {
        "host": host, "port": port, "user": user, "pwd": pwd,
        "from_email": from_email, "from_name": from_name,
        "reply_to": reply_to, "timeout": timeout
    }

def _send_email_raw(to_email: str, subject: str, text: str, html: Optional[str] = None):
    cfg = _smtp_config()
    if not cfg["user"] or not cfg["pwd"] or not cfg["from_email"]:
        raise RuntimeError("SMTP not configured. Set SMTP_USER, SMTP_PASS, and SMTP_FROM.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f'{cfg["from_name"]} <{cfg["from_email"]}>'
    msg["To"] = to_email
    if cfg["reply_to"]:
        msg["Reply-To"] = cfg["reply_to"]

    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    # SSL if 465, otherwise STARTTLS
    if cfg["port"] == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=cfg["timeout"]) as smtp:
            smtp.login(cfg["user"], cfg["pwd"])
            smtp.send_message(msg)
    else:
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=cfg["timeout"]) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.login(cfg["user"], cfg["pwd"])
            smtp.send_message(msg)

def _format_email(case: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, str]:
    order_id = str(case.get("order_id", "Unknown"))
    decision = (result.get("decision") or "").upper()
    subject = f"Your order {order_id}: Decision — {decision}"

    lines = [
        f"Order ID: {order_id}",
        f"Decision: {result.get('decision')}",
        f"Confidence: {result.get('confidence')}",
        f"Source: {result.get('source')}",
        "",
        f"Reason: {result.get('reason')}",
        "",
        "— This is an automated message."
    ]
    text = "\n".join(lines)

    # Precompute/escape reason and replace newlines safely (no backslashes in f-expression)
    reason_raw = str(result.get("reason") or "")
    reason_html = escape(reason_raw).replace("\n", "<br>")

    html = (
        "<div style=\"font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;line-height:1.5;\">"
        f"  <h2 style=\"margin:0 0 8px;\">Order {escape(order_id)}</h2>"
        f"  <p style=\"margin:0 0 6px;\"><b>Decision:</b> {escape(str(result.get('decision')))}</p>"
        f"  <p style=\"margin:0 0 6px;\"><b>Confidence:</b> {escape(str(result.get('confidence')))}</p>"
        f"  <p style=\"margin:0 0 12px;\"><b>Source:</b> {escape(str(result.get('source')))}</p>"
        "  <div style=\"padding:10px 12px;border:1px solid #e5e7eb;border-radius:10px;background:#f9fafb;\">"
        "    <b>Reason</b><br>" + reason_html +
        "  </div>"
        "  <p style=\"color:#6b7280;font-size:12px;margin-top:12px;\">This is an automated message.</p>"
        "</div>"
    )

    return {"subject": subject, "text": text, "html": html}

def maybe_send_decision_email(to_email: str, case: Dict[str, Any], result: Dict[str, Any]) -> bool:
    """
    Best-effort: send to customer if valid-looking email.
    Never raise, so the API response never breaks because of email.
    """
    if not to_email or "@" not in to_email or "." not in to_email.split("@")[-1]:
        return False
    try:
        payload = _format_email(case, result)
        _send_email_raw(to_email, payload["subject"], payload["text"], payload["html"])
        return True
    except Exception as e:
        # Log to console; you can wire this to your audit if you want.
        print(f"[mailer] failed to send to {to_email}: {e}")
        return False

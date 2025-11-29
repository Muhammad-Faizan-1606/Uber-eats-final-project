===============================
🧠 UBER INTELLIGENT COMPLAINT FILTERING MODEL
===============================

This project is a Flask-based intelligent decision system that classifies and logs complaints (e.g., for Uber Eats style refund/deny/escalate decisions). 
It includes:
- ML + Policy Hybrid Engine
- Admin Dashboard with authentication
- Email system to notify customers of decisions (via Gmail SMTP)
- Audit logs with export & analytics

-----------------------------------
📁 PROJECT STRUCTURE
-----------------------------------

agentic_clean_full_ui/
│
├── main.py                # Main Flask app (UI + API)
├── .env                   # Environment file (see below)
│
├── core/
│   ├── audit.py
│   ├── audit_reader.py
│   ├── hybrid_engine.py
│   ├── retrain.py
│   └── mailer.py
│
├── models/                # Trained model files
├── policies/              # Rule-based policies
├── templates/             # Frontend HTML (UI + Admin)
├── static/                # CSS, JS, icons
└── requirements.txt       # Dependencies

-----------------------------------
⚙️ REQUIREMENTS
-----------------------------------

✅ Python 3.10 or higher  
✅ pip installed  
✅ Internet connection (for email SMTP)

-----------------------------------
📦 1. INSTALL DEPENDENCIES
-----------------------------------

🪟 Windows (PowerShell)
-----------------------
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install python-dotenv

🍎 macOS / Linux
----------------
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install python-dotenv

-----------------------------------
🔐 2. SETUP YOUR .ENV FILE
-----------------------------------

Create a new file named `.env` in the same directory as `main.py`.

Paste this inside:

FLASK_SECRET_KEY=dev-change-this

SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=jhn0854@gmail.com (your email)
SMTP_PASS=YOUR_16_CHAR_APP_PASSWORD
SMTP_FROM=jhn0854@gmail.com
SMTP_FROM_NAME=Uber Eats Support Team
SMTP_REPLY_TO=jhn0854@gmail.com
SMTP_TIMEOUT=20

ADMIN_USER=Admin
ADMIN_PASSWORD=admin123

⚠️ Replace `YOUR_16_CHAR_APP_PASSWORD` with your Gmail **App Password** (not your normal Gmail password).  
To generate one:  
https://myaccount.google.com/apppasswords

-----------------------------------
🧠 3. TRAIN / UPDATE MODEL
-----------------------------------

To train your refund classifier:
python core/retrain.py

This generates:
models/refund_classifier.pkl

-----------------------------------
🚀 4. RUN THE APPLICATION
-----------------------------------

Windows:
.\.venv\Scripts\Activate.ps1
python .\main.py

macOS/Linux:
source .venv/bin/activate
python3 main.py

Now open your browser:
http://127.0.0.1:8080

✅ User Page → Decision interface  
✅ Admin Login → http://127.0.0.1:8080/admin/login  
(Login: Admin / admin123)  
✅ Dashboard → Reports, charts, CSV exports

-----------------------------------
📧 5. EMAIL SYSTEM SETUP
-----------------------------------

Your app automatically emails the customer once a decision is made **if they entered their email**.

If you see:
[mailer] failed to send: SMTP not configured
→ It means `.env` was not loaded.  
Ensure you have this line at the **top** of `main.py`:

from dotenv import load_dotenv
load_dotenv()

Test it:
Visit → http://127.0.0.1:8080/api/debug/email

You should see:
{
  "user": "jhn0854@gmail.com",
  "pass_set": true,
  "from": "jhn0854@gmail.com"
}

If `pass_set` is `false`, fix your `.env` location or reload terminal.

-----------------------------------
📊 6. ADMIN DASHBOARD
-----------------------------------

Admin panel:  
→ http://127.0.0.1:8080/admin/login

Use:
Username: Admin
Password: admin123

Features:
- View latest 50 complaints
- Export audit logs as CSV
- View policy decisions & ML confidence stats

-----------------------------------
🧰 7. DEBUGGING EMAILS
-----------------------------------

If you aren’t receiving any emails:

Enable debug mode:
export SMTP_DEBUG=1     # macOS/Linux
$env:SMTP_DEBUG=1       # Windows

Then re-run:
python main.py

You’ll see SMTP logs in terminal.  
Check Gmail “Sent” and “Spam” folders.

-----------------------------------
✅ 8. QUICK TESTS
-----------------------------------

Health check  
→ http://127.0.0.1:8080/api/health/

Decision API test  
curl -X POST http://127.0.0.1:8080/api/decide/ \
  -H "Content-Type: application/json" \
  -d '{"order_id":"ORD123","order_status":"missing_delivery","refund_history_30d":0,"handoff_photo":true,"courier_rating":4.8,"email":"test@example.com"}'

You’ll get a JSON decision response and an email (if configured correctly).

-----------------------------------
🧠 9. COMMON ISSUES
-----------------------------------

❌ “SMTP not configured” → `.env` not loading or missing keys.  
✅ Fix: Add `load_dotenv()` at the top of `main.py`.

❌ “Invalid credentials” → Wrong Gmail App Password.  
✅ Fix: Regenerate your Gmail App Password and update `.env`.

❌ “Connection refused” → Port 465 blocked.  
✅ Fix: Try `SMTP_PORT=587` instead.

❌ No emails received → Check spam, Gmail “Promotions” tab, or `SMTP_DEBUG=1` logs.

-----------------------------------
👨‍💻 10. SUPPORT COMMANDS
-----------------------------------

Export logs:
sqlite3 audit.db "select * from audit limit 5;"

Export CSV from Admin Dashboard:
→ http://127.0.0.1:8080/api/audit/export.csv

Recreate model:
python core/retrain.py

-----------------------------------
🚧 NOTES
-----------------------------------
- Do NOT upload `.env` or model files to GitHub.
- Gmail must have 2FA enabled for App Passwords to work.
- Works on macOS, Windows, and Linux.

-----------------------------------
🧠 AUTHOR
-----------------------------------
Developed by Muhammad Faizan 
Agentic Complaint AI — 2025
"""

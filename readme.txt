===============================
INTELLIGENT COMPLAINT FILTERING MODEL
===============================

This is a Flask-based intelligent decision system that classifies and logs complaints (e.g., for Uber Eats style refund/deny/escalate decisions).

Features:
- ML + Policy Hybrid Engine
- Admin Dashboard with authentication
- Email system to notify customers via Gmail SMTP
- Audit logs with export & analytics

-----------------------------------
PROJECT STRUCTURE
-----------------------------------

agentic_clean_full_ui/
│
├── main.py                # Main Flask app (UI + API)
├── .env                   # Environment variables
│
├── core/
│   ├── audit.py
│   ├── audit_reader.py
│   ├── hybrid_engine.py
│   ├── retrain.py
│   └── mailer.py
│
├── models/                # Trained model files
├── policies/              # Policy JSONs
├── templates/             # Frontend HTML (UI + Admin)
├── static/                # CSS, JS, icons
└── requirements.txt       # Dependencies

-----------------------------------
REQUIREMENTS
-----------------------------------

- Python 3.10 or higher
- pip installed
- Internet connection (for email)

-----------------------------------
1. INSTALL DEPENDENCIES
-----------------------------------

WINDOWS (PowerShell)
--------------------
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install python-dotenv

MACOS / LINUX
--------------
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install python-dotenv

-----------------------------------
2. SETUP YOUR .ENV FILE
-----------------------------------

Create a `.env` file next to main.py and paste:

FLASK_SECRET_KEY=dev-change-this

SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=jhn0854@gmail.com
SMTP_PASS=YOUR_16_CHAR_APP_PASSWORD
SMTP_FROM=jhn0854@gmail.com
SMTP_FROM_NAME=Uber Eats Support Team
SMTP_REPLY_TO=jhn0854@gmail.com
SMTP_TIMEOUT=20

ADMIN_USER=Admin
ADMIN_PASSWORD=admin123

Replace YOUR_16_CHAR_APP_PASSWORD with your Gmail App Password.
Generate it from:
https://myaccount.google.com/apppasswords

-----------------------------------
3. TRAIN / UPDATE MODEL
-----------------------------------

python core/retrain.py
→ Creates models/refund_classifier.pkl

-----------------------------------
4. RUN THE APPLICATION
-----------------------------------

WINDOWS
--------
.\.venv\Scripts\Activate.ps1
python .\main.py

MACOS / LINUX
--------------
source .venv/bin/activate
python3 main.py

Open:
http://127.0.0.1:8080

User Page → Decision Interface  
Admin Login → http://127.0.0.1:8080/admin/login  
(Login: Admin / admin123)  
Dashboard → Reports, charts, CSV exports

-----------------------------------
5. EMAIL SYSTEM SETUP
-----------------------------------

Emails are automatically sent if the customer enters their email.

If you see:
[mailer] failed to send: SMTP not configured  
→ Your .env wasn’t loaded.

At the top of main.py, ensure you have:
from dotenv import load_dotenv
load_dotenv()

Test:
http://127.0.0.1:8080/api/debug/email

You should see:
{ "user": "jhn0854@gmail.com", "pass_set": true }

If pass_set = false, check your .env file path.

-----------------------------------
6. ADMIN DASHBOARD
-----------------------------------

Admin panel:
http://127.0.0.1:8080/admin/login

Username: Admin  
Password: admin123

Features:
- View recent complaints
- Export audit logs as CSV
- View decision confidence + stats

-----------------------------------
7. DEBUGGING EMAILS
-----------------------------------

If you’re not receiving emails:

Enable debug mode:
export SMTP_DEBUG=1        (macOS/Linux)
$env:SMTP_DEBUG=1          (Windows)

Then re-run:
python main.py

Check your Gmail “Sent” and “Spam” folders.

-----------------------------------
8. QUICK TESTS
-----------------------------------

Health check:
http://127.0.0.1:8080/api/health/

Decision API test:
curl -X POST http://127.0.0.1:8080/api/decide/ \
  -H "Content-Type: application/json" \
  -d '{"order_id":"ORD123","order_status":"missing_delivery","refund_history_30d":0,"handoff_photo":true,"courier_rating":4.8,"email":"test@example.com"}'

You’ll get a JSON decision response and email.

-----------------------------------
9. COMMON ISSUES
-----------------------------------

“SMTP not configured” → .env not loaded.  
Fix: Add load_dotenv() in main.py.

“Invalid credentials” → Wrong Gmail App Password.  
Fix: Regenerate your Gmail app password.

“Connection refused” → Port 465 blocked.  
Fix: Try SMTP_PORT=587.

“No emails” → Check spam or set SMTP_DEBUG=1.

-----------------------------------
10. SUPPORT COMMANDS
-----------------------------------

View logs:
sqlite3 audit.db "select * from audit limit 5;"

Export CSV:
http://127.0.0.1:8080/api/audit/export.csv

Recreate model:
python core/retrain.py

-----------------------------------
NOTES
-----------------------------------

- Never upload `.env` to GitHub.
- Gmail 2FA required for App Passwords.
- Works on Windows, macOS, and Linux.

-----------------------------------
AUTHOR
-----------------------------------

Developed by Farasat Anees  
Agentic Complaint AI — 2025

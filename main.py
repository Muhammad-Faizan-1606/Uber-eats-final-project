from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# ----------------------------------------------------
# TODO: wire in YOUR real model / pipeline here
# ----------------------------------------------------
# Example skeleton – replace with your actual loading code.
#
# from joblib import load
# model = load("models/complaint_model.joblib")
# vectorizer = load("models/vectorizer.joblib")
#
# def classify_complaint(text: str) -> dict:
#     X = vectorizer.transform([text])
#     y_proba = model.predict_proba(X)[0]
#     y_pred = model.classes_[y_proba.argmax()]
#     confidence = float(y_proba.max())
#     return {
#         "label": y_pred,
#         "confidence": confidence,
#         "category": "Delivery issue"  # or map label → readable category
#     }

def classify_complaint(text: str) -> dict:
    """
    Dummy implementation so the app runs.
    Replace this with your actual model call.
    """
    lowered = text.lower()

    if "cold" in lowered or "bad" in lowered or "stale" in lowered:
        label = "food_quality"
        category = "Food Quality"
    elif "late" in lowered or "delay" in lowered or "time" in lowered:
        label = "late_delivery"
        category = "Delivery Delay"
    elif "missing" in lowered or "item" in lowered:
        label = "missing_items"
        category = "Missing Items"
    elif "refund" in lowered or "money" in lowered or "charge" in lowered:
        label = "refund_billing"
        category = "Payment / Refund"
    else:
        label = "other"
        category = "Other"

    return {
        "label": label,
        "category": category,
        "confidence": 0.85  # placeholder
    }


def build_agent_reply(text: str, analysis: dict) -> str:
    """
    Turn the model output into a human-style agent response.
    You can customise tone here.
    """
    category = analysis.get("category", "your issue")
    label = analysis.get("label", "other")
    confidence = analysis.get("confidence", 0.0)

    base = f"I've reviewed your complaint and it looks like a *{category}* issue."
    extra = ""

    if label == "late_delivery":
        extra = (
            " I’m sorry your order was delayed. I’ve tagged this as a **delivery delay** "
            "and it should be reviewed for ETA mismatch and potential compensation."
        )
    elif label == "food_quality":
        extra = (
            " That’s not the experience we want you to have with your food. "
            "I’ve flagged this as a **food quality** issue for the restaurant and support team."
        )
    elif label == "missing_items":
        extra = (
            " I’ve marked this as a **missing items** issue so support can verify your order "
            "and process a refund or re-delivery where possible."
        )
    elif label == "refund_billing":
        extra = (
            " I’ve tagged this as a **payment / refund** concern so billing support can look into "
            "charges and possible reversal."
        )
    else:
        extra = (
            " I’ve marked this as a **general support** issue so a human agent can review it in detail."
        )

    conf_text = f" (model confidence: {confidence:.0%})"
    return base + extra + conf_text


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/agent", methods=["POST"])
def agent_endpoint():
    """
    Agent-style endpoint: accepts JSON {message: "..."} and
    returns {reply: "...", analysis: {...}}.
    """
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "No message provided"}), 400

    analysis = classify_complaint(message)
    reply = build_agent_reply(message, analysis)

    return jsonify({
        "reply": reply,
        "analysis": analysis
    })


@app.route("/healthz")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    # Dev only – in production we use gunicorn
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)

"""
Complaint Intelligence Module
Handles severity detection, root cause analysis, multi-issue detection,
sentiment analysis, and complaint rewriting.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class ComplaintIntelligence:
    """
    Advanced complaint analysis:
    - Severity classification
    - Root cause detection
    - Multi-issue handling
    - Sentiment analysis
    - Complaint rewriting
    """
    
    # Issue type keywords
    ISSUE_PATTERNS = {
        "late_delivery": [
            r"\blate\b", r"\bdelay(ed)?\b", r"\bslow\b", r"\bwait(ed|ing)?\b",
            r"took (too )?long", r"hours? late", r"minutes? late"
        ],
        "missing_delivery": [
            r"\bmissing\b", r"never (arrived|came|received|got)",
            r"didn'?t (get|receive|arrive)", r"not delivered", r"no delivery"
        ],
        "wrong_item": [
            r"\bwrong\b", r"\bincorrect\b", r"different (item|order|food)",
            r"not what i ordered", r"someone else'?s"
        ],
        "damaged_item": [
            r"\bdamaged\b", r"\bspilled\b", r"\bleaked\b", r"\bcold\b",
            r"\bsoggy\b", r"\bstale\b", r"poor quality", r"\bbroken\b"
        ],
        "driver_issue": [
            r"\brude\b", r"\bunprofessional\b", r"driver (was|behavior)",
            r"\baggressive\b", r"delivery person"
        ],
        "overcharge": [
            r"\bovercharge[d]?\b", r"charged (too )?much", r"wrong (price|amount)",
            r"double charge", r"\brefund\b.*\bmoney\b"
        ]
    }
    
    # Severity indicators
    SEVERITY_KEYWORDS = {
        "critical": [
            r"food poisoning", r"\ballergic\b", r"\bhospital\b", r"\bsick\b",
            r"\billness\b", r"\bemergency\b", r"health (issue|problem|risk)",
            r"\bcontaminated\b", r"\bunsafe\b"
        ],
        "high": [
            r"completely (wrong|missing|ruined)", r"entire order",
            r"never received", r"\bfraud\b", r"all (items|food)",
            r"very (angry|upset|frustrated)", r"\bunacceptable\b"
        ],
        "medium": [
            r"some items", r"partially", r"\blate\b", r"\bcold\b",
            r"(30|45|60) minutes", r"\bdisappointed\b"
        ],
        "low": [
            r"minor", r"small issue", r"slightly", r"just wanted to let you know",
            r"not a big deal", r"feedback"
        ]
    }
    
    # Root cause patterns
    ROOT_CAUSES = {
        "restaurant_error": [
            r"restaurant", r"kitchen", r"chef", r"forgot to",
            r"didn'?t include", r"packed wrong", r"preparation"
        ],
        "delivery_error": [
            r"driver", r"courier", r"delivery person", r"dropped",
            r"threw", r"left (at|in) wrong", r"handed to someone"
        ],
        "logistics_delay": [
            r"traffic", r"(too )?far", r"multiple (orders|deliveries)",
            r"batched", r"long route", r"waited at restaurant"
        ],
        "app_issue": [
            r"app (crash|error|bug)", r"couldn'?t (track|contact)",
            r"wrong address", r"map", r"gps"
        ],
        "packaging_failure": [
            r"packaging", r"container", r"bag (broke|ripped|torn)",
            r"not sealed", r"lid (off|loose)", r"leaked"
        ],
        "weather_related": [
            r"rain", r"storm", r"weather", r"snow", r"heat"
        ]
    }
    
    # Sentiment words
    SENTIMENT_WORDS = {
        "very_negative": [
            "terrible", "awful", "horrible", "disgusting", "worst",
            "unacceptable", "furious", "outraged", "scam", "theft"
        ],
        "negative": [
            "bad", "poor", "disappointed", "frustrated", "upset",
            "annoyed", "unhappy", "wrong", "missing", "late"
        ],
        "neutral": [
            "okay", "fine", "average", "expected", "understand"
        ],
        "positive": [
            "good", "thank", "appreciate", "helpful", "resolved"
        ]
    }
    
    def analyze(self, text: str, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive complaint analysis.
        """
        text_lower = text.lower() if text else ""
        
        return {
            "severity": self.detect_severity(text_lower, case),
            "categories": self.detect_issues(text_lower),
            "root_cause": self.detect_root_cause(text_lower),
            "sentiment": self.analyze_sentiment(text_lower),
            "is_multi_issue": len(self.detect_issues(text_lower)) > 1,
            "explanation": self.generate_explanation(text_lower, case),
            "suggested_actions": self.suggest_actions(text_lower, case)
        }
    
    def detect_issue_type(self, text: str) -> str:
        """Detect primary issue type from text."""
        issues = self.detect_issues(text.lower())
        return issues[0] if issues else "general_complaint"
    
    def detect_issues(self, text: str) -> List[str]:
        """Detect all issue types in complaint (multi-label)."""
        detected = []
        
        for issue_type, patterns in self.ISSUE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    if issue_type not in detected:
                        detected.append(issue_type)
                    break
        
        return detected if detected else ["general_complaint"]
    
    def detect_severity(self, text: str, case: Dict = None) -> str:
        """
        Detect complaint severity: critical, high, medium, low
        """
        case = case or {}
        
        # Check for critical keywords first
        for pattern in self.SEVERITY_KEYWORDS["critical"]:
            if re.search(pattern, text, re.IGNORECASE):
                return "critical"
        
        # Calculate severity score
        score = 50  # Base score (medium)
        
        # High severity indicators
        for pattern in self.SEVERITY_KEYWORDS["high"]:
            if re.search(pattern, text, re.IGNORECASE):
                score += 20
        
        # Medium indicators
        for pattern in self.SEVERITY_KEYWORDS["medium"]:
            if re.search(pattern, text, re.IGNORECASE):
                score += 5
        
        # Low indicators (reduce score)
        for pattern in self.SEVERITY_KEYWORDS["low"]:
            if re.search(pattern, text, re.IGNORECASE):
                score -= 15
        
        # Case-based adjustments
        order_value = case.get("order_value", 15)
        if order_value > 50:
            score += 10
        elif order_value > 30:
            score += 5
        
        if case.get("order_status") == "missing_delivery":
            score += 15
        
        # Customer history impact
        refund_history = case.get("refund_history_30d", 0)
        if refund_history == 0:
            score += 5  # First-time complainer gets priority
        
        # Map score to severity
        if score >= 80:
            return "high"
        elif score >= 50:
            return "medium"
        else:
            return "low"
    
    def detect_root_cause(self, text: str) -> str:
        """Identify the root cause of the issue."""
        cause_scores = Counter()
        
        for cause, patterns in self.ROOT_CAUSES.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    cause_scores[cause] += 1
        
        if cause_scores:
            return cause_scores.most_common(1)[0][0]
        return "unknown"
    
    def analyze_sentiment(self, text: str) -> str:
        """Analyze customer sentiment."""
        scores = {"very_negative": 0, "negative": 0, "neutral": 0, "positive": 0}
        
        words = text.lower().split()
        for word in words:
            for sentiment, keywords in self.SENTIMENT_WORDS.items():
                if word in keywords:
                    scores[sentiment] += 1
        
        # Determine dominant sentiment
        if scores["very_negative"] > 0:
            return "very_negative"
        elif scores["negative"] > scores["positive"]:
            return "negative"
        elif scores["positive"] > scores["negative"]:
            return "positive"
        return "neutral"
    
    def generate_explanation(self, text: str, case: Dict) -> str:
        """Generate human-readable explanation of the analysis."""
        issues = self.detect_issues(text)
        severity = self.detect_severity(text, case)
        root_cause = self.detect_root_cause(text)
        
        issue_str = ", ".join([i.replace("_", " ") for i in issues])
        
        explanation = f"This is a {severity} severity complaint about {issue_str}."
        
        if root_cause != "unknown":
            explanation += f" The root cause appears to be {root_cause.replace('_', ' ')}."
        
        if case.get("refund_history_30d", 0) >= 3:
            explanation += " Note: Customer has multiple recent refund requests."
        
        if not case.get("handoff_photo") and "missing" in text:
            explanation += " No delivery photo is available to verify delivery."
        
        return explanation
    
    def suggest_actions(self, text: str, case: Dict) -> List[Dict[str, str]]:
        """Suggest actions based on complaint analysis."""
        actions = []
        issues = self.detect_issues(text)
        severity = self.detect_severity(text, case)
        
        if severity == "critical":
            actions.append({
                "action": "immediate_escalation",
                "priority": "urgent",
                "description": "Escalate to supervisor immediately due to health/safety concern"
            })
        
        if "missing_delivery" in issues and not case.get("handoff_photo"):
            actions.append({
                "action": "request_photo_proof",
                "priority": "high",
                "description": "Request delivery photo from driver or check GPS logs"
            })
        
        if case.get("refund_history_30d", 0) >= 3:
            actions.append({
                "action": "review_account",
                "priority": "medium",
                "description": "Review customer account for potential abuse pattern"
            })
        
        if "driver_issue" in issues:
            actions.append({
                "action": "driver_feedback",
                "priority": "medium",
                "description": "Flag delivery partner for quality review"
            })
        
        if "restaurant_error" in self.detect_root_cause(text):
            actions.append({
                "action": "restaurant_feedback",
                "priority": "low",
                "description": "Send feedback to restaurant partner"
            })
        
        return actions
    
    def rewrite_complaint(self, text: str) -> str:
        """
        Rewrite complaint to be clearer and more professional.
        """
        if not text:
            return ""
        
        # Extract key information
        issues = self.detect_issues(text.lower())
        
        # Build structured complaint
        issue_descriptions = {
            "late_delivery": "My order was delivered later than the estimated time",
            "missing_delivery": "I did not receive my order",
            "wrong_item": "I received incorrect items in my order",
            "damaged_item": "Items in my order were damaged or of poor quality",
            "driver_issue": "I experienced an issue with the delivery driver",
            "overcharge": "I was charged incorrectly for my order",
            "general_complaint": "I have an issue with my order"
        }
        
        main_issue = issue_descriptions.get(issues[0], issue_descriptions["general_complaint"])
        
        # Create professional version
        rewritten = f"{main_issue}. "
        
        # Add specifics if found in original
        if re.search(r'\d+\s*(minutes?|hours?|mins?|hrs?)', text, re.IGNORECASE):
            time_match = re.search(r'(\d+)\s*(minutes?|hours?|mins?|hrs?)', text, re.IGNORECASE)
            if time_match:
                rewritten += f"The delay was approximately {time_match.group(1)} {time_match.group(2)}. "
        
        # Add request
        rewritten += "I would appreciate your assistance in resolving this matter."
        
        return rewritten
    
    def get_improvements(self, original: str, rewritten: str) -> List[str]:
        """Get list of improvements made to complaint."""
        improvements = []
        
        if len(rewritten) < len(original):
            improvements.append("Made more concise")
        
        if original.isupper():
            improvements.append("Removed all-caps (less aggressive)")
        
        # Check for profanity removal (simplified)
        bad_words = ["damn", "hell", "crap", "stupid"]
        if any(word in original.lower() for word in bad_words):
            improvements.append("Removed informal language")
        
        improvements.append("Added professional tone")
        improvements.append("Structured with clear issue statement")
        
        return improvements

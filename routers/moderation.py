from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List
from database import get_database
from utils import get_current_user
import re

router = APIRouter()

# Placeholder for AI moderation
# In production, integrate with OpenAI or Hugging Face models

TOXIC_KEYWORDS = [
    "spam", "scam", "hack", "cheat", "bot", "sell", "buy",
    # Add more keywords as needed
]

RULE_VIOLATIONS = {
    "spam": "Excessive repetitive messages",
    "toxicity": "Toxic or hateful content",
    "inappropriate": "Inappropriate content",
    "advertising": "Unauthorized advertising",
}

@router.post("/analyze")
async def analyze_message(
    message: str,
    current_user: dict = Depends(get_current_user)
):
    """Analyze message for violations"""
    
    analysis = {
        "message": message,
        "is_toxic": False,
        "violations": [],
        "confidence": 0.0,
        "suggested_action": "none",
    }
    
    # Simple keyword-based detection (replace with actual AI model)
    message_lower = message.lower()
    
    # Check for spam patterns
    if len(set(message_lower.split())) < len(message_lower.split()) * 0.3:
        analysis["violations"].append("spam")
        analysis["confidence"] = 0.7
    
    # Check for toxic keywords
    toxic_count = sum(1 for keyword in TOXIC_KEYWORDS if keyword in message_lower)
    if toxic_count > 0:
        analysis["is_toxic"] = True
        analysis["violations"].append("toxicity")
        analysis["confidence"] = min(toxic_count * 0.3, 0.95)
    
    # Check for links (potential advertising)
    if re.search(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message):
        analysis["violations"].append("advertising")
        analysis["confidence"] = max(analysis["confidence"], 0.6)
    
    # Suggest action
    if analysis["confidence"] > 0.8:
        analysis["suggested_action"] = "ban"
    elif analysis["confidence"] > 0.5:
        analysis["suggested_action"] = "warn"
    elif analysis["confidence"] > 0.3:
        analysis["suggested_action"] = "flag"
    
    return analysis

@router.post("/warnings/{user_id}")
async def add_warning(
    user_id: str,
    reason: str,
    admin: dict = Depends(get_current_user)
):
    """Add a warning to a user"""
    db = get_database()
    
    warning = {
        "user_id": user_id,
        "reason": reason,
        "issued_by": admin["discord_id"],
        "timestamp": datetime.utcnow(),
    }
    
    await db.warnings.insert_one(warning)
    
    # Log activity
    await db.activity.insert_one({
        "user_id": user_id,
        "action": "warning_issued",
        "metadata": {"reason": reason, "issued_by": admin["discord_id"]},
        "timestamp": datetime.utcnow()
    })
    
    return {"message": "Warning issued"}

@router.get("/warnings/{user_id}")
async def get_warnings(user_id: str):
    """Get warnings for a user"""
    db = get_database()
    
    warnings = await db.warnings.find({"user_id": user_id}).sort(
        "timestamp", -1
    ).to_list(100)
    
    for warning in warnings:
        warning["_id"] = str(warning["_id"])
    
    return {"warnings": warnings}

@router.post("/analyze-application")
async def analyze_application(application_data: dict):
    """Analyze application quality with AI"""
    
    score = 50.0
    factors = []
    
    # Check answer length and quality
    if "reason" in application_data:
        reason = application_data["reason"]
        if len(reason) > 200:
            score += 20
            factors.append("Detailed reason provided")
        elif len(reason) > 100:
            score += 10
            factors.append("Good reason length")
        else:
            factors.append("Reason could be more detailed")
    
    # Check experience
    if "experience" in application_data:
        experience = application_data["experience"]
        if len(experience) > 100:
            score += 15
            factors.append("Good experience description")
    
    # Check gameplay hours
    if "gameplay_hours" in application_data:
        hours = int(application_data.get("gameplay_hours", 0))
        if hours > 500:
            score += 15
            factors.append("Extensive gameplay experience")
        elif hours > 100:
            score += 10
            factors.append("Good gameplay experience")
    
    # Check for spam or low-effort responses
    if any(len(str(v)) < 20 for k, v in application_data.items() if k not in ["gameplay_hours"]):
        score -= 20
        factors.append("Some answers seem too short")
    
    return {
        "score": min(score, 100.0),
        "factors": factors,
        "recommendation": "approve" if score >= 70 else "review" if score >= 50 else "reject"
    }

from datetime import datetime

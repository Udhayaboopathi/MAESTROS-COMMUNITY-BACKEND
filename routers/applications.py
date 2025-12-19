from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from datetime import datetime
from database import get_database
from utils import get_current_user, require_manager_or_admin, get_discord_bot, DiscordRoles
from models import ApplicationCreate, Application
import discord
import os
import re

router = APIRouter()

# Discord Configuration
ACCEPTED_LOG_CHANNEL_ID = int(os.getenv('ACCEPTED_LOG_CHANNEL_ID', '1231990220589629441'))
REJECTED_LOG_CHANNEL_ID = int(os.getenv('REJECTED_LOG_CHANNEL_ID', '1231990340353917008'))
COMMUNITY_MEMBER_ROLE_ID = DiscordRoles.MEMBER_ROLE_ID
APPLICATION_PENDING_ROLE_ID = DiscordRoles.APPLICATION_PENDING_ROLE_ID
SERVER_INVITE_LINK = os.getenv('SERVER_INVITE_LINK', 'https://discord.gg/Xdac4KHXfC')

async def send_dm(bot, user_id: str, embed: discord.Embed) -> bool:
    """Send DM to user, return success status"""
    try:
        user = await bot.bot.fetch_user(int(user_id))
        await user.send(embed=embed)
        return True
    except:
        return False

# Validation schema for application fields
REQUIRED_FIELDS = {
    "personal": ["in_game_name", "date_of_birth", "country"],
    "gaming": ["primary_game", "gameplay_hours", "rank", "experience"],
    "motivation": ["reason", "contribution", "availability"]
}

def validate_application_data(data: dict) -> dict:
    """
    Validate application data server-side
    Returns validation result with errors if any
    """
    errors = {}
    
    # Check all required fields
    all_required = REQUIRED_FIELDS["personal"] + REQUIRED_FIELDS["gaming"] + REQUIRED_FIELDS["motivation"]
    for field in all_required:
        if field not in data or not data[field]:
            errors[field] = f"{field.replace('_', ' ').title()} is required"
    
    # Validate specific fields
    if "date_of_birth" in data:
        try:
            from datetime import datetime
            dob = datetime.fromisoformat(data["date_of_birth"].replace('Z', '+00:00'))
            today = datetime.now()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            if age < 13:
                errors["date_of_birth"] = "You must be at least 13 years old"
            elif age > 100:
                errors["date_of_birth"] = "Please enter a valid date of birth"
            
            # Store calculated age
            data["age"] = age
        except (ValueError, TypeError) as e:
            errors["date_of_birth"] = "Please enter a valid date"
    
    # Validate phone number (optional field)
    if "phone" in data and data["phone"]:
        phone = str(data["phone"]).strip()
        # Basic phone validation (allows international format)
        if len(phone) < 10 or not any(char.isdigit() for char in phone):
            errors["phone"] = "Please enter a valid phone number"
    
    if "gameplay_hours" in data:
        try:
            hours = int(data["gameplay_hours"])
            if hours < 0:
                errors["gameplay_hours"] = "Hours must be a positive number"
        except (ValueError, TypeError):
            errors["gameplay_hours"] = "Hours must be a valid number"
    
    if "availability" in data:
        try:
            availability = int(data["availability"])
            if availability < 0 or availability > 168:
                errors["availability"] = "Hours per week must be between 0 and 168"
        except (ValueError, TypeError):
            errors["availability"] = "Availability must be a valid number"
    
    # Validate text length
    if "experience" in data and len(data["experience"]) < 20:
        errors["experience"] = "Please provide at least 20 characters describing your experience"
    
    if "reason" in data and len(data["reason"]) < 30:
        errors["reason"] = "Please provide at least 30 characters explaining why you want to join"
    
    if "contribution" in data and len(data["contribution"]) < 20:
        errors["contribution"] = "Please provide at least 20 characters about your contribution"
    
    # Validate in-game name
    if "in_game_name" in data:
        ign = data["in_game_name"]
        if len(ign) < 3 or len(ign) > 20:
            errors["in_game_name"] = "In-game name must be between 3 and 20 characters"
    
    # Validate country
    if "country" in data:
        country = data["country"].strip()
        if len(country) < 2:
            errors["country"] = "Please enter a valid country"
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }

@router.post("/validate")
async def validate_application(
    application_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Validate application data without submitting"""
    validation_result = validate_application_data(application_data)
    return validation_result

@router.post("/submit")
async def submit_application(
    application_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Submit a new application with full server-side validation"""
    db = get_database()
    
    # Server-side validation (critical - never trust client)
    validation_result = validate_application_data(application_data)
    if not validation_result["valid"]:
        print(f"❌ Application validation failed for user {current_user.get('username', 'unknown')}")
        print(f"📝 Errors: {validation_result['errors']}")
        print(f"📋 Received data keys: {list(application_data.keys())}")
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed",
                "errors": validation_result["errors"]
            }
        )
    
    # Check if user already has a pending application
    existing = await db.applications.find_one({
        "user_id": current_user["discord_id"],
        "status": "pending"
    })
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have a pending application"
        )
    
    # Create application
    application = {
        "user_id": current_user["discord_id"],
        "form_type": "membership",
        "data": application_data,
        "status": "pending",
        "submitted_at": datetime.utcnow(),
    }
    
    # AI scoring (all logic server-side)
    score, analysis = await analyze_application(application_data)
    application["result_score"] = score
    application["ai_analysis"] = analysis
    
    result = await db.applications.insert_one(application)
    
    # Log activity
    await db.activity.insert_one({
        "user_id": current_user["discord_id"],
        "action": "application_submitted",
        "metadata": {
            "application_id": str(result.inserted_id),
            "score": score
        },
        "timestamp": datetime.utcnow()
    })
    
    # Award XP for submission (logic in backend)
    xp_awarded = 50
    await db.users.update_one(
        {"discord_id": current_user["discord_id"]},
        {"$inc": {"xp": xp_awarded}}
    )
    
    # Recalculate level based on new XP
    user = await db.users.find_one({"discord_id": current_user["discord_id"]})
    new_level = calculate_level(user["xp"])
    old_level = user.get("level", 0)
    
    if new_level > old_level:
        await db.users.update_one(
            {"discord_id": current_user["discord_id"]},
            {"$set": {"level": new_level}}
        )
    
    return {
        "message": "Application submitted successfully",
        "application_id": str(result.inserted_id),
        "score": score,
        "xp_awarded": xp_awarded,
        "level_up": new_level > old_level,
        "new_level": new_level
    }

@router.get("/list")
async def list_applications(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List user's applications"""
    db = get_database()
    
    query = {"user_id": current_user["discord_id"]}
    if status:
        query["status"] = status
    
    applications = await db.applications.find(query).sort(
        "submitted_at", -1
    ).to_list(100)
    
    return {"applications": applications}

@router.get("/status/{application_id}")
async def get_application_status(
    application_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get application status"""
    db = get_database()
    from bson import ObjectId
    
    try:
        application = await db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application["user_id"] != current_user["discord_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {"application": application}

def calculate_level(xp: int) -> int:
    """Calculate level from XP - ALL LOGIC SERVER-SIDE"""
    import math
    return int(math.sqrt(xp / 100))

async def analyze_application(data: dict) -> tuple[float, dict]:
    """
    AI-powered application analysis - ALL LOGIC SERVER-SIDE
    Returns a tuple of (score, detailed_analysis)
    """
    score = 0.0
    analysis = {
        "factors": {},
        "strengths": [],
        "weaknesses": [],
        "confidence": 0.0
    }
    
    # Gaming Experience Analysis (40 points)
    gameplay_hours = int(data.get("gameplay_hours", 0))
    if gameplay_hours > 1000:
        score += 40
        analysis["factors"]["gameplay_hours"] = {"score": 40, "reason": "Extensive gaming experience"}
        analysis["strengths"].append("Very experienced gamer")
    elif gameplay_hours > 500:
        score += 30
        analysis["factors"]["gameplay_hours"] = {"score": 30, "reason": "Good gaming experience"}
        analysis["strengths"].append("Experienced gamer")
    elif gameplay_hours > 100:
        score += 20
        analysis["factors"]["gameplay_hours"] = {"score": 20, "reason": "Moderate gaming experience"}
    else:
        score += 10
        analysis["factors"]["gameplay_hours"] = {"score": 10, "reason": "Limited gaming experience"}
        analysis["weaknesses"].append("Limited gaming hours")
    
    # Motivation Quality Analysis (30 points)
    reason = data.get("reason", "")
    reason_length = len(reason)
    
    # Check for quality keywords
    quality_keywords = ["competitive", "teamwork", "improve", "learn", "community", 
                       "passion", "dedicated", "skilled", "strategic", "professional"]
    keyword_matches = sum(1 for keyword in quality_keywords if keyword.lower() in reason.lower())
    
    if reason_length > 200 and keyword_matches >= 3:
        score += 30
        analysis["factors"]["motivation"] = {"score": 30, "reason": "Excellent motivation"}
        analysis["strengths"].append("Strong motivation and clear goals")
    elif reason_length > 100 and keyword_matches >= 2:
        score += 20
        analysis["factors"]["motivation"] = {"score": 20, "reason": "Good motivation"}
        analysis["strengths"].append("Good understanding of community")
    elif reason_length > 50:
        score += 10
        analysis["factors"]["motivation"] = {"score": 10, "reason": "Basic motivation"}
    else:
        score += 5
        analysis["factors"]["motivation"] = {"score": 5, "reason": "Weak motivation"}
        analysis["weaknesses"].append("Lacks detailed motivation")
    
    # Contribution Analysis (20 points)
    contribution = data.get("contribution", "")
    contribution_keywords = ["help", "teach", "mentor", "organize", "lead", 
                            "content", "stream", "coach", "guide", "support"]
    contribution_matches = sum(1 for keyword in contribution_keywords 
                              if keyword.lower() in contribution.lower())
    
    if len(contribution) > 100 and contribution_matches >= 2:
        score += 20
        analysis["factors"]["contribution"] = {"score": 20, "reason": "Valuable contributions planned"}
        analysis["strengths"].append("Ready to contribute actively")
    elif len(contribution) > 50 and contribution_matches >= 1:
        score += 15
        analysis["factors"]["contribution"] = {"score": 15, "reason": "Some contributions planned"}
    else:
        score += 5
        analysis["factors"]["contribution"] = {"score": 5, "reason": "Limited contribution clarity"}
        analysis["weaknesses"].append("Unclear contribution plans")
    
    # Availability Analysis (10 points)
    availability = int(data.get("availability", 0))
    if availability >= 20:
        score += 10
        analysis["factors"]["availability"] = {"score": 10, "reason": "High availability"}
        analysis["strengths"].append("Highly available for events")
    elif availability >= 10:
        score += 7
        analysis["factors"]["availability"] = {"score": 7, "reason": "Good availability"}
    elif availability >= 5:
        score += 4
        analysis["factors"]["availability"] = {"score": 4, "reason": "Moderate availability"}
    else:
        score += 2
        analysis["factors"]["availability"] = {"score": 2, "reason": "Low availability"}
        analysis["weaknesses"].append("Limited time availability")
    
    # Calculate confidence based on completeness
    total_length = reason_length + len(contribution) + len(data.get("experience", ""))
    if total_length > 500:
        analysis["confidence"] = 0.95
    elif total_length > 300:
        analysis["confidence"] = 0.85
    elif total_length > 150:
        analysis["confidence"] = 0.70
    else:
        analysis["confidence"] = 0.50
    
    # Final score normalization
    score = min(score, 100.0)
    analysis["final_score"] = score
    
    # Recommendation
    if score >= 80:
        analysis["recommendation"] = "Highly recommended for approval"
    elif score >= 60:
        analysis["recommendation"] = "Recommended for approval"
    elif score >= 40:
        analysis["recommendation"] = "Consider for approval with interview"
    else:
        analysis["recommendation"] = "Not recommended"
    
    return score, analysis

# === MANAGER PANEL ENDPOINTS ===

@router.get("/manager/pending")
async def get_pending_applications(
    skip: int = 0,
    limit: int = 50,
    manager: dict = Depends(require_manager_or_admin)
):
    """Get all pending applications - Manager access"""
    db = get_database()
    
    applications = await db.applications.find(
        {"status": "pending"}
    ).sort("submitted_at", -1).skip(skip).limit(limit).to_list(limit)
    
    total = await db.applications.count_documents({"status": "pending"})
    
    # Get user info for each application and flatten data
    for app in applications:
        app["_id"] = str(app["_id"])
        
        # Flatten the nested 'data' field
        if "data" in app:
            app.update(app["data"])
        
        # Rename result_score to score for frontend compatibility
        if "result_score" in app:
            app["score"] = app["result_score"]
        
        user = await db.users.find_one({"discord_id": app["user_id"]})
        if user:
            # Calculate account age from Discord snowflake ID
            discord_id = int(app["user_id"])
            discord_epoch = 1420070400000
            timestamp = ((discord_id >> 22) + discord_epoch) / 1000
            account_created = datetime.fromtimestamp(timestamp)
            
            app["user_info"] = {
                "username": user.get("username"),
                "discriminator": user.get("discriminator", "0"),
                "avatar": user.get("avatar"),
                "email": user.get("email"),
                "level": user.get("level", 1),
                "xp": user.get("xp", 0),
                "badges": user.get("badges", []),
                "guild_roles": user.get("guild_roles", []),
                "joined_at": user.get("joined_at"),
                "last_login": user.get("last_login"),
                "account_created": account_created.isoformat(),
            }
    
    return {
        "applications": applications,
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/manager/all")
async def get_all_applications_manager(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    manager: dict = Depends(require_manager_or_admin)
):
    """Get all applications with optional status filter - Manager access"""
    db = get_database()
    
    query = {}
    if status:
        query["status"] = status
    
    applications = await db.applications.find(query).sort(
        "submitted_at", -1
    ).skip(skip).limit(limit).to_list(limit)
    
    total = await db.applications.count_documents(query)
    
    # Get user info for each application and flatten data
    for app in applications:
        app["_id"] = str(app["_id"])
        
        # Flatten the nested 'data' field
        if "data" in app:
            app.update(app["data"])
        
        # Rename result_score to score for frontend compatibility
        if "result_score" in app:
            app["score"] = app["result_score"]
        
        user = await db.users.find_one({"discord_id": app["user_id"]})
        if user:
            # Calculate account age from Discord snowflake ID
            discord_id = int(app["user_id"])
            discord_epoch = 1420070400000
            timestamp = ((discord_id >> 22) + discord_epoch) / 1000
            account_created = datetime.fromtimestamp(timestamp)
            
            app["user_info"] = {
                "username": user.get("username"),
                "discriminator": user.get("discriminator", "0"),
                "avatar": user.get("avatar"),
                "email": user.get("email"),
                "level": user.get("level", 1),
                "xp": user.get("xp", 0),
                "badges": user.get("badges", []),
                "guild_roles": user.get("guild_roles", []),
                "joined_at": user.get("joined_at"),
                "last_login": user.get("last_login"),
                "account_created": account_created.isoformat(),
            }
    
    return {
        "applications": applications,
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.post("/manager/accept/{application_id}")
async def accept_application(
    application_id: str,
    request: Request,
    request_data: dict = {},
    manager: dict = Depends(require_manager_or_admin)
):
    """Accept an application - Manager access"""
    db = get_database()
    bot = get_discord_bot(request)
    from bson import ObjectId
    
    notes = request_data.get("notes", "Welcome to Maestros!")
    
    try:
        application = await db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot accept application with status: {application['status']}"
        )
    
    user_id = application["user_id"]
    
    # Discord Integration
    if bot and bot.is_ready:
        try:
            guild_id = int(os.getenv('DISCORD_GUILD_ID'))
            guild = bot.bot.get_guild(guild_id)
            
            if guild:
                # Get member
                try:
                    member = await guild.fetch_member(int(user_id))
                    
                    # Add Community Member role
                    member_role = guild.get_role(COMMUNITY_MEMBER_ROLE_ID)
                    if member_role:
                        await member.add_roles(member_role, reason=f"Application accepted by {manager['username']}")
                    
                    # Remove Application Pending role
                    pending_role = guild.get_role(APPLICATION_PENDING_ROLE_ID)
                    if pending_role:
                        await member.remove_roles(pending_role, reason="Application accepted")
                    
                    # Send DM
                    accept_embed = discord.Embed(
                        title="🎉 Welcome to Maestros Community!",
                        description=f"Congratulations, {member.mention}! Your application has been **approved**!\n\nWe're excited to have you join our community of elite gamers.",
                        color=0xFFD700
                    )
                    
                    if guild.icon:
                        accept_embed.set_thumbnail(url=guild.icon.url)
                    
                    accept_embed.add_field(
                        name="✨ What's Next?",
                        value="• Explore our server channels\n• Introduce yourself in the chat\n• Check out our game categories\n• Join voice channels and meet the community\n• Participate in events and tournaments",
                        inline=False
                    )
                    
                    if notes and len(notes) > 10:
                        accept_embed.add_field(name="💬 Manager's Message", value=notes, inline=False)
                    
                    accept_embed.add_field(
                        name="🎮 Quick Links",
                        value=f"[Join Our Discord]({SERVER_INVITE_LINK}) • [Community Rules]({SERVER_INVITE_LINK}) • [Game Rosters]({SERVER_INVITE_LINK})",
                        inline=False
                    )
                    
                    accept_embed.set_footer(text=f"Welcome aboard! • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
                    accept_embed.timestamp = datetime.utcnow()
                    
                    await send_dm(bot, user_id, accept_embed)
                    
                    # Send to acceptance channel
                    log_channel = bot.bot.get_channel(ACCEPTED_LOG_CHANNEL_ID)
                    if log_channel:
                        # Get manager member
                        manager_member = None
                        try:
                            manager_member = await guild.fetch_member(int(manager['discord_id']))
                        except:
                            pass
                        
                        log_embed = discord.Embed(
                            title="✅ Application Accepted",
                            description=f"**Welcome to our server, {member.mention}!**\n\nCongratulations on being accepted to Maestros Community!",
                            color=0x57F287,
                            timestamp=datetime.utcnow()
                        )
                        log_embed.add_field(name="Applicant", value=f"{member.mention} ({member})", inline=True)
                        log_embed.add_field(name="User ID", value=f"`{user_id}`", inline=True)
                        log_embed.add_field(name="Application ID", value=f"`{application_id[:8]}`", inline=True)
                        
                        accepted_by_text = manager_member.mention if manager_member else manager['username']
                        log_embed.add_field(name="Accepted By", value=accepted_by_text, inline=False)
                        
                        if notes:
                            log_embed.add_field(name="Acceptance Notes", value=notes[:500], inline=False)
                        
                        log_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                        log_embed.set_footer(text="🎉 Welcome to Maestros!")
                        await log_channel.send(embed=log_embed)
                        print(f"✅ Acceptance message sent to channel {ACCEPTED_LOG_CHANNEL_ID}")
                    
                except Exception as e:
                    print(f"⚠️ Discord integration error: {e}")
        except Exception as e:
            print(f"❌ Failed Discord integration: {e}")
    
    # Update application status
    update_data = {
        "status": "approved",
        "reviewed_at": datetime.utcnow(),
        "reviewed_by": manager["discord_id"],
        "reviewer_name": manager.get("username", "Unknown")
    }
    
    if notes:
        update_data["review_notes"] = notes
    
    await db.applications.update_one(
        {"_id": ObjectId(application_id)},
        {"$set": update_data}
    )
    
    # Award XP to applicant for acceptance
    xp_bonus = 100
    await db.users.update_one(
        {"discord_id": application["user_id"]},
        {"$inc": {"xp": xp_bonus}}
    )
    
    # Log activity
    await db.activity_logs.insert_one({
        "user_id": application["user_id"],
        "action": "application_approved",
        "metadata": {
            "application_id": application_id,
            "reviewed_by": manager["discord_id"],
            "xp_awarded": xp_bonus
        },
        "timestamp": datetime.utcnow()
    })
    
    print(f"✅ Application {application_id} APPROVED by {manager.get('username')}")
    
    return {
        "message": "Application approved successfully",
        "application_id": application_id,
        "xp_awarded": xp_bonus
    }

@router.post("/manager/reject/{application_id}")
async def reject_application(
    application_id: str,
    request: Request,
    request_data: dict,
    manager: dict = Depends(require_manager_or_admin)
):
    """Reject an application - Manager access"""
    db = get_database()
    bot = get_discord_bot(request)
    from bson import ObjectId
    
    reason = request_data.get("reason", "")
    
    if not reason or len(reason.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="Rejection reason must be at least 10 characters"
        )
    
    try:
        application = await db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject application with status: {application['status']}"
        )
    
    user_id = application["user_id"]
    
    # Discord Integration
    member = None
    if bot and bot.is_ready:
        try:
            guild_id = int(os.getenv('DISCORD_GUILD_ID'))
            guild = bot.bot.get_guild(guild_id)
            
            if guild:
                # Get member
                try:
                    member = await guild.fetch_member(int(user_id))
                    
                    # Remove Application Pending role
                    pending_role = guild.get_role(APPLICATION_PENDING_ROLE_ID)
                    if pending_role:
                        await member.remove_roles(pending_role, reason=f"Application rejected by {manager['username']}")
                    
                    # Send DM
                    from datetime import timedelta
                    next_application_date = datetime.utcnow() + timedelta(days=30)
                    
                    reject_embed = discord.Embed(
                        title="📋 Application Update",
                        description=f"Thank you for your interest in **{guild.name}**.\n\nAfter careful review, we are unable to approve your application at this time.",
                        color=0xED4245
                    )
                    
                    if guild.icon:
                        reject_embed.set_thumbnail(url=guild.icon.url)
                    
                    reject_embed.add_field(
                        name="📝 Feedback from Manager",
                        value=reason,
                        inline=False
                    )
                    
                    reject_embed.add_field(
                        name="🔄 Reapplication Available",
                        value=f"You can submit a new application starting **<t:{int(next_application_date.timestamp())}:F>**\n\n*That's <t:{int(next_application_date.timestamp())}:R> from now.*",
                        inline=False
                    )
                    
                    reject_embed.add_field(
                        name="💡 Tips for Next Time",
                        value="• Review our community guidelines\n• Provide more detailed responses\n• Show your dedication and experience\n• Be active in the community (if possible)",
                        inline=False
                    )
                    
                    reject_embed.set_footer(text=f"Thank you for your understanding • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
                    reject_embed.timestamp = datetime.utcnow()
                    
                    await send_dm(bot, user_id, reject_embed)
                    
                    # Send to rejection channel
                    log_channel = bot.bot.get_channel(REJECTED_LOG_CHANNEL_ID)
                    if log_channel:
                        # Get manager member
                        manager_member = None
                        try:
                            manager_member = await guild.fetch_member(int(manager['discord_id']))
                        except:
                            pass
                        
                        log_embed = discord.Embed(
                            title="❌ Application Rejected",
                            description="An application has been reviewed and rejected.",
                            color=0xED4245,
                            timestamp=datetime.utcnow()
                        )
                        
                        log_embed.add_field(name="Applicant", value=f"{member.mention} ({member})", inline=True)
                        log_embed.add_field(name="User ID", value=f"`{user_id}`", inline=True)
                        log_embed.add_field(name="Application ID", value=f"`{application_id[:8]}`", inline=True)
                        
                        rejected_by_text = manager_member.mention if manager_member else manager['username']
                        log_embed.add_field(name="Rejected By", value=rejected_by_text, inline=False)
                        log_embed.add_field(name="Rejection Reason", value=reason[:500], inline=False)
                        
                        log_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                        log_embed.set_footer(text="Application Decision")
                        
                        await log_channel.send(embed=log_embed)
                        print(f"✅ Rejection message sent to channel {REJECTED_LOG_CHANNEL_ID}")
                    
                except Exception as e:
                    print(f"⚠️ Discord integration error: {e}")
        except Exception as e:
            print(f"❌ Failed Discord integration: {e}")
    
    # Update application status
    await db.applications.update_one(
        {"_id": ObjectId(application_id)},
        {"$set": {
            "status": "rejected",
            "reviewed_at": datetime.utcnow(),
            "reviewed_by": manager["discord_id"],
            "reviewer_name": manager.get("username", "Unknown"),
            "rejection_reason": reason
        }}
    )
    
    # Log activity
    await db.activity_logs.insert_one({
        "user_id": application["user_id"],
        "action": "application_rejected",
        "metadata": {
            "application_id": application_id,
            "reviewed_by": manager["discord_id"],
            "reason": reason
        },
        "timestamp": datetime.utcnow()
    })
    
    print(f"❌ Application {application_id} REJECTED by {manager.get('username')}")
    
    return {
        "message": "Application rejected successfully",
        "application_id": application_id
    }

@router.get("/manager/stats")
async def get_application_stats(
    manager: dict = Depends(require_manager_or_admin)
):
    """Get application statistics - Manager access"""
    db = get_database()
    
    total = await db.applications.count_documents({})
    pending = await db.applications.count_documents({"status": "pending"})
    approved = await db.applications.count_documents({"status": "approved"})
    rejected = await db.applications.count_documents({"status": "rejected"})
    
    # Get recent applications (last 7 days)
    from datetime import timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent = await db.applications.count_documents({
        "submitted_at": {"$gte": week_ago}
    })
    
    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "recent_week": recent,
        "approval_rate": round((approved / total * 100) if total > 0 else 0, 2)
    }

@router.delete("/manager/{application_id}")
async def delete_application(
    application_id: str,
    manager: dict = Depends(require_manager_or_admin)
):
    """Delete an application - Manager access"""
    db = get_database()
    from bson import ObjectId
    
    try:
        app_oid = ObjectId(application_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid application ID")
    
    application = await db.applications.find_one({"_id": app_oid})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Delete the application
    result = await db.applications.delete_one({"_id": app_oid})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Log activity
    await db.activity_logs.insert_one({
        "user_id": application["user_id"],
        "action": "application_deleted",
        "metadata": {
            "application_id": application_id,
            "deleted_by": manager["discord_id"],
            "previous_status": application.get("status")
        },
        "timestamp": datetime.utcnow()
    })
    
    print(f"🗑️ Application {application_id} DELETED by {manager.get('username')}")
    
    return {"message": "Application deleted successfully"}


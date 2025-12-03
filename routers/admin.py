from fastapi import APIRouter, HTTPException, Depends
from typing import List
from database import get_database
from utils import require_admin
from datetime import datetime

router = APIRouter()

@router.get("/users")
async def get_all_users(
    skip: int = 0,
    limit: int = 50,
    admin: dict = Depends(require_admin)
):
    """Get all users (admin only)"""
    db = get_database()
    
    users = await db.users.find().skip(skip).limit(limit).to_list(limit)
    total = await db.users.count_documents({})
    
    for user in users:
        user["_id"] = str(user["_id"])
    
    return {
        "users": users,
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/applications")
async def get_all_applications(
    status: str = None,
    skip: int = 0,
    limit: int = 50,
    admin: dict = Depends(require_admin)
):
    """Get all applications (admin only)"""
    db = get_database()
    
    query = {}
    if status:
        query["status"] = status
    
    applications = await db.applications.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.applications.count_documents(query)
    
    for app in applications:
        app["_id"] = str(app["_id"])
    
    return {
        "applications": applications,
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.put("/applications/{application_id}/review")
async def review_application(
    application_id: str,
    status: str,
    admin: dict = Depends(require_admin)
):
    """Review an application (admin only) - ALL LOGIC SERVER-SIDE"""
    db = get_database()
    from bson import ObjectId
    from utils import calculate_level
    
    # Validate status
    if status not in ["approved", "rejected"]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid status. Must be 'approved' or 'rejected'"
        )
    
    # Find application
    try:
        application = await db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Check if already reviewed
    if application.get("status") != "pending":
        raise HTTPException(
            status_code=400, 
            detail=f"Application already {application.get('status')}"
        )
    
    # Update application
    result = await db.applications.update_one(
        {"_id": ObjectId(application_id)},
        {
            "$set": {
                "status": status,
                "reviewed_at": datetime.utcnow(),
                "reviewed_by": admin["discord_id"]
            }
        }
    )
    
    user_id = application["user_id"]
    
    # Process rewards/penalties based on status (server-side only)
    if status == "approved":
        # Award XP
        xp_reward = 100
        await db.users.update_one(
            {"discord_id": user_id},
            {"$inc": {"xp": xp_reward}}
        )
        
        # Recalculate level
        user = await db.users.find_one({"discord_id": user_id})
        new_level = calculate_level(user["xp"])
        old_level = user.get("level", 0)
        
        if new_level > old_level:
            await db.users.update_one(
                {"discord_id": user_id},
                {"$set": {"level": new_level}}
            )
        
        # Add member badge
        await db.users.update_one(
            {"discord_id": user_id},
            {"$addToSet": {"badges": "Member"}}
        )
        
        # Add member role
        await db.users.update_one(
            {"discord_id": user_id},
            {"$addToSet": {"roles": "Member"}}
        )
        
        # Log activity
        await db.activity.insert_one({
            "user_id": user_id,
            "action": "application_approved",
            "metadata": {
                "application_id": application_id,
                "reviewed_by": admin["discord_id"],
                "xp_awarded": xp_reward,
                "level_up": new_level > old_level
            },
            "timestamp": datetime.utcnow()
        })
        
        return {
            "message": "Application approved",
            "xp_awarded": xp_reward,
            "badges_added": ["Member"],
            "roles_added": ["Member"]
        }
    else:
        # Log rejection
        await db.activity.insert_one({
            "user_id": user_id,
            "action": "application_rejected",
            "metadata": {
                "application_id": application_id,
                "reviewed_by": admin["discord_id"]
            },
            "timestamp": datetime.utcnow()
        })
        
        return {"message": "Application rejected"}

@router.post("/users/{user_id}/xp")
async def award_xp(
    user_id: str,
    amount: int,
    reason: str = "Admin award",
    admin: dict = Depends(require_admin)
):
    """Award XP to a user (admin only) - ALL CALCULATIONS SERVER-SIDE"""
    db = get_database()
    from utils import calculate_level
    
    # Validation
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if amount > 10000:
        raise HTTPException(status_code=400, detail="Cannot award more than 10000 XP at once")
    
    user = await db.users.find_one({"discord_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    old_xp = user.get("xp", 0)
    old_level = user.get("level", 0)
    new_xp = old_xp + amount
    new_level = calculate_level(new_xp)
    
    # Update user
    await db.users.update_one(
        {"discord_id": user_id},
        {"$set": {"xp": new_xp, "level": new_level}}
    )
    
    # Log activity
    await db.activity.insert_one({
        "user_id": user_id,
        "action": "xp_awarded",
        "metadata": {
            "amount": amount,
            "reason": reason,
            "awarded_by": admin["discord_id"],
            "old_xp": old_xp,
            "new_xp": new_xp,
            "old_level": old_level,
            "new_level": new_level
        },
        "timestamp": datetime.utcnow()
    })
    
    return {
        "message": f"Awarded {amount} XP",
        "old_xp": old_xp,
        "new_xp": new_xp,
        "old_level": old_level,
        "new_level": new_level,
        "level_up": new_level > old_level
    }

@router.post("/users/{user_id}/badge")
async def award_badge(
    user_id: str,
    badge: str,
    admin: dict = Depends(require_admin)
):
    """Award a badge to a user (admin only) - VALIDATION SERVER-SIDE"""
    db = get_database()
    
    # Validate badge name
    if not badge or len(badge) < 2:
        raise HTTPException(status_code=400, detail="Invalid badge name")
    
    valid_badges = ["Member", "VIP", "Elite", "Champion", "Legend", "Staff", 
                    "Moderator", "Event Winner", "Tournament Victor", "Top Player"]
    if badge not in valid_badges:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid badge. Must be one of: {', '.join(valid_badges)}"
        )
    
    user = await db.users.find_one({"discord_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user already has badge
    if badge in user.get("badges", []):
        raise HTTPException(status_code=400, detail="User already has this badge")
    
    await db.users.update_one(
        {"discord_id": user_id},
        {"$addToSet": {"badges": badge}}
    )
    
    # Log activity
    await db.activity.insert_one({
        "user_id": user_id,
        "action": "badge_awarded",
        "metadata": {"badge": badge, "awarded_by": admin["discord_id"]},
        "timestamp": datetime.utcnow()
    })
    
    return {
        "message": f"Awarded badge: {badge}",
        "badge": badge
    }

@router.delete("/users/{user_id}/badge")
async def remove_badge(
    user_id: str,
    badge: str,
    admin: dict = Depends(require_admin)
):
    """Remove a badge from a user (admin only)"""
    db = get_database()
    
    await db.users.update_one(
        {"discord_id": user_id},
        {"$pull": {"badges": badge}}
    )
    
    return {"message": f"Removed badge: {badge}"}

@router.get("/logs")
async def get_logs(
    limit: int = 100,
    admin: dict = Depends(require_admin)
):
    """Get system logs (admin only)"""
    db = get_database()
    
    logs = await db.logs.find().sort("timestamp", -1).limit(limit).to_list(limit)
    
    for log in logs:
        log["_id"] = str(log["_id"])
    
    return {"logs": logs}

@router.get("/stats")
async def get_admin_stats(admin: dict = Depends(require_admin)):
    """Get admin dashboard stats"""
    db = get_database()
    
    total_users = await db.users.count_documents({})
    pending_applications = await db.applications.count_documents({"status": "pending"})
    total_events = await db.events.count_documents({})
    upcoming_events = await db.events.count_documents({
        "status": "upcoming",
        "date": {"$gte": datetime.utcnow()}
    })
    
    return {
        "total_users": total_users,
        "pending_applications": pending_applications,
        "total_events": total_events,
        "upcoming_events": upcoming_events,
    }

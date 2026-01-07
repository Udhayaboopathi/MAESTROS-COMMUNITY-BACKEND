from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.core.database import get_database
from app.utils import require_admin
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
    """Review an application (admin only)"""
    db = get_database()
    from bson import ObjectId
    
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
    
    # Process rewards based on status
    if status == "approved":
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
                "reviewed_by": admin["discord_id"]
            },
            "timestamp": datetime.utcnow()
        })
        
        return {
            "message": "Application approved",
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


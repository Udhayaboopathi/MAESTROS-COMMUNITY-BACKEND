from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
from database import get_database
from utils import get_current_user, calculate_level, require_admin
from models import EventCreate, Event

router = APIRouter()

def validate_event_data(data: dict) -> dict:
    """
    Validate event data server-side
    Returns validation result with errors if any
    """
    errors = {}
    
    # Required fields
    required_fields = ["title", "description", "game", "date", "max_participants"]
    for field in required_fields:
        if field not in data or not data[field]:
            errors[field] = f"{field.replace('_', ' ').title()} is required"
    
    # Validate title length
    if "title" in data:
        title = data["title"]
        if len(title) < 5 or len(title) > 100:
            errors["title"] = "Title must be between 5 and 100 characters"
    
    # Validate description length
    if "description" in data:
        desc = data["description"]
        if len(desc) < 20:
            errors["description"] = "Description must be at least 20 characters"
    
    # Validate max participants
    if "max_participants" in data:
        try:
            max_p = int(data["max_participants"])
            if max_p < 2:
                errors["max_participants"] = "Must allow at least 2 participants"
            elif max_p > 1000:
                errors["max_participants"] = "Maximum 1000 participants allowed"
        except (ValueError, TypeError):
            errors["max_participants"] = "Must be a valid number"
    
    # Validate date is in future
    if "date" in data:
        try:
            event_date = datetime.fromisoformat(data["date"].replace('Z', '+00:00'))
            if event_date < datetime.utcnow():
                errors["date"] = "Event date must be in the future"
        except (ValueError, AttributeError):
            errors["date"] = "Invalid date format"
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }

@router.post("/create")
async def create_event(
    event_data: dict,
    current_user: dict = Depends(require_admin)
):
    """Create a new event (admin only) - ALL VALIDATION SERVER-SIDE"""
    db = get_database()
    
    # Server-side validation
    validation_result = validate_event_data(event_data)
    if not validation_result["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed",
                "errors": validation_result["errors"]
            }
        )
    
    event = {
        **event_data,
        "participants": [],
        "winners": [],
        "status": "upcoming",
        "created_by": current_user["discord_id"],
        "created_at": datetime.utcnow(),
    }
    
    if isinstance(event_data.get("date"), str):
        event["date"] = datetime.fromisoformat(event_data["date"].replace('Z', '+00:00'))
    
    result = await db.events.insert_one(event)
    
    # Log activity
    await db.activity.insert_one({
        "user_id": current_user["discord_id"],
        "action": "event_created",
        "metadata": {"event_id": str(result.inserted_id), "title": event_data["title"]},
        "timestamp": datetime.utcnow()
    })
    
    return {
        "message": "Event created successfully",
        "event_id": str(result.inserted_id)
    }

@router.get("/list")
async def list_events(
    status: Optional[str] = None,
    limit: int = 10
):
    """List events"""
    db = get_database()
    
    query = {}
    if status:
        query["status"] = status
    
    events = await db.events.find(query).sort("date", -1).limit(limit).to_list(limit)
    
    # Convert ObjectId to string
    for event in events:
        event["_id"] = str(event["_id"])
        if "date" in event:
            event["date"] = event["date"].isoformat()
        if "created_at" in event:
            event["created_at"] = event["created_at"].isoformat()
    
    return {"events": events}

@router.get("/{event_id}")
async def get_event(event_id: str):
    """Get event details"""
    db = get_database()
    from bson import ObjectId
    
    try:
        event = await db.events.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    event["_id"] = str(event["_id"])
    if "date" in event:
        event["date"] = event["date"].isoformat()
    if "created_at" in event:
        event["created_at"] = event["created_at"].isoformat()
    
    return {"event": event}

@router.post("/{event_id}/register")
async def register_for_event(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Register for an event - ALL VALIDATION SERVER-SIDE"""
    db = get_database()
    from bson import ObjectId
    
    try:
        event = await db.events.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Server-side validation checks
    if current_user["discord_id"] in event.get("participants", []):
        raise HTTPException(status_code=400, detail="Already registered for this event")
    
    max_participants = event.get("max_participants", 0)
    current_participants = len(event.get("participants", []))
    
    if current_participants >= max_participants:
        raise HTTPException(
            status_code=400, 
            detail=f"Event is full ({current_participants}/{max_participants} participants)"
        )
    
    if event.get("status") != "upcoming":
        raise HTTPException(
            status_code=400, 
            detail=f"Event registration closed (status: {event.get('status')})"
        )
    
    # Check if event has already started
    event_date = event.get("date")
    if event_date and event_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Event has already started")
    
    # Add participant
    await db.events.update_one(
        {"_id": ObjectId(event_id)},
        {"$push": {"participants": current_user["discord_id"]}}
    )
    
    # Log activity
    await db.activity.insert_one({
        "user_id": current_user["discord_id"],
        "action": "event_registered",
        "metadata": {
            "event_id": event_id, 
            "event_title": event.get("title"),
            "participant_count": current_participants + 1
        },
        "timestamp": datetime.utcnow()
    })
    
    # Award XP (server-side calculation)
    xp_reward = 25
    await db.users.update_one(
        {"discord_id": current_user["discord_id"]},
        {"$inc": {"xp": xp_reward}}
    )
    
    # Recalculate level
    updated_user = await db.users.find_one({"discord_id": current_user["discord_id"]})
    new_level = calculate_level(updated_user["xp"])
    old_level = updated_user.get("level", 0)
    
    if new_level > old_level:
        await db.users.update_one(
            {"discord_id": current_user["discord_id"]},
            {"$set": {"level": new_level}}
        )
    
    return {
        "message": "Registered successfully",
        "xp_awarded": xp_reward,
        "level_up": new_level > old_level,
        "new_level": new_level,
        "participant_count": current_participants + 1,
        "spots_remaining": max_participants - (current_participants + 1)
    }

@router.post("/{event_id}/unregister")
async def unregister_from_event(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Unregister from an event"""
    db = get_database()
    from bson import ObjectId
    
    try:
        event = await db.events.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Check if registered
    if current_user["discord_id"] not in event.get("participants", []):
        raise HTTPException(status_code=400, detail="Not registered")
    
    # Remove participant
    await db.events.update_one(
        {"_id": ObjectId(event_id)},
        {"$pull": {"participants": current_user["discord_id"]}}
    )
    
    return {"message": "Unregistered successfully"}

@router.get("/upcoming/list")
async def get_upcoming_events(limit: int = 5):
    """Get upcoming events"""
    db = get_database()
    
    events = await db.events.find({
        "status": "upcoming",
        "date": {"$gte": datetime.utcnow()}
    }).sort("date", 1).limit(limit).to_list(limit)
    
    for event in events:
        event["_id"] = str(event["_id"])
        if "date" in event:
            event["date"] = event["date"].isoformat()
    
    return {"events": events}

# Manager CRUD endpoints
@router.put("/manager/{event_id}")
async def update_event(
    event_id: str,
    event_data: EventCreate,
    current_user: dict = Depends(get_current_user)
):
    """Update an event (Manager only)"""
    permissions = current_user.get("permissions", {})
    if not permissions.get("can_manage_applications"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    db = get_database()
    from bson import ObjectId
    
    try:
        event_oid = ObjectId(event_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid event ID")
    
    existing_event = await db.events.find_one({"_id": event_oid})
    if not existing_event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    update_data = event_data.dict()
    update_data["updated_at"] = datetime.utcnow()
    update_data["updated_by"] = current_user["discord_id"]
    
    await db.events.update_one({"_id": event_oid}, {"$set": update_data})
    
    updated_event = await db.events.find_one({"_id": event_oid})
    updated_event["_id"] = str(updated_event["_id"])
    if "date" in updated_event:
        updated_event["date"] = updated_event["date"].isoformat()
    
    return {"message": "Event updated successfully", "event": updated_event}

@router.delete("/manager/{event_id}")
async def delete_event(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete an event (Manager only)"""
    permissions = current_user.get("permissions", {})
    if not permissions.get("can_manage_applications"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    db = get_database()
    from bson import ObjectId
    
    try:
        event_oid = ObjectId(event_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid event ID")
    
    result = await db.events.delete_one({"_id": event_oid})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    
    return {"message": "Event deleted successfully"}

@router.get("/manager/all")
async def get_all_events_manager(
    current_user: dict = Depends(get_current_user)
):
    """Get all events for manager panel"""
    permissions = current_user.get("permissions", {})
    if not permissions.get("can_manage_applications"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    db = get_database()
    
    events = await db.events.find({}).sort("date", -1).to_list(100)
    
    for event in events:
        event["_id"] = str(event["_id"])
        if "date" in event:
            event["date"] = event["date"].isoformat()
        event["participant_count"] = len(event.get("participants", []))
    
    return {"events": events, "count": len(events)}

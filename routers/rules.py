from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from database import get_database
from utils import get_current_user, require_manager_or_admin
from datetime import datetime
from pydantic import BaseModel
from bson import ObjectId
import os

router = APIRouter()

# Discord Rules Category ID (contains Server-Rules, Community-Rules, RP-Rules channels)
RULES_CATEGORY_ID = os.getenv("RULES_CATEGORY_ID", "1228292116677922826")

class RuleCreate(BaseModel):
    title: str
    rule_content: str
    category: Optional[str] = "general"
    active: bool = True

class RuleUpdate(BaseModel):
    title: Optional[str] = None
    rule_content: Optional[str] = None
    category: Optional[str] = None
    active: Optional[bool] = None

@router.get("")
async def get_rules(
    active_only: bool = True,
    category: Optional[str] = None
):
    """Get all rules (public endpoint)"""
    db = get_database()
    
    query = {}
    if active_only:
        query["active"] = True
    if category:
        query["category"] = category
    
    rules = await db.rules.find(query).sort("created_at", -1).to_list(1000)
    
    # Convert ObjectId to string
    for rule in rules:
        rule["_id"] = str(rule["_id"])
    
    return {"rules": rules, "count": len(rules)}

@router.get("/categories/channels")
async def get_rule_categories():
    """Get available rule categories from Discord channels"""
    try:
        from main import discord_bot
        
        if not discord_bot or not discord_bot.is_ready:
            # Return default categories if bot is not ready
            return {
                "channels": [
                    {"id": "general", "name": "general", "display_name": "General"},
                    {"id": "conduct", "name": "conduct", "display_name": "Conduct"},
                    {"id": "gameplay", "name": "gameplay", "display_name": "Gameplay"}
                ]
            }
        
        channels = await discord_bot.get_category_channels(RULES_CATEGORY_ID)
        return {"channels": channels}
        
    except Exception as e:
        print(f"Error fetching rule categories: {e}")
        # Return default categories on error
        return {
            "channels": [
                {"id": "general", "name": "general", "display_name": "General"},
                {"id": "conduct", "name": "conduct", "display_name": "Conduct"},
                {"id": "gameplay", "name": "gameplay", "display_name": "Gameplay"}
            ]
        }

@router.get("/{rule_id}")
async def get_rule(rule_id: str):
    """Get a single rule by ID"""
    db = get_database()
    
    from bson import ObjectId
    try:
        rule = await db.rules.find_one({"_id": ObjectId(rule_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    rule["_id"] = str(rule["_id"])
    return rule

@router.post("")
async def create_rule(
    rule_data: RuleCreate,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Create a new rule (Manager only)"""
    
    db = get_database()
    
    rule_dict = rule_data.dict()
    rule_dict.update({
        "created_by": current_user["discord_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    result = await db.rules.insert_one(rule_dict)
    
    new_rule = await db.rules.find_one({"_id": result.inserted_id})
    new_rule["_id"] = str(new_rule["_id"])
    
    # Post to Discord
    try:
        from main import discord_bot
        if discord_bot and discord_bot.is_ready:
            # Convert ObjectId back to original for Discord function
            discord_rule = dict(new_rule)
            discord_rule["_id"] = result.inserted_id
            await discord_bot.post_rule_to_discord(discord_rule, RULES_CATEGORY_ID)
    except Exception as e:
        print(f"⚠️ Failed to post rule to Discord: {e}")
    
    return {"message": "Rule created successfully", "rule": new_rule}

@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    rule_data: RuleUpdate,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Update a rule (Manager only)"""
    
    db = get_database()
    
    try:
        rule_oid = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    
    # Check if rule exists
    existing_rule = await db.rules.find_one({"_id": rule_oid})
    if not existing_rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Update only provided fields
    update_data = {k: v for k, v in rule_data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    update_data["updated_by"] = current_user["discord_id"]
    
    await db.rules.update_one({"_id": rule_oid}, {"$set": update_data})
    
    updated_rule = await db.rules.find_one({"_id": rule_oid})
    updated_rule["_id"] = str(updated_rule["_id"])
    
    # Update on Discord
    try:
        from main import discord_bot
        if discord_bot and discord_bot.is_ready:
            discord_rule = dict(updated_rule)
            discord_rule["_id"] = rule_oid
            await discord_bot.post_rule_to_discord(discord_rule, RULES_CATEGORY_ID)
    except Exception as e:
        print(f"⚠️ Failed to update rule on Discord: {e}")
    
    return {"message": "Rule updated successfully", "rule": updated_rule}

@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Delete a rule (Manager only)"""
    
    db = get_database()
    
    try:
        rule_oid = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    
    # Get rule data before deletion for Discord cleanup
    rule_to_delete = await db.rules.find_one({"_id": rule_oid})
    if not rule_to_delete:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    result = await db.rules.delete_one({"_id": rule_oid})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Delete from Discord
    try:
        from main import discord_bot
        if discord_bot and discord_bot.is_ready:
            await discord_bot.delete_rule_from_discord(rule_to_delete, RULES_CATEGORY_ID)
    except Exception as e:
        print(f"⚠️ Failed to delete rule from Discord: {e}")
    
    return {"message": "Rule deleted successfully"}
    return {"message": "Rule deleted successfully"}

@router.get("/manager/all")
async def get_all_rules_manager(
    current_user: dict = Depends(require_manager_or_admin)
):
    """Get all rules for manager panel (including inactive)"""
    
    db = get_database()
    
    rules = await db.rules.find({}).sort("created_at", -1).to_list(1000)
    
    for rule in rules:
        rule["_id"] = str(rule["_id"])
    
    return {"rules": rules, "count": len(rules)}

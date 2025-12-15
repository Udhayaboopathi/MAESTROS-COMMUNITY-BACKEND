from fastapi import APIRouter, HTTPException
from typing import Dict
from database import get_database

router = APIRouter()

# In-memory stats updated by Discord bot every 10 seconds
discord_stats = {
    "total": 0,
    "online": 0,
    "managers": [],
    "members": [],
    "last_update": None
}

@router.get("/stats")
async def get_discord_stats() -> Dict:
    """Get live Discord server stats (updated by integrated bot)"""
    return discord_stats

@router.get("/status")
async def get_bot_status():
    """Get Discord bot connection status"""
    return {
        "online": discord_stats.get("total", 0) > 0,
        "last_update": discord_stats.get("last_update"),
    }

@router.get("/user/{discord_id}")
async def get_user_details(discord_id: str):
    """Get detailed user information by Discord ID"""
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    user = await db.users.find_one({'discord_id': discord_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Convert ObjectId to string
    user['_id'] = str(user['_id'])
    
    # Convert datetime objects to ISO format strings
    if 'joined_at' in user and user['joined_at']:
        user['joined_at'] = user['joined_at'].isoformat()
    if 'last_login' in user and user['last_login']:
        user['last_login'] = user['last_login'].isoformat()
    
    return user

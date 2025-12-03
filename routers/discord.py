from fastapi import APIRouter
from typing import Dict

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

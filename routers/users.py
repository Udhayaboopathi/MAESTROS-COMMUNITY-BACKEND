from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from database import get_database
from utils import get_current_user, calculate_level
from datetime import datetime
import os

router = APIRouter()

# Access to global bot instance
def get_bot_instance():
    """Get the Discord bot instance from main"""
    import main
    return main.discord_bot

@router.get("/me")
async def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "id": str(current_user["_id"]),
        "discord_id": current_user["discord_id"],
        "username": current_user["username"],
        "avatar": current_user.get("avatar"),
        "level": current_user.get("level", 1),
        "xp": current_user.get("xp", 0),
        "badges": current_user.get("badges", []),
        "roles": current_user.get("roles", []),
        "joined_at": current_user.get("joined_at"),
    }

@router.get("/dashboard")
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    """Get user dashboard data"""
    db = get_database()
    
    # Get user's recent activity
    recent_activity = await db.activity.find(
        {"user_id": current_user["discord_id"]}
    ).sort("timestamp", -1).limit(10).to_list(10)
    
    # Get user's applications
    applications = await db.applications.find(
        {"user_id": current_user["discord_id"]}
    ).sort("submitted_at", -1).limit(5).to_list(5)
    
    # Get user's event registrations
    events = await db.events.find(
        {"participants": current_user["discord_id"]}
    ).sort("date", -1).limit(5).to_list(5)
    
    return {
        "user": {
            "username": current_user["username"],
            "level": current_user.get("level", 1),
            "xp": current_user.get("xp", 0),
            "badges": current_user.get("badges", []),
        },
        "recent_activity": recent_activity,
        "applications": applications,
        "events": events,
    }

@router.put("/update")
async def update_user(
    username: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Update user profile"""
    db = get_database()
    
    update_data = {}
    if username:
        update_data["username"] = username
    
    if update_data:
        await db.users.update_one(
            {"discord_id": current_user["discord_id"]},
            {"$set": update_data}
        )
    
    updated_user = await db.users.find_one({"discord_id": current_user["discord_id"]})
    return {"message": "Profile updated", "user": updated_user}

@router.get("/{user_id}")
async def get_user_by_id(user_id: str, request: Request):
    """Get user by ID with full Discord guild member info"""
    db = get_database()
    user = await db.users.find_one({"discord_id": user_id})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Try to get Discord bot instance (first from app state, then from global)
    discord_bot = getattr(request.app.state, 'discord_bot', None)
    if not discord_bot:
        discord_bot = get_bot_instance()
    
    # Base user data
    user_data = {
        "id": str(user["_id"]),
        "discord_id": user["discord_id"],
        "username": user.get("username"),
        "display_name": user.get("display_name"),
        "discriminator": user.get("discriminator"),
        "avatar": user.get("avatar"),
        "level": user.get("level", 1),
        "xp": user.get("xp", 0),
        "badges": user.get("badges", []),
        "guild_roles": user.get("guild_roles", []),
        "permissions": user.get("permissions", {}),
        "joined_at": user.get("joined_at"),
        "last_seen": user.get("last_seen"),
        "last_login": user.get("last_login"),
        "created_at": user.get("created_at"),
        "discord_details": None,
    }
    
    # Try to fetch Discord guild member info
    try:
        if discord_bot and hasattr(discord_bot, 'bot') and discord_bot.bot and discord_bot.is_ready:
            guild = discord_bot.bot.get_guild(discord_bot.guild_id)
            if guild:
                member = guild.get_member(int(user_id))
                if member:
                    # Update avatar from Discord member
                    if member.avatar:
                        user_data["avatar"] = member.avatar.key
                    
                    # Add Discord guild member details
                    user_data["discord_details"] = {
                        "global_name": member.global_name,
                        "server_nickname": member.nick,
                        "server_avatar": member.guild_avatar.key if member.guild_avatar else None,
                        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                        "premium_since": member.premium_since.isoformat() if member.premium_since else None,
                    }
                    
                    # Get role names
                    role_names = [role.name for role in member.roles if role.name != "@everyone"]
                    user_data["guild_roles"] = role_names
                    print(f"✅ Fetched Discord data for user {user_id}: nickname={member.nick}, roles={len(role_names)}, avatar={user_data['avatar']}")
                else:
                    print(f"⚠️ Member {user_id} not found in guild")
            else:
                print(f"⚠️ Guild {discord_bot.guild_id} not found")
        else:
            print(f"⚠️ Discord bot not ready: bot={discord_bot is not None}, ready={discord_bot.is_ready if discord_bot else False}")
    except Exception as e:
        print(f"❌ Error fetching Discord member info for {user_id}: {e}")
        import traceback
        traceback.print_exc()
    
    return user_data

@router.get("/leaderboard/xp")
async def get_xp_leaderboard(limit: int = 10):
    """Get XP leaderboard"""
    db = get_database()
    users = await db.users.find().sort("xp", -1).limit(limit).to_list(limit)
    
    leaderboard = []
    for idx, user in enumerate(users, 1):
        leaderboard.append({
            "rank": idx,
            "username": user["username"],
            "avatar": user.get("avatar"),
            "xp": user.get("xp", 0),
            "level": user.get("level", 1),
            "badges": user.get("badges", []),
        })
    
    return {"leaderboard": leaderboard}

@router.post("/add-xp")
async def add_xp(amount: int, current_user: dict = Depends(get_current_user)):
    """Add XP to current user"""
    db = get_database()
    
    new_xp = current_user.get("xp", 0) + amount
    new_level = calculate_level(new_xp)
    
    await db.users.update_one(
        {"discord_id": current_user["discord_id"]},
        {"$set": {"xp": new_xp, "level": new_level}}
    )
    
    # Log activity
    await db.activity.insert_one({
        "user_id": current_user["discord_id"],
        "action": "xp_gained",
        "metadata": {"amount": amount, "new_xp": new_xp, "new_level": new_level},
        "timestamp": datetime.utcnow()
    })
    
    return {"message": f"Added {amount} XP", "xp": new_xp, "level": new_level}

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from database import get_database
from utils import get_current_user, calculate_level
from datetime import datetime
import os

router = APIRouter()

def get_account_creation_date(discord_id: str) -> datetime:
    """Extract account creation date from Discord snowflake ID"""
    try:
        snowflake = int(discord_id)
        # Discord epoch starts at 2015-01-01
        discord_epoch = 1420070400000
        timestamp_ms = (snowflake >> 22) + discord_epoch
        return datetime.fromtimestamp(timestamp_ms / 1000)
    except:
        return None

# Load role IDs from environment variables
CEO_ROLE_ID = os.getenv('CEO_ROLE_ID')
MANAGER_ROLE_ID = os.getenv('MANAGER_ROLE_ID')
MEMBER_ROLE_ID = os.getenv('MEMBER_ROLE_ID')

# Role hierarchy (1 = highest/first, 2 = second, 3 = third) - using role IDs
ROLE_HIERARCHY = {
    CEO_ROLE_ID: {"name": "CEO", "priority": 1, "color": "#FFD700"},
    MANAGER_ROLE_ID: {"name": "Manager", "priority": 2, "color": "#1E90FF"},
    MEMBER_ROLE_ID: {"name": "Member", "priority": 3, "color": "#00FF00"}
}

def get_highest_role(role_ids: List[int], discord_roles=None) -> dict:
    """Determine the highest role from CEO, Manager, or Member using role IDs"""
    highest = None
    highest_priority = 999  # Start with a very high number (lower is better)
    highest_role_id = None
    highest_role_color = "#99AAB5"
    
    for role_id in role_ids:
        role_id_str = str(role_id)
        if role_id_str in ROLE_HIERARCHY:
            role_info = ROLE_HIERARCHY[role_id_str]
            if role_info["priority"] < highest_priority:  # Lower priority number = higher importance
                highest = role_info["name"]
                highest_priority = role_info["priority"]
                highest_role_id = role_id_str
                
                # Get actual Discord role color if available
                if discord_roles:
                    for discord_role in discord_roles:
                        if str(discord_role.id) == role_id_str:
                            highest_role_color = f"#{discord_role.color.value:06x}" if discord_role.color.value != 0 else "#99AAB5"
                            break
    
    if highest:
        return {
            "name": highest,
            "color": highest_role_color,
            "priority": highest_priority
        }
    
    return {"name": None, "color": "#99AAB5", "priority": 999}

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
    
    # Try to get Discord bot instance (first from app state, then from global)
    discord_bot = getattr(request.app.state, 'discord_bot', None)
    if not discord_bot:
        discord_bot = get_bot_instance()
    
    # Initialize base user data
    # Extract account creation date from Discord ID
    account_created = get_account_creation_date(user_id)
    
    if user:
        # User exists in database
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
            "account_created_at": account_created.isoformat() if account_created else None,
            "discord_details": None,
            "in_database": True,
            "highest_role": get_highest_role(user.get("guild_roles", [])),
        }
    else:
        # User not in database, will try to fetch from Discord
        user_data = {
            "id": None,
            "discord_id": user_id,
            "username": None,
            "display_name": None,
            "discriminator": None,
            "avatar": None,
            "level": 0,
            "xp": 0,
            "badges": [],
            "guild_roles": [],
            "permissions": {},
            "joined_at": None,
            "last_seen": None,
            "last_login": None,
            "created_at": None,
            "account_created_at": account_created.isoformat() if account_created else None,
            "discord_details": None,
            "in_database": False,
            "highest_role": {"name": None, "color": "#99AAB5", "priority": 0},
        }
    
    # Try to fetch Discord guild member info
    discord_member_found = False
    try:
        if discord_bot and hasattr(discord_bot, 'bot') and discord_bot.bot and discord_bot.is_ready:
            guild = discord_bot.bot.get_guild(discord_bot.guild_id)
            if guild:
                member = guild.get_member(int(user_id))
                if member:
                    discord_member_found = True
                    
                    # Update basic info from Discord
                    user_data["username"] = member.name
                    user_data["display_name"] = member.display_name
                    user_data["discriminator"] = member.discriminator
                    
                    # Update avatar from Discord member
                    if member.avatar:
                        user_data["avatar"] = member.avatar.key
                    
                    # Add Discord guild member details
                    # Get all activities (games, Spotify, custom status, etc.)
                    activity_data = None
                    
                    if member.activities:
                        for activity in member.activities:
                            # Check for Spotify first (listening)
                            if hasattr(activity, 'type') and str(activity.type) == 'ActivityType.listening':
                                if hasattr(activity, 'title'):  # Spotify activity
                                    activity_data = {
                                        "type": "listening",
                                        "name": activity.title if hasattr(activity, 'title') else None,
                                        "details": activity.artist if hasattr(activity, 'artist') else None,
                                        "state": activity.album if hasattr(activity, 'album') else None,
                                        "large_image": activity.album_cover_url if hasattr(activity, 'album_cover_url') else None,
                                        "start": activity.start.isoformat() if hasattr(activity, 'start') and activity.start else None,
                                        "end": activity.end.isoformat() if hasattr(activity, 'end') and activity.end else None,
                                        "duration": activity.duration.total_seconds() if hasattr(activity, 'duration') and activity.duration else None,
                                    }
                                    break
                            # Then check for games (playing)
                            elif hasattr(activity, 'type') and str(activity.type) == 'ActivityType.playing':
                                large_image_url = None
                                if hasattr(activity, 'large_image_url'):
                                    large_image_url = activity.large_image_url
                                elif hasattr(activity, 'application_id') and activity.application_id:
                                    # Construct Discord CDN URL for game icon
                                    if hasattr(activity, 'large_image_id') and activity.large_image_id:
                                        large_image_url = f"https://cdn.discordapp.com/app-assets/{activity.application_id}/{activity.large_image_id}.png"
                                
                                activity_data = {
                                    "type": "playing",
                                    "name": activity.name,
                                    "details": activity.details if hasattr(activity, 'details') else None,
                                    "state": activity.state if hasattr(activity, 'state') else None,
                                    "large_image": large_image_url,
                                    "small_image": activity.small_image_url if hasattr(activity, 'small_image_url') else None,
                                    "start": activity.start.isoformat() if hasattr(activity, 'start') and activity.start else None,
                                }
                                break
                            # Check for streaming
                            elif hasattr(activity, 'type') and str(activity.type) == 'ActivityType.streaming':
                                activity_data = {
                                    "type": "streaming",
                                    "name": activity.name,
                                    "details": activity.details if hasattr(activity, 'details') else None,
                                    "url": activity.url if hasattr(activity, 'url') else None,
                                }
                                break
                            # Check for watching
                            elif hasattr(activity, 'type') and str(activity.type) == 'ActivityType.watching':
                                activity_data = {
                                    "type": "watching",
                                    "name": activity.name,
                                    "details": activity.details if hasattr(activity, 'details') else None,
                                }
                                break
                    
                    user_data["discord_details"] = {
                        "global_name": member.global_name,
                        "server_nickname": member.nick,
                        "server_avatar": member.guild_avatar.key if member.guild_avatar else None,
                        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                        "premium_since": member.premium_since.isoformat() if member.premium_since else None,
                        "status": str(member.status),  # online, idle, dnd, offline
                        "activity_data": activity_data,
                    }
                    
                    # Get role names, IDs, and colors
                    role_names = [role.name for role in member.roles if role.name != "@everyone"]
                    role_ids = [role.id for role in member.roles if role.name != "@everyone"]
                    role_colors = [{
                        "name": role.name,
                        "color": f"#{role.color.value:06x}" if role.color.value != 0 else "#99AAB5"
                    } for role in member.roles if role.name != "@everyone"]
                    user_data["guild_roles"] = role_names
                    user_data["role_colors"] = role_colors
                    
                    # Determine highest role for display using role IDs and Discord roles
                    highest_role = get_highest_role(role_ids, member.roles)
                    user_data["highest_role"] = highest_role
                    
                    print(f"✅ Fetched Discord data for user {user_id}: nickname={member.nick}, roles={len(role_names)}, highest_role={highest_role['name']}, avatar={user_data['avatar']}")
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
    
    # If user not in database and not found in Discord, return 404
    if not user and not discord_member_found:
        raise HTTPException(status_code=404, detail="User not found in database or Discord server")
    
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

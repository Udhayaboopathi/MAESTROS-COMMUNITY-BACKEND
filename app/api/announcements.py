"""
Discord Announcement Manager Router
Allows managers/admins to send customizable embed announcements
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Dict, Optional
from datetime import datetime
from app.core.database import get_database
from app.utils import require_manager_or_admin, get_discord_bot, DiscordRoles
from app.core.models import AnnouncementCreate, AnnouncementLog
import discord
import os

router = APIRouter()

# ==========================================
# Helper Functions
# ==========================================

def hex_to_discord_color(hex_color: str) -> int:
    """Convert HEX color to Discord integer"""
    try:
        hex_color = hex_color.lstrip('#')
        return int(hex_color, 16)
    except:
        return 0x5865F2  # Discord blurple default

async def check_bot_permissions(channel: discord.TextChannel) -> Dict[str, bool]:
    """Check if bot has required permissions in channel"""
    permissions = channel.permissions_for(channel.guild.me)
    return {
        "send_messages": permissions.send_messages,
        "embed_links": permissions.embed_links,
        "mention_everyone": permissions.mention_everyone,
        "mention_roles": True,  # Usually allowed if send_messages is true
    }

async def log_announcement(db, announcement_data: dict, success: bool, error: Optional[str] = None):
    """Log announcement to database for audit trail"""
    log_entry = {
        **announcement_data,
        "success": success,
        "error_message": error,
        "timestamp": datetime.utcnow()
    }
    await db.announcement_logs.insert_one(log_entry)

# ==========================================
# API Endpoints
# ==========================================

@router.get("/guilds")
async def get_guilds(
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Get all guilds the bot is connected to"""
    bot = get_discord_bot(request)
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guilds = []
    for guild in bot.bot.guilds:
        guilds.append({
            "id": str(guild.id),
            "name": guild.name,
            "icon": str(guild.icon.url) if guild.icon else None,
            "member_count": guild.member_count,
        })
    
    return {"guilds": guilds}

@router.get("/guilds/{guild_id}/channels")
async def get_guild_channels(
    guild_id: str,
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Get all text channels in a guild"""
    bot = get_discord_bot(request)
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild = bot.bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    channels = []
    for channel in guild.text_channels:
        # Check bot permissions
        permissions = await check_bot_permissions(channel)
        
        channels.append({
            "id": str(channel.id),
            "name": channel.name,
            "category": channel.category.name if channel.category else "Uncategorized",
            "position": channel.position,
            "permissions": permissions,
            "can_send": permissions["send_messages"] and permissions["embed_links"]
        })
    
    # Sort by category and position
    channels.sort(key=lambda x: (x["category"], x["position"]))
    
    return {"channels": channels}

@router.get("/guilds/{guild_id}/roles")
async def get_guild_roles(
    guild_id: str,
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Get all roles in a guild for mention selection"""
    bot = get_discord_bot(request)
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild = bot.bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    roles = []
    for role in guild.roles:
        if role.name != "@everyone":  # Exclude @everyone from list
            roles.append({
                "id": str(role.id),
                "name": role.name,
                "color": str(role.color),
                "position": role.position,
                "mentionable": role.mentionable,
                "member_count": len(role.members)
            })
    
    # Sort by position (highest first)
    roles.sort(key=lambda x: x["position"], reverse=True)
    
    return {"roles": roles}

@router.get("/guilds/{guild_id}/members/search")
async def search_guild_members(
    guild_id: str,
    query: str,
    request: Request,
    limit: int = 20,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Search guild members for mention selection"""
    bot = get_discord_bot(request)
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild = bot.bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    query_lower = query.lower()
    members = []
    
    for member in guild.members:
        if member.bot:
            continue
            
        # Search by username or display name
        if (query_lower in member.name.lower() or 
            query_lower in member.display_name.lower()):
            members.append({
                "id": str(member.id),
                "username": member.name,
                "display_name": member.display_name,
                "discriminator": member.discriminator if member.discriminator != '0' else None,
                "avatar": str(member.avatar.url) if member.avatar else None,
            })
            
            if len(members) >= limit:
                break
    
    return {"members": members}

@router.post("/send")
async def send_announcement(
    announcement: AnnouncementCreate,
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Send announcement with embed to selected channel"""
    bot = get_discord_bot(request)
    db = get_database()
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    # Get guild and channel
    guild = bot.bot.get_guild(int(announcement.guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    channel = guild.get_channel(int(announcement.channel_id))
    if not channel or not isinstance(channel, discord.TextChannel):
        raise HTTPException(status_code=404, detail="Text channel not found")
    
    # Check permissions
    permissions = await check_bot_permissions(channel)
    if not permissions["send_messages"] or not permissions["embed_links"]:
        raise HTTPException(
            status_code=403, 
            detail="Bot lacks required permissions (Send Messages, Embed Links)"
        )
    
    # Check @everyone/@here permission if needed
    if (announcement.mentions.everyone or announcement.mentions.here) and not permissions["mention_everyone"]:
        raise HTTPException(
            status_code=403,
            detail="Bot lacks permission to mention @everyone/@here"
        )
    
    # Build embed
    embed = discord.Embed()
    
    if announcement.embed.title:
        embed.title = announcement.embed.title
    
    if announcement.embed.description:
        embed.description = announcement.embed.description
    
    if announcement.embed.color:
        embed.color = hex_to_discord_color(announcement.embed.color)
    
    if announcement.embed.thumbnail_url:
        embed.set_thumbnail(url=announcement.embed.thumbnail_url)
    
    if announcement.embed.image_url:
        embed.set_image(url=announcement.embed.image_url)
    
    if announcement.embed.footer_text:
        embed.set_footer(
            text=announcement.embed.footer_text,
            icon_url=announcement.embed.footer_icon_url
        )
    
    if announcement.embed.author_name:
        embed.set_author(
            name=announcement.embed.author_name,
            icon_url=announcement.embed.author_icon_url
        )
    
    if announcement.embed.timestamp:
        embed.timestamp = datetime.utcnow()
    
    # Add fields
    for field in announcement.embed.fields:
        embed.add_field(
            name=field.name,
            value=field.value,
            inline=field.inline
        )
    
    # Build mention message
    mention_parts = []
    
    if announcement.mentions.everyone:
        mention_parts.append("@everyone")
    
    if announcement.mentions.here:
        mention_parts.append("@here")
    
    for role_id in announcement.mentions.role_ids:
        role = guild.get_role(int(role_id))
        if role:
            mention_parts.append(role.mention)
    
    for user_id in announcement.mentions.user_ids:
        mention_parts.append(f"<@{user_id}>")
    
    # Combine content with mentions
    final_content = announcement.content or ""
    if mention_parts:
        mention_string = " ".join(mention_parts)
        final_content = f"{mention_string}\n{final_content}" if final_content else mention_string
    
    # Send message
    try:
        sent_message = await channel.send(content=final_content or None, embed=embed)
        
        # Log success
        await log_announcement(db, {
            "manager_id": current_user.get("discord_id"),
            "manager_username": current_user.get("username"),
            "guild_id": announcement.guild_id,
            "guild_name": guild.name,
            "channel_id": announcement.channel_id,
            "channel_name": channel.name,
            "embed_summary": {
                "title": announcement.embed.title,
                "description": announcement.embed.description[:100] if announcement.embed.description else None,
                "fields_count": len(announcement.embed.fields)
            },
            "mentions": {
                "everyone": announcement.mentions.everyone,
                "here": announcement.mentions.here,
                "roles_count": len(announcement.mentions.role_ids),
                "users_count": len(announcement.mentions.user_ids)
            },
            "content": announcement.content
        }, success=True)
        
        return {
            "success": True,
            "message_id": str(sent_message.id),
            "channel_name": channel.name,
            "guild_name": guild.name,
            "message_url": sent_message.jump_url
        }
        
    except discord.Forbidden as e:
        error_msg = f"Permission denied: {str(e)}"
        await log_announcement(db, {
            "manager_id": current_user.get("discord_id"),
            "manager_username": current_user.get("username"),
            "guild_id": announcement.guild_id,
            "guild_name": guild.name,
            "channel_id": announcement.channel_id,
            "channel_name": channel.name,
            "embed_summary": {},
            "mentions": {}
        }, success=False, error=error_msg)
        
        raise HTTPException(status_code=403, detail=error_msg)
        
    except Exception as e:
        error_msg = f"Failed to send message: {str(e)}"
        await log_announcement(db, {
            "manager_id": current_user.get("discord_id"),
            "manager_username": current_user.get("username"),
            "guild_id": announcement.guild_id,
            "guild_name": guild.name,
            "channel_id": announcement.channel_id,
            "channel_name": channel.name,
            "embed_summary": {},
            "mentions": {}
        }, success=False, error=error_msg)
        
        raise HTTPException(status_code=500, detail=error_msg)

@router.get("/logs")
async def get_announcement_logs(
    request: Request,
    limit: int = 50,
    skip: int = 0,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Get announcement logs for audit trail"""
    db = get_database()
    
    logs = await db.announcement_logs.find().sort("timestamp", -1).skip(skip).limit(limit).to_list(length=limit)
    total = await db.announcement_logs.count_documents({})
    
    return {
        "logs": logs,
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit
    }

@router.get("/logs/{log_id}")
async def get_announcement_log_detail(
    log_id: str,
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Get detailed announcement log"""
    from bson import ObjectId
    db = get_database()
    
    log = await db.announcement_logs.find_one({"_id": ObjectId(log_id)})
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    
    return log


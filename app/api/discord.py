from fastapi import APIRouter, HTTPException, Request
from typing import Dict, List
from pydantic import BaseModel
from app.core.database import get_database
from app.utils import get_discord_bot, DiscordRoles
from app.config import settings
import discord

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

@router.get("/guild/members")
async def get_all_guild_members(request: Request):
    """Get ALL members from Discord guild who have CEO, Manager, or Member role (regardless of online status)"""
    # Get Discord bot instance using centralized helper
    discord_bot = get_discord_bot(request)
    
    if not discord_bot or not discord_bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    # Use centralized role constants
    CEO_ROLE_ID = DiscordRoles.CEO_ROLE_ID
    MANAGER_ROLE_ID = DiscordRoles.MANAGER_ROLE_ID
    MEMBER_ROLE_ID = DiscordRoles.MEMBER_ROLE_ID
    
    # Get guild
    guild_id = int(settings.discord_guild_id)
    guild = discord_bot.bot.get_guild(guild_id)
    
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    # Fetch all guild members (this may be cached)
    all_members = []
    db = get_database()
    
    for member in guild.members:
        if member.bot:
            continue
            
        member_role_ids = [role.id for role in member.roles]
        
        # Only include members with CEO, Manager, or Member role
        has_role = (
            (CEO_ROLE_ID and CEO_ROLE_ID in member_role_ids) or
            (MANAGER_ROLE_ID and MANAGER_ROLE_ID in member_role_ids) or
            (MEMBER_ROLE_ID and MEMBER_ROLE_ID in member_role_ids)
        )
        
        if not has_role:
            continue
        
        # Determine online status
        is_online = str(member.status) != 'offline'
        
        # Create member info
        member_info = {
            'display_name': str(member.display_name),
            'username': str(member.name),
            'discriminator': str(member.discriminator) if member.discriminator != '0' else None,
            'discord_id': str(member.id),
            'avatar': str(member.avatar.key) if member.avatar else None,
            'guild_roles': [str(role_id) for role_id in member_role_ids],
            'is_online': is_online,
        }
        
        # Add permissions info
        is_ceo = CEO_ROLE_ID and CEO_ROLE_ID in member_role_ids
        is_manager = MANAGER_ROLE_ID and MANAGER_ROLE_ID in member_role_ids
        is_admin = any('admin' in role.name.lower() for role in member.roles)
        
        member_info['permissions'] = {
            'is_ceo': is_ceo,
            'is_manager': is_manager,
            'is_admin': is_admin,
            'can_manage_applications': is_manager or is_ceo or is_admin
        }
        
        # Fetch additional user data from database if available
        if db is not None:
            try:
                user_data = await db.users.find_one({'discord_id': str(member.id)})
                if user_data:
                    member_info.update({
                        'level': user_data.get('level', 1),
                        'xp': user_data.get('xp', 0),
                        'badges': user_data.get('badges', []),
                        'joined_at': user_data.get('joined_at').isoformat() if user_data.get('joined_at') else None,
                        'last_login': user_data.get('last_login').isoformat() if user_data.get('last_login') else None,
                    })
            except Exception as e:
                print(f'⚠️ Error fetching user data for {member.name}: {e}')
        
        all_members.append(member_info)
    
    return {
        "total_members": len(all_members),
        "members": all_members
    }

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

@router.get("/guilds")
async def get_guilds(request: Request):
    """Get list of Discord guilds the bot is in"""
    discord_bot = get_discord_bot(request)
    
    if not discord_bot or not discord_bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guilds = []
    for guild in discord_bot.bot.guilds:
        guilds.append({
            "id": str(guild.id),
            "name": guild.name
        })
    
    return guilds

@router.get("/guilds/{guild_id}/channels")
async def get_guild_channels(guild_id: str, request: Request):
    """Get list of channels in a guild"""
    discord_bot = get_discord_bot(request)
    
    if not discord_bot or not discord_bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild = discord_bot.bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    channels = []
    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel):
            channels.append({
                "id": str(channel.id),
                "name": channel.name,
                "type": 0  # Text channel
            })
    
    return channels

@router.get("/guilds/{guild_id}/roles")
async def get_guild_roles(guild_id: str, request: Request):
    """Get list of roles in a guild"""
    discord_bot = get_discord_bot(request)
    
    if not discord_bot or not discord_bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild = discord_bot.bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    roles = []
    for role in guild.roles:
        if role.name != "@everyone":
            roles.append({
                "id": str(role.id),
                "name": role.name
            })
    
    return roles

@router.get("/guilds/{guild_id}/members")
async def get_guild_members_list(guild_id: str, request: Request):
    """Get list of members in a guild"""
    discord_bot = get_discord_bot(request)
    
    if not discord_bot or not discord_bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild = discord_bot.bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    members = []
    for member in guild.members:
        if not member.bot:
            members.append({
                "user": {
                    "id": str(member.id),
                    "username": member.name,
                    "discriminator": member.discriminator if member.discriminator != '0' else '0000',
                    "display_name": member.display_name
                }
            })
    
    return members

class AnnouncementRequest(BaseModel):
    channel_id: str
    content: str = ""
    mention_everyone: bool = False
    mention_here: bool = False
    mention_roles: List[str] = []
    mention_users: List[str] = []
    embed: Dict = None

@router.post("/send-announcement")
async def send_announcement(request: Request, data: AnnouncementRequest):
    """Send announcement to Discord channel"""
    discord_bot = get_discord_bot(request)
    
    if not discord_bot or not discord_bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    try:
        channel = discord_bot.bot.get_channel(int(data.channel_id))
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        # Build message content with mentions
        message_content = data.content
        
        if data.mention_everyone:
            message_content = f"@everyone {message_content}"
        elif data.mention_here:
            message_content = f"@here {message_content}"
        
        # Add role mentions
        if data.mention_roles:
            role_mentions = " ".join([f"<@&{role_id}>" for role_id in data.mention_roles])
            message_content = f"{role_mentions} {message_content}"
        
        # Add user mentions
        if data.mention_users:
            user_mentions = " ".join([f"<@{user_id}>" for user_id in data.mention_users])
            message_content = f"{user_mentions} {message_content}"
        
        # Create embed if provided
        embed_obj = None
        if data.embed:
            # Only create embed if there's actual content
            title = data.embed.get("title") if data.embed.get("title") else None
            description = data.embed.get("description") if data.embed.get("description") else None
            
            # Discord requires at least title or description
            if title or description:
                embed_obj = discord.Embed(
                    color=data.embed.get("color", 0xFFD700)
                )
                
                if title:
                    embed_obj.title = title
                if description:
                    embed_obj.description = description
                
                if data.embed.get("thumbnail") and data.embed["thumbnail"].get("url"):
                    try:
                        embed_obj.set_thumbnail(url=data.embed["thumbnail"]["url"])
                    except:
                        pass
                
                if data.embed.get("image") and data.embed["image"].get("url"):
                    try:
                        embed_obj.set_image(url=data.embed["image"]["url"])
                    except:
                        pass
                
                if data.embed.get("footer") and data.embed["footer"].get("text"):
                    embed_obj.set_footer(text=data.embed["footer"]["text"])
                
                if data.embed.get("author") and data.embed["author"].get("name"):
                    embed_obj.set_author(name=data.embed["author"]["name"])
                
                if data.embed.get("fields"):
                    for field in data.embed["fields"]:
                        if field.get("name") and field.get("value"):
                            embed_obj.add_field(
                                name=field.get("name"),
                                value=field.get("value"),
                                inline=field.get("inline", False)
                            )
        
        # Send message
        if embed_obj and message_content.strip():
            await channel.send(content=message_content.strip(), embed=embed_obj)
        elif embed_obj:
            await channel.send(embed=embed_obj)
        elif message_content.strip():
            await channel.send(content=message_content.strip())
        else:
            raise HTTPException(status_code=400, detail="Message must have content or embed")
        
        return {"success": True, "message": "Announcement sent successfully"}
    
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Bot doesn't have permission to send messages in that channel")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send announcement: {str(e)}")

class ServerInviteRequest(BaseModel):
    server_name: str
    owner_name: str
    discord_id: str
    server_description: str
    player_count: str = ""
    server_ip: str = ""
    additional_info: str = ""

@router.post("/send-invite-request")
async def send_invite_request(request: Request, data: ServerInviteRequest):
    """Send RP Server invite request to Discord channel"""
    # Get Discord bot instance using centralized helper
    discord_bot = get_discord_bot(request)
    
    if not discord_bot or not discord_bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    # Get channel ID from settings
    channel_id = settings.rp_invite_channel_id
    if not channel_id:
        raise HTTPException(status_code=500, detail="RP invite channel not configured")
    
    try:
        # Get the channel
        channel = discord_bot.bot.get_channel(int(channel_id))
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        # Create vertical embed layout
        embed = discord.Embed(
            title="🌟 New Partnership Opportunity",
            description=f"> **{data.server_name}**\n> Looking to partner with Maestros Community!",
            color=0xFF6B6B  # Vibrant red/coral
        )
        
        # All fields in vertical layout (inline=False)
        embed.add_field(name="👤 Server Owner", value=data.owner_name, inline=False)
        embed.add_field(name="🔗 Discord ID", value=f"`{data.discord_id}`", inline=False)
        
        if data.player_count:
            embed.add_field(name="👥 Community Size", value=data.player_count, inline=False)
        
        # Server description with clean formatting
        description_text = data.server_description[:500]
        embed.add_field(
            name="📖 Server Description",
            value=f"{description_text}",
            inline=False
        )
        
        # Additional info section
        if data.additional_info:
            embed.add_field(
                name="📌 Extra Information",
                value=f">>> {data.additional_info[:300]}",
                inline=False
            )
        
        embed.set_author(name="RP Server Partnership Request", icon_url="https://cdn-icons-png.flaticon.com/512/2666/2666505.png")
        embed.set_footer(text="Review and respond • Maestros Community")
        embed.timestamp = discord.utils.utcnow()
        
        # Send embed
        await channel.send(embed=embed)
        
        # Send Server IP as a separate normal message if provided
        if data.server_ip:
            await channel.send(f"{data.server_ip}")
        
        return {"success": True, "message": "Request sent successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send request: {str(e)}")


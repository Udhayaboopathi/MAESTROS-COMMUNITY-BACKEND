from fastapi import APIRouter, HTTPException, Request
from typing import Dict, List
from pydantic import BaseModel
from database import get_database
from utils import get_discord_bot, DiscordRoles
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
    guild_id = int(os.getenv('DISCORD_GUILD_ID'))
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
    discord_bot = getattr(request.app.state, 'discord_bot', None)
    if not discord_bot:
        discord_bot = get_bot_instance()
    
    if not discord_bot or not discord_bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    # Get channel ID from environment variable
    channel_id = os.getenv('RP_INVITE_CHANNEL_ID')
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

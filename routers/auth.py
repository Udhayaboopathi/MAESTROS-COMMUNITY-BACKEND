from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from typing import List
import aiohttp
from datetime import datetime, timedelta

from config import settings
from database import get_database
from utils import create_access_token, get_current_user, get_discord_bot
from models import UserCreate, User

router = APIRouter()

@router.get("/login")
async def login():
    """Initiate Discord OAuth login - returns redirect URL"""
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={settings.discord_client_id}"
        f"&redirect_uri={settings.discord_redirect_uri}"
        f"&response_type=code"
        f"&scope=identify email guilds"
    )
    return RedirectResponse(url=discord_auth_url)

@router.get("/callback")
async def callback(code: str, request: Request):
    """Handle Discord OAuth callback and redirect to frontend with token"""
    try:
        # Determine frontend URL from settings or referer
        frontend_url = settings.frontend_url
        
        # If frontend_url not set, try to extract from referer
        if not frontend_url:
            referer = request.headers.get("referer", "")
            if referer:
                from urllib.parse import urlparse
                parsed = urlparse(referer)
                frontend_url = f"{parsed.scheme}://{parsed.netloc}"
            else:
                raise HTTPException(status_code=500, detail="Frontend URL not configured")
        
        async with aiohttp.ClientSession() as session:
            # Exchange code for access token
            token_url = "https://discord.com/api/oauth2/token"
            data = {
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord_redirect_uri,
            }
            
            async with session.post(token_url, data=data) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"❌ Token exchange failed: {error_text}")
                    return RedirectResponse(url=f"{frontend_url}/?error=token_failed")
                token_data = await resp.json()
            
            # Get user info from Discord
            headers = {"Authorization": f"Bearer {token_data['access_token']}"}
            
            async with session.get("https://discord.com/api/users/@me", headers=headers) as resp:
                if resp.status != 200:
                    return RedirectResponse(url=f"{frontend_url}/?error=user_info_failed")
                user_data = await resp.json()
            
            # Get user guilds
            async with session.get("https://discord.com/api/users/@me/guilds", headers=headers) as resp:
                if resp.status == 200:
                    guilds = await resp.json()
                    is_member = any(g["id"] == settings.discord_guild_id for g in guilds)
                else:
                    is_member = False
            
            # Get guild member data to fetch roles (requires bot token)
            guild_roles = []
            display_name = user_data["username"]  # Default to username
            if is_member:
                bot_headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
                guild_member_url = f"https://discord.com/api/v10/guilds/{settings.discord_guild_id}/members/{user_data['id']}"
                
                try:
                    async with session.get(guild_member_url, headers=bot_headers) as resp:
                        if resp.status == 200:
                            member_data = await resp.json()
                            guild_roles = member_data.get("roles", [])
                            # Get server nickname (nick) or global display name, fallback to username
                            nick = member_data.get("nick")
                            global_name = user_data.get("global_name")
                            display_name = nick or global_name or user_data["username"]
                            print(f"✅ Fetched roles for {user_data['username']}: {guild_roles}")
                            print(f"   Server Nickname: {nick if nick else 'Not set'}")
                            print(f"   Global Display Name: {global_name if global_name else 'Not set'}")
                            print(f"   Display Name used: {display_name}")
                        else:
                            print(f"⚠️ Could not fetch guild member data: {resp.status}")
                except Exception as e:
                    print(f"⚠️ Error fetching guild roles: {str(e)}")
        
        # Create or update user in database (no display_name - fetch in real-time)
        db = get_database()
        existing_user = await db.users.find_one({"discord_id": user_data["id"]})
        
        user_dict = {
            "discord_id": user_data["id"],
            "username": user_data["username"],
            "discriminator": user_data.get("discriminator", "0"),
            "avatar": user_data.get("avatar"),
            "email": user_data.get("email"),
            "last_login": datetime.utcnow(),
            "guild_roles": guild_roles,  
        }
        
        if existing_user:
            # Update existing user
            await db.users.update_one(
                {"discord_id": user_data["id"]},
                {"$set": user_dict}
            )
            user = await db.users.find_one({"discord_id": user_data["id"]})
        else:
            # Create new user
            user_dict.update({
                "roles": [],
                "guild_roles": [],
                "xp": 0,
                "level": 1,
                "badges": [],
                "joined_at": datetime.utcnow(),
            })
            result = await db.users.insert_one(user_dict)
            user = await db.users.find_one({"_id": result.inserted_id})
        
        # Create JWT token
        access_token = create_access_token(
            data={"sub": user_data["id"]},
            expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes)
        )
        
        # Redirect to frontend with token
        redirect_url = f"{frontend_url}/?token={access_token}"
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        print(f"❌ OAuth callback error: {str(e)}")
        # Use frontend_url from settings or referer
        fallback_url = settings.frontend_url or locals().get('frontend_url', '')
        if fallback_url:
            return RedirectResponse(url=f"{fallback_url}/?error=auth_failed")
        else:
            raise HTTPException(status_code=500, detail="OAuth callback failed and frontend URL not configured")

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user), request: Request = None):
    """Get current user info with role details - fetches live data from Discord"""
    guild_roles = current_user.get("guild_roles", [])
    
    # Check if user is manager or CEO using role IDs (stored as strings in guild_roles)
    is_manager = settings.manager_role_id in [str(role) for role in guild_roles]
    is_ceo = settings.ceo_role_id in [str(role) for role in guild_roles]
    is_admin = current_user.get("discord_id") in settings.admin_ids_list
    
    # Fetch comprehensive Discord user data
    display_name = current_user["username"]
    avatar = current_user.get("avatar")
    discord_details = {}
    
    # Try to get Discord bot instance for live data using centralized helper
    discord_bot = get_discord_bot(request) if request else None
    
    # Fetch from Discord bot if available
    if discord_bot and hasattr(discord_bot, 'bot') and discord_bot.bot and discord_bot.is_ready:
        try:
            guild = discord_bot.bot.get_guild(discord_bot.guild_id)
            if guild:
                member = guild.get_member(int(current_user['discord_id']))
                if member:
                    # Update avatar from Discord member
                    if member.avatar:
                        avatar = member.avatar.key
                    
                    # Get role names
                    role_names = [role.name for role in member.roles if role.name != "@everyone"]
                    guild_roles = role_names
                    
                    discord_details = {
                        "global_name": member.global_name,
                        "server_nickname": member.nick,
                        "server_avatar": member.guild_avatar.key if member.guild_avatar else None,
                        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                        "premium_since": member.premium_since.isoformat() if member.premium_since else None,
                    }
                    
                    # Priority for display name
                    display_name = member.nick or member.global_name or current_user["username"]
                    print(f"✅ /me endpoint - Fetched Discord data for {current_user['discord_id']}: avatar={avatar}, nickname={member.nick}")
        except Exception as e:
            print(f"⚠️ Bot fetch failed in /me, falling back to API: {str(e)}")
    
    # Fallback to Discord API if bot not available
    if not discord_details:
        try:
            async with aiohttp.ClientSession() as session:
                # Get user data for global info
                user_headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
                user_url = f"https://discord.com/api/v10/users/{current_user['discord_id']}"
                
                async with session.get(user_url, headers=user_headers) as user_resp:
                    if user_resp.status == 200:
                        user_info = await user_resp.json()
                        if not avatar and user_info.get("avatar"):
                            avatar = user_info.get("avatar")
                        discord_details = {
                            "global_name": user_info.get("global_name"),
                            "avatar_hash": user_info.get("avatar"),
                            "banner": user_info.get("banner"),
                            "banner_color": user_info.get("banner_color"),
                            "accent_color": user_info.get("accent_color"),
                            "bot": user_info.get("bot", False),
                            "public_flags": user_info.get("public_flags", 0),
                        }
                
                # Get guild member data for server-specific info
                guild_member_url = f"https://discord.com/api/v10/guilds/{settings.discord_guild_id}/members/{current_user['discord_id']}"
                
                async with session.get(guild_member_url, headers=user_headers) as resp:
                    if resp.status == 200:
                        member_data = await resp.json()
                        discord_details.update({
                            "server_nickname": member_data.get("nick"),
                            "server_avatar": member_data.get("avatar"),
                            "joined_at": member_data.get("joined_at"),
                            "premium_since": member_data.get("premium_since"),
                            "pending": member_data.get("pending", False),
                            "communication_disabled_until": member_data.get("communication_disabled_until"),
                        })
                        
                        # Priority for display name
                        display_name = member_data.get("nick") or discord_details.get("global_name") or current_user["username"]
        except Exception as e:
            print(f"⚠️ Could not fetch Discord details: {str(e)}")
    
    return {
        "id": str(current_user["_id"]),
        "discord_id": current_user["discord_id"],
        "username": current_user["username"],
        "display_name": display_name,
        "discriminator": current_user.get("discriminator", "0"),
        "avatar": avatar,
        "email": current_user.get("email"),
        "roles": current_user.get("roles", []),
        "guild_roles": guild_roles,
        "xp": current_user.get("xp", 0),
        "level": current_user.get("level", 1),
        "badges": current_user.get("badges", []),
        "joined_at": current_user.get("joined_at"),
        "last_login": current_user.get("last_login"),
        "discord_details": discord_details,  # All Discord-specific info
        "permissions": {
            "is_admin": is_admin,
            "is_ceo": is_ceo,
            "is_manager": is_manager,
            "can_manage_applications": is_admin or is_ceo or is_manager
        }
    }

@router.post("/sync-roles")
async def sync_user_roles(current_user: dict = Depends(get_current_user)):
    """Sync user's Discord guild roles"""
    import aiohttp
    
    db = get_database()
    bot_headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
    guild_member_url = f"https://discord.com/api/v10/guilds/{settings.discord_guild_id}/members/{current_user['discord_id']}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(guild_member_url, headers=bot_headers) as resp:
                if resp.status == 200:
                    member_data = await resp.json()
                    guild_roles = member_data.get("roles", [])
                    
                    # Update user's guild roles
                    await db.users.update_one(
                        {"discord_id": current_user["discord_id"]},
                        {"$set": {"guild_roles": guild_roles}}
                    )
                    
                    print(f"✅ Synced roles for {current_user['username']}: {guild_roles}")
                    
                    # Check permissions using role IDs (stored as strings)
                    is_manager = settings.manager_role_id in [str(role) for role in guild_roles]
                    is_ceo = settings.ceo_role_id in [str(role) for role in guild_roles]
                    is_admin = current_user.get("discord_id") in settings.admin_ids_list
                    
                    return {
                        "message": "Roles synced successfully",
                        "guild_roles": guild_roles,
                        "permissions": {
                            "is_admin": is_admin,
                            "is_ceo": is_ceo,
                            "is_manager": is_manager,
                            "can_manage_applications": is_admin or is_ceo or is_manager
                        }
                    }
                else:
                    raise HTTPException(status_code=400, detail="Failed to fetch guild member data")
    except Exception as e:
        print(f"❌ Role sync error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to sync roles")

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout user"""
    # In a JWT-based system, logout is handled client-side by removing the token
    return {"message": "Logged out successfully"}

@router.post("/refresh")
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """Refresh access token"""
    access_token = create_access_token(
        data={"sub": current_user["discord_id"]},
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    return {"access_token": access_token, "token_type": "bearer"}

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from typing import List
import aiohttp
from datetime import datetime, timedelta

from config import settings
from database import get_database
from utils import create_access_token, get_current_user
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
async def callback(code: str):
    """Handle Discord OAuth callback and redirect to frontend with token"""
    try:
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
                    return RedirectResponse(url=f"{settings.frontend_url}/?error=token_failed")
                token_data = await resp.json()
            
            # Get user info from Discord
            headers = {"Authorization": f"Bearer {token_data['access_token']}"}
            
            async with session.get("https://discord.com/api/users/@me", headers=headers) as resp:
                if resp.status != 200:
                    return RedirectResponse(url=f"{settings.frontend_url}/?error=user_info_failed")
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
            if is_member:
                bot_headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
                guild_member_url = f"https://discord.com/api/v10/guilds/{settings.discord_guild_id}/members/{user_data['id']}"
                
                try:
                    async with session.get(guild_member_url, headers=bot_headers) as resp:
                        if resp.status == 200:
                            member_data = await resp.json()
                            guild_roles = member_data.get("roles", [])
                            print(f"✅ Fetched roles for {user_data['username']}: {guild_roles}")
                        else:
                            print(f"⚠️ Could not fetch guild member data: {resp.status}")
                except Exception as e:
                    print(f"⚠️ Error fetching guild roles: {str(e)}")
        
        # Create or update user in database
        db = get_database()
        
        user_dict = {
            "discord_id": user_data["id"],
            "username": user_data["username"],
            "discriminator": user_data.get("discriminator", "0"),
            "avatar": user_data.get("avatar"),
            "email": user_data.get("email"),
            "last_login": datetime.utcnow(),
            "guild_roles": guild_roles,  
        }
        
        existing_user = await db.users.find_one({"discord_id": user_data["id"]})
        
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
        frontend_url = f"{settings.frontend_url}/?token={access_token}"
        return RedirectResponse(url=frontend_url)
        
    except Exception as e:
        print(f"❌ OAuth callback error: {str(e)}")
        return RedirectResponse(url=f"{settings.frontend_url}/?error=auth_failed")

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info with role details"""
    guild_roles = current_user.get("guild_roles", [])
    
    # Check if user is manager or CEO
    is_manager = settings.manager_role_id in guild_roles
    is_ceo = settings.ceo_role_id in guild_roles
    is_admin = current_user.get("discord_id") in settings.admin_ids_list
    
    return {
        "id": str(current_user["_id"]),
        "discord_id": current_user["discord_id"],
        "username": current_user["username"],
        "discriminator": current_user.get("discriminator", "0"),
        "avatar": current_user.get("avatar"),
        "roles": current_user.get("roles", []),
        "guild_roles": guild_roles,
        "xp": current_user.get("xp", 0),
        "level": current_user.get("level", 1),
        "badges": current_user.get("badges", []),
        "joined_at": current_user.get("joined_at"),
        "last_login": current_user.get("last_login"),
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
                    
                    # Check permissions
                    is_manager = settings.manager_role_id in guild_roles
                    is_ceo = settings.ceo_role_id in guild_roles
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

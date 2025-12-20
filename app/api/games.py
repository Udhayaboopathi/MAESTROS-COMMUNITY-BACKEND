from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from app.core.database import get_database
from app.utils import get_current_user, require_manager_or_admin, get_discord_bot, DiscordRoles
from datetime import datetime
from pydantic import BaseModel
from app.cache import cache_game_data, invalidate_game_cache
import discord
import os

router = APIRouter()

class GameCreate(BaseModel):
    name: str
    description: str
    image_url: Optional[str] = None
    category: Optional[str] = None
    platform: Optional[str] = None
    clan: Optional[str] = None
    active: bool = True

class GameUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    platform: Optional[str] = None
    clan: Optional[str] = None
    active: Optional[bool] = None

@cache_game_data(ttl=600)  # Cache for 10 minutes
async def _get_games_cached(active_only: bool, limit: int, skip: int):
    """Internal cached function for getting games"""
    db = get_database()
    
    query = {"active": True} if active_only else {}
    # Use projection to only fetch needed fields for better performance
    games = await db.games.find(query, {
        "_id": 1, "name": 1, "description": 1, "image_url": 1,
        "category": 1, "platform": 1, "clan": 1, "active": 1
    }).skip(skip).limit(limit).to_list(limit)
    
    # Convert ObjectId to string
    for game in games:
        game["_id"] = str(game["_id"])
    
    return {"games": games, "count": len(games)}

@router.get("")
async def get_games(
    active_only: bool = False,
    limit: int = 100,
    skip: int = 0
):
    """Get all games (public endpoint) - with caching"""
    return await _get_games_cached(active_only, limit, skip)

@router.get("/{game_id}")
async def get_game(game_id: str):
    """Get a single game by ID"""
    db = get_database()
    
    from bson import ObjectId
    try:
        game = await db.games.find_one({"_id": ObjectId(game_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid game ID")
    
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game["_id"] = str(game["_id"])
    return game

@router.post("")
async def create_game(
    game_data: GameCreate,
    request: Request,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Create a new game and automatically create Discord category, role, and channels with specific structure"""
    
    db = get_database()
    
    game_dict = game_data.dict()
    game_dict.update({
        "created_by": current_user["discord_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    # Insert game into database first
    result = await db.games.insert_one(game_dict)
    
    # Invalidate game cache since we added a new game
    invalidate_game_cache()
    
    new_game = await db.games.find_one({"_id": result.inserted_id})
    new_game["_id"] = str(new_game["_id"])
    
    # Create Discord structures
    discord_info = {}
    try:
        discord_bot = get_discord_bot(request)
        
        if discord_bot and discord_bot.is_ready:
            import os
            guild_id = int(os.getenv('DISCORD_GUILD_ID'))
            guild = discord_bot.bot.get_guild(guild_id)
            
            if guild:
                # Get IDs from centralized sources
                COMMUNITY_CATEGORY_ID = int(os.getenv('COMMUNITY_CATEGORY_ID'))
                MEMBER_ROLE_ID = DiscordRoles.MEMBER_ROLE_ID
                EVERYONE_ROLE_ID = DiscordRoles.EVERYONE_ROLE_ID
                MANAGER_ROLE_ID = DiscordRoles.MANAGER_ROLE_ID
                CEO_ROLE_ID = DiscordRoles.CEO_ROLE_ID
                
                community_category = guild.get_channel(COMMUNITY_CATEGORY_ID)
                member_role = guild.get_role(MEMBER_ROLE_ID)  # This is the "Members" role shown in Discord
                everyone_role = guild.get_role(EVERYONE_ROLE_ID)
                manager_role = guild.get_role(MANAGER_ROLE_ID) if MANAGER_ROLE_ID else None
                ceo_role = guild.get_role(CEO_ROLE_ID) if CEO_ROLE_ID else None
                
                if not community_category:
                    raise Exception("Community category not found")
                
                # Generate short tag from game name (first letters of each word)
                game_words = game_data.name.split()
                short_tag = ''.join([word[0].upper() for word in game_words if word])
                
                # Step 1: Create game role
                # Position: Below Members role (the one with 19 members in your screenshot)
                target_role_position = member_role.position - 1 if member_role else 1  # -1 to place BELOW Members
                
                game_role = await guild.create_role(
                    name=game_data.name,
                    color=discord.Color.blue(),
                    mentionable=True,
                    reason=f"Auto-created for game: {game_data.name}"
                )
                
                # Move role to correct position (below member role)
                await game_role.edit(position=target_role_position)
                
                # Step 2: Create category with specific name format
                category_name = f"⭑⭑★✪ 💕{game_data.name}💕 ✪★⭑⭑"
                target_category_position = community_category.position + 1
                
                # Set up category permissions
                category_overwrites = {
                    everyone_role: discord.PermissionOverwrite(
                        view_channel=False,
                        send_messages=False,
                        connect=False,
                        speak=False
                    ),  # Everyone role has NO permissions
                    game_role: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_messages=True,
                        connect=True,
                        speak=True
                    )
                }
                
                # Add member role permissions if exists
                if member_role:
                    category_overwrites[member_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_messages=True,
                        connect=True,
                        speak=True
                    )
                
                # Add manager and CEO full permissions
                if manager_role:
                    category_overwrites[manager_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_messages=True,
                        connect=True,
                        speak=True,
                        manage_channels=True,
                        manage_permissions=True
                    )
                if ceo_role:
                    category_overwrites[ceo_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_messages=True,
                        connect=True,
                        speak=True,
                        manage_channels=True,
                        manage_permissions=True
                    )
                
                # Create category
                game_category = await guild.create_category(
                    name=category_name,
                    position=target_category_position,
                    overwrites=category_overwrites,
                    reason=f"Auto-created for game: {game_data.name}"
                )
                
                # Step 3: Create Announcement Channel
                announcement_overwrites = {
                    everyone_role: discord.PermissionOverwrite(view_channel=False, send_messages=False),
                    game_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),  # View only
                }
                
                if member_role:
                    announcement_overwrites[member_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)  # View only
                
                if manager_role:
                    announcement_overwrites[manager_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)  # Can send
                if ceo_role:
                    announcement_overwrites[ceo_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)  # Can send
                
                announcement_channel = await guild.create_text_channel(
                    name=f"📰｜{game_data.name} 𝐀𝚗𝚗𝚘𝚞𝚗𝚌𝚎𝚖𝚎𝚗𝚝𝚜",
                    category=game_category,
                    topic=f"Official announcements for {game_data.name} - Managers only",
                    overwrites=announcement_overwrites,
                    reason=f"Auto-created announcement channel for game: {game_data.name}"
                )
                
                # Step 4: Create Chat Channels
                chat_channel_1 = await guild.create_text_channel(
                    name=f"💌｜{short_tag} 𝐂𝚑𝚊𝚝 1",
                    category=game_category,
                    topic=f"General chat 1 for {game_data.name}",
                    reason=f"Auto-created chat channel for game: {game_data.name}"
                )
                
                chat_channel_2 = await guild.create_text_channel(
                    name=f"💌｜{short_tag} IC Name/ID",
                    category=game_category,
                    topic=f"IC Name/ID for {game_data.name}",
                    reason=f"Auto-created chat channel for game: {game_data.name}"
                )
                
                # Step 5: Create Voice Channels
                voice_channel_1 = await guild.create_voice_channel(
                    name=f"🔊｜{short_tag} 𝐕𝙲 1",
                    category=game_category,
                    reason=f"Auto-created voice channel for game: {game_data.name}"
                )
                
                voice_channel_2 = await guild.create_voice_channel(
                    name=f"🔊｜{short_tag} 𝐕𝙲 2",
                    category=game_category,
                    reason=f"Auto-created voice channel for game: {game_data.name}"
                )
                
                # Store Discord info in game document
                discord_info = {
                    "category_id": str(game_category.id),
                    "category_name": category_name,
                    "role_id": str(game_role.id),
                    "short_tag": short_tag,
                    "channels": {
                        "announcement": str(announcement_channel.id),
                        "chat_1": str(chat_channel_1.id),
                        "chat_2": str(chat_channel_2.id),
                        "voice_1": str(voice_channel_1.id),
                        "voice_2": str(voice_channel_2.id)
                    }
                }
                
                # Update game with Discord info
                await db.games.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"discord_info": discord_info}}
                )
                
                new_game["discord_info"] = discord_info
                
                print(f"✅ Successfully created Discord structures for game: {game_data.name}")
                print(f"   Category: {category_name}")
                print(f"   Role: {game_data.name} (positioned below Members role)")
                print(f"   Short Tag: {short_tag}")
                print(f"   Channels: 1 announcement, 2 chat, 2 voice")
                
    except Exception as e:
        print(f"❌ Failed to create Discord structures: {str(e)}")
        import traceback
        traceback.print_exc()
        # Don't fail the game creation if Discord creation fails
    
    return {
        "message": "Game created successfully",
        "game": new_game,
        "discord_created": bool(discord_info)
    }

@router.put("/{game_id}")
async def update_game(
    game_id: str,
    game_data: GameUpdate,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Update a game (Manager only)"""
    
    db = get_database()
    
    from bson import ObjectId
    try:
        game_oid = ObjectId(game_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid game ID")
    
    # Check if game exists
    existing_game = await db.games.find_one({"_id": game_oid})
    if not existing_game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Update only provided fields
    update_data = {k: v for k, v in game_data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    update_data["updated_by"] = current_user["discord_id"]
    
    await db.games.update_one({"_id": game_oid}, {"$set": update_data})
    
    # Invalidate game cache since we updated a game
    invalidate_game_cache()
    
    updated_game = await db.games.find_one({"_id": game_oid})
    updated_game["_id"] = str(updated_game["_id"])
    
    return {"message": "Game updated successfully", "game": updated_game}

@router.delete("/{game_id}")
async def delete_game(
    game_id: str,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Delete a game (Manager only) - Note: You need to manually delete the Discord category"""
    
    db = get_database()
    
    from bson import ObjectId
    try:
        game_oid = ObjectId(game_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid game ID")
    
    # Get game info before deletion
    game = await db.games.find_one({"_id": game_oid})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Delete game from database
    result = await db.games.delete_one({"_id": game_oid})
    
    # Invalidate game cache since we deleted a game
    invalidate_game_cache()
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Game not found")
    
    return {
        "message": "Game deleted successfully",
        "note": "Please manually delete the Discord category and role if needed"
    }


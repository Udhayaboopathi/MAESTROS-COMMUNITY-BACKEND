from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from database import get_database
from utils import get_current_user, require_manager_or_admin
from datetime import datetime
from pydantic import BaseModel

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

@router.get("")
async def get_games(
    active_only: bool = False,
    limit: int = 100,
    skip: int = 0
):
    """Get all games (public endpoint)"""
    db = get_database()
    
    query = {"active": True} if active_only else {}
    games = await db.games.find(query).skip(skip).limit(limit).to_list(limit)
    
    # Convert ObjectId to string
    for game in games:
        game["_id"] = str(game["_id"])
    
    return {"games": games, "count": len(games)}

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
    current_user: dict = Depends(require_manager_or_admin)
):
    """Create a new game (Manager only)"""
    
    db = get_database()
    
    game_dict = game_data.dict()
    game_dict.update({
        "created_by": current_user["discord_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    result = await db.games.insert_one(game_dict)
    
    new_game = await db.games.find_one({"_id": result.inserted_id})
    new_game["_id"] = str(new_game["_id"])
    
    return {"message": "Game created successfully", "game": new_game}

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
    
    updated_game = await db.games.find_one({"_id": game_oid})
    updated_game["_id"] = str(updated_game["_id"])
    
    return {"message": "Game updated successfully", "game": updated_game}

@router.delete("/{game_id}")
async def delete_game(
    game_id: str,
    current_user: dict = Depends(require_manager_or_admin)
):
    """Delete a game (Manager only)"""
    
    db = get_database()
    
    from bson import ObjectId
    try:
        game_oid = ObjectId(game_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid game ID")
    
    result = await db.games.delete_one({"_id": game_oid})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Game not found")
    
    return {"message": "Game deleted successfully"}

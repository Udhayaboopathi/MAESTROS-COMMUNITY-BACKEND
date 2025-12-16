from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from config import settings
from database import get_database

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def verify_token(token: str):
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    
    discord_id: str = payload.get("sub")
    if discord_id is None:
        raise credentials_exception
    
    db = get_database()
    user = await db.users.find_one({"discord_id": discord_id})
    
    if user is None:
        raise credentials_exception
    
    return user

async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    """Get current active user"""
    return current_user

async def require_admin(current_user: dict = Depends(get_current_user)):
    """Require admin role"""
    if current_user.get("discord_id") not in settings.admin_ids_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

async def require_manager_or_admin(current_user: dict = Depends(get_current_user)):
    """Require Manager role or Admin - for application reviews"""
    discord_id = current_user.get("discord_id")
    
    # Check if user is admin
    if discord_id in settings.admin_ids_list:
        return current_user
    
    # Check if user has Manager or CEO role from guild_roles
    guild_roles = current_user.get("guild_roles", [])
    manager_role_id = settings.manager_role_id
    ceo_role_id = settings.ceo_role_id
    
    # Convert role IDs to strings for comparison
    guild_role_strs = [str(role) for role in guild_roles]
    
    if manager_role_id in guild_role_strs or ceo_role_id in guild_role_strs:
        return current_user
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Manager or Admin access required"
    )

def calculate_level(xp: int) -> int:
    """Calculate level from XP"""
    import math
    return int(math.sqrt(xp / 100))

def xp_for_level(level: int) -> int:
    """Calculate XP needed for level"""
    return level ** 2 * 100

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.config import settings
from app.core.database import get_database

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
    discord_id = current_user.get("discord_id")
    # Convert to int for comparison with admin_ids_list (which contains integers)
    try:
        discord_id_int = int(discord_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    if discord_id_int not in settings.admin_ids_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

async def require_manager_or_admin(current_user: dict = Depends(get_current_user)):
    """Require Manager role or Admin - for application reviews"""
    discord_id = current_user.get("discord_id")
    
    # Check if user is admin (convert to int for comparison)
    try:
        discord_id_int = int(discord_id)
        if discord_id_int in settings.admin_ids_list:
            return current_user
    except (ValueError, TypeError):
        pass  # Continue to role check
    
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

# ==========================================
# Discord Bot Helpers (Centralized)
# ==========================================

def get_discord_bot(request = None):
    """
    Get Discord bot instance - centralized helper to avoid duplication
    
    Args:
        request: Optional FastAPI Request object
        
    Returns:
        DiscordBot instance or None
    """
    # Try to get from request state first
    if request:
        bot = getattr(request.app.state, 'discord_bot', None)
        if bot:
            return bot
    
    # Fallback: import from main
    try:
        import main
        return main.discord_bot
    except (ImportError, AttributeError):
        return None

class DiscordRoles:
    """Centralized Discord role IDs - loaded once from environment"""
    _loaded = False
    CEO_ROLE_ID: int = 0
    MANAGER_ROLE_ID: int = 0
    MEMBER_ROLE_ID: int = 0
    APPLICATION_PENDING_ROLE_ID: int = 0
    EVERYONE_ROLE_ID: int = 0
    
    @classmethod
    def load(cls):
        """Load role IDs from environment variables"""
        if not cls._loaded:
            import os
            cls.CEO_ROLE_ID = int(os.getenv('CEO_ROLE_ID', 0))
            cls.MANAGER_ROLE_ID = int(os.getenv('MANAGER_ROLE_ID', 0))
            cls.MEMBER_ROLE_ID = int(os.getenv('MEMBER_ROLE_ID', 0))
            cls.APPLICATION_PENDING_ROLE_ID = int(os.getenv('APPLICATION_PENDING_ROLE_ID', 0))
            cls.EVERYONE_ROLE_ID = int(os.getenv('EVERYONE_ROLE_ID', 0))
            cls._loaded = True
        return cls

# Load role IDs on module import
DiscordRoles.load()


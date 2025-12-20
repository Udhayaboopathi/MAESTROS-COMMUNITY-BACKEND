"""Debug script to decode JWT token and check user permissions"""
from jose import jwt
import os
from dotenv import load_dotenv
import asyncio
from app.core.database import get_database
from app.config import settings

load_dotenv()

async def debug_user():
    """Debug user permissions"""
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1ODExNDIwMDE3Mzk2Mjg1NjUiLCJleHAiOjE3NjYzNDYyMjZ9.Hogqok7-qDkfWLGnBE-cr_Q9_oCnStaPeDb-zV9AAq0"
    
    try:
        # Decode token
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        print(f"✅ Token decoded successfully")
        print(f"   Discord ID: {payload.get('sub')}")
        print(f"   Expires: {payload.get('exp')}")
        
        # Import database connection
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(settings.mongodb_uri)
        db = client[settings.mongodb_db_name]
        
        # Get user from database
        user = await db.users.find_one({"discord_id": payload.get('sub')})
        
        if user:
            print(f"\n✅ User found in database:")
            print(f"   Username: {user.get('username')}")
            print(f"   Discord ID: {user.get('discord_id')}")
            print(f"   Guild Roles: {user.get('guild_roles', [])}")
            print(f"   Is Member: {user.get('is_member')}")
            
            # Check role IDs from settings
            print(f"\n📋 Role IDs from settings:")
            print(f"   Manager Role ID: {settings.manager_role_id}")
            print(f"   CEO Role ID: {settings.ceo_role_id}")
            print(f"   Admin IDs: {settings.admin_ids_list}")
            
            # Check permissions
            guild_roles = user.get("guild_roles", [])
            guild_role_strs = [str(role) for role in guild_roles]
            
            # Convert discord_id to int for admin check
            try:
                discord_id_int = int(user.get("discord_id"))
                is_admin = discord_id_int in settings.admin_ids_list
            except (ValueError, TypeError):
                is_admin = False
            
            has_manager = settings.manager_role_id in guild_role_strs
            has_ceo = settings.ceo_role_id in guild_role_strs
            
            print(f"\n🔍 Permission Check:")
            print(f"   Is Admin: {is_admin}")
            print(f"   Has Manager Role: {has_manager}")
            print(f"   Has CEO Role: {has_ceo}")
            print(f"   Should have access: {is_admin or has_manager or has_ceo}")
            
        else:
            print(f"❌ User not found in database")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_user())

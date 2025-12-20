"""Fix guild_roles in database - convert role names to role IDs"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
import os
from dotenv import load_dotenv

load_dotenv()

# Mapping of role names to role IDs based on your Discord server
ROLE_NAME_TO_ID = {
    "Management": "1228309637493952586",
    "CEO": "1228309908622020709",
    "Application Pending": os.getenv('APPLICATION_PENDING_ROLE_ID', ''),
    ".": os.getenv('EVERYONE_ROLE_ID', ''),
}

async def fix_guild_roles():
    """Fix all users' guild_roles from names to IDs"""
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]
    
    # Get all users
    users = await db.users.find({}).to_list(None)
    
    fixed_count = 0
    for user in users:
        guild_roles = user.get("guild_roles", [])
        
        # Check if roles are names (not IDs)
        if guild_roles and not all(role.isdigit() for role in guild_roles):
            # Convert role names to IDs
            role_ids = []
            for role in guild_roles:
                if role in ROLE_NAME_TO_ID and ROLE_NAME_TO_ID[role]:
                    role_ids.append(ROLE_NAME_TO_ID[role])
            
            # Update user
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"guild_roles": role_ids}}
            )
            
            print(f"✅ Fixed {user['username']}: {guild_roles} → {role_ids}")
            fixed_count += 1
    
    print(f"\n✅ Fixed {fixed_count} users")
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_guild_roles())

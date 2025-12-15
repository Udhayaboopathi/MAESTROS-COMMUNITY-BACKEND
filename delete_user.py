import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def delete_user():
    client = AsyncIOMotorClient("mongodb+srv://udhaya:udhaya@maestros.qwqfgnk.mongodb.net/?appName=maestros")
    db = client["maestros_community"]
    
    # Find and delete the user
    result = await db.users.delete_one({'username': 'groot0820'})
    
    if result.deleted_count > 0:
        print(f"✅ Successfully deleted user 'groot0820'")
    else:
        print("❌ User 'groot0820' not found")
    
    client.close()

asyncio.run(delete_user())

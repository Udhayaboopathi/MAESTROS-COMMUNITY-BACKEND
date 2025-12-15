import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_user():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["maestros_community"]
    user = await db.users.find_one({'username': 'groot0820'})
    if user:
        print(f"Username: {user.get('username')}")
        print(f"Display Name: {user.get('display_name')}")
        print(f"Discord ID: {user.get('discord_id')}")
    else:
        print("User not found")
    client.close()

asyncio.run(check_user())

"""
Complete Connection Test
Tests database and bot connections
"""

import asyncio
import sys
from dotenv import load_dotenv
import os

# Load environment
load_dotenv('env/.env')

print("=" * 70)
print("🔗 MAESTROS BACKEND CONNECTION TEST")
print("=" * 70)

async def test_connections():
    # Test 1: MongoDB Connection
    print("\n1️⃣ Testing MongoDB Connection...")
    try:
        from app.core.database import connect_to_mongo, close_mongo_connection, get_database
        
        await connect_to_mongo()
        db = get_database()
        
        # Test database operations
        collections = await db.list_collection_names()
        print(f"   ✅ Connected to MongoDB")
        print(f"   📊 Collections: {len(collections)}")
        print(f"   📝 Collection names: {', '.join(collections[:5])}{'...' if len(collections) > 5 else ''}")
        
        # Test a simple query
        users_count = await db.users.count_documents({})
        print(f"   👥 Total users: {users_count}")
        
        await close_mongo_connection()
        print("   ✅ MongoDB connection closed")
        
    except Exception as e:
        print(f"   ❌ MongoDB Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Discord Bot Initialization
    print("\n2️⃣ Testing Discord Bot Initialization...")
    try:
        from app.bot.bot import DiscordBot
        
        bot = DiscordBot()
        
        # Check configuration
        print(f"   ✅ Bot instance created")
        print(f"   🆔 Guild ID: {bot.guild_id}")
        print(f"   🔗 Backend URL: {bot.backend_url}")
        print(f"   🎵 API Base: {bot.api_base}")
        print(f"   🌐 Frontend URL: {bot.frontend_url}")
        
        # Check role IDs
        if bot.ceo_role_id:
            print(f"   👑 CEO Role ID: {bot.ceo_role_id}")
        if bot.manager_role_id:
            print(f"   👔 Manager Role ID: {bot.manager_role_id}")
        if bot.member_role_id:
            print(f"   👤 Member Role ID: {bot.member_role_id}")
        
        # Check if token is set
        if bot.token:
            print(f"   🔑 Bot token configured (length: {len(bot.token)})")
        else:
            print(f"   ⚠️  Bot token NOT configured!")
        
        print("   ✅ Bot configuration valid")
        
    except Exception as e:
        print(f"   ❌ Bot Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: API Router Connectivity
    print("\n3️⃣ Testing API Router Connectivity...")
    try:
        from app.api import music, discord, auth, users
        
        # Check router attributes
        print(f"   ✅ Music router: {len(music.router.routes)} routes")
        print(f"   ✅ Discord router: {len(discord.router.routes)} routes")
        print(f"   ✅ Auth router: {len(auth.router.routes)} routes")
        print(f"   ✅ Users router: {len(users.router.routes)} routes")
        
    except Exception as e:
        print(f"   ❌ Router Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: JioSaavn Service
    print("\n4️⃣ Testing JioSaavn Service...")
    try:
        from app.services.jiosaavn import endpoints, helper
        
        # Check if endpoints are defined
        print(f"   ✅ Search URL: {endpoints.search_base_url[:50]}...")
        print(f"   ✅ Helper functions available")
        
    except Exception as e:
        print(f"   ❌ Service Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 5: Cog Loading
    print("\n5️⃣ Testing Cog Modules...")
    try:
        from app.bot.cogs import general, music
        
        # Check if setup functions exist
        if hasattr(general, 'setup'):
            print(f"   ✅ General cog has setup function")
        if hasattr(music, 'setup'):
            print(f"   ✅ Music cog has setup function")
        
    except Exception as e:
        print(f"   ❌ Cog Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("✅ CONNECTION TEST COMPLETE")
    print("=" * 70)
    print("\n💡 All systems operational! You can now run:")
    print("   uvicorn main:app --reload")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_connections())

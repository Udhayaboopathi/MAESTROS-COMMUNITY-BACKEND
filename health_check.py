"""
Backend Health Check Script
Tests all imports and connections
"""

import sys
import os

print("=" * 60)
print("🔍 MAESTROS BACKEND HEALTH CHECK")
print("=" * 60)

# Test 1: Environment Variables
print("\n1️⃣ Testing Environment Variables...")
try:
    from dotenv import load_dotenv
    load_dotenv('env/.env')
    
    required_vars = [
        'MONGODB_URI',
        'DISCORD_BOT_TOKEN',
        'DISCORD_GUILD_ID',
        'JWT_SECRET_KEY',
        'API_HOST',
        'API_PORT'
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print(f"   ⚠️  Missing: {', '.join(missing)}")
    else:
        print("   ✅ All required environment variables found")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Configuration
print("\n2️⃣ Testing Configuration...")
try:
    from app.config import settings
    print(f"   ✅ Config loaded - DB: {settings.mongodb_db_name}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Core Database
print("\n3️⃣ Testing Core Database...")
try:
    from app.core.database import get_database, connect_to_mongo, close_mongo_connection
    print("   ✅ Database module imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 4: Core Models
print("\n4️⃣ Testing Core Models...")
try:
    from app.core.models import User, Event
    print("   ✅ Models imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 5: Utilities
print("\n5️⃣ Testing Utilities...")
try:
    from app.utils import get_current_user, calculate_level
    from app.cache import cache_user_data
    print("   ✅ Utils and cache imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 6: API Routers
print("\n6️⃣ Testing API Routers...")
try:
    from app.api import (
        auth, users, discord, applications, 
        events, admin, moderation, games, 
        rules, application_manager, announcements, music
    )
    print("   ✅ All 12 routers imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 7: JioSaavn Service
print("\n7️⃣ Testing JioSaavn Service...")
try:
    from app.services.jiosaavn import endpoints, helper
    print("   ✅ JioSaavn service imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 8: Discord Bot
print("\n8️⃣ Testing Discord Bot...")
try:
    from app.bot.bot import DiscordBot
    print("   ✅ Discord Bot class imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 9: Bot Cogs
print("\n9️⃣ Testing Bot Cogs...")
try:
    from app.bot.cogs import general, music
    print("   ✅ Both cogs (general, music) imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 10: Main Application
print("\n🔟 Testing Main Application...")
try:
    from main import app
    print("   ✅ FastAPI app imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
print("✅ HEALTH CHECK COMPLETE")
print("=" * 60)
print("\nNext step: Run 'uvicorn main:app --reload' to start server")

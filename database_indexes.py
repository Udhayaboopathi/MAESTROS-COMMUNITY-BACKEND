"""
Database Indexes Management
Creates and manages indexes for optimal query performance
"""
from database import get_database
import asyncio

async def create_indexes():
    """Create all necessary database indexes for optimal performance"""
    db = get_database()
    
    print("📊 Creating database indexes...")
    
    try:
        # Users collection indexes
        await db.users.create_index("discord_id", unique=True)
        print("✅ Created unique index on users.discord_id")
        
        await db.users.create_index("username")
        print("✅ Created index on users.username")
        
        await db.users.create_index([("xp", -1)])  # Descending for leaderboard
        print("✅ Created index on users.xp (descending)")
        
        await db.users.create_index([("level", -1)])
        print("✅ Created index on users.level (descending)")
        
        # Games collection indexes
        await db.games.create_index("active")
        print("✅ Created index on games.active")
        
        await db.games.create_index([("created_at", -1)])
        print("✅ Created index on games.created_at (descending)")
        
        await db.games.create_index("name")
        print("✅ Created index on games.name")
        
        # Applications collection indexes
        await db.applications.create_index("user_id")
        print("✅ Created index on applications.user_id")
        
        await db.applications.create_index("status")
        print("✅ Created index on applications.status")
        
        await db.applications.create_index([("submitted_at", -1)])
        print("✅ Created index on applications.submitted_at (descending)")
        
        # Compound index for common query pattern
        await db.applications.create_index([("user_id", 1), ("status", 1)])
        print("✅ Created compound index on applications (user_id, status)")
        
        # Activity logs indexes
        await db.activity.create_index([("user_id", 1), ("timestamp", -1)])
        print("✅ Created compound index on activity (user_id, timestamp)")
        
        await db.activity.create_index([("timestamp", -1)])
        print("✅ Created index on activity.timestamp (descending)")
        
        # Events collection indexes
        await db.events.create_index("status")
        print("✅ Created index on events.status")
        
        await db.events.create_index([("date", 1)])
        print("✅ Created index on events.date (ascending)")
        
        await db.events.create_index("participants")
        print("✅ Created index on events.participants")
        
        # Rules collection indexes
        await db.rules.create_index("category")
        print("✅ Created index on rules.category")
        
        await db.rules.create_index([("order", 1)])
        print("✅ Created index on rules.order (ascending)")
        
        print("✅ All database indexes created successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error creating indexes: {str(e)}")
        return False

async def verify_indexes():
    """Verify that all indexes exist"""
    db = get_database()
    
    print("\n🔍 Verifying database indexes...")
    
    collections = {
        "users": ["discord_id", "username", "xp", "level"],
        "games": ["active", "created_at", "name"],
        "applications": ["user_id", "status", "submitted_at"],
        "activity": ["user_id", "timestamp"],
        "events": ["status", "date", "participants"],
        "rules": ["category", "order"]
    }
    
    all_verified = True
    
    for collection_name, expected_indexes in collections.items():
        collection = db[collection_name]
        indexes = await collection.index_information()
        index_fields = [list(idx['key'].keys())[0] if len(idx['key']) == 1 else 'compound' 
                       for idx in indexes.values() if idx.get('key')]
        
        print(f"\n📋 {collection_name} indexes:")
        for field in expected_indexes:
            if field in str(index_fields):
                print(f"  ✅ {field}")
            else:
                print(f"  ❌ {field} - MISSING!")
                all_verified = False
    
    if all_verified:
        print("\n✅ All indexes verified successfully!")
    else:
        print("\n⚠️  Some indexes are missing. Run create_indexes() to fix.")
    
    return all_verified

async def drop_all_indexes():
    """Drop all indexes (use with caution - for testing only)"""
    db = get_database()
    
    print("⚠️  Dropping all indexes (except _id)...")
    
    collections = ["users", "games", "applications", "activity", "events", "rules"]
    
    for collection_name in collections:
        try:
            collection = db[collection_name]
            await collection.drop_indexes()
            print(f"✅ Dropped indexes from {collection_name}")
        except Exception as e:
            print(f"❌ Error dropping indexes from {collection_name}: {str(e)}")

if __name__ == "__main__":
    # Run index creation
    asyncio.run(create_indexes())
    
    # Verify indexes
    asyncio.run(verify_indexes())

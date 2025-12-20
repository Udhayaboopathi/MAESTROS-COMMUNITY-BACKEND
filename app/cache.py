"""
Simple in-memory caching layer for backend API
Uses TTL-based caching to reduce database and external API calls
"""
from cachetools import TTLCache, LRUCache
from typing import Any, Optional, Callable
import functools
import hashlib
import json

# Cache instances
# TTL Cache: Automatically expires after specified seconds
user_cache = TTLCache(maxsize=1000, ttl=300)  # 5 minutes TTL
game_cache = TTLCache(maxsize=500, ttl=600)   # 10 minutes TTL
discord_cache = TTLCache(maxsize=1000, ttl=300)  # 5 minutes TTL for Discord API data
general_cache = LRUCache(maxsize=500)  # General purpose LRU cache

def generate_cache_key(*args, **kwargs) -> str:
    """Generate a cache key from function arguments"""
    key_data = {
        'args': args,
        'kwargs': kwargs
    }
    key_string = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.md5(key_string.encode()).hexdigest()

def cache_user_data(ttl: int = 300):
    """
    Decorator to cache user data
    Args:
        ttl: Time to live in seconds (default 5 minutes)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{func.__name__}:{generate_cache_key(*args, **kwargs)}"
            
            # Check cache
            if cache_key in user_cache:
                print(f"🎯 Cache HIT: {func.__name__}")
                return user_cache[cache_key]
            
            # Cache miss - call function
            print(f"❌ Cache MISS: {func.__name__}")
            result = await func(*args, **kwargs)
            
            # Store in cache
            user_cache[cache_key] = result
            return result
        
        return wrapper
    return decorator

def cache_game_data(ttl: int = 600):
    """
    Decorator to cache game data
    Args:
        ttl: Time to live in seconds (default 10 minutes)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{generate_cache_key(*args, **kwargs)}"
            
            if cache_key in game_cache:
                print(f"🎯 Cache HIT: {func.__name__}")
                return game_cache[cache_key]
            
            print(f"❌ Cache MISS: {func.__name__}")
            result = await func(*args, **kwargs)
            game_cache[cache_key] = result
            return result
        
        return wrapper
    return decorator

def cache_discord_data(ttl: int = 300):
    """
    Decorator to cache Discord API data
    Args:
        ttl: Time to live in seconds (default 5 minutes)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{generate_cache_key(*args, **kwargs)}"
            
            if cache_key in discord_cache:
                print(f"🎯 Cache HIT: {func.__name__}")
                return discord_cache[cache_key]
            
            print(f"❌ Cache MISS: {func.__name__}")
            result = await func(*args, **kwargs)
            discord_cache[cache_key] = result
            return result
        
        return wrapper
    return decorator

def invalidate_user_cache(discord_id: str = None):
    """Invalidate user cache for a specific user or all users"""
    if discord_id:
        # Invalidate specific user
        keys_to_delete = [k for k in user_cache.keys() if discord_id in k]
        for key in keys_to_delete:
            del user_cache[key]
        print(f"🗑️  Invalidated cache for user: {discord_id}")
    else:
        # Invalidate all user cache
        user_cache.clear()
        print("🗑️  Invalidated all user cache")

def invalidate_game_cache():
    """Invalidate all game cache"""
    game_cache.clear()
    print("🗑️  Invalidated all game cache")

def invalidate_discord_cache(discord_id: str = None):
    """Invalidate Discord cache for a specific user or all"""
    if discord_id:
        keys_to_delete = [k for k in discord_cache.keys() if discord_id in k]
        for key in keys_to_delete:
            del discord_cache[key]
        print(f"🗑️  Invalidated Discord cache for: {discord_id}")
    else:
        discord_cache.clear()
        print("🗑️  Invalidated all Discord cache")

def get_cache_stats() -> dict:
    """Get cache statistics"""
    return {
        "user_cache": {
            "size": len(user_cache),
            "maxsize": user_cache.maxsize,
            "ttl": 300,
            "currsize": user_cache.currsize
        },
        "game_cache": {
            "size": len(game_cache),
            "maxsize": game_cache.maxsize,
            "ttl": 600,
            "currsize": game_cache.currsize
        },
        "discord_cache": {
            "size": len(discord_cache),
            "maxsize": discord_cache.maxsize,
            "ttl": 300,
            "currsize": discord_cache.currsize
        },
        "general_cache": {
            "size": len(general_cache),
            "maxsize": general_cache.maxsize
        }
    }

def clear_all_caches():
    """Clear all caches"""
    user_cache.clear()
    game_cache.clear()
    discord_cache.clear()
    general_cache.clear()
    print("🗑️  Cleared all caches")


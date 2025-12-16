from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

from config import settings
from database import connect_to_mongo, close_mongo_connection

# Import routers
from routers import auth, users, discord, applications, events, admin, moderation, games, rules, application_manager

# Import Discord bot
from bot import DiscordBot

# Global bot instance
discord_bot = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - starts both FastAPI and Discord bot"""
    global discord_bot
    
    # Startup
    print("🚀 Starting Maestros Community Backend...")
    
    # Connect to MongoDB
    await connect_to_mongo()
    print("✅ MongoDB connected")
    
    # Start Discord bot in background
    discord_bot = DiscordBot()
    asyncio.create_task(discord_bot.start_bot())
    print("✅ Discord bot starting...")
    
    # Make bot instance available to routes
    app.state.discord_bot = discord_bot
    
    yield
    
    # Shutdown
    print("🛑 Shutting down...")
    if discord_bot:
        await discord_bot.stop_bot()
    await close_mongo_connection()
    print("✅ Shutdown complete")

app = FastAPI(
    title="Maestros Community API",
    description="Backend API for Maestros Gaming Community (with Discord Bot)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(discord.router, prefix="/discord", tags=["Discord"])
app.include_router(applications.router, prefix="/applications", tags=["Applications"])
app.include_router(application_manager.router, prefix="/application-manager", tags=["Application Manager"])
app.include_router(events.router, prefix="/events", tags=["Events"])
app.include_router(games.router, prefix="/games", tags=["Games"])
app.include_router(rules.router, prefix="/rules", tags=["Rules"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(moderation.router, prefix="/moderation", tags=["Moderation"])

@app.get("/")
async def root():
    return {
        "message": "Maestros Community API + Discord Bot",
        "version": "1.0.0",
        "status": "online",
        "discord_bot": "active" if discord_bot and discord_bot.is_ready else "starting"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "api": "online",
        "discord_bot": discord_bot.is_ready if discord_bot else False
    }

@app.get("/bot/status")
async def bot_status():
    """Get Discord bot status"""
    if not discord_bot:
        return {"status": "not_started"}
    
    return {
        "status": "online" if discord_bot.is_ready else "starting",
        "guilds": len(discord_bot.bot.guilds) if discord_bot.bot else 0,
        "latency": round(discord_bot.bot.latency * 1000) if discord_bot.bot else 0
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload
    )

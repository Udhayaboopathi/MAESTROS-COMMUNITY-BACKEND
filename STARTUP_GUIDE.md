# 🚀 Maestros Backend - Startup Guide

## ✅ Pre-Flight Checks

Before starting, verify everything is ready:

```bash
# Run health check
python health_check.py

# Run connection test (includes database)
python test_connections.py
```

Both should show all ✅ checks passing.

## 🎬 Starting the Server

```bash
# Development mode (with auto-reload)
uvicorn main:app --reload

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 📊 Expected Startup Output

```
🚀 Starting Maestros Community Backend...
✅ MongoDB connected
✅ Connected to MongoDB: maestros_community
✅ Discord bot starting...
✅ Discord Bot: YourBot#1234 connected!
📊 Connected to 1 guild(s)
🔄 Loading 2 cogs...
   Loading app.bot.cogs.general...
✅ Loaded cog: app.bot.cogs.general
   Set parent_bot reference for General
   Loading app.bot.cogs.music...
✅ Loaded cog: app.bot.cogs.music
   Set parent_bot reference for Music
✅ Synced 13 slash command(s)
✅ Discord Bot is ready!
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 🎯 Slash Commands Available

### General Commands (7)

- `/ping` - Check bot latency
- `/stats` - Show server statistics
- `/help` - Show all commands
- `/apply` - Get application link
- `/events` - Show upcoming events
- `/announce` - Make announcement (Admin only)

### Music Commands (7)

- `/play <song>` - Play a song
- `/playlist <name>` - Play a playlist
- `/album <name>` - Play an album
- `/skip` - Skip current song
- `/queue` - Show queue
- `/stop` - Stop playback
- `/leave` - Leave voice channel

**Total: 13+ slash commands**

## 🔍 Testing Endpoints

After server starts:

```bash
# Health check
curl http://localhost:8000/health

# Bot status
curl http://localhost:8000/bot/status

# Discord stats
curl http://localhost:8000/discord/stats

# Music search
curl "http://localhost:8000/music/song/?query=unstoppable"
```

## 🐛 Troubleshooting

### Issue: 0 slash commands synced

**Solution:** Check console for cog loading errors. Should see:

- `🔄 Loading 2 cogs...`
- `✅ Loaded cog: app.bot.cogs.general`
- `✅ Loaded cog: app.bot.cogs.music`

### Issue: MongoDB connection failed

**Solution:** Check `env/.env` file has correct `MONGODB_URI`

### Issue: Discord bot not starting

**Solution:** Verify `DISCORD_BOT_TOKEN` in `env/.env`

### Issue: Import errors

**Solution:** Run `python health_check.py` to identify issue

## 📁 Important Files

- `main.py` - FastAPI entry point
- `env/.env` - Environment configuration
- `app/bot/bot.py` - Discord bot main class
- `app/bot/cogs/` - Bot command modules
- `app/api/` - API routers
- `app/core/database.py` - MongoDB connection

## 🎉 Success Indicators

✅ All health checks pass
✅ MongoDB connected
✅ Discord bot connected to guild
✅ 13+ slash commands synced
✅ Background tasks running
✅ API responding on http://localhost:8000

## 🔧 Development Commands

```bash
# Health check (imports only)
python health_check.py

# Connection test (includes database)
python test_connections.py

# Start server
uvicorn main:app --reload

# Clear Python cache
find . -type d -name "__pycache__" -exec rm -rf {} +
```

## 🌟 You're Ready!

Everything is configured and tested. Your backend is production-ready!

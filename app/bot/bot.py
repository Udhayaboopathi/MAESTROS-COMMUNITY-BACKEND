"""
Discord Bot Module - Runs alongside FastAPI backend
Handles Discord server management, stats, and commands
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import asyncio
import os
from datetime import datetime
from app.core.database import get_database
from collections import deque
import requests
import random

class DiscordBot:
    """Discord Bot integrated with FastAPI backend"""
    
    def __init__(self):
        self.token = os.getenv('DISCORD_BOT_TOKEN')
        self.guild_id = int(os.getenv('DISCORD_GUILD_ID', 0))
        
        # API Configuration - Get from environment
        api_host = os.getenv('API_HOST', 'localhost')
        api_port = os.getenv('API_PORT', '8000')
        
        # Fix: Use localhost/127.0.0.1 for client connections, not 0.0.0.0
        if api_host == '0.0.0.0':
            api_host = 'localhost'
        
        self.backend_url = f"http://{api_host}:{api_port}"
        self.api_base = f"{self.backend_url}/music"
        self.frontend_url = os.getenv('FRONTEND_URL', 'https://maestros-community-frontend-5arz.vercel.app')
        
        # Load individual role IDs
        self.ceo_role_id = int(os.getenv('CEO_ROLE_ID')) if os.getenv('CEO_ROLE_ID') else None
        self.manager_role_id = int(os.getenv('MANAGER_ROLE_ID')) if os.getenv('MANAGER_ROLE_ID') else None
        self.member_role_id = int(os.getenv('MEMBER_ROLE_ID')) if os.getenv('MEMBER_ROLE_ID') else None
        
        print(f'🔧 CEO Role ID: {self.ceo_role_id}')
        print(f'🔧 Manager Role ID: {self.manager_role_id}')
        print(f'🔧 Member Role ID: {self.member_role_id}')
        
        # Music bot variables
        self.queues = {}  # guild_id -> deque of (media_url, title, song_data)
        self.now_playing = {}  # guild_id -> song_data
        self.loop_mode = {}  # guild_id -> bool
        self.shuffle_mode = {}  # guild_id -> bool
        self.music_messages = {}  # guild_id -> message_id
        
        # FFmpeg options for audio
        self.FFMPEG_OPTIONS = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn"
        }
        
        # Reaction emojis for music controls
        self.REACTIONS = {
            "pause": "⏸️",
            "resume": "▶️",
            "skip": "⏭️",
            "loop": "🔁",
            "shuffle": "🔀",
            "stop": "⏹️",
            "queue": "📋"
        }
        
        # Setup intents
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        intents.message_content = True
        intents.guilds = True
        intents.voice_states = True
        
        # Create bot instance
        self.bot = commands.Bot(
            command_prefix=os.getenv('COMMAND_PREFIX', '!'),
            intents=intents,
            help_command=None
        )
        
        self.is_ready = False
        self._setup_events()
    
    def _setup_events(self):
        """Setup Discord event handlers"""
        
        @self.bot.event
        async def on_ready():
            """Bot startup event"""
            print(f'✅ Discord Bot: {self.bot.user} connected!')
            print(f'📊 Connected to {len(self.bot.guilds)} guild(s)')
            
            # Load cogs
            await self.load_cogs_async()
            
            # Sync slash commands
            try:
                synced = await self.bot.tree.sync()
                print(f'✅ Synced {len(synced)} slash command(s)')
            except Exception as e:
                print(f'⚠️ Failed to sync commands: {e}')
            
            # Set bot status to DND
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="Maestros Community"
                ),
                status=discord.Status.dnd
            )
            
            # Start background tasks
            self.update_stats.start()
            self.sync_roles.start()
            self.rotate_status.start()
            
            self.is_ready = True
            print('✅ Discord Bot is ready!')
        
        @self.bot.event
        async def on_member_join(member):
            """Handle member join"""
            guild = member.guild
            
            # Log to database
            db = get_database()
            if db is not None:
                await db.logs.insert_one({
                    'event': 'member_join',
                    'level': 'info',
                    'metadata': {
                        'user_id': str(member.id),
                        'username': str(member),
                        'guild_id': str(guild.id)
                    },
                    'timestamp': datetime.utcnow()
                })
            
            # Send welcome message
            system_channel = guild.system_channel
            if system_channel:
                embed = discord.Embed(
                    title='🎮 Welcome to Maestros!',
                    description=f'Welcome {member.mention}! Check out the rules and introduce yourself!',
                    color=0xFFD363
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                await system_channel.send(embed=embed)
        
        @self.bot.event
        async def on_member_remove(member):
            """Handle member leave"""
            db = get_database()
            if db is not None:
                await db.logs.insert_one({
                    'event': 'member_leave',
                    'level': 'info',
                    'metadata': {
                        'user_id': str(member.id),
                        'username': str(member),
                        'guild_id': str(member.guild.id)
                    },
                    'timestamp': datetime.utcnow()
                })
        
        @self.bot.event
        async def on_command_error(ctx, error):
            """Handle command errors"""
            if isinstance(error, commands.CommandNotFound):
                return
            elif isinstance(error, commands.MissingPermissions):
                await ctx.send('❌ You don\'t have permission to use this command.')
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f'❌ Missing argument: {error.param}')
            else:
                print(f'Bot Error: {error}')
                await ctx.send('❌ An error occurred while processing the command.')
        
        @self.bot.event
        async def on_interaction(interaction: discord.Interaction):
            """Handle button interactions for applications"""
            if interaction.type != discord.InteractionType.modal_submit:
                return
            
            # Check if user is CEO or Manager
            role_ids = [role.id for role in interaction.user.roles]
            if self.ceo_role_id not in role_ids and self.manager_role_id not in role_ids:
                await interaction.response.send_message("❌ Only CEOs and Managers can review applications.", ephemeral=True)
                return
            
            custom_id = interaction.data.get('custom_id', '')
            
            if custom_id.startswith('accept_modal_'):
                await self._handle_accept(interaction)
            elif custom_id.startswith('reject_modal_'):
                await self._handle_reject(interaction)
        
        async def _handle_accept(self, interaction: discord.Interaction):
            """Process application acceptance"""
            try:
                # Extract application ID from modal custom_id
                app_id = interaction.data['custom_id'].replace('accept_modal_', '')
                notes = interaction.data.get('components', [[]])[0].get('components', [[]])[0].get('value', '')
                
                # Call backend API to process acceptance
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.backend_url}/application-manager/manager/accept/{app_id}",
                        json={"notes": notes, "manager_id": str(interaction.user.id)}
                    ) as resp:
                        if resp.status == 200:
                            await interaction.response.send_message("✅ Application accepted successfully!", ephemeral=True)
                        else:
                            await interaction.response.send_message("❌ Failed to accept application.", ephemeral=True)
            except Exception as e:
                print(f"Error handling accept: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
        
        async def _handle_reject(self, interaction: discord.Interaction):
            """Process application rejection"""
            try:
                app_id = interaction.data['custom_id'].replace('reject_modal_', '')
                reason = interaction.data.get('components', [[]])[0].get('components', [[]])[0].get('value', '')
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.backend_url}/application-manager/manager/reject/{app_id}",
                        json={"reason": reason, "manager_id": str(interaction.user.id)}
                    ) as resp:
                        if resp.status == 200:
                            await interaction.response.send_message("❌ Application rejected.", ephemeral=True)
                        else:
                            await interaction.response.send_message("❌ Failed to reject application.", ephemeral=True)
            except Exception as e:
                print(f"Error handling reject: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
    
    async def load_cogs_async(self):
        """Async method to load cogs after bot is ready"""
        import sys
        import traceback
        
        cogs_to_load = ['app.bot.cogs.general', 'app.bot.cogs.music', 'app.bot.cogs.fuel_delivery']
        print(f'🔄 Loading {len(cogs_to_load)} cogs...')
        
        for cog in cogs_to_load:
            try:
                print(f'   Loading {cog}...')
                await self.bot.load_extension(cog)
                print(f'✅ Loaded cog: {cog}')
                
                # Set parent_bot reference for accessing api_base and other properties
                cog_name = cog.split('.')[-1].capitalize()
                cog_instance = self.bot.get_cog(cog_name)
                if cog_instance and hasattr(cog_instance, 'parent_bot'):
                    cog_instance.parent_bot = self
                    print(f'   Set parent_bot reference for {cog_name}')
                    
            except Exception as e:
                print(f'❌ Failed to load cog {cog}:')
                print(f'   Error: {e}')
                traceback.print_exc()
    
    @tasks.loop(seconds=10)
    async def update_stats(self):
        """Update Discord stats every 10 seconds"""
        try:
            if not self.guild_id:
                return
            
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                print(f'⚠️ Guild {self.guild_id} not found')
                return
            
            # Get online members
            online_members = [m for m in guild.members if m.status != discord.Status.offline and not m.bot]
            
            # Get online count for each role with both nickname and username
            ceo_online = []
            manager_online = []
            community_member_online = []
            
            # Get database reference
            db = get_database()
            
            for member in online_members:
                member_role_ids = [role.id for role in member.roles]
                
                # Create basic member info with both display_name (nickname) and name (username)
                member_info = {
                    'display_name': str(member.display_name),  # Server nickname or username if no nickname
                    'username': str(member.name),  # Actual Discord username
                    'discriminator': str(member.discriminator) if member.discriminator != '0' else None,
                    'discord_id': str(member.id),
                    'avatar': str(member.avatar.key) if member.avatar else None,
                    'guild_roles': [str(role_id) for role_id in member_role_ids],  # Store role IDs as strings
                }
                
                # Add permissions info for ALL members
                is_ceo = self.ceo_role_id and self.ceo_role_id in member_role_ids
                is_manager = self.manager_role_id and self.manager_role_id in member_role_ids
                is_admin = any('admin' in role.name.lower() for role in member.roles)
                
                member_info['permissions'] = {
                    'is_ceo': is_ceo,
                    'is_manager': is_manager,
                    'is_admin': is_admin,
                    'can_manage_applications': is_manager or is_ceo or is_admin
                }
                
                # Fetch additional user data from database if available
                if db is not None:
                    try:
                        user_data = await db.users.find_one({'discord_id': str(member.id)})
                        if user_data:
                            member_info.update({
                                'level': user_data.get('level', 1),
                                'xp': user_data.get('xp', 0),
                                'badges': user_data.get('badges', []),
                                'joined_at': user_data.get('joined_at').isoformat() if user_data.get('joined_at') else None,
                                'last_login': user_data.get('last_login').isoformat() if user_data.get('last_login') else None,
                            })
                    except Exception as e:
                        print(f'⚠️ Error fetching user data for {member.name}: {e}')
                
                # Check each role (member can have multiple roles)
                if self.ceo_role_id and self.ceo_role_id in member_role_ids:
                    ceo_online.append(member_info)
                elif self.manager_role_id and self.manager_role_id in member_role_ids:
                    manager_online.append(member_info)
                elif self.member_role_id and self.member_role_id in member_role_ids:
                    community_member_online.append(member_info)
            
            print(f'📊 Stats - Total: {guild.member_count}, Online: {len(online_members)}, CEO: {len(ceo_online)}, Managers: {len(manager_online)}, Community: {len(community_member_online)}')
            
            # Combine CEO and Managers into managers array
            # All members with CEO or Manager role go to managers
            managers_combined = ceo_online + manager_online
            
            # Regular members go to members array
            members_array = community_member_online
            
            # Update in-memory stats (accessed by discord router)
            from app.api.discord import discord_stats
            discord_stats.update({
                'total': guild.member_count,
                'online': len(online_members),
                'managers': managers_combined,  # CEOs + Managers
                'members': members_array,       # Regular members
                'last_update': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            print(f'❌ Error updating stats: {e}')
    
    @tasks.loop(seconds=5)
    async def rotate_status(self):
        """Rotate bot status every 5 seconds"""
        try:
            activities = [
                discord.Activity(type=discord.ActivityType.listening, name="Maestros Community"),
                discord.Activity(type=discord.ActivityType.listening, name="@I AM GROOT")
            ]
            
            # Rotate between activities
            if not hasattr(self, '_status_index'):
                self._status_index = 0
            
            await self.bot.change_presence(
                activity=activities[self._status_index],
                status=discord.Status.dnd
            )
            
            self._status_index = (self._status_index + 1) % len(activities)
        except Exception as e:
            print(f"❌ Error rotating status: {e}")
    
    @tasks.loop(minutes=5)
    async def sync_roles(self):
        """Sync Discord roles with database every 5 minutes"""
        try:
            if not self.guild_id:
                return
                
            guild = self.bot.get_guild(self.guild_id)
            db = get_database()
            
            if not guild or db is None:
                return
            
            for member in guild.members:
                if member.bot:
                    continue
                
                role_ids = [str(role.id) for role in member.roles if role.name != '@everyone']
                
                await db.users.update_one(
                    {'discord_id': str(member.id)},
                    {
                        '$set': {
                            'guild_roles': role_ids,
                            'username': str(member.name),
                            'discriminator': member.discriminator,
                            'avatar': str(member.display_avatar.url)
                        }
                    },
                    upsert=False
                )
            
            print('✅ Discord roles synced')
            
        except Exception as e:
            print(f'❌ Error syncing roles: {e}')
    
    async def start_bot(self):
        """Start the Discord bot"""
        if not self.token:
            print('❌ DISCORD_BOT_TOKEN not found in environment variables')
            return
        
        try:
            await self.bot.start(self.token)
        except Exception as e:
            print(f'❌ Failed to start Discord bot: {e}')
    
    async def stop_bot(self):
        """Stop the Discord bot"""
        if self.bot:
            await self.bot.close()
            print('✅ Discord bot stopped')
    
    async def post_rule_to_discord(self, rule_data: dict, category_id: str):
        """Post or update a rule in Discord channel based on category"""
        try:
            if not self.is_ready:
                print('⚠️ Bot not ready, skipping Discord rule post')
                return
            
            # Get the category
            category = self.bot.get_channel(int(category_id))
            if not category or not isinstance(category, discord.CategoryChannel):
                print(f'⚠️ Discord category {category_id} not found or not a category')
                return
            
            # Get rule category and find matching channel
            rule_category = rule_data.get('category', '').lower()
            
            # Find channel in category that matches the rule category name
            channel = None
            for ch in category.channels:
                if isinstance(ch, discord.TextChannel):
                    # Match channel name with rule category (e.g., "Server-Rules" -> "server-rules")
                    ch_name = ch.name.lower()
                    # Remove hyphens/underscores for comparison
                    ch_name_clean = ch_name.replace('-', '').replace('_', '')
                    rule_cat_clean = rule_category.replace('-', '').replace('_', '')
                    
                    if rule_cat_clean in ch_name_clean or ch_name_clean in rule_cat_clean:
                        channel = ch
                        break
            
            if not channel:
                print(f'⚠️ No matching channel found in category for: {rule_category}')
                print(f'   Available channels: {[ch.name for ch in category.channels if isinstance(ch, discord.TextChannel)]}')
                # Use first text channel in category as fallback
                for ch in category.channels:
                    if isinstance(ch, discord.TextChannel):
                        channel = ch
                        print(f'⚠️ Using fallback channel: {ch.name}')
                        break
            
            if not channel:
                print(f'⚠️ No text channels found in category {category_id}')
                return
            
            print(f'📝 Posting rule to channel: {channel.name}')
            
            # Parse individual rules from rule_content
            rules_list = rule_data['rule_content'].split('\n')
            rules_list = [r.strip() for r in rules_list if r.strip()]
            
            # Get guild icon URL
            guild = self.bot.get_guild(self.guild_id)
            guild_icon_url = None
            if guild and guild.icon:
                guild_icon_url = str(guild.icon.url)
            
            # Create a clean, professional embed with justified content style
            embed = discord.Embed(
                title=f"📜 {rule_data['title']}",
                color=0xD4AF37,  # Professional gold color
                timestamp=datetime.utcnow()
            )
            
            # Set author with guild icon
            if guild_icon_url:
                embed.set_author(
                    name="Maestros Community Rules",
                    icon_url=guild_icon_url
                )
            else:
                embed.set_author(name="Maestros Community Rules")
            
            # Add each rule as a separate field for clean, justified layout
            for idx, rule_text in enumerate(rules_list, 1):
                embed.add_field(
                    name=f"📌 Rule {idx}",
                    value=rule_text,
                    inline=False
                )
            
            # Add guild icon as thumbnail if available
            if guild_icon_url:
                embed.set_thumbnail(url=guild_icon_url)
            
            # Simple, clean footer
            if guild_icon_url:
                embed.set_footer(
                    text="Regards from Maestros Community",
                    icon_url=guild_icon_url
                )
            else:
                embed.set_footer(text="Regards from Maestros Community")
            
            # Check if there's an existing message to update (stored in database)
            db = get_database()
            if db is not None:
                existing_msg = await db.rules.find_one({'_id': rule_data.get('_id')})
                discord_msg_id = existing_msg.get('discord_message_id') if existing_msg else None
                
                if discord_msg_id:
                    # Try to edit existing message
                    try:
                        message = await channel.fetch_message(int(discord_msg_id))
                        await message.edit(embed=embed)
                        print(f'✅ Updated rule in Discord channel {channel.name}')
                        return
                    except discord.NotFound:
                        print(f'⚠️ Original message not found, posting new one')
                    except Exception as e:
                        print(f'⚠️ Error updating Discord message: {e}')
                
                # Post new message
                message = await channel.send(embed=embed)
                
                # Store message ID in database for future updates
                if rule_data.get('_id'):
                    await db.rules.update_one(
                        {'_id': rule_data['_id']},
                        {'$set': {'discord_message_id': str(message.id)}}
                    )
                
                print(f'✅ Posted rule to Discord channel {channel.name}')
                
        except Exception as e:
            print(f'❌ Error posting rule to Discord: {e}')
    
    async def delete_rule_from_discord(self, rule_data: dict, category_id: str):
        """Delete a rule message from Discord channel"""
        try:
            if not self.is_ready:
                return
            
            discord_msg_id = rule_data.get('discord_message_id')
            if not discord_msg_id:
                return
            
            # Get the category
            category = self.bot.get_channel(int(category_id))
            if not category or not isinstance(category, discord.CategoryChannel):
                return
            
            # Get rule category and find matching channel
            rule_category = rule_data.get('category', '').lower()
            
            channel = None
            for ch in category.channels:
                if isinstance(ch, discord.TextChannel):
                    ch_name = ch.name.lower()
                    ch_name_clean = ch_name.replace('-', '').replace('_', '')
                    rule_cat_clean = rule_category.replace('-', '').replace('_', '')
                    
                    if rule_cat_clean in ch_name_clean or ch_name_clean in rule_cat_clean:
                        channel = ch
                        break
            
            if not channel:
                return
            
            discord_msg_id = rule_data.get('discord_message_id')
            if not discord_msg_id:
                return
            
            # Get the category
            category = self.bot.get_channel(int(category_id))
            if not category or not isinstance(category, discord.CategoryChannel):
                return
            
            # Get rule category and find matching channel
            rule_category = rule_data.get('category', '').lower()
            
            channel = None
            for ch in category.channels:
                if isinstance(ch, discord.TextChannel):
                    ch_name = ch.name.lower().replace('-', '-')
                    if rule_category in ch_name or ch_name in rule_category:
                        channel = ch
                        break
            
            if not channel:
                return
            
            try:
                message = await channel.fetch_message(int(discord_msg_id))
                await message.delete()
                print(f'✅ Deleted rule from Discord channel {channel.name}')
            except discord.NotFound:
                print(f'⚠️ Discord message not found')
            except Exception as e:
                print(f'❌ Error deleting Discord message: {e}')
                
        except Exception as e:
            print(f'❌ Error deleting rule from Discord: {e}')
    
    async def get_category_channels(self, category_id: str) -> list:
        """Get all text channel names from a category"""
        try:
            if not self.is_ready:
                return []
            
            category = self.bot.get_channel(int(category_id))
            if not category or not isinstance(category, discord.CategoryChannel):
                return []
            
            channels = []
            for ch in category.channels:
                if isinstance(ch, discord.TextChannel):
                    channels.append({
                        'id': str(ch.id),
                        'name': ch.name,
                        'display_name': ch.name.replace('-', ' ').title()
                    })
            
            return channels
            
        except Exception as e:
            print(f'❌ Error getting category channels: {e}')
            return []
    
    # ==================== MUSIC BOT METHODS ====================
    
    def get_queue(self, guild_id):
        """Get or create queue for guild"""
        if guild_id not in self.queues:
            self.queues[guild_id] = deque()
        return self.queues[guild_id]
    
    def create_music_embed(self, song_data, embed_type="now_playing", status="playing",
                          requester=None, channel_name=None, playlist_name=None, album_name=None):
        """Create a standardized music embed"""
        song_title = song_data.get("song", "Unknown")
        image = song_data.get("image", "")
        album = song_data.get("album", "Unknown Album")
        year = song_data.get("year", "Unknown")
        duration = song_data.get("duration", 0)
        music = song_data.get("music", "Unknown")
        singers = song_data.get("singers", "Unknown")
        
        if embed_type == "playlist":
            title = "📀 Playlist - Now Playing"
            color = 0x9B59B6
        elif embed_type == "album":
            title = "💿 Album - Now Playing"
            color = 0xFFD700
        elif embed_type == "queued":
            title = "➕ Added to Queue"
            color = discord.Color.blue()
        else:
            title = "🎵 Now Playing"
            color = 0x1DB954
        
        embed = discord.Embed(title=title, description=f"**{song_title}**", color=color)
        embed.set_thumbnail(url=image)
        
        status_icons = {
            "playing": "🟢 Playing",
            "paused": "⏸️ Paused",
            "stopped": "⏹️ Stopped",
            "queued": "⏸️ Queued"
        }
        status_text = status_icons.get(status, "🟢 Playing")
        
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="💿 Album", value=album, inline=True)
        embed.add_field(name="📅 Year", value=year, inline=True)
        embed.add_field(name="⏱️ Duration", value=f"{duration} min", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="🎼 Music", value=music, inline=True)
        embed.add_field(name="🎚️ Status", value=status_text, inline=True)
        if channel_name:
            embed.add_field(name="📢 Channel", value=channel_name, inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="🎤 Singers", value=singers, inline=False)
        
        if embed_type == "playlist":
            embed.add_field(name="📀 Playlist", value=playlist_name or "Unknown", inline=False)
        elif embed_type == "album":
            embed.add_field(name="💿 Album Name", value=album_name or album, inline=False)
        
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="", value="", inline=True)
        
        if requester:
            embed.add_field(name="👤 Requested by", value=requester, inline=False)
        
        if embed_type == "playlist":
            embed.set_footer(text="🎶 Playlist • Use 🔀 button to shuffle")
        elif embed_type == "album":
            embed.set_footer(text="🎶 Album • Use 🔀 button to shuffle")
        elif embed_type == "queued":
            embed.set_footer(text="🎶 Added to queue")
        else:
            embed.set_footer(text="🎶 Enjoy the music!")
        
        return embed
    
    def play_next(self, guild_id, voice_client):
        """Play next song in queue"""
        print(f"\n🔄 play_next called for guild {guild_id}")
        
        if not voice_client or not voice_client.is_connected():
            print(f"❌ Voice client not connected for guild {guild_id}")
            return
        
        queue = self.get_queue(guild_id)
        print(f"📊 Current queue length: {len(queue)}")
        
        if queue:
            media_url, title, song_data = queue.popleft()
            print(f"▶️ Popped from queue: {title}")
            print(f"🔗 Media URL: {media_url[:50]}...")
            self.now_playing[guild_id] = song_data
            
            def after_playing(error):
                if error:
                    print(f"❌ Error playing song: {error}")
                print(f"✅ Song finished: {title}")
                print(f"🔄 Calling play_next from callback...")
                self.play_next(guild_id, voice_client)
            
            try:
                source = discord.FFmpegPCMAudio(media_url, **self.FFMPEG_OPTIONS)
                voice_client.play(source, after=after_playing)
                print(f"🎵 Now playing: {title}\n")
            except Exception as e:
                print(f"❌ Failed to play {title}: {e}")
                self.play_next(guild_id, voice_client)
        else:
            print(f"📭 Queue empty for guild {guild_id}")
            if guild_id in self.now_playing:
                del self.now_playing[guild_id]
    
    async def add_music_reactions(self, message):
        """Add all music control reactions to a message"""
        for emoji in self.REACTIONS.values():
            await message.add_reaction(emoji)



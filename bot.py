"""
Discord Bot Module - Runs alongside FastAPI backend
Handles Discord server management, stats, and commands
"""

import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import os
from datetime import datetime
from database import get_database

class DiscordBot:
    """Discord Bot integrated with FastAPI backend"""
    
    def __init__(self):
        self.token = os.getenv('DISCORD_BOT_TOKEN')
        self.guild_id = int(os.getenv('DISCORD_GUILD_ID', 0))
        
        # Load individual role IDs
        self.ceo_role_id = int(os.getenv('CEO_ROLE_ID')) if os.getenv('CEO_ROLE_ID') else None
        self.manager_role_id = int(os.getenv('MANAGER_ROLE_ID')) if os.getenv('MANAGER_ROLE_ID') else None
        self.member_role_id = int(os.getenv('MEMBER_ROLE_ID')) if os.getenv('MEMBER_ROLE_ID') else None
        
        print(f'🔧 CEO Role ID: {self.ceo_role_id}')
        print(f'🔧 Manager Role ID: {self.manager_role_id}')
        print(f'🔧 Member Role ID: {self.member_role_id}')
        
        # Setup intents
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        intents.message_content = True
        intents.guilds = True
        
        # Create bot instance
        self.bot = commands.Bot(
            command_prefix=os.getenv('COMMAND_PREFIX', '!'),
            intents=intents,
            help_command=None
        )
        
        self.is_ready = False
        self._setup_events()
        self._setup_commands()
    
    def _setup_events(self):
        """Setup Discord event handlers"""
        
        @self.bot.event
        async def on_ready():
            """Bot startup event"""
            print(f'✅ Discord Bot: {self.bot.user} connected!')
            print(f'📊 Connected to {len(self.bot.guilds)} guild(s)')
            
            # Set bot status
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=os.getenv('BOT_STATUS', 'Maestros Community')
                ),
                status=discord.Status.online
            )
            
            # Start background tasks
            self.update_stats.start()
            self.sync_roles.start()
            
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
    
    def _setup_commands(self):
        """Setup Discord bot commands"""
        
        @self.bot.command(name='ping')
        async def ping(ctx):
            """Check bot latency"""
            latency = round(self.bot.latency * 1000)
            embed = discord.Embed(
                title='🏓 Pong!',
                description=f'Latency: {latency}ms',
                color=0xFFD363
            )
            await ctx.send(embed=embed)
        
        @self.bot.command(name='stats')
        async def stats(ctx):
            """Show server stats"""
            guild = ctx.guild
            online = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
            
            embed = discord.Embed(title='📊 Server Statistics', color=0xFFD363)
            embed.add_field(name='Total Members', value=guild.member_count, inline=True)
            embed.add_field(name='Online', value=online, inline=True)
            embed.add_field(name='Channels', value=len(guild.channels), inline=True)
            embed.add_field(name='Roles', value=len(guild.roles), inline=True)
            embed.add_field(name='Boost Level', value=guild.premium_tier, inline=True)
            embed.add_field(name='Boosts', value=guild.premium_subscription_count, inline=True)
            embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            embed.set_footer(text=f'Server ID: {guild.id}')
            await ctx.send(embed=embed)
        
        @self.bot.command(name='help')
        async def help_command(ctx):
            """Show bot commands"""
            embed = discord.Embed(
                title='🤖 Maestros Bot Commands',
                description='Here are the available commands:',
                color=0xFFD363
            )
            commands_list = [
                ('!ping', 'Check bot latency'),
                ('!stats', 'Show server statistics'),
                ('!help', 'Show this help message'),
                ('!apply', 'Get application link'),
                ('!events', 'Show upcoming events'),
            ]
            for cmd, desc in commands_list:
                embed.add_field(name=cmd, value=desc, inline=False)
            await ctx.send(embed=embed)
        
        @self.bot.command(name='apply')
        async def apply(ctx):
            """Get application link"""
            embed = discord.Embed(
                title='📝 Apply to Maestros',
                description='Ready to join our elite community? Apply now!',
                color=0xFFD363
            )
            embed.add_field(
                name='Application Portal',
                value='[Click here to apply](https://maestros-community-frontend-5arz.vercel.app//apply)',
                inline=False
            )
            embed.add_field(
                name='Requirements',
                value='• Active Discord member\n• Positive attitude\n• Team player\n• Gaming experience',
                inline=False
            )
            await ctx.send(embed=embed)
        
        @self.bot.command(name='events')
        async def events(ctx):
            """Show upcoming events"""
            db = get_database()
            if db is None:
                await ctx.send('❌ Database not connected')
                return
            
            upcoming = await db.events.find({
                'status': 'upcoming',
                'date': {'$gte': datetime.utcnow()}
            }).sort('date', 1).limit(5).to_list(5)
            
            if not upcoming:
                await ctx.send('No upcoming events at the moment.')
                return
            
            embed = discord.Embed(title='📅 Upcoming Events', color=0xFFD363)
            for event in upcoming:
                date_str = event['date'].strftime('%Y-%m-%d %H:%M UTC')
                participants = len(event.get('participants', []))
                max_participants = event.get('max_participants', 0)
                embed.add_field(
                    name=event['title'],
                    value=f"📅 {date_str}\n🎮 {event.get('game', 'N/A')}\n👥 {participants}/{max_participants}\n🏆 {event.get('prize', 'N/A')}",
                    inline=False
                )
            embed.set_footer(text='Visit the website to register')
            await ctx.send(embed=embed)
        
        @self.bot.command(name='announce')
        @commands.has_permissions(administrator=True)
        async def announce(ctx, channel: discord.TextChannel, *, message):
            """Make an announcement (Admin only)"""
            embed = discord.Embed(
                title='📢 Announcement',
                description=message,
                color=0xFFD363,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f'By {ctx.author}', icon_url=ctx.author.display_avatar.url)
            await channel.send('@everyone', embed=embed)
            await ctx.send(f'✅ Announcement sent to {channel.mention}')
    
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
                            
                            # Add permissions info
                            is_ceo = self.ceo_role_id and self.ceo_role_id in member_role_ids
                            is_manager = self.manager_role_id and self.manager_role_id in member_role_ids
                            is_admin = any('admin' in role.name.lower() for role in member.roles)
                            
                            member_info['permissions'] = {
                                'is_ceo': is_ceo,
                                'is_manager': is_manager,
                                'is_admin': is_admin,
                                'can_manage_applications': is_manager or is_ceo or is_admin
                            }
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
            
            # Update in-memory stats (accessed by discord router)
            from routers.discord import discord_stats
            discord_stats.update({
                'total': guild.member_count,
                'online': len(online_members),
                'ceo_online': ceo_online,
                'manager_online': manager_online,
                'community_member_online': community_member_online,
                'last_update': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            print(f'❌ Error updating stats: {e}')
    
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
                
                role_names = [role.name for role in member.roles if role.name != '@everyone']
                
                await db.users.update_one(
                    {'discord_id': str(member.id)},
                    {
                        '$set': {
                            'guild_roles': role_names,
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

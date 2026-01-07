"""
Server Stats Cog - Handles FiveM and Discord statistics display
Updates voice channels with live player counts and member statistics
"""

import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import os
from datetime import datetime
import fivempy


class ServerStats(commands.Cog):
    """Cog for displaying server statistics in voice channels"""
    
    def __init__(self, bot):
        self.bot = bot
        self.guild_id = int(os.getenv('DISCORD_GUILD_ID', 0))
        
        # FiveM Server Configuration
        self.fivem_server_ip = os.getenv('FIVEM_SERVER_IP', '')
        self.fivem_server_name = os.getenv('FIVEM_SERVER_NAME', 'Maestros RP')
        self.fivem_stats_channel_id = int(os.getenv('FIVEM_STATS_CHANNEL_ID')) if os.getenv('FIVEM_STATS_CHANNEL_ID') else None
        self.member_count_channel_id = int(os.getenv('MEMBER_COUNT_CHANNEL_ID')) if os.getenv('MEMBER_COUNT_CHANNEL_ID') else None
        self.fivem_stats_text_channel_id = int(os.getenv('FIVEM_STATS_TEXT_CHANNEL_ID')) if os.getenv('FIVEM_STATS_TEXT_CHANNEL_ID') else None
        
        # Store the stats message ID for updating
        self.stats_message_id = None
        
        print(f'🎮 [ServerStats] FiveM Server: {self.fivem_server_name}')
        print(f'🎮 [ServerStats] FiveM IP: {self.fivem_server_ip}')
        print(f'📊 [ServerStats] FiveM Stats Channel: {self.fivem_stats_channel_id}')
        print(f'📊 [ServerStats] Member Count Channel: {self.member_count_channel_id}')
        print(f'💬 [ServerStats] FiveM Stats Text Channel: {self.fivem_stats_text_channel_id}')
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        print('✅ [ServerStats] Starting server stats update task...')
        self.update_server_stats.start()
    
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        print('⚠️ [ServerStats] Stopping server stats update task...')
        self.update_server_stats.cancel()
    
    async def fetch_fivem_server_info(self):
        """Fetch FiveM server information using fivempy library"""
        try:
            if not self.fivem_server_ip:
                return None
            
            # Use fivempy to fetch server data
            loop = asyncio.get_event_loop()
            server = await loop.run_in_executor(None, fivempy.Server, self.fivem_server_ip)
            
            if server and server.dynamic:
                print(f'✅ [ServerStats] Connected to FiveM server: {server.dynamic.get("hostname", "Unknown")}')
                return {
                    'clients': server.dynamic.get('clients', 0),
                    'sv_maxclients': int(server.dynamic.get('sv_maxclients', 32)),
                    'hostname': server.dynamic.get('hostname', self.fivem_server_name),
                    'gametype': server.dynamic.get('gametype', 'Roleplay'),
                    'mapname': server.dynamic.get('mapname', 'Los Santos'),
                    'server_obj': server  # Store the server object for later use
                }
        except Exception as e:
            print(f'⚠️ [ServerStats] Error fetching FiveM server info: {e}')
        
        return None
    
    async def fetch_fivem_players(self):
        """Fetch detailed player list from FiveM server using fivempy"""
        try:
            if not self.fivem_server_ip:
                return None
            
            loop = asyncio.get_event_loop()
            server = await loop.run_in_executor(None, fivempy.Server, self.fivem_server_ip)
            
            if server and server.players:
                return server.players
        except Exception as e:
            print(f'⚠️ [ServerStats] Error fetching player list: {e}')
        
        return None
    
    async def fetch_fivem_info(self):
        """Fetch static server information from FiveM using fivempy"""
        try:
            if not self.fivem_server_ip:
                return None
            
            loop = asyncio.get_event_loop()
            server = await loop.run_in_executor(None, fivempy.Server, self.fivem_server_ip)
            
            if server and server.info:
                return server.info
        except Exception as e:
            print(f'⚠️ [ServerStats] Error fetching server info: {e}')
        
        return None
    
    @tasks.loop(minutes=1)
    async def update_server_stats(self):
        """Update voice channel names with FiveM and Discord stats every 1 minute for real-time updates"""
        try:
            if not self.guild_id:
                return
            
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                print(f'⚠️ [ServerStats] Guild {self.guild_id} not found')
                return
            
            # Update FiveM stats channel
            if self.fivem_stats_channel_id and self.fivem_server_ip:
                await self._update_fivem_stats(guild)
            
            # Update Discord member count channel
            if self.member_count_channel_id:
                await self._update_member_count(guild)
            
            # Update detailed FiveM stats in text channel
            if self.fivem_stats_text_channel_id and self.fivem_server_ip:
                await self._update_stats_embed(guild)
            
        except discord.errors.HTTPException as e:
            # Rate limit or other Discord API error
            if e.status == 429:
                print('⚠️ [ServerStats] Rate limited when updating stats channels')
            else:
                print(f'⚠️ [ServerStats] Discord HTTP error updating stats: {e}')
        except Exception as e:
            print(f'❌ [ServerStats] Error updating server stats: {e}')
    
    async def _update_fivem_stats(self, guild):
        """Update the FiveM player count channel"""
        try:
            fivem_info = await self.fetch_fivem_server_info()
            channel = guild.get_channel(self.fivem_stats_channel_id)
            
            if not channel or not isinstance(channel, discord.VoiceChannel):
                print(f'⚠️ [ServerStats] FiveM stats channel {self.fivem_stats_channel_id} not found or not a voice channel')
                return
            
            if fivem_info:
                player_count = fivem_info['clients']
                max_players = fivem_info['sv_maxclients']
                new_name = f"🎮 Players: {player_count}/{max_players}"
                
                if channel.name != new_name:
                    await channel.edit(name=new_name)
                    print(f'✅ [ServerStats] Updated FiveM stats: {new_name}')
            else:
                # Server offline or unreachable
                new_name = "🎮 Server: Offline"
                if channel.name != new_name:
                    await channel.edit(name=new_name)
                    print('⚠️ [ServerStats] FiveM server appears offline')
        except Exception as e:
            print(f'❌ [ServerStats] Error updating FiveM stats: {e}')
    
    async def _update_member_count(self, guild):
        """Update the Discord member count channel"""
        try:
            channel = guild.get_channel(self.member_count_channel_id)
            
            if not channel or not isinstance(channel, discord.VoiceChannel):
                print(f'⚠️ [ServerStats] Member count channel {self.member_count_channel_id} not found or not a voice channel')
                return
            
            member_count = guild.member_count
            new_name = f"👥 Members: {member_count}"
            
            if channel.name != new_name:
                await channel.edit(name=new_name)
                print(f'✅ [ServerStats] Updated member count: {new_name}')
        except Exception as e:
            print(f'❌ [ServerStats] Error updating member count: {e}')
    
    async def _update_stats_embed(self, guild):
        """Update or create detailed stats embed in text channel"""
        try:
            channel = guild.get_channel(self.fivem_stats_text_channel_id)
            
            if not channel or not isinstance(channel, discord.TextChannel):
                print(f'⚠️ [ServerStats] Stats text channel {self.fivem_stats_text_channel_id} not found or not a text channel')
                return
            
            # Fetch all server data
            server_info = await self.fetch_fivem_server_info()
            players_data = await self.fetch_fivem_players()
            info_data = await self.fetch_fivem_info()
            
            # Create embed
            embed = await self._create_stats_embed(guild, server_info, players_data, info_data)
            
            # Update or send message
            if self.stats_message_id:
                try:
                    message = await channel.fetch_message(self.stats_message_id)
                    await message.edit(embed=embed)
                    print('✅ [ServerStats] Updated stats embed')
                except discord.NotFound:
                    # Message deleted, send new one
                    message = await channel.send(embed=embed)
                    self.stats_message_id = message.id
                    print('✅ [ServerStats] Created new stats embed')
            else:
                # First time or message not found, send new message
                message = await channel.send(embed=embed)
                self.stats_message_id = message.id
                print('✅ [ServerStats] Created stats embed')
                
        except Exception as e:
            print(f'❌ [ServerStats] Error updating stats embed: {e}')
    
    async def _create_stats_embed(self, guild, server_info, players_data, info_data):
        """Create a rich embed with all server statistics and community member tracking"""
        timestamp = datetime.utcnow()
        
        if not server_info:
            # Server offline
            embed = discord.Embed(
                title="🎮 FiveM Server Status",
                description="**Server is currently OFFLINE** ⚠️",
                color=discord.Color.red(),
                timestamp=timestamp
            )
            embed.add_field(name="🏷️ Server Name", value=self.fivem_server_name, inline=False)
            embed.add_field(name="🌐 Server IP", value=f"`{self.fivem_server_ip}`", inline=False)
            embed.add_field(
                name="💡 Tip",
                value="The bot will automatically update when the server comes back online!",
                inline=False
            )
            embed.set_footer(text="Updates every minute • Last Checked")
            return embed
        
        # Server online - create detailed embed
        player_count = server_info['clients']
        max_players = server_info['sv_maxclients']
        hostname = server_info['hostname']
        gametype = server_info['gametype']
        mapname = server_info['mapname']
        
        # Determine color based on player count
        if player_count == 0:
            color = discord.Color.orange()
            status_emoji = "🟠"
            status_text = "ONLINE - Empty"
        elif player_count >= max_players * 0.8:
            color = discord.Color.red()
            status_emoji = "🔴"
            status_text = "ONLINE - Nearly Full"
        else:
            color = discord.Color.green()
            status_emoji = "🟢"
            status_text = "ONLINE"
        
        embed = discord.Embed(
            title=f"{status_emoji} {hostname}",
            description=f"**Status:** {status_text}\n**Game Mode:** {gametype} | **Map:** {mapname}",
            color=color,
            timestamp=timestamp
        )
        
        # Server Info Section
        embed.add_field(
            name="📊 Server Statistics",
            value=f"**👥 Players Online:** `{player_count}/{max_players}`\n"
                  f"**🌐 Connect:** `{self.fivem_server_ip}`\n"
                  f"**🎮 Server:** {self.fivem_server_name}",
            inline=False
        )
        
        # Player tracking with community member detection
        if players_data and len(players_data) > 0:
            community_players = []
            guest_players = []
            
            for player in players_data:
                name = player.get('name', 'Unknown')
                ping = player.get('ping', 0)
                player_id = player.get('id', '?')
                
                # Extract identifiers
                identifiers = player.get('identifiers', [])
                discord_id = next((id.split(':')[1] for id in identifiers if id.startswith('discord:')), None)
                steam_id = next((id.split(':')[1] for id in identifiers if id.startswith('steam:')), None)
                
                # Check if this Discord ID belongs to a guild member
                is_community_member = False
                member = None
                if discord_id:
                    try:
                        member = guild.get_member(int(discord_id))
                        if member:
                            is_community_member = True
                    except:
                        pass
                
                player_info = {
                    'name': name,
                    'id': player_id,
                    'ping': ping,
                    'discord_id': discord_id,
                    'steam_id': steam_id,
                    'member': member
                }
                
                if is_community_member:
                    community_players.append(player_info)
                else:
                    guest_players.append(player_info)
            
            # Show Community Members Playing (Priority)
            if community_players:
                member_lines = []
                for i, player in enumerate(community_players, 1):
                    mention = f"<@{player['discord_id']}>" if player['discord_id'] else ""
                    line = f"`{i}.` **{player['name']}** {mention}"
                    if player['ping']:
                        line += f" `({player['ping']}ms)`"
                    member_lines.append(line)
                
                embed.add_field(
                    name=f"⭐ Community Members Playing ({len(community_players)})",
                    value="\n".join(member_lines) if member_lines else "None",
                    inline=False
                )
            
            # Show All Other Players
            if guest_players:
                guest_lines = []
                # Show up to 15 guest players
                for i, player in enumerate(guest_players[:15], 1):
                    line = f"`{i}.` **{player['name']}**"
                    if player['ping']:
                        line += f" `({player['ping']}ms)`"
                    if player['discord_id']:
                        line += f" 🔗"  # Has Discord linked but not in server
                    guest_lines.append(line)
                
                if len(guest_players) > 15:
                    guest_lines.append(f"\n*... and {len(guest_players) - 15} more players*")
                
                embed.add_field(
                    name=f"👤 Other Players ({len(guest_players)})",
                    value="\n".join(guest_lines) if guest_lines else "None",
                    inline=False
                )
            
            # Summary Stats
            embed.add_field(
                name="📈 Player Breakdown",
                value=f"**Community Members:** {len(community_players)}\n"
                      f"**Guest Players:** {len(guest_players)}\n"
                      f"**Total Online:** {player_count}",
                inline=True
            )
        else:
            embed.add_field(
                name="👥 Online Players (0)",
                value="*No players currently online*\n\nBe the first to join!",
                inline=False
            )
        
        # Server Resources (if available)
        if info_data:
            resources = info_data.get('resources', [])
            server_version = info_data.get('server', 'Unknown')
            vars_data = info_data.get('vars', {})
            
            resource_count = len(resources)
            onesync = vars_data.get('onesync_enabled', 'Unknown')
            
            embed.add_field(
                name="⚙️ Server Info",
                value=f"**Version:** {server_version}\n"
                      f"**Resources:** {resource_count}\n"
                      f"**OneSync:** {'✅ Enabled' if onesync == '1' else '❌ Disabled'}",
                inline=True
            )
        
        # Discord Community Stats
        online_members = len([m for m in guild.members if m.status != discord.Status.offline and not m.bot])
        embed.add_field(
            name="💬 Discord Community",
            value=f"**Total Members:** {guild.member_count}\n"
                  f"**Online Now:** {online_members}",
            inline=True
        )
        
        embed.set_footer(text="🔄 Real-time updates every minute • Last Updated")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        return embed
    
    @update_server_stats.before_loop
    async def before_update_server_stats(self):
        """Wait for bot to be ready before starting the loop"""
        await self.bot.wait_until_ready()
        print('✅ [ServerStats] Bot ready, starting stats updates...')


async def setup(bot):
    """Setup function to load the cog"""
    await bot.add_cog(ServerStats(bot))

"""
Music Commands Cog
Contains music playback commands for Discord voice channels
"""

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import random
from collections import deque


class Music(commands.Cog):
    """Music playback commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.parent_bot = None  # Will be set by parent DiscordBot instance
        
        # Music bot variables
        self.queues = {}  # guild_id -> deque of (media_url, title, song_data)
        self.now_playing = {}  # guild_id -> song_data
        self.history = {}  # guild_id -> list of (media_url, title, song_data)
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
            "previous": "⏮️",
            "pause": "⏸️",
            "resume": "▶️",
            "skip": "⏭️",
            "loop": "🔁",
            "shuffle": "🔀",
            "stop": "⏹️",
            "queue": "📋"
        }
    
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
        embed.set_image(url="https://cdn.pixabay.com/animation/2024/01/13/23/46/23-46-52-835_512.gif")
        
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
            
            # Add current song to history before playing next
            if guild_id not in self.history:
                self.history[guild_id] = []
            if guild_id in self.now_playing:
                # Add the currently playing song to history
                current = self.now_playing[guild_id]
                if current.get('media_url'):
                    self.history[guild_id].append((current['media_url'], current.get('song', 'Unknown'), current))
                    # Keep only last 10 songs in history
                    if len(self.history[guild_id]) > 10:
                        self.history[guild_id].pop(0)
            
            # Add media_url to song_data for later use
            song_data['media_url'] = media_url
            self.now_playing[guild_id] = song_data
            
            # Update the embed message for the new song
            if guild_id in self.music_messages:
                self.bot.loop.create_task(self.update_now_playing_embed(guild_id, song_data, voice_client))
            
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
    
    async def update_now_playing_embed(self, guild_id, song_data, voice_client):
        """Update the now playing embed message"""
        try:
            # Wait a bit for the song to start playing
            await asyncio.sleep(0.5)
            
            if guild_id not in self.music_messages:
                print(f"⚠️ No music message found for guild {guild_id}")
                return
            
            message_id = self.music_messages[guild_id]
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print(f"⚠️ Guild {guild_id} not found")
                return
            
            # Try to find and update the message
            message = None
            for channel in guild.text_channels:
                try:
                    message = await channel.fetch_message(message_id)
                    if message:
                        channel_name = voice_client.channel.name if voice_client and voice_client.channel else None
                        embed = self.create_music_embed(song_data, "now_playing", "playing", None, channel_name)
                        await message.edit(embed=embed)
                        print(f"✅ Updated embed in {channel.name} for guild {guild_id}")
                        print(f"🎵 Now showing: {song_data.get('song', 'Unknown')}")
                        return
                except discord.NotFound:
                    # Message deleted, remove from tracking
                    print(f"⚠️ Message {message_id} not found in {channel.name}")
                    continue
                except discord.Forbidden:
                    print(f"⚠️ No permission to edit message in {channel.name}")
                    continue
                except Exception as e:
                    continue
            
            if not message:
                print(f"⚠️ Could not find message {message_id} in any channel")
                # Clean up the reference
                del self.music_messages[guild_id]
        except Exception as e:
            print(f"❌ Failed to update embed: {e}")
            import traceback
            traceback.print_exc()
    
    async def add_music_reactions(self, message):
        """Add all music control reactions to a message"""
        for emoji in self.REACTIONS.values():
            await message.add_reaction(emoji)
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handle music control reactions"""
        if user.bot:
            return
        
        guild = reaction.message.guild
        emoji = str(reaction.emoji)
        
        # Handle queue jump reactions
        if hasattr(self, 'queue_messages') and reaction.message.id in self.queue_messages:
            number_emojis = {"1️⃣": 0, "2️⃣": 1, "3️⃣": 2, "4️⃣": 3, "5️⃣": 4, "6️⃣": 5, "7️⃣": 6, "8️⃣": 7, "9️⃣": 8, "🔟": 9}
            if emoji in number_emojis:
                jump_index = number_emojis[emoji]
                queue = self.get_queue(guild.id)
                vc = guild.voice_client
                
                if jump_index < len(queue):
                    # Remove all songs before the target song
                    for _ in range(jump_index):
                        queue.popleft()
                    
                    # Skip current song to start the target song
                    if vc and vc.is_playing():
                        vc.stop()
                    
                    await reaction.message.channel.send(f"⏭️ Jumping to song #{jump_index + 1}!")
                    # Delete queue message after jump
                    try:
                        await reaction.message.delete()
                    except:
                        pass
                else:
                    await reaction.message.channel.send(f"❌ Song #{jump_index + 1} not in queue!")
            return
        
        # Handle music control reactions on now playing message
        if reaction.message.guild.id not in self.music_messages:
            return
        if self.music_messages[reaction.message.guild.id] != reaction.message.id:
            return
        
        vc = guild.voice_client
        
        await reaction.remove(user)
        
        # Get current song data for embed updates
        song_data = self.now_playing.get(guild.id)
        if not song_data:
            return
        
        updated = False
        
        if emoji == self.REACTIONS["previous"] and vc:
            # Go back to previous song
            history = self.history.get(guild.id, [])
            if history:
                # Get the last song from history
                prev_media_url, prev_title, prev_song_data = history.pop()
                
                # Add current song back to front of queue
                queue = self.get_queue(guild.id)
                if guild.id in self.now_playing:
                    current = self.now_playing[guild.id]
                    queue.appendleft((current['media_url'], current.get('song', 'Unknown'), current))
                
                # Play previous song
                vc.stop()  # This will trigger play_next, but we'll override
                prev_song_data['media_url'] = prev_media_url
                self.now_playing[guild.id] = prev_song_data
                
                try:
                    source = discord.FFmpegPCMAudio(prev_media_url, **self.FFMPEG_OPTIONS)
                    
                    def after_prev(error):
                        if error:
                            print(f"❌ Error playing previous song: {error}")
                        self.play_next(guild.id, vc)
                    
                    vc.play(source, after=after_prev)
                    # Update embed for previous song
                    self.bot.loop.create_task(self.update_now_playing_embed(guild.id, prev_song_data, vc))
                except Exception as e:
                    print(f"❌ Failed to play previous song: {e}")
            else:
                await user.send("⏮️ No previous song in history!")
        elif emoji == self.REACTIONS["pause"] and vc and vc.is_playing():
            vc.pause()
            embed = self.create_music_embed(song_data, "now_playing", "paused", None, vc.channel.name if vc.channel else None)
            updated = True
        elif emoji == self.REACTIONS["resume"] and vc and vc.is_paused():
            vc.resume()
            embed = self.create_music_embed(song_data, "now_playing", "playing", None, vc.channel.name if vc.channel else None)
            updated = True
        elif emoji == self.REACTIONS["skip"] and vc and vc.is_playing():
            vc.stop()
            # Don't set updated=True, let play_next handle the embed update
            print(f"⏭️ Skipped song, play_next will update embed")
        elif emoji == self.REACTIONS["loop"]:
            guild_id = guild.id
            self.loop_mode[guild_id] = not self.loop_mode.get(guild_id, False)
            loop_status = "🔁 Loop: ON" if self.loop_mode[guild_id] else "🔁 Loop: OFF"
            msg = await reaction.message.channel.send(loop_status)
            # Auto-delete after 3 seconds
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except:
                pass
        elif emoji == self.REACTIONS["shuffle"]:
            queue = self.get_queue(guild.id)
            if len(queue) > 1:
                queue_list = list(queue)
                random.shuffle(queue_list)
                queue.clear()
                queue.extend(queue_list)
                msg = await reaction.message.channel.send("🔀 Queue shuffled!")
                # Auto-delete after 3 seconds
                await asyncio.sleep(3)
                try:
                    await msg.delete()
                except:
                    pass
        elif emoji == self.REACTIONS["stop"] and vc and vc.is_playing():
            vc.stop()
            queue = self.get_queue(guild.id)
            queue.clear()
            if guild.id in self.now_playing:
                del self.now_playing[guild.id]
            if guild.id in self.history:
                self.history[guild.id].clear()
            embed = discord.Embed(title="⏹️ Stopped", description="Playback stopped and queue cleared.", color=discord.Color.red())
            updated = True
        elif emoji == self.REACTIONS["queue"]:
            queue = self.get_queue(guild.id)
            if not queue:
                embed_queue = discord.Embed(title="📋 Queue Empty", description="No songs in queue.", color=discord.Color.light_gray())
                queue_msg = await reaction.message.channel.send(embed=embed_queue)
                # Auto-delete after 10 seconds
                await asyncio.sleep(10)
                try:
                    await queue_msg.delete()
                except:
                    pass
            else:
                queue_list = "\n".join([f"**{idx + 1}.** {title}" for idx, (_, title, _) in enumerate(list(queue)[:10])])
                embed_queue = discord.Embed(title="📋 Current Queue", description=queue_list, color=discord.Color.blue())
                embed_queue.set_footer(text=f"Total: {len(queue)} songs" + (" (showing first 10)" if len(queue) > 10 else "") + "\nReact with number to jump to that song!")
                queue_msg = await reaction.message.channel.send(embed=embed_queue)
                
                # Add number reactions to jump to songs
                number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
                for i in range(min(len(queue), 10)):
                    try:
                        await queue_msg.add_reaction(number_emojis[i])
                    except:
                        pass
                
                # Store queue message for jump handling
                if not hasattr(self, 'queue_messages'):
                    self.queue_messages = {}
                self.queue_messages[queue_msg.id] = guild.id
        
        # Update the message embed if state changed
        if updated:
            try:
                await reaction.message.edit(embed=embed)
            except Exception as e:
                print(f"❌ Failed to update embed: {e}")
    
    @app_commands.command(name="play", description="Play a song in voice channel")
    @app_commands.describe(song_name="Name of the song to play")
    async def play(self, interaction: discord.Interaction, song_name: str):
        """Play a song in voice channel"""
        print(f"🎵 Play command invoked for: {song_name}")
        await interaction.response.defer()
        
        if not interaction.user.voice:
            embed = discord.Embed(title="❌ Error", description="You must be in a voice channel to use this command!", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return

        voice_channel = interaction.user.voice.channel
        
        # Get API base URL from parent bot
        api_base = self.parent_bot.api_base if self.parent_bot else "http://localhost:8000/music"
        
        print(f"🔍 Searching for song: {song_name} at {api_base}")

        try:
            # Use aiohttp for async HTTP requests
            timeout = aiohttp.ClientTimeout(total=20, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{api_base}/song/", params={"query": song_name}) as response:
                    print(f"✅ API responded with status {response.status}")
                    if response.status == 404:
                        embed = discord.Embed(title="❌ Not Found", description=f"Could not find: **{song_name}**", color=discord.Color.orange())
                        await interaction.followup.send(embed=embed)
                        return
                    elif response.status != 200:
                        embed = discord.Embed(title="❌ API Error", description=f"Music API returned error {response.status}. Please try again.", color=discord.Color.red())
                        await interaction.followup.send(embed=embed)
                        return
                    
                    data = await response.json()
                    print(f"✅ Got song data: {data.get('song', 'Unknown')}")
        except aiohttp.ClientError as e:
            print(f"❌ HTTP error: {type(e).__name__}: {e}")
            embed = discord.Embed(title="❌ Connection Error", description="Cannot connect to music service. Please try again later.", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return
        except Exception as e:
            print(f"❌ Unexpected error: {type(e).__name__}: {e}")
            embed = discord.Embed(title="❌ Error", description=f"Failed to fetch song: {str(e)[:100]}", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return

        media_url = data.get("media_url")
        if not media_url:
            embed = discord.Embed(title="❌ Not Found", description=f"Could not find: **{song_name}**", color=discord.Color.orange())
            await interaction.followup.send(embed=embed)
            return

        song_title = data.get("song", song_name)

        if interaction.guild.voice_client is None:
            vc = await voice_channel.connect()
        else:
            vc = interaction.guild.voice_client

        queue = self.get_queue(interaction.guild.id)
        queue.append((media_url, song_title, data))

        if not vc.is_playing():
            self.play_next(interaction.guild.id, vc)
            embed = self.create_music_embed(data, "now_playing", "playing", interaction.user.mention, voice_channel.name)
            message = await interaction.followup.send(embed=embed)
            self.music_messages[interaction.guild.id] = message.id
            await self.add_music_reactions(message)
        else:
            embed = self.create_music_embed(data, "queued", "queued", interaction.user.mention, voice_channel.name)
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="playlist", description="Play a playlist in voice channel")
    @app_commands.describe(playlist_name="Name or URL of the playlist")
    async def playlist(self, interaction: discord.Interaction, playlist_name: str):
        """Play a playlist in voice channel"""
        await interaction.response.defer()
        
        if not interaction.user.voice:
            embed = discord.Embed(title="❌ Error", description="You must be in a voice channel!", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return
        
        # Get API base URL from parent bot
        api_base = self.parent_bot.api_base if self.parent_bot else "http://localhost:8000/music"

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{api_base}/playlist/", params={"query": playlist_name}) as response:
                    if response.status != 200:
                        raise Exception(f"API returned status {response.status}")
                    data = await response.json()
        except aiohttp.ClientError as e:
            embed = discord.Embed(title="⏱️ Timeout", description=f"Loading playlist **{playlist_name}** took too long. Try again.", color=discord.Color.orange())
            await interaction.followup.send(embed=embed)
            return
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=f"Failed to fetch playlist: {str(e)[:100]}", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return

        songs = data.get("songs", [])
        if not songs:
            embed = discord.Embed(title="❌ Not Found", description=f"Playlist empty: **{playlist_name}**", color=discord.Color.orange())
            await interaction.followup.send(embed=embed)
            return

        voice_channel = interaction.user.voice.channel
        if interaction.guild.voice_client is None:
            vc = await voice_channel.connect()
        else:
            vc = interaction.guild.voice_client

        queue = self.get_queue(interaction.guild.id)
        for song in songs:
            if song.get("media_url"):
                queue.append((song["media_url"], song.get("song", "Unknown"), song))

        if not vc.is_playing():
            self.play_next(interaction.guild.id, vc)

        embed = self.create_music_embed(songs[0], "playlist", "playing", interaction.user.mention, voice_channel.name, playlist_name)
        message = await interaction.followup.send(embed=embed)
        self.music_messages[interaction.guild.id] = message.id
        await self.add_music_reactions(message)
    
    @app_commands.command(name="album", description="Play an album in voice channel")
    @app_commands.describe(album_name="Name or URL of the album")
    async def album(self, interaction: discord.Interaction, album_name: str):
        """Play an album in voice channel"""
        await interaction.response.defer()
        
        if not interaction.user.voice:
            embed = discord.Embed(title="❌ Error", description="You must be in a voice channel!", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return
        
        # Get API base URL from parent bot
        api_base = self.parent_bot.api_base if self.parent_bot else "http://localhost:8000/music"

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{api_base}/album/", params={"query": album_name}) as response:
                    if response.status != 200:
                        raise Exception(f"API returned status {response.status}")
                    data = await response.json()
        except aiohttp.ClientError as e:
            embed = discord.Embed(title="⏱️ Timeout", description=f"Loading album **{album_name}** took too long. Try again.", color=discord.Color.orange())
            await interaction.followup.send(embed=embed)
            return
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=f"Failed to fetch album: {str(e)[:100]}", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return

        songs = data.get("songs", [])
        if not songs:
            embed = discord.Embed(title="❌ Not Found", description=f"Album empty: **{album_name}**", color=discord.Color.orange())
            await interaction.followup.send(embed=embed)
            return

        voice_channel = interaction.user.voice.channel
        if interaction.guild.voice_client is None:
            vc = await voice_channel.connect()
        else:
            vc = interaction.guild.voice_client

        queue = self.get_queue(interaction.guild.id)
        for song in songs:
            if song.get("media_url"):
                queue.append((song["media_url"], song.get("song", "Unknown"), song))

        if not vc.is_playing():
            self.play_next(interaction.guild.id, vc)

        embed = self.create_music_embed(songs[0], "album", "playing", interaction.user.mention, voice_channel.name, None, album_name)
        message = await interaction.followup.send(embed=embed)
        self.music_messages[interaction.guild.id] = message.id
        await self.add_music_reactions(message)
    
    @app_commands.command(name="skip", description="Skip to the next song")
    async def skip(self, interaction: discord.Interaction):
        """Skip to the next song"""
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped!")
        else:
            await interaction.response.send_message("❌ Nothing is playing.")
    
    @app_commands.command(name="queue", description="Show the current queue")
    async def show_queue(self, interaction: discord.Interaction):
        """Show the current queue"""
        queue = self.get_queue(interaction.guild.id)
        if not queue:
            embed = discord.Embed(title="📋 Queue Empty", description="No songs in queue. Use `/play` to add some!", color=discord.Color.light_gray())
            await interaction.response.send_message(embed=embed)
            return
        
        queue_list = "\n".join([f"**{idx + 1}.** {title}" for idx, (_, title, _) in enumerate(list(queue)[:10])])
        embed = discord.Embed(title="📋 Current Queue", description=queue_list, color=discord.Color.blue())
        embed.set_footer(text=f"Total: {len(queue)} songs" + (" (showing first 10)" if len(queue) > 10 else ""))
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="stop", description="Stop playback and clear queue")
    async def stop(self, interaction: discord.Interaction):
        """Stop playback and clear queue"""
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            self.get_queue(interaction.guild.id).clear()
            await interaction.response.send_message("⏹️ Playback stopped and queue cleared.")
        else:
            await interaction.response.send_message("❌ Nothing is playing.")
    
    @app_commands.command(name="leave", description="Leave the voice channel")
    async def leave(self, interaction: discord.Interaction):
        """Leave the voice channel"""
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 Left the voice channel.")
        else:
            await interaction.response.send_message("❌ Not in a voice channel.")


async def setup(bot):
    """Setup function to load the cog"""
    await bot.add_cog(Music(bot))


"""
Music Commands Cog
Contains music playback commands for Discord voice channels
"""

import discord
from discord import app_commands
from discord.ext import commands
import requests
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
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handle music control reactions"""
        if user.bot:
            return
        
        if reaction.message.guild.id not in self.music_messages:
            return
        if self.music_messages[reaction.message.guild.id] != reaction.message.id:
            return
        
        guild = reaction.message.guild
        vc = guild.voice_client
        emoji = str(reaction.emoji)
        
        await reaction.remove(user)
        
        if emoji == self.REACTIONS["pause"] and vc and vc.is_playing():
            vc.pause()
        elif emoji == self.REACTIONS["resume"] and vc and vc.is_paused():
            vc.resume()
        elif emoji == self.REACTIONS["skip"] and vc and vc.is_playing():
            vc.stop()
        elif emoji == self.REACTIONS["loop"]:
            guild_id = guild.id
            self.loop_mode[guild_id] = not self.loop_mode.get(guild_id, False)
        elif emoji == self.REACTIONS["shuffle"]:
            queue = self.get_queue(guild.id)
            if len(queue) > 1:
                queue_list = list(queue)
                random.shuffle(queue_list)
                queue.clear()
                queue.extend(queue_list)
        elif emoji == self.REACTIONS["stop"] and vc and vc.is_playing():
            vc.stop()
            queue = self.get_queue(guild.id)
            queue.clear()
            if guild.id in self.now_playing:
                del self.now_playing[guild.id]
        elif emoji == self.REACTIONS["queue"]:
            queue = self.get_queue(guild.id)
            if not queue:
                embed = discord.Embed(title="📋 Queue Empty", description="No songs in queue.", color=discord.Color.light_gray())
                await user.send(embed=embed)
            else:
                queue_list = "\n".join([f"**{idx + 1}.** {title}" for idx, (_, title, _) in enumerate(list(queue)[:10])])
                embed = discord.Embed(title="📋 Current Queue", description=queue_list, color=discord.Color.blue())
                embed.set_footer(text=f"Total: {len(queue)} songs" + (" (showing first 10)" if len(queue) > 10 else ""))
                await user.send(embed=embed)
    
    @app_commands.command(name="play", description="Play a song in voice channel")
    @app_commands.describe(song_name="Name of the song to play")
    async def play(self, interaction: discord.Interaction, song_name: str):
        """Play a song in voice channel"""
        await interaction.response.defer()
        
        if not interaction.user.voice:
            embed = discord.Embed(title="❌ Error", description="You must be in a voice channel to use this command!", color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return

        voice_channel = interaction.user.voice.channel
        
        # Get API base URL from parent bot
        api_base = self.parent_bot.api_base if self.parent_bot else "http://localhost:8000/music"

        try:
            response = requests.get(f"{api_base}/song/", params={"query": song_name}, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=f"Failed to fetch song: {e}", color=discord.Color.red())
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
            response = requests.get(f"{api_base}/playlist/", params={"query": playlist_name}, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=f"Failed to fetch playlist: {e}", color=discord.Color.red())
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
            response = requests.get(f"{api_base}/album/", params={"query": album_name}, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=f"Failed to fetch album: {e}", color=discord.Color.red())
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

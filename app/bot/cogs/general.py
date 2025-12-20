"""
General Commands Cog
Contains general utility commands for the Discord bot
"""

import discord
from discord import app_commands
from discord.ext import commands
import os
from datetime import datetime
from app.core.database import get_database


class General(commands.Cog):
    """General utility commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.parent_bot = None  # Will be set by parent DiscordBot instance
    
    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title='🏓 Pong!',
            description=f'Latency: {latency}ms',
            color=0xFFD363
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="stats", description="Show server statistics")
    async def stats(self, interaction: discord.Interaction):
        """Show server stats"""
        guild = interaction.guild
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
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="help", description="Show bot commands")
    async def help_command(self, interaction: discord.Interaction):
        """Show bot commands"""
        embed = discord.Embed(
            title='🤖 Maestros Bot Commands',
            description='Here are the available slash commands:',
            color=0xFFD363
        )
        commands_list = [
            ('/ping', 'Check bot latency'),
            ('/stats', 'Show server statistics'),
            ('/help', 'Show this help message'),
            ('/apply', 'Get application link'),
            ('/events', 'Show upcoming events'),
            ('/announce', 'Make an announcement (Admin only)'),
            ('/play', 'Play a song in voice channel'),
            ('/playlist', 'Play a playlist'),
            ('/album', 'Play an album'),
            ('/skip', 'Skip to next song'),
            ('/queue', 'Show current queue'),
            ('/stop', 'Stop playback and clear queue'),
            ('/leave', 'Leave voice channel'),
        ]
        for cmd, desc in commands_list:
            embed.add_field(name=cmd, value=desc, inline=False)
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="apply", description="Get application link to join Maestros")
    async def apply(self, interaction: discord.Interaction):
        """Get application link"""
        frontend_url = os.getenv('FRONTEND_URL', 'https://maestros-community-frontend-5arz.vercel.app')
        
        embed = discord.Embed(
            title='📝 Apply to Maestros',
            description='Ready to join our elite community? Apply now!',
            color=0xFFD363
        )
        embed.add_field(
            name='Application Portal',
            value=f'[Click here to apply]({frontend_url}/apply)',
            inline=False
        )
        embed.add_field(
            name='Requirements',
            value='• Active Discord member\n• Positive attitude\n• Team player\n• Gaming experience',
            inline=False
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="events", description="Show upcoming events")
    async def events(self, interaction: discord.Interaction):
        """Show upcoming events"""
        db = get_database()
        if db is None:
            await interaction.response.send_message('❌ Database not connected')
            return
        
        upcoming = await db.events.find({
            'status': 'upcoming',
            'date': {'$gte': datetime.utcnow()}
        }).sort('date', 1).limit(5).to_list(5)
        
        if not upcoming:
            await interaction.response.send_message('No upcoming events at the moment.')
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
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="announce", description="Make an announcement (Admin only)")
    @app_commands.describe(
        channel="The channel to send the announcement to",
        message="The announcement message"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def announce(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        """Make an announcement (Admin only)"""
        embed = discord.Embed(
            title='📢 Announcement',
            description=message,
            color=0xFFD363,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f'By {interaction.user}', icon_url=interaction.user.display_avatar.url)
        await channel.send('@everyone', embed=embed)
        await interaction.response.send_message(f'✅ Announcement sent to {channel.mention}', ephemeral=True)
    
    @announce.error
    async def announce_error(self, interaction: discord.Interaction, error):
        """Handle announce command errors"""
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message('❌ You need Administrator permissions to use this command.', ephemeral=True)


async def setup(bot):
    """Setup function to load the cog"""
    await bot.add_cog(General(bot))


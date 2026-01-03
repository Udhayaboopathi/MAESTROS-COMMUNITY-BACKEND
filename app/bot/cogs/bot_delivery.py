"""
Bot Dealership Delivery Log Cog
Handles vehicle delivery logging with modal and persistent button
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import asyncio
import io


class BotDeliveryModal(discord.ui.Modal):
    """Modal for bot/vehicle delivery information"""
    
    def __init__(self):
        super().__init__(title='🚚 Mx Delivery Log')
    
    delivered_to = discord.ui.TextInput(
        label='Delivered To',
        placeholder='Enter location (e.g., Bot Dealership)',
        required=True,
        max_length=100
    )
    
    orders = discord.ui.TextInput(
        label='Orders',
        placeholder='Enter vehicle details (e.g., 25 Dominor)',
        required=True,
        max_length=100
    )
    
    delivery_date = discord.ui.TextInput(
        label='Date',
        placeholder='Enter date (e.g., 01.01.2026)',
        required=True,
        max_length=50
    )
    
    delivery_time = discord.ui.TextInput(
        label='Time',
        placeholder='Enter time (e.g., 17.25 - (5.35))',
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        # Create embed for the delivery log
        embed = discord.Embed(
            title='🚚 Mx Delivery Log',
            color=0xFFD700,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name='Delivered To', value=self.delivered_to.value, inline=True)
        embed.add_field(name='Orders', value=self.orders.value, inline=True)
        embed.add_field(name='Date', value=self.delivery_date.value, inline=True)
        embed.add_field(name='Time', value=self.delivery_time.value, inline=True)
        embed.add_field(name='Logged By', value=interaction.user.mention, inline=True)
        
        embed.set_footer(text=f'Submitted by {interaction.user.name}', icon_url=interaction.user.display_avatar.url)
        
        # Send the log to the channel
        await interaction.response.send_message(embed=embed, ephemeral=False)
        
        # Move button to bottom after posting log
        cog = interaction.client.get_cog('BotDelivery')
        if cog:
            await cog.move_button_to_bottom()


class BotDeliveryView(discord.ui.View):
    """Persistent view with bot delivery button"""
    
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
    
    @discord.ui.button(
        label='🚚 Mx Delivery Log',
        style=discord.ButtonStyle.primary,
        custom_id='bot_delivery_button'
    )
    async def bot_delivery_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle button click to show modal"""
        modal = BotDeliveryModal()
        await interaction.response.send_modal(modal)


class BotDelivery(commands.Cog):
    """Bot Dealership Delivery logging commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = 1440258251068407938  # Channel ID for the button
        self.button_message_id = None  # Store the button message ID
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        # Register the persistent view
        self.bot.add_view(BotDeliveryView())
        print('✅ Bot Delivery cog loaded with persistent view')
        
        # Auto-create button on bot startup
        await self.auto_setup_button()
    
    async def move_button_to_bottom(self):
        """Move the button to the bottom of the channel"""
        try:
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                return
            
            # Delete old button if it exists
            if self.button_message_id:
                try:
                    old_message = await channel.fetch_message(self.button_message_id)
                    await old_message.delete()
                except:
                    pass  # Message might already be deleted
            
            # Create new button at bottom
            embed = discord.Embed(
                title='🚚 Mx Delivery Log System',
                description='Click the button below to log a vehicle delivery.',
                color=0xFFD700
            )
            embed.add_field(
                name='How to use:',
                value='1. Click the **Mx Delivery Log** button\n'
                      '2. Fill in the delivery information\n'
                      '3. Submit the form\n'
                      '4. The log will be posted to this channel',
                inline=False
            )
            embed.set_footer(text='Bot Dealership Delivery Management System')
            
            view = BotDeliveryView()
            message = await channel.send(embed=embed, view=view)
            self.button_message_id = message.id
            
        except Exception as e:
            print(f'❌ Error moving button to bottom: {e}')
    
    async def auto_setup_button(self):
        """Automatically setup the button when bot starts"""
        try:
            await asyncio.sleep(3)  # Wait for bot to be fully ready
            channel = self.bot.get_channel(self.channel_id)
            
            if not channel:
                print(f'⚠️ Could not find channel with ID: {self.channel_id}')
                return
            
            # Check if button already exists in recent messages
            async for message in channel.history(limit=50):
                if message.author == self.bot.user and len(message.embeds) > 0:
                    if message.embeds[0].title == '🚚 Mx Delivery Log System':
                        print(f'✅ Bot delivery button already exists in channel')
                        self.button_message_id = message.id
                        return
            
            # Create the button if it doesn't exist
            embed = discord.Embed(
                title='🚚 Mx Delivery Log System',
                description='Click the button below to log a vehicle delivery.',
                color=0xFFD700
            )
            embed.add_field(
                name='How to use:',
                value='1. Click the **Mx Delivery Log** button\n'
                      '2. Fill in the delivery information\n'
                      '3. Submit the form\n'
                      '4. The log will be posted to this channel',
                inline=False
            )
            embed.set_footer(text='Bot Dealership Delivery Management System')
            
            view = BotDeliveryView()
            message = await channel.send(embed=embed, view=view)
            self.button_message_id = message.id
            print(f'✅ Bot delivery button created in channel {self.channel_id}')
            
        except Exception as e:
            print(f'❌ Error setting up bot delivery button: {e}')
    
    @app_commands.command(name="setup_bot_delivery", description="Setup bot delivery log button (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_bot_delivery(self, interaction: discord.Interaction):
        """Setup the bot delivery button in the specified channel"""
        channel = self.bot.get_channel(self.channel_id)
        
        if not channel:
            await interaction.response.send_message(
                f'❌ Could not find channel with ID: {self.channel_id}',
                ephemeral=True
            )
            return
        
        # Create embed for the button message
        embed = discord.Embed(
            title='🚚 Mx Delivery Log System',
            description='Click the button below to log a vehicle delivery.',
            color=0xFFD700
        )
        embed.add_field(
            name='How to use:',
            value='1. Click the **Mx Delivery Log** button\n'
                  '2. Fill in the delivery information\n'
                  '3. Submit the form\n'
                  '4. The log will be posted to this channel',
            inline=False
        )
        embed.set_footer(text='Bot Dealership Delivery Management System')
        
        # Send the message with the button
        view = BotDeliveryView()
        await channel.send(embed=embed, view=view)
        
        await interaction.response.send_message(
            f'✅ Bot delivery log button has been set up in <#{self.channel_id}>',
            ephemeral=True
        )
    
    @setup_bot_delivery.error
    async def setup_bot_delivery_error(self, interaction: discord.Interaction, error):
        """Handle setup command errors"""
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                '❌ You need Administrator permissions to use this command.',
                ephemeral=True
            )


async def setup(bot):
    """Setup function for cog"""
    await bot.add_cog(BotDelivery(bot))

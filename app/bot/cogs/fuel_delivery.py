"""
Fuel Delivery Log Cog
Handles fuel delivery logging with modal and persistent button
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import asyncio
import io


class FuelDeliveryModal(discord.ui.Modal):
    """Modal for fuel delivery information"""
    
    def __init__(self):
        super().__init__(title='📦 Fuel Delivery Log')
    
    order_id = discord.ui.TextInput(
        label='Order ID',
        placeholder='Enter order ID (e.g., 43)',
        required=True,
        max_length=50
    )
    
    delivered_to = discord.ui.TextInput(
        label='Delivered To',
        placeholder='Enter location (e.g., Gas Station 15)',
        required=True,
        max_length=100
    )
    
    orders = discord.ui.TextInput(
        label='Orders (Liters)',
        placeholder='Enter amount in liters (e.g., 10000)',
        required=True,
        max_length=50
    )
    
    delivery_datetime = discord.ui.TextInput(
        label='Date and Time',
        placeholder='Enter date and time (e.g., 02.01.2026 11:20 PM)',
        default='02.01.2026 11:20 pm',
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        # Create embed for the delivery log
        embed = discord.Embed(
            title='📦 Fuel Delivery Log',
            color=0x00FF00,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name='Order ID', value=self.order_id.value, inline=True)
        embed.add_field(name='Delivered To', value=self.delivered_to.value, inline=True)
        embed.add_field(name='Orders', value=f"{self.orders.value} Liters", inline=True)
        embed.add_field(name='Date & Time', value=self.delivery_datetime.value, inline=True)
        embed.add_field(name='Logged By', value=interaction.user.mention, inline=True)
        embed.add_field(name='📸 Screenshot', value='⏳ Waiting for upload...', inline=False)
        
        embed.set_footer(text=f'Submitted by {interaction.user.name}', icon_url=interaction.user.display_avatar.url)
        
        # Send the log to the channel
        await interaction.response.send_message(embed=embed, ephemeral=False)
        
        # Get the message we just sent
        log_message = await interaction.original_response()
        
        # Move button to bottom after posting log
        cog = interaction.client.get_cog('FuelDelivery')
        if cog:
            await cog.move_button_to_bottom()
        
        # Create a thread for this delivery
        try:
            thread = await log_message.create_thread(
                name=f"📸 Order {self.order_id.value} - Upload Screenshot",
                auto_archive_duration=60  # Archive after 1 hour of inactivity
            )
            
            # Send instructions in the thread
            await thread.send(
                f'{interaction.user.mention} **📸 Upload your delivery screenshot here!**\n\n'
                f'**How to upload:**\n'
                f'1️⃣ Click the **+** or **📎** button below\n'
                f'2️⃣ Select your image file\n'
                f'3️⃣ Send it here in this thread\n'
                f'4️⃣ Your log will automatically update! ✅\n\n'
                f'⏱️ This thread will archive after 1 hour of inactivity.'
            )
            
            # Store this pending upload in the cog with thread ID
            cog = interaction.client.get_cog('FuelDelivery')
            if cog:
                cog.pending_uploads[interaction.user.id] = {
                    'message': log_message,
                    'embed': embed,
                    'timestamp': datetime.utcnow(),
                    'thread_id': thread.id
                }
        except Exception as e:
            print(f'Error creating thread: {e}')
            # Fallback to old method
            await interaction.followup.send(
                f'{interaction.user.mention} **📸 Upload your screenshot now!**\n'
                f'Drag & drop your image file here (you have 5 minutes).',
                ephemeral=True
            )
            
            cog = interaction.client.get_cog('FuelDelivery')
            if cog:
                cog.pending_uploads[interaction.user.id] = {
                    'message': log_message,
                    'embed': embed,
                    'timestamp': datetime.utcnow(),
                    'thread_id': None
                }


class FuelDeliveryView(discord.ui.View):
    """Persistent view with fuel delivery button"""
    
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view
    
    @discord.ui.button(
        label='📦 Fuel Delivery Log',
        style=discord.ButtonStyle.primary,
        custom_id='fuel_delivery_button'
    )
    async def fuel_delivery_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle button click to show modal"""
        modal = FuelDeliveryModal()
        await interaction.response.send_modal(modal)


class FuelDelivery(commands.Cog):
    """Fuel Delivery logging commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = 1456240608372068465  # Channel ID for the button
        self.button_message_id = None  # Store the button message ID
        self.pending_uploads = {}  # user_id -> {message, embed, timestamp}
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        # Register the persistent view
        self.bot.add_view(FuelDeliveryView())
        print('✅ Fuel Delivery cog loaded with persistent view')
        
        # Auto-create button on bot startup
        await self.auto_setup_button()
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for screenshot uploads from users with pending logs"""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Check if this user has a pending upload
        if message.author.id not in self.pending_uploads:
            return
        
        pending = self.pending_uploads[message.author.id]
        
        # Check if upload is in the correct thread (if thread exists) or channel
        if pending.get('thread_id'):
            # Must be in the thread
            if not isinstance(message.channel, discord.Thread) or message.channel.id != pending['thread_id']:
                return
        else:
            # Must be in the main channel
            if not message.attachments or message.channel.id != self.channel_id:
                return
        
        # Check if upload is still valid (within 1 hour for threads, 5 minutes otherwise)
        time_limit = 3600 if pending.get('thread_id') else 300  # 1 hour or 5 minutes
        time_diff = (datetime.utcnow() - pending['timestamp']).total_seconds()
        if time_diff > time_limit:
            del self.pending_uploads[message.author.id]
            return
        
        # Check if message has attachments
        if not message.attachments:
            return
        
        # Get the first image attachment
        image_attachment = None
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                image_attachment = attachment
                break
        
        if image_attachment:
            # Update the embed with the screenshot
            embed = pending['embed']
            
            # Find and update the screenshot field
            for i, field in enumerate(embed.fields):
                if field.name == '📸 Screenshot':
                    embed.set_field_at(i, name='📸 Screenshot', value='✅ Screenshot attached', inline=False)
                    break
            
            # Set the image
            embed.set_image(url=image_attachment.url)
            
            # Update the original log message
            try:
                await pending['message'].edit(embed=embed)
                await message.add_reaction('✅')
                
                # If in thread, send confirmation and delete thread
                if pending.get('thread_id'):
                    await message.reply('✅ Screenshot added to your delivery log! This thread will be deleted in 5 seconds.')
                    # Delete the thread after 5 seconds
                    thread = message.channel
                    if isinstance(thread, discord.Thread):
                        await asyncio.sleep(5)
                        await thread.delete()
                else:
                    await message.reply('✅ Screenshot added to your delivery log!', delete_after=5)
                    
            except Exception as e:
                print(f'Error updating log with screenshot: {e}')
            
            # Remove from pending uploads
            del self.pending_uploads[message.author.id]
    
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
                title='📦 Fuel Delivery Log System',
                description='Click the button below to log a fuel delivery.',
                color=0x0099FF
            )
            embed.add_field(
                name='How to use:',
                value='1. Click the **Fuel Delivery Log** button\n'
                      '2. Fill in the delivery information\n'
                      '3. Submit the form\n'
                      '4. The log will be posted to this channel',
                inline=False
            )
            embed.set_footer(text='Fuel Delivery Management System')
            
            view = FuelDeliveryView()
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
                    if message.embeds[0].title == '📦 Fuel Delivery Log System':
                        print(f'✅ Fuel delivery button already exists in channel')
                        self.button_message_id = message.id
                        return
            
            # Create the button if it doesn't exist
            embed = discord.Embed(
                title='📦 Fuel Delivery Log System',
                description='Click the button below to log a fuel delivery.',
                color=0x0099FF
            )
            embed.add_field(
                name='How to use:',
                value='1. Click the **Fuel Delivery Log** button\n'
                      '2. Fill in the delivery information\n'
                      '3. Submit the form\n'
                      '4. The log will be posted to this channel',
                inline=False
            )
            embed.set_footer(text='Fuel Delivery Management System')
            
            view = FuelDeliveryView()
            message = await channel.send(embed=embed, view=view)
            self.button_message_id = message.id
            print(f'✅ Fuel delivery button created in channel {self.channel_id}')
            
        except Exception as e:
            print(f'❌ Error setting up fuel delivery button: {e}')
    
    @app_commands.command(name="setup_fuel_delivery", description="Setup fuel delivery log button (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_fuel_delivery(self, interaction: discord.Interaction):
        """Setup the fuel delivery button in the specified channel"""
        channel = self.bot.get_channel(self.channel_id)
        
        if not channel:
            await interaction.response.send_message(
                f'❌ Could not find channel with ID: {self.channel_id}',
                ephemeral=True
            )
            return
        
        # Create embed for the button message
        embed = discord.Embed(
            title='📦 Fuel Delivery Log System',
            description='Click the button below to log a fuel delivery.',
            color=0x0099FF
        )
        embed.add_field(
            name='How to use:',
            value='1. Click the **Fuel Delivery Log** button\n'
                  '2. Fill in the delivery information\n'
                  '3. Submit the form\n'
                  '4. The log will be posted to this channel',
            inline=False
        )
        embed.set_footer(text='Fuel Delivery Management System')
        
        # Send the message with the button
        view = FuelDeliveryView()
        await channel.send(embed=embed, view=view)
        
        await interaction.response.send_message(
            f'✅ Fuel delivery log button has been set up in <#{self.channel_id}>',
            ephemeral=True
        )
    
    @setup_fuel_delivery.error
    async def setup_fuel_delivery_error(self, interaction: discord.Interaction, error):
        """Handle setup command errors"""
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                '❌ You need Administrator permissions to use this command.',
                ephemeral=True
            )


async def setup(bot):
    """Setup function for cog"""
    await bot.add_cog(FuelDelivery(bot))
"""
Discord Application Management System
Handles full application lifecycle with Discord integration
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, Dict
from datetime import datetime, timedelta
from app.core.database import get_database
from app.utils import get_current_user, require_manager_or_admin, get_discord_bot, DiscordRoles
from bson import ObjectId
import discord
import os

router = APIRouter()

# Configuration from environment
APPLICATION_CHANNEL_ID = int(os.getenv('APPLICATION_CHANNEL_ID', '1231993753003229194'))
ACCEPTED_LOG_CHANNEL_ID = int(os.getenv('ACCEPTED_LOG_CHANNEL_ID', '1231990220589629441'))
REJECTED_LOG_CHANNEL_ID = int(os.getenv('REJECTED_LOG_CHANNEL_ID', '1231990340353917008'))
AUDIT_LOG_CHANNEL_ID = int(os.getenv('AUDIT_LOG_CHANNEL_ID') or '0')

# Use centralized role constants
COMMUNITY_MEMBER_ROLE_ID = DiscordRoles.MEMBER_ROLE_ID
APPLICATION_PENDING_ROLE_ID = DiscordRoles.APPLICATION_PENDING_ROLE_ID
MANAGER_ROLE_ID = DiscordRoles.MANAGER_ROLE_ID
CEO_ROLE_ID = DiscordRoles.CEO_ROLE_ID

COOLDOWN_DAYS = 30
COOLDOWN_SECONDS = COOLDOWN_DAYS * 24 * 60 * 60

async def log_audit(bot, action: str, user_info: dict, details: dict):
    """Log all actions to audit channel"""
    if not AUDIT_LOG_CHANNEL_ID:
        return
    
    try:
        channel = bot.bot.get_channel(AUDIT_LOG_CHANNEL_ID)
        if not channel:
            return
        
        embed = discord.Embed(
            title=f"🔒 {action}",
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="User", value=f"{user_info.get('username', 'Unknown')} ({user_info.get('discord_id', 'N/A')})", inline=False)
        
        for key, value in details.items():
            embed.add_field(name=key, value=str(value), inline=True)
        
        await channel.send(embed=embed)
    except Exception as e:
        print(f"❌ Failed to log audit: {e}")

async def send_dm(bot, user_id: str, embed: discord.Embed) -> bool:
    """Send DM to user, return success status"""
    try:
        user = await bot.bot.fetch_user(int(user_id))
        await user.send(embed=embed)
        return True
    except:
        return False

async def get_online_manager(bot, guild_id: int) -> Optional[dict]:
    """Get an online manager for assignment - excludes CEOs, prioritizes Managers"""
    guild = bot.bot.get_guild(guild_id)
    if not guild:
        return None
    
    regular_managers = []
    ceo_managers = []
    
    for member in guild.members:
        if member.bot:
            continue
        
        role_ids = [role.id for role in member.roles]
        has_manager = MANAGER_ROLE_ID in role_ids
        has_ceo = CEO_ROLE_ID in role_ids
        
        if has_manager:
            is_online = str(member.status) != 'offline'
            manager_data = {
                'id': str(member.id),
                'name': member.display_name,
                'online': is_online
            }
            
            # Separate CEOs from regular managers
            if has_ceo:
                ceo_managers.append(manager_data)
            else:
                regular_managers.append(manager_data)
    
    # PRIORITY 1: Online regular managers (not CEOs)
    online_regular = [m for m in regular_managers if m['online']]
    if online_regular:
        return online_regular[0]
    
    # PRIORITY 2: Any regular manager (even offline)
    if regular_managers:
        return regular_managers[0]
    
    # PRIORITY 3: Online CEO (if they also have manager role)
    online_ceo = [m for m in ceo_managers if m['online']]
    if online_ceo:
        return online_ceo[0]
    
    # PRIORITY 4: Any CEO with manager role
    if ceo_managers:
        return ceo_managers[0]
    
    return None

@router.post("/check-eligibility")
async def check_application_eligibility(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    STEP-BY-STEP eligibility validation
    Returns detailed status for frontend
    """
    db = get_database()
    bot = get_discord_bot(request)
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild_id = int(os.getenv('DISCORD_GUILD_ID'))
    guild = bot.bot.get_guild(guild_id)
    
    if not guild:
        raise HTTPException(status_code=503, detail="Guild not found")
    
    user_id = current_user['discord_id']
    
    # STEP 1: Server membership check
    try:
        member = await guild.fetch_member(int(user_id))
    except:
        return {
            "eligible": False,
            "reason": "NOT_IN_SERVER",
            "message": "You must be a member of the Discord server to apply.",
            "action": "JOIN_SERVER",
            "invite_url": "https://discord.gg/pG83VJECT3"
        }
    
    role_ids = [role.id for role in member.roles]
    
    # STEP 2: Community member check
    if COMMUNITY_MEMBER_ROLE_ID in role_ids:
        return {
            "eligible": False,
            "reason": "ALREADY_MEMBER",
            "message": "You are already a community member.",
            "action": "NONE"
        }
    
    # STEP 3: Pending application check
    if APPLICATION_PENDING_ROLE_ID in role_ids:
        # Check if application actually exists in database
        app = await db.applications.find_one({
            "user_id": user_id,
            "status": "pending"
        })
        
        if not app:
            # Role exists but no application - remove the role
            try:
                role = guild.get_role(APPLICATION_PENDING_ROLE_ID)
                if role:
                    await member.remove_roles(role, reason="No pending application found")
                    print(f"⚠️ Removed orphaned pending role from {member.display_name}")
            except Exception as e:
                print(f"❌ Failed to remove orphaned role: {e}")
            
            # Allow them to apply
            return {
                "eligible": True,
                "message": "You are eligible to submit an application.",
                "action": "APPLY"
            }
        
        return {
            "eligible": False,
            "reason": "PENDING",
            "message": "Your application is under review. Please contact a Manager in Discord for updates.",
            "action": "WAIT",
            "estimated_time": "24-48 hours"
        }
    
    # STEP 4: Cooldown check
    last_app = await db.applications.find_one(
        {"user_id": user_id},
        sort=[("submitted_at", -1)]
    )
    
    if last_app:
        last_applied = last_app.get('submitted_at')
        if last_applied:
            time_since = (datetime.utcnow() - last_applied).total_seconds()
            
            # Check for CEO override
            override = last_app.get('override_by_ceo')
            override_expires = last_app.get('override_expires_at')
            
            has_valid_override = False
            if override and override_expires:
                has_valid_override = datetime.utcnow() < override_expires
            
            if time_since < COOLDOWN_SECONDS and not has_valid_override:
                days_left = int((COOLDOWN_SECONDS - time_since) / 86400)
                return {
                    "eligible": False,
                    "reason": "COOLDOWN",
                    "message": f"You can apply only once every {COOLDOWN_DAYS} days. Wait {days_left} days or contact a CEO for early reapplication permission.",
                    "action": "WAIT",
                    "days_remaining": days_left,
                    "can_apply_after": (last_applied + timedelta(days=COOLDOWN_DAYS)).isoformat()
                }
    
    # All checks passed
    return {
        "eligible": True,
        "message": "You are eligible to submit an application.",
        "action": "APPLY"
    }

@router.post("/ceo/grant-reapply/{user_id}")
async def ceo_grant_reapply_override(
    user_id: str,
    request: Request,
    ceo: dict = Depends(require_manager_or_admin)
):
    """
    CEO can grant a user permission to reapply before 30-day cooldown expires
    """
    db = get_database()
    bot = get_discord_bot(request)
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    # Verify requester is CEO
    guild_id = int(os.getenv('DISCORD_GUILD_ID'))
    guild = bot.bot.get_guild(guild_id)
    
    try:
        ceo_member = await guild.fetch_member(int(ceo['discord_id']))
        role_ids = [role.id for role in ceo_member.roles]
        
        if CEO_ROLE_ID not in role_ids:
            raise HTTPException(status_code=403, detail="Only CEOs can grant reapply permission")
    except:
        raise HTTPException(status_code=403, detail="Authorization failed")
    
    # Find user's last rejected application
    last_app = await db.applications.find_one(
        {"user_id": user_id, "status": "rejected"},
        sort=[("submitted_at", -1)]
    )
    
    if not last_app:
        raise HTTPException(status_code=404, detail="No rejected application found for this user")
    
    # Grant 7-day override window
    override_expires = datetime.utcnow() + timedelta(days=7)
    
    await db.applications.update_one(
        {"_id": last_app['_id']},
        {
            "$set": {
                "override_by_ceo": True,
                "override_granted_by": ceo['discord_id'],
                "override_granted_at": datetime.utcnow(),
                "override_expires_at": override_expires
            }
        }
    )
    
    # Fetch target member for logging
    target_member = None
    try:
        target_member = await guild.fetch_member(int(user_id))
    except Exception as e:
        print(f"⚠️ Failed to fetch target member: {e}")
    
    # Send DM to user
    try:
        override_embed = discord.Embed(
            title="🎉 Early Reapplication Granted",
            description="The CEO has granted you permission to reapply before the 30-day cooldown!",
            color=0x57F287
        )
        override_embed.add_field(
            name="Valid Until",
            value=f"<t:{int(override_expires.timestamp())}:F>",
            inline=False
        )
        override_embed.add_field(
            name="Next Steps",
            value="Visit the application portal to submit your new application.",
            inline=False
        )
        
        await send_dm(bot, user_id, override_embed)
    except Exception as e:
        print(f"⚠️ Failed to send override DM: {e}")
    
    # Log to audit
    await log_audit(bot, "CEO Reapply Override Granted", {
        'username': target_member.display_name if target_member else f"User {user_id}",
        'discord_id': user_id
    }, {
        'Granted By': ceo_member.display_name,
        'Valid Until': override_expires.strftime('%Y-%m-%d %H:%M UTC'),
        'Application ID': str(last_app['_id'])
    })
    
    return {
        "success": True,
        "message": "Reapply permission granted",
        "valid_until": override_expires.isoformat()
    }

@router.post("/submit-with-discord")
async def submit_application_with_discord(
    request: Request,
    application_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Full application submission with Discord integration
    """
    db = get_database()
    bot = get_discord_bot(request)
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild_id = int(os.getenv('DISCORD_GUILD_ID'))
    guild = bot.bot.get_guild(guild_id)
    
    # Re-validate eligibility
    eligibility = await check_application_eligibility(request, current_user)
    if not eligibility['eligible']:
        raise HTTPException(status_code=400, detail=eligibility)
    
    user_id = current_user['discord_id']
    
    try:
        member = await guild.fetch_member(int(user_id))
    except:
        raise HTTPException(status_code=400, detail="User not found in server")
    
    # Create application
    application = {
        "user_id": user_id,
        "username": member.display_name,
        "form_type": "membership",
        "data": application_data,
        "status": "pending",
        "submitted_at": datetime.utcnow(),
        "application_version": "v1.0",
        "discord_user_info": {
            "username": str(member),
            "display_name": member.display_name,
            "account_created": member.created_at.isoformat(),
            "joined_server": member.joined_at.isoformat() if member.joined_at else None,
            "avatar_url": str(member.avatar.url) if member.avatar else None
        }
    }
    
    # Calculate score
    from app.api.applications import analyze_application
    score, analysis = await analyze_application(application_data)
    application["result_score"] = score
    application["ai_analysis"] = analysis
    
    # Insert to DB
    result = await db.applications.insert_one(application)
    app_id = str(result.inserted_id)
    application['_id'] = app_id
    
    # Add Application Pending role
    try:
        role = guild.get_role(APPLICATION_PENDING_ROLE_ID)
        if role:
            await member.add_roles(role, reason="Application submitted")
    except Exception as e:
        print(f"⚠️ Failed to add pending role: {e}")
    
    # Send DM to applicant
    dm_embed = discord.Embed(
        title="✅ Application Received",
        description="Thank you for your application to Maestros Community!",
        color=0x57F287
    )
    dm_embed.add_field(name="Application ID", value=f"`{app_id[:8]}`", inline=False)
    dm_embed.add_field(name="Next Steps", value="A Manager will review your application soon. Contact a Manager in Discord for updates.", inline=False)
    dm_embed.add_field(name="Estimated Review Time", value="24-48 hours", inline=False)
    dm_embed.set_footer(text="You will be notified once your application is reviewed.")
    
    dm_success = await send_dm(bot, user_id, dm_embed)
    
    await db.applications.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {"dm_delivery_status": "sent" if dm_success else "failed"}}
    )
    
    # Send application to review channel
    try:
        channel = bot.bot.get_channel(APPLICATION_CHANNEL_ID)
        if channel:
            review_embed = discord.Embed(
                title="📄 New Application Submitted",
                description=f"**{member.mention}** has submitted a membership application",
                color=0xFEE75C,
                timestamp=datetime.utcnow()
            )
            
            # User Info Section
            review_embed.add_field(name="👤 Discord Tag", value=str(member), inline=True)
            review_embed.add_field(name="🆔 User ID", value=f"`{user_id}`", inline=True)
            review_embed.add_field(name="📊 Level", value=str(current_user.get('level', 1)), inline=True)
            
            review_embed.add_field(name="📧 Email", value=current_user.get('email', 'Not provided'), inline=True)
            review_embed.add_field(
                name="🎂 Account Created",
                value=f"<t:{int(member.created_at.timestamp())}:D>",
                inline=True
            )
            if member.joined_at:
                review_embed.add_field(
                    name="📅 Server Joined",
                    value=f"<t:{int(member.joined_at.timestamp())}:D>",
                    inline=True
                )
            
            # Gaming Info
            review_embed.add_field(
                name="🎮 Primary Game", 
                value=application_data.get('primary_game', 'N/A'), 
                inline=True
            )
            review_embed.add_field(
                name="⏱️ Gameplay Hours", 
                value=f"{application_data.get('gameplay_hours', 0)} hrs", 
                inline=True
            )
            review_embed.add_field(
                name="🏆 Rank", 
                value=application_data.get('rank', 'N/A'), 
                inline=True
            )
            review_embed.add_field(
                name="📅 Availability", 
                value=f"{application_data.get('availability', 0)} hrs/week", 
                inline=True
            )
            review_embed.add_field(
                name="🤖 AI Score", 
                value=f"**{score:.1f}%**", 
                inline=True
            )
            review_embed.add_field(
                name="📋 Application ID", 
                value=f"`{app_id[:8]}`", 
                inline=True
            )
            
            # Application Responses
            review_embed.add_field(
                name="💼 Experience",
                value=application_data.get('experience', 'N/A')[:1024],
                inline=False
            )
            review_embed.add_field(
                name="💭 Why Join Maestros?",
                value=application_data.get('reason', 'N/A')[:1024],
                inline=False
            )
            review_embed.add_field(
                name="🌟 Contribution Plans",
                value=application_data.get('contribution', 'N/A')[:1024],
                inline=False
            )
            
            # AI Analysis
            if analysis:
                strengths = analysis.get('strengths', [])
                weaknesses = analysis.get('weaknesses', [])
                
                if strengths:
                    review_embed.add_field(
                        name="✅ Strengths",
                        value="• " + "\n• ".join(strengths[:3]),
                        inline=True
                    )
                
                if weaknesses:
                    review_embed.add_field(
                        name="⚠️ Weaknesses",
                        value="• " + "\n• ".join(weaknesses[:3]),
                        inline=True
                    )
            
            review_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            review_embed.set_footer(text=f"Status: PENDING • Review this application in the Manager Panel")
            
            await channel.send(embed=review_embed)
            print(f"✅ Application sent to review channel {APPLICATION_CHANNEL_ID}")
    except Exception as e:
        print(f"❌ Failed to send to review channel: {e}")
        import traceback
        traceback.print_exc()
    
    # Log to audit
    await log_audit(bot, "Application Submitted", {
        'username': member.display_name,
        'discord_id': user_id
    }, {
        'Application ID': app_id[:8],
        'DM Delivered': '✅' if dm_success else '❌',
        'Score': f"{score:.1f}/100"
    })
    
    return {
        "success": True,
        "message": "Application submitted successfully",
        "application_id": app_id,
        "dm_sent": dm_success,
        "score": score
    }

class ApplicationReviewButtons(discord.ui.View):
    """Discord UI buttons for application review"""
    
    def __init__(self, application_id: str):
        super().__init__(timeout=None)
        self.application_id = application_id
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="accept_app")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AcceptModal(self.application_id))
    
    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, custom_id="reject_app")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RejectModal(self.application_id))

class AcceptModal(discord.ui.Modal, title="Accept Application"):
    reason = discord.ui.TextInput(
        label="Acceptance Notes (Optional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )
    
    def __init__(self, application_id: str):
        super().__init__()
        self.application_id = application_id
        self.custom_id = f"accept_modal_{application_id}"
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Processing acceptance...", ephemeral=True)

class RejectModal(discord.ui.Modal, title="Reject Application"):
    reason = discord.ui.TextInput(
        label="Rejection Reason (Required)",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=10,
        max_length=500
    )
    
    def __init__(self, application_id: str):
        super().__init__()
        self.application_id = application_id
        self.custom_id = f"reject_modal_{application_id}"
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ Processing rejection...", ephemeral=True)

@router.post("/manager/accept/{application_id}")
async def accept_application_with_discord(
    application_id: str,
    request: Request,
    request_data: dict = {},
    manager: dict = Depends(require_manager_or_admin)
):
    """Accept application with full Discord integration"""
    db = get_database()
    bot = get_discord_bot(request)
    
    print(f"🔍 DEBUG: Bot object: {bot}")
    print(f"🔍 DEBUG: Bot is_ready: {bot.is_ready if bot else 'Bot is None'}")
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild_id = int(os.getenv('DISCORD_GUILD_ID'))
    guild = bot.bot.get_guild(guild_id)
    
    print(f"🔍 DEBUG: Guild ID: {guild_id}")
    print(f"🔍 DEBUG: Guild object: {guild}")
    
    if not guild:
        raise HTTPException(status_code=503, detail="Guild not found")
    
    # Get application
    try:
        app = await db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid application ID")
    
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if app['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Application is not pending")
    
    user_id = app['user_id']
    acceptance_notes = request_data.get('notes', 'Welcome to Maestros!')
    
    print(f"🔍 DEBUG: User ID: {user_id}")
    print(f"🔍 DEBUG: Acceptance notes: {acceptance_notes}")
    
    try:
        member = await guild.fetch_member(int(user_id))
        print(f"🔍 DEBUG: Member fetched: {member}")
    except Exception as e:
        print(f"❌ Failed to fetch member: {e}")
        raise HTTPException(status_code=404, detail="User not found in server")
    
    # Add Community Member role
    try:
        member_role = guild.get_role(COMMUNITY_MEMBER_ROLE_ID)
        if member_role:
            await member.add_roles(member_role, reason=f"Application accepted by {manager['username']}")
    except Exception as e:
        print(f"⚠️ Failed to add member role: {e}")
    
    # Remove Application Pending role
    try:
        pending_role = guild.get_role(APPLICATION_PENDING_ROLE_ID)
        if pending_role:
            await member.remove_roles(pending_role, reason="Application accepted")
    except Exception as e:
        print(f"⚠️ Failed to remove pending role: {e}")
    
    # Update database
    await db.applications.update_one(
        {"_id": ObjectId(application_id)},
        {
            "$set": {
                "status": "accepted",
                "handled_by": manager['discord_id'],
                "handler_name": manager['username'],
                "decision_timestamp": datetime.utcnow(),
                "decision_reason": acceptance_notes
            }
        }
    )
    
    print(f"✅ Database updated - Application accepted")
    
    # Send DM to applicant
    accept_embed = discord.Embed(
        title="🎉 Application Accepted!",
        description="Congratulations! Your application has been approved.",
        color=0x57F287
    )
    accept_embed.add_field(name="Welcome Message", value=acceptance_notes, inline=False)
    accept_embed.add_field(name="Next Steps", value="You now have full access to the community!", inline=False)
    accept_embed.set_footer(text="Welcome to Maestros Community!")
    
    print(f"📧 Sending DM to user {user_id}...")
    dm_success = await send_dm(bot, user_id, accept_embed)
    print(f"📧 DM sent: {dm_success}")
    
    print(f"📢 Starting to send acceptance message to channel...")
    # Post to accepted log channel
    try:
        log_channel = bot.bot.get_channel(ACCEPTED_LOG_CHANNEL_ID)
        print(f"📢 Attempting to send accept message to channel {ACCEPTED_LOG_CHANNEL_ID}")
        print(f"📢 Channel object: {log_channel}")
        
        if log_channel:
            # Get manager member object
            manager_member = None
            try:
                manager_member = await guild.fetch_member(int(manager['discord_id']))
                print(f"📢 Manager member fetched: {manager_member}")
            except Exception as e:
                print(f"⚠️ Failed to fetch manager member: {e}")
            
            log_embed = discord.Embed(
                title="✅ Application Accepted",
                description=f"**Welcome to our server, {member.mention}!**\n\nCongratulations on being accepted to Maestros Community!",
                color=0x57F287,
                timestamp=datetime.utcnow()
            )
            log_embed.add_field(name="Applicant", value=f"{member.mention} ({member})", inline=True)
            log_embed.add_field(name="User ID", value=f"`{user_id}`", inline=True)
            log_embed.add_field(name="Application ID", value=f"`{application_id[:8]}`", inline=True)
            
            # Show who accepted with mention
            accepted_by_text = manager_member.mention if manager_member else manager['username']
            log_embed.add_field(name="Accepted By", value=accepted_by_text, inline=False)
            
            if acceptance_notes:
                log_embed.add_field(name="Acceptance Notes", value=acceptance_notes[:500], inline=False)
            
            log_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            log_embed.set_footer(text="🎉 Welcome to Maestros!")
            
            print(f"📢 Sending embed to channel...")
            await log_channel.send(embed=log_embed)
            print(f"✅ Accept message sent successfully to channel {ACCEPTED_LOG_CHANNEL_ID}")
        else:
            print(f"❌ Channel {ACCEPTED_LOG_CHANNEL_ID} not found!")
    except Exception as e:
        print(f"❌ Failed to send to accepted log channel: {e}")
        import traceback
        traceback.print_exc()
    
    # Audit log
    await log_audit(bot, "Application Accepted", {
        'username': member.display_name,
        'discord_id': user_id
    }, {
        'Handled By': manager['username'],
        'Application ID': application_id[:8],
        'DM Delivered': '✅' if dm_success else '❌'
    })
    
    return {
        "success": True,
        "message": "Application accepted successfully",
        "dm_sent": dm_success
    }

@router.post("/manager/reject/{application_id}")
async def reject_application_with_discord(
    application_id: str,
    request: Request,
    request_data: dict,
    manager: dict = Depends(require_manager_or_admin)
):
    """Reject application with full Discord integration"""
    db = get_database()
    bot = get_discord_bot(request)
    
    if not bot or not bot.is_ready:
        raise HTTPException(status_code=503, detail="Discord bot not connected")
    
    guild_id = int(os.getenv('DISCORD_GUILD_ID'))
    guild = bot.bot.get_guild(guild_id)
    
    if not guild:
        raise HTTPException(status_code=503, detail="Guild not found")
    
    rejection_reason = request_data.get('reason', '')
    if len(rejection_reason) < 10:
        raise HTTPException(status_code=400, detail="Rejection reason must be at least 10 characters")
    
    # Get application
    try:
        app = await db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid application ID")
    
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if app['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Application is not pending")
    
    user_id = app['user_id']
    
    try:
        member = await guild.fetch_member(int(user_id))
    except:
        # User might have left the server
        member = None
    
    # Remove Application Pending role
    if member:
        try:
            pending_role = guild.get_role(APPLICATION_PENDING_ROLE_ID)
            if pending_role:
                await member.remove_roles(pending_role, reason=f"Application rejected by {manager['username']}")
        except Exception as e:
            print(f"⚠️ Failed to remove pending role: {e}")
    
    # Update database
    await db.applications.update_one(
        {"_id": ObjectId(application_id)},
        {
            "$set": {
                "status": "rejected",
                "handled_by": manager['discord_id'],
                "handler_name": manager['username'],
                "decision_timestamp": datetime.utcnow(),
                "decision_reason": rejection_reason
            }
        }
    )
    
    # Send DM to applicant
    dm_success = False
    if member:
        reject_embed = discord.Embed(
            title="❌ Application Decision",
            description="Thank you for your interest in Maestros Community.",
            color=0xED4245
        )
        reject_embed.add_field(
            name="Status",
            value="Your application has been reviewed and was not approved at this time.",
            inline=False
        )
        reject_embed.add_field(
            name="Feedback",
            value=rejection_reason,
            inline=False
        )
        reject_embed.add_field(
            name="Reapplication",
            value=f"You may reapply after {COOLDOWN_DAYS} days.",
            inline=False
        )
        reject_embed.set_footer(text="Thank you for your understanding")
        
        dm_success = await send_dm(bot, user_id, reject_embed)
    
    # Post to rejected log channel
    try:
        log_channel = bot.bot.get_channel(ACCEPTED_LOG_CHANNEL_ID)  # Using same channel for both
        print(f"📢 Attempting to send reject message to channel {ACCEPTED_LOG_CHANNEL_ID}")
        print(f"📢 Channel object: {log_channel}")
        
        if log_channel:
            # Get manager member object
            manager_member = None
            try:
                manager_member = await guild.fetch_member(int(manager['discord_id']))
                print(f"📢 Manager member fetched: {manager_member}")
            except Exception as e:
                print(f"⚠️ Failed to fetch manager member: {e}")
            
            log_embed = discord.Embed(
                title="❌ Application Rejected",
                description="An application has been reviewed and rejected.",
                color=0xED4245,
                timestamp=datetime.utcnow()
            )
            
            if member:
                log_embed.add_field(name="Applicant", value=f"{member.mention} ({member})", inline=True)
                log_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            else:
                log_embed.add_field(name="Applicant", value=f"User ID: `{user_id}` (Left server)", inline=True)
            
            log_embed.add_field(name="User ID", value=f"`{user_id}`", inline=True)
            log_embed.add_field(name="Application ID", value=f"`{application_id[:8]}`", inline=True)
            
            # Show who rejected with mention
            rejected_by_text = manager_member.mention if manager_member else manager['username']
            log_embed.add_field(name="Rejected By", value=rejected_by_text, inline=False)
            
            log_embed.add_field(name="Rejection Reason", value=rejection_reason[:500], inline=False)
            log_embed.set_footer(text="Application Decision")
            
            print(f"📢 Sending reject embed to channel...")
            await log_channel.send(embed=log_embed)
            print(f"✅ Reject message sent successfully to channel {ACCEPTED_LOG_CHANNEL_ID}")
        else:
            print(f"❌ Channel {ACCEPTED_LOG_CHANNEL_ID} not found!")
    except Exception as e:
        print(f"❌ Failed to send to rejected log channel: {e}")
        import traceback
        traceback.print_exc()
    
    # Audit log
    await log_audit(bot, "Application Rejected", {
        'username': member.display_name if member else f"User {user_id}",
        'discord_id': user_id
    }, {
        'Handled By': manager['username'],
        'Application ID': application_id[:8],
        'DM Delivered': '✅' if dm_success else '❌',
        'Reason': rejection_reason[:100]
    })
    
    return {
        "success": True,
        "message": "Application rejected successfully",
        "dm_sent": dm_success
    }



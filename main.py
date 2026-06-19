import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime, timedelta
import json
import random
from collections import defaultdict

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Channel IDs
WELCOME_CHANNEL = 1514684270596198594
SUPPORT_CHANNEL = 1514684277764128800
GITHUB_CHANNEL = 1514684267811180808
BOT_LOG_CHANNEL = 1514684302502268929
MOD_LOG_CHANNEL = 1514684302502268929

# Role IDs
OWNERSHIP_ROLE = 1517219295623516370
EXECUTIVE_ROLE = 1517219295623516370
ADMIN_ROLE = 1517237018642481252
LEADERSHIP_ROLE_1 = 1517219295623516370
LEADERSHIP_ROLE_2 = 1517222332991668425

# Raid protection settings
RAID_THRESHOLD = 5
RAID_TIME_WINDOW = 10
BAN_ON_RAID = True

# In-memory tracking
join_tracker = defaultdict(list)
mute_tracker = {}

# Database setup
def init_db():
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS bot_logs
                 (id INTEGER PRIMARY KEY, user_id TEXT, bot_name TEXT, service TEXT, 
                  github_link TEXT, status TEXT, created_at TIMESTAMP, last_check TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bot_hosting
                 (id INTEGER PRIMARY KEY, user_id TEXT, bot_name TEXT, bot_token TEXT,
                  status TEXT, uptime REAL, created_at TIMESTAMP, last_check TIMESTAMP, last_alert TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS economy
                 (user_id TEXT PRIMARY KEY, balance REAL, level INTEGER, xp REAL, last_daily TIMESTAMP,
                  total_earned REAL, achievements TEXT, streak INTEGER, last_streak_date TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS support_tickets
                 (id INTEGER PRIMARY KEY, user_id TEXT, claimed_by TEXT, service TEXT, channel_id TEXT, 
                  status TEXT, created_at TIMESTAMP, closed_at TIMESTAMP, close_reason TEXT, rating INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ticket_messages
                 (id INTEGER PRIMARY KEY, ticket_id INTEGER, message_id TEXT, channel_id TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS moderation
                 (id INTEGER PRIMARY KEY, user_id TEXT, action TEXT, reason TEXT, 
                  moderator_id TEXT, created_at TIMESTAMP, expires_at TIMESTAMP, 
                  is_active INTEGER DEFAULT 1)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS warnings
                 (id INTEGER PRIMARY KEY, user_id TEXT, reason TEXT, moderator_id TEXT, created_at TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS raid_logs
                 (id INTEGER PRIMARY KEY, user_id TEXT, action TEXT, reason TEXT, created_at TIMESTAMP)''')
    
    conn.commit()
    conn.close()

init_db()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="P Code Studio"))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.event
async def on_member_join(member):
    """Send welcome message when member joins"""
    current_time = datetime.now()
    guild_id = str(member.guild.id)
    
    # Raid detection
    join_tracker[guild_id].append(current_time)
    join_tracker[guild_id] = [t for t in join_tracker[guild_id] 
                              if (current_time - t).total_seconds() < RAID_TIME_WINDOW]
    
    if len(join_tracker[guild_id]) >= RAID_THRESHOLD:
        await handle_raid(member.guild, member)
        return
    
    # Normal welcome message
    channel = bot.get_channel(WELCOME_CHANNEL)
    if not channel:
        return
    
    embed = discord.Embed(
        title="🚀 Welcome to P Code Studio!",
        description="We're excited to have you join our growing community of developers, designers, creators, and innovators.",
        color=0x028DEF
    )
    
    embed.add_field(
        name="We Specialize In:",
        value="🤖 Discord Bot Development\n🎮 Roblox Development\n🎨 Graphic & UI Design\n🛠️ Discord Server Design\n💡 Custom Solutions",
        inline=False
    )
    
    embed.add_field(
        name="Check Out:",
        value="📌 #rules\n📌 #services\n📌 #pricing\n📌 #portfolio\n📌 #meet-the-team",
        inline=False
    )
    
    embed.set_footer(text="✨ Code. Design. Create.\n👑 Founded by itss_Gre1mi")
    
    await channel.send(f"🚀 Welcome to P Code Studio, {member.mention}!", embed=embed)
    
    # Initialize economy
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO economy 
                 (user_id, balance, level, xp, last_daily, total_earned, achievements, streak, last_streak_date) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (str(member.id), 100.0, 1, 0.0, None, 100.0, json.dumps([]), 0, None))
    conn.commit()
    conn.close()

async def handle_raid(guild, member):
    """Handle raid detection"""
    raid_channel = bot.get_channel(MOD_LOG_CHANNEL)
    if not raid_channel:
        return
    
    embed = discord.Embed(
        title="🚨 RAID DETECTED",
        description="Multiple accounts joining rapidly detected!",
        color=0xFF0000
    )
    embed.add_field(name="Latest Joiner", value=f"{member.mention} ({member.id})", inline=False)
    embed.add_field(name="Account Age", value=f"Created <t:{int(member.created_at.timestamp())}:R>", inline=False)
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("INSERT INTO raid_logs (user_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
              (str(member.id), "RAID_DETECTED", "Raid event triggered", datetime.now()))
    
    if BAN_ON_RAID:
        try:
            await member.ban(reason="Raid protection - automatic ban")
            embed.add_field(name="Action Taken", value="✅ User automatically banned", inline=False)
            c.execute("INSERT INTO raid_logs (user_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
                      (str(member.id), "AUTO_BAN", "Raid detection auto-ban", datetime.now()))
        except:
            embed.add_field(name="Action Taken", value="⚠️ Could not ban user", inline=False)
    
    conn.commit()
    conn.close()
    
    embed.set_footer(text=f"Guild: {guild.name}")
    await raid_channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    """Send goodbye message"""
    channel = bot.get_channel(WELCOME_CHANNEL)
    if not channel:
        return
    
    embed = discord.Embed(
        title="📤 Farewell",
        description=f"{member.name} has left P Code Studio.",
        color=0x028DEF
    )
    embed.set_footer(text="✨ Code. Design. Create.")
    
    await channel.send(embed=embed)

# ==================== SUPPORT PANEL ====================

class CloseTicketModal(discord.ui.Modal):
    def __init__(self, ticket_id):
        super().__init__(title="Close Support Ticket")
        self.ticket_id = ticket_id
        
        self.reason = discord.ui.TextInput(
            label="Close Reason",
            placeholder="Why are you closing this ticket?",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.reason)
    
    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason.value or "No reason provided"
        
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("""UPDATE support_tickets 
                     SET status = ?, closed_at = ?, close_reason = ?
                     WHERE id = ?""",
                  ("closed", datetime.now(), reason, self.ticket_id))
        conn.commit()
        
        c.execute("SELECT user_id, channel_id FROM support_tickets WHERE id = ?", (self.ticket_id,))
        ticket = c.fetchone()
        conn.close()
        
        if ticket:
            channel = bot.get_channel(int(ticket[1]))
            if channel:
                embed = discord.Embed(
                    title="🔒 Ticket Closed",
                    description=f"**Closed By:** {interaction.user.mention}\n**Reason:** {reason}",
                    color=0xFF0000
                )
                await channel.send(embed=embed)
        
        await interaction.response.send_message("✅ Ticket closed!", ephemeral=True)

class TicketButtonView(discord.ui.View):
    def __init__(self, ticket_id, user_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.user_id = user_id
    
    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, emoji="👋")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_roles = [role.id for role in interaction.user.roles]
        if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
            await interaction.response.send_message("❌ No permission", ephemeral=True)
            return
        
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("SELECT claimed_by FROM support_tickets WHERE id = ?", (self.ticket_id,))
        result = c.fetchone()
        
        if result and result[0]:
            await interaction.response.send_message("❌ Already claimed!", ephemeral=True)
            conn.close()
            return
        
        c.execute("UPDATE support_tickets SET claimed_by = ? WHERE id = ?",
                  (str(interaction.user.id), self.ticket_id))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(title="✅ Claimed", description=f"By {interaction.user.mention}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    
    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def unclaim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_roles = [role.id for role in interaction.user.roles]
        if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
            await interaction.response.send_message("❌ No permission", ephemeral=True)
            return
        
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("UPDATE support_tickets SET claimed_by = NULL WHERE id = ?", (self.ticket_id,))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(title="🔄 Unclaimed", color=0xFFFF00)
        await interaction.response.send_message(embed=embed)
    
    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_roles = [role.id for role in interaction.user.roles]
        if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
            await interaction.response.send_message("❌ No permission", ephemeral=True)
            return
        
        await interaction.response.send_modal(CloseTicketModal(self.ticket_id))

class ServiceSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="👑 Leadership Support", value="leadership"),
            discord.SelectOption(label="🤖 Bot Development", value="bot_dev"),
            discord.SelectOption(label="🎮 Roblox Development", value="roblox"),
            discord.SelectOption(label="🎨 Graphic & UI Design", value="design"),
            discord.SelectOption(label="🛠️ Server Design", value="server_design"),
            discord.SelectOption(label="💡 Custom Solutions", value="custom"),
            discord.SelectOption(label="🧑‍🏫 Training", value="training"),
            discord.SelectOption(label="💬 General Support", value="general"),
        ]
        super().__init__(placeholder="Select a service...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        service = self.values[0]
        user = interaction.user
        
        services = {
            "leadership": {"name": "👑 Leadership Support", "roles": [LEADERSHIP_ROLE_1, LEADERSHIP_ROLE_2]},
            "bot_dev": {"name": "🤖 Bot Development", "roles": [1517239326704930837, 1517237815421964470, 1517238791771783409]},
            "roblox": {"name": "🎮 Roblox", "roles": [1517240614163447819, 1517240911309050049, 1517239644989685911]},
            "design": {"name": "🎨 Design", "roles": [1517241987986620486]},
            "server_design": {"name": "🛠️ Server Design", "roles": [1517306660589273209]},
            "custom": {"name": "💡 Custom", "roles": [1517310391473148045]},
            "training": {"name": "🧑‍🏫 Training", "roles": [1517237018642481252]},
            "general": {"name": "💬 General", "roles": [1517237018642481252]},
        }
        
        service_info = services[service]
        
        guild = interaction.guild
        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
        )
        
        for role_id in service_info["roles"]:
            role = guild.get_role(role_id)
            if role:
                await channel.set_permissions(role, view_channel=True, send_messages=True)
        
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("""INSERT INTO support_tickets 
                     (user_id, claimed_by, service, channel_id, status, created_at, closed_at, close_reason, rating) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (str(user.id), None, service, str(channel.id), "open", datetime.now(), None, None, 0))
        conn.commit()
        ticket_id = c.lastrowid
        conn.close()
        
        embed = discord.Embed(title=f"New {service_info['name']} Ticket", color=0x028DEF)
        embed.add_field(name="Ticket ID", value=str(ticket_id), inline=False)
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.set_footer(text="© P Code Studio | All Rights Reserved")
        
        mention_text = " ".join([f"<@&{role_id}>" for role_id in service_info["roles"]])
        await channel.send(mention_text, embed=embed, view=TicketButtonView(ticket_id, str(user.id)))
        
        await interaction.response.send_message(f"✅ Ticket created! {channel.mention}", ephemeral=True)

class ServiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ServiceSelect())

@bot.tree.command(name="assistance", description="Open support panel")
async def assistance_panel(interaction: discord.Interaction):
    user_roles = [role.id for role in interaction.user.roles]
    if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="P Code Studio - Support Panel",
        description="Select a service below to create a support ticket.",
        color=0x028DEF
    )
    
    embed.add_field(
        name="📋 Office Hours",
        value="**Monday - Friday:** <t:1781776800:t> - <t:1781836200:t>\n**Saturday - Sunday:** <t:1781787600:t> - <t:1781834400:t>",
        inline=False
    )
    
    embed.set_footer(text="© P Code Studio | All Rights Reserved")
    
    await interaction.response.send_message(embed=embed, view=ServiceView())

# ==================== MODERATION ====================

async def log_moderation(user_id, action, reason, moderator_id, expires_at=None):
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("""INSERT INTO moderation (user_id, action, reason, moderator_id, created_at, expires_at)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (user_id, action, reason, moderator_id, datetime.now(), expires_at))
    conn.commit()
    conn.close()

async def send_mod_log(embed):
    channel = bot.get_channel(MOD_LOG_CHANNEL)
    if channel:
        await channel.send(embed=embed)

def has_mod_permission(user_roles):
    return ADMIN_ROLE in user_roles or EXECUTIVE_ROLE in user_roles or OWNERSHIP_ROLE in user_roles

@bot.tree.command(name="warn", description="Warn a user")
@discord.app_commands.describe(user="User to warn", reason="Reason")
async def warn(interaction: discord.Interaction, user: discord.User, reason: str = "No reason"):
    user_roles = [role.id for role in interaction.user.roles]
    if not has_mod_permission(user_roles):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("INSERT INTO warnings (user_id, reason, moderator_id, created_at) VALUES (?, ?, ?, ?)",
              (str(user.id), reason, str(interaction.user.id), datetime.now()))
    c.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ?", (str(user.id),))
    warn_count = c.fetchone()[0]
    conn.commit()
    conn.close()
    
    await log_moderation(str(user.id), "WARN", reason, str(interaction.user.id))
    
    embed = discord.Embed(title="⚠️ User Warned", description=f"**User:** {user.mention}\n**Reason:** {reason}\n**Count:** {warn_count}", color=0xFFFF00)
    await interaction.response.send_message(embed=embed)
    await send_mod_log(embed)

@bot.tree.command(name="mute", description="Mute a user")
@discord.app_commands.describe(user="User to mute", duration="Duration in minutes", reason="Reason")
async def mute_user(interaction: discord.Interaction, user: discord.User, duration: int = 10, reason: str = "No reason"):
    user_roles = [role.id for role in interaction.user.roles]
    if not has_mod_permission(user_roles):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    guild_user = interaction.guild.get_member(user.id)
    if not guild_user:
        await interaction.response.send_message("❌ User not found", ephemeral=True)
        return
    
    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not muted_role:
        muted_role = await interaction.guild.create_role(name="Muted", color=discord.Color.dark_gray())
        for channel in interaction.guild.channels:
            await channel.set_permissions(muted_role, send_messages=False, speak=False)
    
    await guild_user.add_roles(muted_role)
    unmute_time = datetime.now() + timedelta(minutes=duration)
    mute_tracker[str(user.id)] = unmute_time
    
    await log_moderation(str(user.id), "MUTE", reason, str(interaction.user.id), unmute_time)
    
    embed = discord.Embed(title="🔇 User Muted", description=f"**User:** {user.mention}\n**Duration:** {duration}m\n**Reason:** {reason}", color=0xFF9900)
    await interaction.response.send_message(embed=embed)
    await send_mod_log(embed)

@bot.tree.command(name="unmute", description="Unmute a user")
@discord.app_commands.describe(user="User to unmute")
async def unmute_user(interaction: discord.Interaction, user: discord.User):
    user_roles = [role.id for role in interaction.user.roles]
    if not has_mod_permission(user_roles):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    guild_user = interaction.guild.get_member(user.id)
    if not guild_user:
        await interaction.response.send_message("❌ User not found", ephemeral=True)
        return
    
    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if muted_role and muted_role in guild_user.roles:
        await guild_user.remove_roles(muted_role)
        if str(user.id) in mute_tracker:
            del mute_tracker[str(user.id)]
        
        embed = discord.Embed(title="🔊 User Unmuted", description=f"**User:** {user.mention}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(embed)

@bot.tree.command(name="kick", description="Kick a user")
@discord.app_commands.describe(user="User to kick", reason="Reason")
async def kick(interaction: discord.Interaction, user: discord.User, reason: str = "No reason"):
    user_roles = [role.id for role in interaction.user.roles]
    if not has_mod_permission(user_roles):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    try:
        await interaction.guild.kick(user, reason=reason)
        await log_moderation(str(user.id), "KICK", reason, str(interaction.user.id))
        
        embed = discord.Embed(title="👢 User Kicked", description=f"**User:** {user.mention}\n**Reason:** {reason}", color=0xFF6600)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a user")
@discord.app_commands.describe(user="User to ban", reason="Reason")
async def ban(interaction: discord.Interaction, user: discord.User, reason: str = "No reason"):
    user_roles = [role.id for role in interaction.user.roles]
    if not has_mod_permission(user_roles):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    try:
        await interaction.guild.ban(user, reason=reason)
        await log_moderation(str(user.id), "BAN", reason, str(interaction.user.id))
        
        embed = discord.Embed(title="🚫 User Banned", description=f"**User:** {user.mention}\n**Reason:** {reason}", color=0xFF0000)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@bot.tree.command(name="unban", description="Unban a user")
@discord.app_commands.describe(user_id="User ID to unban", reason="Reason")
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason"):
    user_roles = [role.id for role in interaction.user.roles]
    if OWNERSHIP_ROLE not in user_roles:
        await interaction.response.send_message("❌ Only owners can unban", ephemeral=True)
        return
    
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        
        embed = discord.Embed(title="✅ User Unbanned", description=f"**User:** {user.mention}\n**Reason:** {reason}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@bot.tree.command(name="promote", description="Promote a user")
@discord.app_commands.describe(user="User to promote", role="Role to add")
async def promote(interaction: discord.Interaction, user: discord.User, role: discord.Role):
    user_roles = [role.id for role in interaction.user.roles]
    if EXECUTIVE_ROLE not in user_roles and OWNERSHIP_ROLE not in user_roles:
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    guild_user = interaction.guild.get_member(user.id)
    if not guild_user:
        await interaction.response.send_message("❌ User not found", ephemeral=True)
        return
    
    try:
        await guild_user.add_roles(role)
        
        embed = discord.Embed(title="⬆️ User Promoted", description=f"**User:** {user.mention}\n**Role:** {role.mention}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@bot.tree.command(name="demote", description="Demote a user")
@discord.app_commands.describe(user="User to demote", role="Role to remove")
async def demote(interaction: discord.Interaction, user: discord.User, role: discord.Role):
    user_roles = [role.id for role in interaction.user.roles]
    if EXECUTIVE_ROLE not in user_roles and OWNERSHIP_ROLE not in user_roles:
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    guild_user = interaction.guild.get_member(user.id)
    if not guild_user:
        await interaction.response.send_message("❌ User not found", ephemeral=True)
        return
    
    try:
        await guild_user.remove_roles(role)
        
        embed = discord.Embed(title="⬇️ User Demoted", description=f"**User:** {user.mention}\n**Role Removed:** {role.mention}", color=0xFF0000)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@bot.tree.command(name="modinfo", description="View moderation history")
@discord.app_commands.describe(user="User to check")
async def modinfo(interaction: discord.Interaction, user: discord.User):
    user_roles = [role.id for role in interaction.user.roles]
    if not has_mod_permission(user_roles):
        await interaction.response.send_message("❌ No permission", ephemeral=True)
        return
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("SELECT action, reason, moderator_id, created_at FROM moderation WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
              (str(user.id),))
    records = c.fetchall()
    conn.close()
    
    embed = discord.Embed(title=f"📋 Moderation History - {user.name}", color=0x028DEF)
    
    if records:
        history = ""
        for action, reason, moderator_id, created_at in records:
            history += f"**{action}** - {reason}\n"
        embed.description = history
    else:
        embed.description = "No records"
    
    embed.set_thumbnail(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# ==================== BOT LOG ====================

@bot.tree.command(name="bot_log", description="Log a bot")
@discord.app_commands.describe(bot_name="Bot name", service="Service", link="Link")
async def bot_log(interaction: discord.Interaction, bot_name: str, service: str, link: str):
    user = interaction.user
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("""INSERT INTO bot_logs (user_id, bot_name, service, github_link, status, created_at, last_check)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (str(user.id), bot_name, service, link, "active", datetime.now(), datetime.now()))
    conn.commit()
    log_id = c.lastrowid
    conn.close()
    
    channel = bot.get_channel(BOT_LOG_CHANNEL)
    if channel:
        embed = discord.Embed(title=f"🤖 {bot_name}", description=f"**Dev:** {user.mention}\n**Service:** {service}", color=0x028DEF)
        await channel.send(embed=embed)
    
    await interaction.response.send_message(f"✅ Logged! ID: {log_id}", ephemeral=True)

# ==================== BOT HOST ====================

@bot.tree.command(name="bot_host", description="Host a bot")
@discord.app_commands.describe(bot_name="Bot name", bot_token="Bot token")
async def bot_host(interaction: discord.Interaction, bot_name: str, bot_token: str):
    user = interaction.user
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("""INSERT INTO bot_hosting (user_id, bot_name, bot_token, status, uptime, created_at, last_check, last_alert)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (str(user.id), bot_name, bot_token, "online", 100.0, datetime.now(), datetime.now(), None))
    conn.commit()
    hosting_id = c.lastrowid
    conn.close()
    
    embed = discord.Embed(title="✅ Bot Hosted", description=f"**Bot:** {bot_name}\n**Status:** Online", color=0x028DEF)
    await interaction.response.send_message(embed=embed)

# ==================== ECONOMY ====================

def add_xp(user_id, xp_amount):
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("SELECT xp, level FROM economy WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if not result:
        return None
    
    current_xp, level = result
    new_xp = current_xp + xp_amount
    xp_needed = 100 * (level ** 1.5)
    
    level_up = False
    while new_xp >= xp_needed:
        new_xp -= xp_needed
        level += 1
        xp_needed = 100 * (level ** 1.5)
        level_up = True
    
    c.execute("UPDATE economy SET xp = ?, level = ? WHERE user_id = ?", (new_xp, level, user_id))
    conn.commit()
    conn.close()
    
    return level_up, level

@bot.tree.command(name="balance", description="Check balance")
@discord.app_commands.describe(user="User (optional)")
async def balance(interaction: discord.Interaction, user: discord.User = None):
    if user is None:
        user = interaction.user
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("SELECT balance, level, xp, total_earned, achievements, streak FROM economy WHERE user_id = ?", 
              (str(user.id),))
    result = c.fetchone()
    conn.close()
    
    if result is None:
        balance_amt, level, xp, total_earned, achievements, streak = 0, 1, 0, 0, "[]", 0
    else:
        balance_amt, level, xp, total_earned, achievements, streak = result
    
    achievements = json.loads(achievements)
    xp_needed = 100 * (level ** 1.5) if level > 0 else 100
    xp_progress = (xp / xp_needed * 100) if xp_needed > 0 else 0
    
    embed = discord.Embed(title=f"💰 {user.name}", color=0x028DEF)
    embed.add_field(name="Balance", value=f"💵 {balance_amt:.2f}", inline=True)
    embed.add_field(name="Level", value=str(level), inline=True)
    embed.add_field(name="XP", value=f"{xp:.0f}/{xp_needed:.0f}", inline=True)
    embed.set_thumbnail(url=user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily", description="Claim daily reward")
async def daily(interaction: discord.Interaction):
    user = interaction.user
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("SELECT last_daily, balance, streak FROM economy WHERE user_id = ?", (str(user.id),))
    result = c.fetchone()
    
    if result is None:
        c.execute("""INSERT INTO economy 
                     (user_id, balance, level, xp, last_daily, total_earned, achievements, streak, last_streak_date) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (str(user.id), 100.0, 1, 0.0, datetime.now(), 100.0, json.dumps([]), 1, datetime.now()))
        conn.commit()
        conn.close()
        await interaction.response.send_message("✅ You claimed 💵100!")
        return
    
    last_daily, balance, streak = result
    
    if last_daily:
        last_daily = datetime.fromisoformat(last_daily)
        if (datetime.now() - last_daily).days < 1:
            await interaction.response.send_message("❌ Already claimed today!", ephemeral=True)
            conn.close()
            return
        streak += 1
    else:
        streak = 1
    
    reward = 100 + min(streak * 10, 100)
    new_balance = balance + reward
    
    c.execute("UPDATE economy SET balance = ?, last_daily = ?, streak = ? WHERE user_id = ?",
              (new_balance, datetime.now(), streak, str(user.id)))
    conn.commit()
    conn.close()
    
    add_xp(str(user.id), 10)
    
    embed = discord.Embed(title="✅ Daily Claimed", description=f"💵{reward}", color=0x00FF00)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="transfer", description="Transfer money")
@discord.app_commands.describe(user="User", amount="Amount")
async def transfer(interaction: discord.Interaction, user: discord.User, amount: float):
    sender = interaction.user
    
    if amount <= 0 or sender.id == user.id:
        await interaction.response.send_message("❌ Invalid", ephemeral=True)
        return
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM economy WHERE user_id = ?", (str(sender.id),))
    result = c.fetchone()
    
    if not result or result[0] < amount:
        await interaction.response.send_message("❌ Not enough balance!", ephemeral=True)
        conn.close()
        return
    
    c.execute("UPDATE economy SET balance = balance - ? WHERE user_id = ?", (amount, str(sender.id)))
    c.execute("INSERT OR IGNORE INTO economy (user_id, balance, level, xp, last_daily, total_earned, achievements, streak, last_streak_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (str(user.id), 0, 1, 0, None, 0, json.dumps([]), 0, None))
    c.execute("UPDATE economy SET balance = balance + ? WHERE user_id = ?", (amount, str(user.id)))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(title="✅ Transferred", description=f"💵{amount:.2f}", color=0x028DEF)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="View leaderboard")
@discord.app_commands.describe(category="balance, level, or streak")
async def leaderboard(interaction: discord.Interaction, category: str = "balance"):
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    
    if category == "level":
        c.execute("SELECT user_id, level FROM economy ORDER BY level DESC LIMIT 10")
    elif category == "streak":
        c.execute("SELECT user_id, streak FROM economy ORDER BY streak DESC LIMIT 10")
    else:
        c.execute("SELECT user_id, balance FROM economy ORDER BY balance DESC LIMIT 10")
    
    results = c.fetchall()
    conn.close()
    
    embed = discord.Embed(title="📊 Leaderboard", color=0x028DEF)
    text = ""
    for i, result in enumerate(results, 1):
        try:
            user = await bot.fetch_user(int(result[0]))
            text += f"{i}. {user.name}\n"
        except:
            pass
    
    embed.description = text if text else "No data"
    await interaction.response.send_message(embed=embed)

# ==================== FUN ====================

@bot.tree.command(name="8ball", description="Magic 8 ball")
@discord.app_commands.describe(question="Your question")
async def magic_8ball(interaction: discord.Interaction, question: str):
    responses = ["Yes!", "No!", "Maybe!", "Ask again later!", "Signs point to yes!", "Very doubtful!"]
    embed = discord.Embed(title="🎱 8 Ball", description=random.choice(responses), color=0x028DEF)
    add_xp(str(interaction.user.id), 1)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dice", description="Roll dice")
@discord.app_commands.describe(sides="Number of sides")
async def dice(interaction: discord.Interaction, sides: int = 6):
    if sides < 2:
        await interaction.response.send_message("❌ Min 2 sides!", ephemeral=True)
        return
    
    roll = random.randint(1, sides)
    embed = discord.Embed(title="🎲 Dice", description=f"**Result:** {roll}", color=0x028DEF)
    add_xp(str(interaction.user.id), 1)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="Flip coin")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    embed = discord.Embed(title="🪙 Coin", description=result, color=0x028DEF)
    add_xp(str(interaction.user.id), 1)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="joke", description="Random joke")
async def joke(interaction: discord.Interaction):
    jokes = ["Why don't scientists trust atoms? Because they make up everything!", "Why did the coffee file a police report? It got mugged!"]
    embed = discord.Embed(title="😄 Joke", description=random.choice(jokes), color=0x028DEF)
    add_xp(str(interaction.user.id), 1)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rps", description="Rock Paper Scissors")
@discord.app_commands.describe(choice="rock, paper, or scissors")
async def rps(interaction: discord.Interaction, choice: str):
    valid = ["rock", "paper", "scissors"]
    choice = choice.lower()
    
    if choice not in valid:
        await interaction.response.send_message("❌ Invalid!", ephemeral=True)
        return
    
    bot_choice = random.choice(valid)
    
    if choice == bot_choice:
        result = "Tie! 🤝"
        reward = 10
    elif (choice == "rock" and bot_choice == "scissors") or (choice == "paper" and bot_choice == "rock") or (choice == "scissors" and bot_choice == "paper"):
        result = "You win! 🎉"
        reward = 50
    else:
        result = "I win! 🤖"
        reward = 10
    
    embed = discord.Embed(title="🎮 RPS", description=f"You: {choice}\nMe: {bot_choice}\n{result}", color=0x028DEF)
    
    if reward > 10:
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("UPDATE economy SET balance = balance + ? WHERE user_id = ?", (reward, str(interaction.user.id)))
        conn.commit()
        conn.close()
        embed.add_field(name="Reward", value=f"💵{reward}", inline=False)
    
    add_xp(str(interaction.user.id), 5)
    await interaction.response.send_message(embed=embed)

# Run bot
bot.run(TOKEN)

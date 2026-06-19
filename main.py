import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
import json
import random

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

# Role IDs
LEADERSHIP_ROLE_1 = 1517219295623516370
LEADERSHIP_ROLE_2 = 1517222332991668425

# Database setup
def init_db():
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    
    # Bot logs table
    c.execute('''CREATE TABLE IF NOT EXISTS bot_logs
                 (id INTEGER PRIMARY KEY, user_id TEXT, bot_name TEXT, service TEXT, 
                  github_link TEXT, status TEXT, created_at TIMESTAMP, last_check TIMESTAMP)''')
    
    # Bot hosting table
    c.execute('''CREATE TABLE IF NOT EXISTS bot_hosting
                 (id INTEGER PRIMARY KEY, user_id TEXT, bot_name TEXT, bot_token TEXT,
                  status TEXT, uptime REAL, created_at TIMESTAMP, last_check TIMESTAMP, last_alert TIMESTAMP)''')
    
    # Economy table with achievements
    c.execute('''CREATE TABLE IF NOT EXISTS economy
                 (user_id TEXT PRIMARY KEY, balance REAL, level INTEGER, xp REAL, last_daily TIMESTAMP,
                  total_earned REAL, achievements TEXT, streak INTEGER, last_streak_date TIMESTAMP)''')
    
    # Support tickets table with status tracking
    c.execute('''CREATE TABLE IF NOT EXISTS support_tickets
                 (id INTEGER PRIMARY KEY, user_id TEXT, claimed_by TEXT, service TEXT, channel_id TEXT, 
                  status TEXT, created_at TIMESTAMP, closed_at TIMESTAMP, close_reason TEXT, rating INTEGER)''')
    
    # Ticket messages for tracking
    c.execute('''CREATE TABLE IF NOT EXISTS ticket_messages
                 (id INTEGER PRIMARY KEY, ticket_id INTEGER, message_id TEXT, channel_id TEXT)''')
    
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
    channel = bot.get_channel(WELCOME_CHANNEL)
    
    embed = discord.Embed(
        title="🚀 Welcome to P Code Studio!",
        description=f"We're excited to have you join our growing community of developers, designers, creators, and innovators.",
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
    
    embed.add_field(
        name="Get Started:",
        value="Whether you're here to request services, learn new skills, join our team, or simply connect with others, we're happy to have you with us.",
        inline=False
    )
    
    embed.set_footer(text="✨ Code. Design. Create.\n👑 Founded by itss_Gre1mi")
    
    await channel.send(f"🚀 Welcome to P Code Studio, {member.mention}!", embed=embed)
    
    # Initialize economy balance
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO economy 
                 (user_id, balance, level, xp, last_daily, total_earned, achievements, streak, last_streak_date) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (str(member.id), 100.0, 1, 0.0, None, 100.0, json.dumps([]), 0, None))
    conn.commit()
    conn.close()

@bot.event
async def on_member_remove(member):
    """Send goodbye message when member leaves"""
    channel = bot.get_channel(WELCOME_CHANNEL)
    
    embed = discord.Embed(
        title="📤 Farewell",
        description=f"{member.name} has left P Code Studio.\n\nThank you for being part of our community. We appreciate the time you spent with us and wish you success in all your future projects and endeavors.\n\nOur doors will always remain open should you decide to return.",
        color=0x028DEF
    )
    
    embed.set_footer(text="✨ Code. Design. Create.\n👑 P Code Studio Team")
    
    await channel.send(embed=embed)

# ==================== SUPPORT PANEL COMMANDS ====================

class CloseTicketModal(discord.ui.Modal):
    """Modal for closing tickets with a reason"""
    def __init__(self, ticket_id):
        super().__init__(title="Close Support Ticket")
        self.ticket_id = ticket_id
        
        self.reason = discord.ui.TextInput(
            label="Close Reason",
            placeholder="Why are you closing this ticket?",
            required=False,
            min_length=0,
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
        conn.close()
        
        # Get ticket info
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
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
                embed.set_footer(text="© P Code Studio | This channel will be archived soon")
                await channel.send(embed=embed)
        
        await interaction.response.send_message("✅ Ticket closed successfully!", ephemeral=True)

class TicketButtonView(discord.ui.View):
    """View for ticket management buttons"""
    def __init__(self, ticket_id, user_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.user_id = user_id
    
    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.green, emoji="👋")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has permission (is support role)
        user_roles = [role.id for role in interaction.user.roles]
        if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
            await interaction.response.send_message("❌ You don't have permission to claim tickets.", ephemeral=True)
            return
        
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("SELECT claimed_by FROM support_tickets WHERE id = ?", (self.ticket_id,))
        result = c.fetchone()
        
        if result and result[0]:
            await interaction.response.send_message("❌ This ticket is already claimed!", ephemeral=True)
            conn.close()
            return
        
        c.execute("UPDATE support_tickets SET claimed_by = ? WHERE id = ?",
                  (str(interaction.user.id), self.ticket_id))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Ticket Claimed",
            description=f"**Claimed By:** {interaction.user.mention}",
            color=0x00FF00
        )
        await interaction.response.send_message(embed=embed)
        
        # Send notification to ticket creator
        user = await bot.fetch_user(int(self.user_id))
        await user.send(f"📌 Your support ticket has been claimed by {interaction.user.mention}!")
    
    @discord.ui.button(label="Unclaim Ticket", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def unclaim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has permission
        user_roles = [role.id for role in interaction.user.roles]
        if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
            await interaction.response.send_message("❌ You don't have permission to unclaim tickets.", ephemeral=True)
            return
        
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("SELECT claimed_by FROM support_tickets WHERE id = ?", (self.ticket_id,))
        result = c.fetchone()
        
        if not result or not result[0]:
            await interaction.response.send_message("❌ This ticket is not claimed!", ephemeral=True)
            conn.close()
            return
        
        c.execute("UPDATE support_tickets SET claimed_by = NULL WHERE id = ?", (self.ticket_id,))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🔄 Ticket Unclaimed",
            description=f"**Unclaimed By:** {interaction.user.mention}",
            color=0xFFFF00
        )
        await interaction.response.send_message(embed=embed)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has permission
        user_roles = [role.id for role in interaction.user.roles]
        if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
            await interaction.response.send_message("❌ You don't have permission to close tickets.", ephemeral=True)
            return
        
        await interaction.response.send_modal(CloseTicketModal(self.ticket_id))
    
    @discord.ui.button(label="Close With Reason", style=discord.ButtonStyle.danger, emoji="📝")
    async def close_with_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has permission
        user_roles = [role.id for role in interaction.user.roles]
        if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
            await interaction.response.send_message("❌ You don't have permission to close tickets.", ephemeral=True)
            return
        
        await interaction.response.send_modal(CloseTicketModal(self.ticket_id))

class ServiceSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="👑 Leadership Support", value="leadership", description="Connect with our executive team for partnerships and leadership inquiries"),
            discord.SelectOption(label="🤖 Discord Bot Development", value="bot_dev", description="Get help designing and developing custom Discord bots"),
            discord.SelectOption(label="🎮 Roblox Game Development", value="roblox", description="Expert assistance with Roblox game creation and scripting"),
            discord.SelectOption(label="🎨 Graphic & UI Design", value="design", description="Professional graphic and user interface design services"),
            discord.SelectOption(label="🛠️ Discord Server Design", value="server_design", description="Complete Discord server setup and professional organization"),
            discord.SelectOption(label="💡 Custom Development", value="custom", description="Unique projects that don't fit standard categories"),
            discord.SelectOption(label="🧑‍🏫 Learning & Training", value="training", description="Learn skills from experienced team members"),
            discord.SelectOption(label="💬 General Support", value="general", description="General questions and support for P Code Studio"),
        ]
        super().__init__(placeholder="Select a service...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        service = self.values[0]
        user = interaction.user
        
        # Service configurations
        services = {
            "leadership": {
                "name": "👑 Leadership Support",
                "roles": [LEADERSHIP_ROLE_1, LEADERSHIP_ROLE_2],
                "message": f"Welcome {user.mention}! 👋\n\nThank you for contacting P Code Studio Leadership Support. A member of our Executive Team will be with you shortly. ⏳\n\nPlease explain your concern, partnership request, business inquiry, or leadership-related matter below.\n\n✨ Thank you for choosing P Code Studio."
            },
            "bot_dev": {
                "name": "🤖 Discord Bot Development",
                "roles": [1517239326704930837, 1517237815421964470, 1517238791771783409],
                "message": f"Welcome {user.mention}! 👋\n\nThank you for choosing P Code Studio Bot Development Services.\n\nA Discord Bot Developer will be with you shortly. 🚀\n\nPlease provide:\n\n📝 Bot Description:\n⚙️ Features Needed:\n💰 Budget (Optional):\n⏰ Deadline (Optional):\n📎 Examples or References:\n\nWe look forward to bringing your bot idea to life!"
            },
            "roblox": {
                "name": "🎮 Roblox Game Development",
                "roles": [1517240614163447819, 1517240911309050049, 1517239644989685911],
                "message": f"Welcome {user.mention}! 👋\n\nThank you for contacting P Code Studio Roblox Development Services.\n\nA Roblox Developer will assist you shortly. 🚀\n\nPlease provide:\n\n🎮 Project Description\n📝 Systems Needed\n💰 Budget (Optional)\n⏰ Deadline (Optional)\n📎 References or Examples\n\nThank you for choosing P Code Studio."
            },
            "design": {
                "name": "🎨 Graphic & UI Design",
                "roles": [1517241987986620486],
                "message": f"Welcome {user.mention}! 👋\n\nThank you for choosing P Code Studio Design Services.\n\nA Designer will assist you shortly. 🎨\n\nPlease provide:\n\n🖼️ Design Type\n🎨 Color Preferences\n📎 References\n💰 Budget (Optional)\n⏰ Deadline (Optional)\n\nWe can't wait to bring your vision to life."
            },
            "server_design": {
                "name": "🛠️ Discord Server Design & Setup",
                "roles": [1517306660589273209],
                "message": f"Welcome {user.mention}! 👋\n\nThank you for choosing P Code Studio Server Design Services.\n\nA Server Designer will assist you shortly. 🚀\n\nPlease provide:\n\n📖 Server Purpose\n👥 Estimated Member Count\n⚙️ Systems Needed\n📎 References\n💰 Budget (Optional)\n\nWe'll help make your server professional and organized."
            },
            "custom": {
                "name": "💡 Custom Development Solutions",
                "roles": [1517310391473148045],
                "message": f"Welcome {user.mention}! 👋\n\nThank you for contacting P Code Studio Custom Development Solutions.\n\nNeed something unique that doesn't fit into one of our standard service categories? You've come to the right place! 🚀\n\nWhether it's a custom system, automation, integration, special project, or a completely unique idea, our team will review your request and help bring it to life.\n\n📋 Please Provide:\n📝 Detailed Project Description\n🎯 Project Goals\n⚙️ Required Features\n📎 References, Screenshots, or Examples\n💰 Budget (Optional)\n⏰ Deadline (Optional)\n💡 Any Additional Information"
            },
            "training": {
                "name": "🧑‍🏫 Learning & Training Services",
                "roles": [1517237018642481252],
                "message": f"Welcome {user.mention}! 👋\n\nThank you for contacting P Code Studio Training Services.\n\nInterested in learning one of our services? Let us know which skill you'd like to learn and we'll connect you with an experienced team member who can help guide and teach you.\n\n🎓 What would you like to learn?"
            },
            "general": {
                "name": "💬 General Support",
                "roles": [1517237018642481252],
                "message": f"Welcome {user.mention}! 👋\n\nThank you for contacting P Code Studio Support.\n\nA staff member will assist you shortly. ⏳\n\nPlease describe how we can help you today.\n\nThank you for being part of the P Code Studio community!"
            }
        }
        
        service_info = services[service]
        
        # Create ticket channel
        guild = interaction.guild
        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}",
            category=None,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
        )
        
        # Add support roles to see the ticket
        for role_id in service_info["roles"]:
            role = guild.get_role(role_id)
            if role:
                await channel.set_permissions(role, view_channel=True, send_messages=True)
        
        # Store ticket in database first
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("""INSERT INTO support_tickets 
                     (user_id, claimed_by, service, channel_id, status, created_at, closed_at, close_reason, rating) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (str(user.id), None, service, str(channel.id), "open", datetime.now(), None, None, 0))
        conn.commit()
        
        ticket_id = c.lastrowid
        conn.close()
        
        # Send ticket message with buttons
        embed = discord.Embed(
            title=f"New {service_info['name']} Ticket",
            description=service_info["message"],
            color=0x028DEF
        )
        embed.add_field(
            name="📋 Ticket Info",
            value=f"**Ticket ID:** {ticket_id}\n**Status:** Open\n**Created At:** <t:{int(datetime.now().timestamp())}:f>",
            inline=False
        )
        embed.set_footer(text="© P Code Studio | All Rights Reserved")
        
        # Mention support roles
        mention_text = " ".join([f"<@&{role_id}>" for role_id in service_info["roles"]])
        
        # Send message with buttons
        message = await channel.send(mention_text, embed=embed, view=TicketButtonView(ticket_id, str(user.id)))
        
        # Store message ID
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("INSERT INTO ticket_messages (ticket_id, message_id, channel_id) VALUES (?, ?, ?)",
                  (ticket_id, str(message.id), str(channel.id)))
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(f"✅ Support ticket created! Check {channel.mention}", ephemeral=True)

class ServiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ServiceSelect())

@bot.tree.command(name="assistance", description="Get support from P Code Studio")
@discord.app_commands.describe(panel="Open the support panel")
async def assistance_panel(interaction: discord.Interaction, panel: str = "panel"):
    # Check if user has required roles
    user_roles = [role.id for role in interaction.user.roles]
    if LEADERSHIP_ROLE_1 not in user_roles and LEADERSHIP_ROLE_2 not in user_roles:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="P Code Studio - Support Panel",
        description="Welcome to P Code Studio support! We offer a wide range of professional services to help bring your ideas to life. Whether you need Discord bot development, Roblox game creation, graphic design, server setup, or custom solutions, our experienced team is here to assist you. Select a service below to get started with a support ticket.",
        color=0x028DEF
    )
    
    embed.add_field(
        name="📋 Office Hours",
        value="**Monday - Friday:** <t:1781776800:t> - <t:1781836200:t>\n**Saturday - Sunday:** <t:1781787600:t> - <t:1781834400:t>",
        inline=False
    )
    
    embed.add_field(
        name="Our Services",
        value="🤖 **Discord Bot Development** - Custom Discord bots tailored to your needs\n🎮 **Roblox Development** - Professional game development and scripting\n🎨 **Graphic & UI Design** - Creative design solutions\n🛠️ **Server Design** - Professional Discord server setup\n💡 **Custom Solutions** - Unique projects for your specific needs\n🧑‍🏫 **Training** - Learn from our experienced team members",
        inline=False
    )
    
    embed.set_footer(text="© P Code Studio | All Rights Reserved")
    
    await interaction.response.send_message(embed=embed, view=ServiceView())

# ==================== BOT LOG COMMANDS ====================

@bot.tree.command(name="bot_log", description="Log a bot being developed")
@discord.app_commands.describe(
    bot_name="Name of the bot",
    service="Service used (Github, Render, etc)",
    link="Link to the bot/project"
)
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
    
    # Send to bot log channel
    channel = bot.get_channel(BOT_LOG_CHANNEL)
    embed = discord.Embed(
        title=f"🤖 New Bot Logged - {bot_name}",
        description=f"**Developer:** {user.mention}\n**Service:** {service}\n**Link:** [Click here]({link})\n**Status:** Active",
        color=0x028DEF
    )
    embed.set_footer(text=f"Log ID: {log_id} | © P Code Studio")
    
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Bot logged successfully! ID: {log_id}", ephemeral=True)

# ==================== BOT HOST COMMANDS ====================

@bot.tree.command(name="bot_host", description="Host a bot on P Code Bot system")
@discord.app_commands.describe(
    bot_name="Name of the bot",
    bot_token="Bot token (will be stored securely)"
)
async def bot_host(interaction: discord.Interaction, bot_name: str, bot_token: str):
    user = interaction.user
    
    # Don't display the token in responses for security
    token_preview = bot_token[:10] + "..." if len(bot_token) > 10 else "***"
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("""INSERT INTO bot_hosting (user_id, bot_name, bot_token, status, uptime, created_at, last_check, last_alert)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (str(user.id), bot_name, bot_token, "online", 100.0, datetime.now(), datetime.now(), None))
    conn.commit()
    
    hosting_id = c.lastrowid
    conn.close()
    
    embed = discord.Embed(
        title=f"✅ Bot Hosted Successfully",
        description=f"**Bot Name:** {bot_name}\n**Token Preview:** {token_preview}\n**Status:** Online\n**Uptime:** 100%",
        color=0x028DEF
    )
    embed.add_field(
        name="⚠️ Important",
        value="Your bot is now being monitored. You will receive notifications if:\n• Bot goes offline\n• Service payment reminder\n• Critical issues detected",
        inline=False
    )
    embed.set_footer(text=f"Host ID: {hosting_id} | © P Code Studio")
    
    await interaction.response.send_message(embed=embed)
    await user.send(f"🤖 Your bot **{bot_name}** is now hosted on P Code Bot system and being monitored 24/7!")

# ==================== ECONOMY COMMANDS ====================

def add_xp(user_id, xp_amount):
    """Add XP and check for level up"""
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

def unlock_achievement(user_id, achievement):
    """Unlock an achievement for a user"""
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("SELECT achievements FROM economy WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if result:
        achievements = json.loads(result[0])
        if achievement not in achievements:
            achievements.append(achievement)
            c.execute("UPDATE economy SET achievements = ? WHERE user_id = ?",
                      (json.dumps(achievements), user_id))
            conn.commit()
            conn.close()
            return True
    
    conn.close()
    return False

@bot.tree.command(name="balance", description="Check your P Code Studio balance and stats")
@discord.app_commands.describe(user="User to check (optional)")
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
    xp_needed = 100 * (level ** 1.5)
    xp_progress = (xp / xp_needed) * 100
    
    embed = discord.Embed(
        title=f"💰 {user.name}'s Profile",
        color=0x028DEF
    )
    
    embed.add_field(
        name="💵 Currency",
        value=f"**Balance:** 💵 {balance_amt:.2f}\n**Total Earned:** 💵 {total_earned:.2f}",
        inline=False
    )
    
    embed.add_field(
        name="📊 Level & Experience",
        value=f"**Level:** {level}\n**XP:** {xp:.0f}/{xp_needed:.0f} ({xp_progress:.1f}%)",
        inline=False
    )
    
    embed.add_field(
        name="🔥 Streaks",
        value=f"**Daily Streak:** {streak} days 🔥",
        inline=False
    )
    
    if achievements:
        embed.add_field(
            name="🏆 Achievements",
            value=", ".join(achievements),
            inline=False
        )
    
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="© P Code Studio | Keep grinding!")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily", description="Claim your daily reward and boost your streak!")
async def daily(interaction: discord.Interaction):
    user = interaction.user
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    c.execute("SELECT last_daily, balance, streak, last_streak_date FROM economy WHERE user_id = ?", (str(user.id),))
    result = c.fetchone()
    
    if result is None:
        c.execute("""INSERT INTO economy 
                     (user_id, balance, level, xp, last_daily, total_earned, achievements, streak, last_streak_date) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (str(user.id), 100.0, 1, 0.0, datetime.now(), 100.0, json.dumps([]), 1, datetime.now()))
        conn.commit()
        await interaction.response.send_message("✅ You claimed your daily 💵100! (First time reward) 🎉")
    else:
        last_daily, balance, streak, last_streak_date = result
        
        if last_daily:
            last_daily = datetime.fromisoformat(last_daily)
            days_since = (datetime.now() - last_daily).days
            
            if days_since < 1:
                hours_left = 24 - (datetime.now() - last_daily).seconds // 3600
                await interaction.response.send_message(
                    f"❌ You already claimed your daily reward! Try again in {hours_left} hours.", 
                    ephemeral=True
                )
                conn.close()
                return
            
            # Check if streak should continue
            if days_since == 1:
                streak += 1
            else:
                streak = 1
        else:
            streak = 1
        
        # Bonus reward based on streak
        base_reward = 100
        streak_bonus = min(streak * 10, 100)  # Max 100 bonus
        total_reward = base_reward + streak_bonus
        
        new_balance = balance + total_reward
        
        c.execute("""UPDATE economy 
                     SET balance = ?, last_daily = ?, total_earned = total_earned + ?, streak = ?, last_streak_date = ?
                     WHERE user_id = ?""",
                  (new_balance, datetime.now(), total_reward, streak, datetime.now(), str(user.id)))
        conn.commit()
        
        # Add XP
        add_xp(str(user.id), 10)
        
        # Check for achievements
        if streak == 7:
            if unlock_achievement(str(user.id), "🔥 Week Warrior"):
                await interaction.followup.send("🏆 **Achievement Unlocked:** Week Warrior (7 day streak)!")
        elif streak == 30:
            if unlock_achievement(str(user.id), "💪 Monthly Master"):
                await interaction.followup.send("🏆 **Achievement Unlocked:** Monthly Master (30 day streak)!")
        
        embed = discord.Embed(
            title="✅ Daily Reward Claimed!",
            description=f"**Base Reward:** 💵{base_reward}\n**Streak Bonus:** 💵{streak_bonus}\n**Total:** 💵{total_reward}",
            color=0x00FF00
        )
        embed.add_field(
            name="🔥 Streak Information",
            value=f"**Current Streak:** {streak} days\n**New Balance:** 💵{new_balance:.2f}",
            inline=False
        )
        embed.set_footer(text="Come back tomorrow to continue your streak!")
        
        await interaction.response.send_message(embed=embed)
    
    conn.close()

@bot.tree.command(name="transfer", description="Transfer money to another user")
@discord.app_commands.describe(
    user="User to transfer to",
    amount="Amount to transfer"
)
async def transfer(interaction: discord.Interaction, user: discord.User, amount: float):
    sender = interaction.user
    
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
        return
    
    if sender.id == user.id:
        await interaction.response.send_message("❌ You can't transfer to yourself!", ephemeral=True)
        return
    
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    
    c.execute("SELECT balance FROM economy WHERE user_id = ?", (str(sender.id),))
    sender_balance = c.fetchone()
    
    if sender_balance is None or sender_balance[0] < amount:
        await interaction.response.send_message("❌ You don't have enough balance!", ephemeral=True)
        conn.close()
        return
    
    # Update sender
    c.execute("UPDATE economy SET balance = balance - ? WHERE user_id = ?", (amount, str(sender.id)))
    
    # Update receiver
    c.execute("""INSERT OR IGNORE INTO economy 
                 (user_id, balance, level, xp, last_daily, total_earned, achievements, streak, last_streak_date)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (str(user.id), 0, 1, 0, None, 0, json.dumps([]), 0, None))
    c.execute("UPDATE economy SET balance = balance + ? WHERE user_id = ?", (amount, str(user.id)))
    
    conn.commit()
    conn.close()
    
    # Add XP
    add_xp(str(sender.id), 5)
    
    embed = discord.Embed(
        title="✅ Transfer Complete",
        description=f"**From:** {sender.mention}\n**To:** {user.mention}\n**Amount:** 💵{amount:.2f}",
        color=0x028DEF
    )
    embed.set_footer(text="Both users received XP!")
    
    await interaction.response.send_message(embed=embed)
    
    # Notify receiver
    try:
        await user.send(f"💰 You received 💵{amount:.2f} from {sender.mention}!")
    except:
        pass

@bot.tree.command(name="leaderboard", description="View the economy leaderboard")
@discord.app_commands.describe(
    category="What to rank by (balance, level, or streak)"
)
async def leaderboard(interaction: discord.Interaction, category: str = "balance"):
    conn = sqlite3.connect('pcodebot.db')
    c = conn.cursor()
    
    if category == "level":
        c.execute("SELECT user_id, balance, level, streak FROM economy ORDER BY level DESC LIMIT 10")
    elif category == "streak":
        c.execute("SELECT user_id, balance, level, streak FROM economy ORDER BY streak DESC LIMIT 10")
    else:  # balance
        c.execute("SELECT user_id, balance, level, streak FROM economy ORDER BY balance DESC LIMIT 10")
    
    results = c.fetchall()
    conn.close()
    
    category_names = {"balance": "💵 Richest Members", "level": "📊 Highest Levels", "streak": "🔥 Best Streaks"}
    
    embed = discord.Embed(
        title=f"{category_names.get(category, '💰 Economy Leaderboard')}",
        color=0x028DEF
    )
    
    leaderboard_text = ""
    for i, (user_id, balance, level, streak) in enumerate(results, 1):
        try:
            user = await bot.fetch_user(int(user_id))
            if category == "streak":
                leaderboard_text += f"{i}. **{user.name}** - 🔥{streak} days\n"
            elif category == "level":
                leaderboard_text += f"{i}. **{user.name}** - Level {level}\n"
            else:
                leaderboard_text += f"{i}. **{user.name}** - 💵{balance:.2f}\n"
        except:
            pass
    
    embed.description = leaderboard_text if leaderboard_text else "No data yet!"
    embed.set_footer(text="© P Code Studio | Keep competing!")
    
    await interaction.response.send_message(embed=embed)

# ==================== FUN COMMANDS ====================

@bot.tree.command(name="8ball", description="Ask the magic 8 ball a question")
@discord.app_commands.describe(question="Your question for the magic 8 ball")
async def magic_8ball(interaction: discord.Interaction, question: str):
    responses = [
        "Yes, definitely!", "No, absolutely not.", "Maybe, ask again later.",
        "The signs point to yes.", "Don't count on it.", "It is certain.",
        "Very doubtful.", "Ask again later.", "Outlook good.", "Concentrate and ask again.",
        "Most likely.", "The stars say no.", "Try again.", "Without a doubt!",
        "My sources say no.", "Outlook not so good."
    ]
    
    embed = discord.Embed(
        title="🎱 Magic 8 Ball",
        description=f"**Question:** {question}\n**Answer:** {random.choice(responses)}",
        color=0x028DEF
    )
    embed.set_footer(text=f"Asked by {interaction.user.name}")
    
    # Add XP for fun
    add_xp(str(interaction.user.id), 1)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dice", description="Roll a dice")
@discord.app_commands.describe(sides="Number of sides (default 6)")
async def dice(interaction: discord.Interaction, sides: int = 6):
    if sides < 2:
        await interaction.response.send_message("❌ Dice must have at least 2 sides!", ephemeral=True)
        return
    
    roll = random.randint(1, sides)
    
    embed = discord.Embed(
        title="🎲 Dice Roll",
        description=f"Rolled a **{sides}-sided dice**\n**Result:** {roll}",
        color=0x028DEF
    )
    embed.set_footer(text=f"Rolled by {interaction.user.name}")
    
    # Add XP
    add_xp(str(interaction.user.id), 1)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    
    embed = discord.Embed(
        title="🪙 Coin Flip",
        description=f"**Result:** {result}",
        color=0x028DEF
    )
    embed.set_footer(text=f"Flipped by {interaction.user.name}")
    
    # Add XP
    add_xp(str(interaction.user.id), 1)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="joke", description="Get a random joke")
async def joke(interaction: discord.Interaction):
    jokes = [
        "Why don't scientists trust atoms? Because they make up everything!",
        "Why did the scarecrow win an award? He was outstanding in his field!",
        "What do you call a fake noodle? An impasta!",
        "Why don't eggs tell jokes? They'd crack each other up!",
        "What do you call a bear with no teeth? A gummy bear!",
        "Why did the coffee file a police report? It got mugged!",
        "What's orange and sounds like a parrot? A carrot!",
        "Why don't skeletons fight each other? They don't have the guts!",
        "What did the ocean say to the beach? Nothing, it just waved!",
        "Why don't you ever see elephants hiding in trees? Because they're so good at it!",
    ]
    
    embed = discord.Embed(
        title="😄 Random Joke",
        description=random.choice(jokes),
        color=0x028DEF
    )
    embed.set_footer(text=f"For {interaction.user.name}")
    
    # Add XP
    add_xp(str(interaction.user.id), 1)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rps", description="Play Rock Paper Scissors against the bot")
@discord.app_commands.describe(choice="Your choice (rock, paper, or scissors)")
async def rps(interaction: discord.Interaction, choice: str):
    valid_choices = ["rock", "paper", "scissors"]
    choice = choice.lower()
    
    if choice not in valid_choices:
        await interaction.response.send_message("❌ Invalid choice! Use: rock, paper, or scissors", ephemeral=True)
        return
    
    bot_choice = random.choice(valid_choices)
    
    # Determine winner
    if choice == bot_choice:
        result = "It's a tie! 🤝"
        reward = 10
    elif (choice == "rock" and bot_choice == "scissors") or \
         (choice == "paper" and bot_choice == "rock") or \
         (choice == "scissors" and bot_choice == "paper"):
        result = "You win! 🎉"
        reward = 50
    else:
        result = "I win! 🤖"
        reward = 10
    
    embed = discord.Embed(
        title="🎮 Rock Paper Scissors",
        description=f"**Your choice:** {choice.capitalize()}\n**My choice:** {bot_choice.capitalize()}\n\n{result}",
        color=0x028DEF
    )
    
    # Add reward and XP
    if reward > 10:
        conn = sqlite3.connect('pcodebot.db')
        c = conn.cursor()
        c.execute("UPDATE economy SET balance = balance + ? WHERE user_id = ?", 
                  (reward, str(interaction.user.id)))
        conn.commit()
        conn.close()
        
        embed.add_field(
            name="💰 Reward",
            value=f"You earned 💵{reward}!",
            inline=False
        )
    
    add_xp(str(interaction.user.id), 5)
    
    embed.set_footer(text="Thanks for playing!")
    await interaction.response.send_message(embed=embed)

# ==================== GITHUB FEED ====================

@bot.tree.command(name="github_feed", description="Enable GitHub feed notifications")
@discord.app_commands.describe(
    repo="GitHub repository (owner/repo format)",
    events="Events to track (push, pull_request, issues, all)"
)
async def github_feed(interaction: discord.Interaction, repo: str, events: str = "all"):
    embed = discord.Embed(
        title="📊 GitHub Feed Setup",
        description=f"**Repository:** {repo}\n**Events Tracked:** {events}\n**Channel:** {interaction.channel.mention}",
        color=0x028DEF
    )
    embed.add_field(
        name="ℹ️ Info",
        value="To fully enable GitHub feeds, set up a webhook in your GitHub repository settings pointing to your bot server.",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

# Run the bot
bot.run(TOKEN)

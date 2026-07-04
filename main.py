"""
P Code Studio Discord Bot - single-file build.

Support ticket system with post-close surveys and staff ratings, an
/assistancepanel, raid/spam protection, /bot-add /bot-status (Developer
role only), a GitHub activity feed, a fun economy system restricted to
#commands, and invite tracking.

Run with: python main.py
Required env var: DISCORD_TOKEN
Optional env var: GITHUB_TOKEN (raises GitHub API rate limits / private repos)
"""

import asyncio
import json
import os
import random
import re
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")


# ============================================================
# CONFIG - channel IDs, role IDs, and tunable constants.
# ============================================================

class config:
    # ---------------- CHANNEL IDS ----------------
    WELCOME_CHANNEL = 1514684270596198594
    SUPPORT_CHANNEL = 1514684277764128800
    GITHUB_CHANNEL = 1514684267811180808
    BOT_LOG_CHANNEL = 1514684302502268929
    MOD_LOG_CHANNEL = 1514684296990818415
    TEAM_STATS_CHANNEL = 1517214941755478066
    COMMANDS_CHANNEL = 1514684285376925757
    INVITES_CHANNEL = 1514684303957688530

    # ---------------- ROLE IDS ----------------
    # Organizational "team" hierarchy, lowest to highest:
    # Development Team < Administration Team < Executive Team < Ownership
    OWNERSHIP_ROLE = 1517219295623516370
    EXECUTIVE_ROLE = 1517222332991668425
    ADMIN_ROLE = 1517237018642481252
    LEADERSHIP_ROLE_1 = OWNERSHIP_ROLE
    LEADERSHIP_ROLE_2 = EXECUTIVE_ROLE
    DEVELOPER_ROLE = 1517236903588528311

    LEADERSHIP_ROLES = [LEADERSHIP_ROLE_1, LEADERSHIP_ROLE_2]

    # Team roles ranked above Development Team (does NOT include
    # Development Team itself). Used for "Development Team and above"
    # permission checks.
    ROLES_ABOVE_DEVELOPMENT = [ADMIN_ROLE, EXECUTIVE_ROLE, OWNERSHIP_ROLE]

    # Development Team + everything above it. Permission set for:
    # - who can post the /assistancepanel
    # - who (besides the claimer) can close/remove a ticket
    STAFF_MANAGE_ROLES = [DEVELOPER_ROLE] + ROLES_ABOVE_DEVELOPMENT

    # Roles allowed to claim/manage tickets for each service category.
    SERVICE_ROLES = {
        "leadership": [LEADERSHIP_ROLE_1, LEADERSHIP_ROLE_2],
        "bot_dev": [1517239326704930837, 1517237815421964470, 1517238791771783409],
        "roblox": [1517239326704930837, 1517237815421964470, 1517238791771783409],
        "design": [1517239326704930837, 1517237815421964470, 1517238791771783409],
        "server_design": [1517239326704930837, 1517237815421964470, 1517238791771783409],
        "custom": [1517239326704930837, 1517237815421964470, 1517238791771783409],
        "training": [1517239326704930837, 1517237815421964470, 1517238791771783409],
        "general": [1517239326704930837, 1517237815421964470, 1517238791771783409],
    }

    # Service categories used for tickets AND for the staff statistics system.
    SERVICE_CATEGORIES = {
        "leadership": "Leadership Support",
        "bot_dev": "Discord Bot Development",
        "roblox_scripting": "Roblox Scripting",
        "roblox_building": "Roblox Building",
        "server_design": "Discord Server Design",
        "ui_design": "UI Design",
        "graphic_design": "Graphic Design",
        "blender": "Blender",
        "animation": "Animation",
        "training": "Training",
        "custom": "Custom Solutions",
        "general": "General Support",
        "other": "Other",
    }

    # Options presented in the /assistancepanel service select menu.
    TICKET_SERVICE_OPTIONS = [
        ("leadership", "\U0001F451 Leadership Support"),
        ("bot_dev", "\U0001F916 Bot Development"),
        ("roblox_scripting", "\U0001F3AE Roblox Scripting"),
        ("roblox_building", "\U0001F3D7\uFE0F Roblox Building"),
        ("server_design", "\U0001F6E0\uFE0F Server Design"),
        ("ui_design", "\U0001F3A8 UI Design"),
        ("graphic_design", "\U0001F5BC\uFE0F Graphic Design"),
        ("blender", "\U0001F9CA Blender"),
        ("animation", "\U0001F3AC Animation"),
        ("custom", "\U0001F4A1 Custom Solutions"),
        ("training", "\U0001F9D1\u200D\U0001F3EB Training"),
        ("general", "\U0001F4AC General Support"),
    ]

    BRAND_NAME = "P Code Studio"
    BRAND_COLOR = 0x028DEF
    DANGER_COLOR = 0xFF0000
    SUCCESS_COLOR = 0x00FF00
    WARN_COLOR = 0xFFFF00
    BANNER_IMAGE_PATH = "attached_assets/3_1783185510768.png"

    # ---------------- RAID / AUTOMOD SETTINGS ----------------
    RAID_THRESHOLD = 5
    RAID_TIME_WINDOW = 10
    BAN_ON_RAID = True

    MENTION_SPAM_THRESHOLD = 5
    MENTION_SPAM_WINDOW = 10
    INVITE_SPAM_THRESHOLD = 3
    INVITE_SPAM_WINDOW = 15

    # ---------------- ECONOMY SETTINGS ----------------
    DAILY_REWARD = 250.0
    WORK_MIN = 50.0
    WORK_MAX = 300.0
    WORK_COOLDOWN_SECONDS = 60 * 60

    SHOP_ITEMS = {
        "fishing_rod": {"name": "Fishing Rod", "price": 500.0, "emoji": "\U0001F3A3"},
        "lucky_coin": {"name": "Lucky Coin", "price": 1000.0, "emoji": "\U0001FA99"},
        "trophy": {"name": "Trophy", "price": 2500.0, "emoji": "\U0001F3C6"},
        "vip_badge": {"name": "VIP Badge", "price": 5000.0, "emoji": "\U0001F48E"},
    }

    # ---------------- GITHUB FEED SETTINGS ----------------
    GITHUB_POLL_SECONDS = 120

    _HERE = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(_HERE, "data", "pcodebot.db")


# ============================================================
# DATABASE - SQLite persistence layer.
# ============================================================

class db:
    @staticmethod
    def get_conn():
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _column_exists(c, table, column):
        c.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in c.fetchall())

    @staticmethod
    def init_db():
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        conn = db.get_conn()
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS bot_logs
                     (id INTEGER PRIMARY KEY, user_id TEXT, bot_name TEXT, service TEXT,
                      github_link TEXT, status TEXT, created_at TIMESTAMP, last_check TIMESTAMP)""")

        c.execute("""CREATE TABLE IF NOT EXISTS bot_hosting
                     (id INTEGER PRIMARY KEY, customer_id TEXT, bot_name TEXT, bot_id TEXT,
                      github_repo TEXT, render_service TEXT, purchase_date TEXT,
                      renewal_date TEXT, status TEXT, created_at TIMESTAMP,
                      registered_by TEXT, last_notified_sha TEXT)""")

        c.execute("""CREATE TABLE IF NOT EXISTS economy
                     (user_id TEXT PRIMARY KEY, balance REAL, level INTEGER, xp REAL, last_daily TIMESTAMP,
                      total_earned REAL, achievements TEXT, streak INTEGER, last_streak_date TIMESTAMP,
                      last_work TIMESTAMP, inventory TEXT)""")

        c.execute("""CREATE TABLE IF NOT EXISTS support_tickets
                     (id INTEGER PRIMARY KEY, user_id TEXT, claimed_by TEXT, service TEXT, channel_id TEXT,
                      status TEXT, created_at TIMESTAMP, closed_at TIMESTAMP, close_reason TEXT, rating INTEGER,
                      helpers TEXT, priority TEXT, closed_by TEXT)""")

        c.execute("""CREATE TABLE IF NOT EXISTS ticket_messages
                     (id INTEGER PRIMARY KEY, ticket_id INTEGER, message_id TEXT, channel_id TEXT)""")

        c.execute("""CREATE TABLE IF NOT EXISTS moderation
                     (id INTEGER PRIMARY KEY, user_id TEXT, action TEXT, reason TEXT,
                      moderator_id TEXT, created_at TIMESTAMP, expires_at TIMESTAMP,
                      is_active INTEGER DEFAULT 1)""")

        c.execute("""CREATE TABLE IF NOT EXISTS warnings
                     (id INTEGER PRIMARY KEY, user_id TEXT, reason TEXT, moderator_id TEXT, created_at TIMESTAMP)""")

        c.execute("""CREATE TABLE IF NOT EXISTS raid_logs
                     (id INTEGER PRIMARY KEY, user_id TEXT, action TEXT, reason TEXT, created_at TIMESTAMP)""")

        c.execute("""CREATE TABLE IF NOT EXISTS surveys
                     (id INTEGER PRIMARY KEY, ticket_id INTEGER, user_id TEXT,
                      overall_rating INTEGER, communication_rating INTEGER, expectations TEXT,
                      liked_most TEXT, suggestions TEXT, created_at TIMESTAMP)""")

        c.execute("""CREATE TABLE IF NOT EXISTS staff_ratings
                     (id INTEGER PRIMARY KEY, staff_id TEXT, category TEXT, rating INTEGER,
                      ticket_id INTEGER, created_at TIMESTAMP)""")

        c.execute("""CREATE TABLE IF NOT EXISTS staff_stats
                     (staff_id TEXT, category TEXT, total_jobs INTEGER DEFAULT 0,
                      sum_ratings INTEGER DEFAULT 0, five_star INTEGER DEFAULT 0,
                      four_star INTEGER DEFAULT 0, three_star INTEGER DEFAULT 0,
                      two_star INTEGER DEFAULT 0, one_star INTEGER DEFAULT 0,
                      PRIMARY KEY (staff_id, category))""")

        c.execute("""CREATE TABLE IF NOT EXISTS invites
                     (id INTEGER PRIMARY KEY, guild_id TEXT, code TEXT UNIQUE, inviter_id TEXT,
                      uses INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 0,
                      created_at TIMESTAMP, expires_at TIMESTAMP)""")

        for column, ddl in [
            ("helpers", "ALTER TABLE support_tickets ADD COLUMN helpers TEXT"),
            ("priority", "ALTER TABLE support_tickets ADD COLUMN priority TEXT"),
            ("closed_by", "ALTER TABLE support_tickets ADD COLUMN closed_by TEXT"),
        ]:
            if not db._column_exists(c, "support_tickets", column):
                c.execute(ddl)

        if not db._column_exists(c, "economy", "last_work"):
            c.execute("ALTER TABLE economy ADD COLUMN last_work TIMESTAMP")
        if not db._column_exists(c, "economy", "inventory"):
            c.execute("ALTER TABLE economy ADD COLUMN inventory TEXT")

        conn.commit()
        conn.close()

    @staticmethod
    def now():
        return datetime.now()

    @staticmethod
    def ensure_economy_account(user_id: str):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id FROM economy WHERE user_id = ?", (user_id,))
        if not c.fetchone():
            c.execute(
                """INSERT INTO economy
                   (user_id, balance, level, xp, last_daily, total_earned, achievements, streak, last_streak_date, last_work, inventory)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, 100.0, 1, 0.0, None, 100.0, json.dumps([]), 0, None, None, json.dumps({})),
            )
            conn.commit()
        conn.close()

    @staticmethod
    def record_staff_rating(staff_id: str, category: str, rating: int, ticket_id: int):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO staff_ratings (staff_id, category, rating, ticket_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (staff_id, category, rating, ticket_id, db.now()),
        )

        star_column = {1: "one_star", 2: "two_star", 3: "three_star", 4: "four_star", 5: "five_star"}[rating]

        c.execute("SELECT * FROM staff_stats WHERE staff_id = ? AND category = ?", (staff_id, category))
        row = c.fetchone()
        if row is None:
            c.execute(
                f"""INSERT INTO staff_stats (staff_id, category, total_jobs, sum_ratings, {star_column})
                    VALUES (?, ?, 1, ?, 1)""",
                (staff_id, category, rating),
            )
        else:
            c.execute(
                f"""UPDATE staff_stats
                    SET total_jobs = total_jobs + 1,
                        sum_ratings = sum_ratings + ?,
                        {star_column} = {star_column} + 1
                    WHERE staff_id = ? AND category = ?""",
                (rating, staff_id, category),
            )
        conn.commit()

        c.execute("SELECT * FROM staff_stats WHERE staff_id = ? AND category = ?", (staff_id, category))
        result = dict(c.fetchone())
        conn.close()
        return result


# ============================================================
# BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ============================================================
# EVENTS COG - welcome/goodbye, raid protection, automod.
# ============================================================

class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.join_tracker: dict[int, list[float]] = defaultdict(list)
        self.mention_tracker: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))
        self.invite_msg_tracker: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))

    async def log_action(self, guild: discord.Guild, title: str, description: str, color: int = config.BRAND_COLOR, fields: list[tuple[str, str]] | None = None):
        channel = guild.get_channel(config.MOD_LOG_CHANNEL) or self.bot.get_channel(config.MOD_LOG_CHANNEL)
        if not channel:
            return
        embed = discord.Embed(title=title, description=description, color=color, timestamp=db.now())
        for name, value in (fields or []):
            embed.add_field(name=name, value=value, inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user} has connected to Discord!")
        await self.bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="P Code Studio")
        )
        try:
            synced = await self.bot.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Command sync failed: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        current_time = time.time()
        guild_id = member.guild.id

        self.join_tracker[guild_id].append(current_time)
        self.join_tracker[guild_id] = [
            t for t in self.join_tracker[guild_id] if current_time - t < config.RAID_TIME_WINDOW
        ]

        if len(self.join_tracker[guild_id]) >= config.RAID_THRESHOLD:
            await self.handle_raid(member.guild, member)
            return

        channel = self.bot.get_channel(config.WELCOME_CHANNEL)
        if channel:
            embed = discord.Embed(
                title=f"\U0001F680 Welcome to {config.BRAND_NAME}!",
                description="We're excited to have you join our growing community of developers, designers, creators, and innovators.",
                color=config.BRAND_COLOR,
            )
            embed.add_field(
                name="We Specialize In:",
                value="\U0001F916 Discord Bot Development\n\U0001F3AE Roblox Development\n\U0001F3A8 Graphic & UI Design\n\U0001F6E0\uFE0F Discord Server Design\n\U0001F4A1 Custom Solutions",
                inline=False,
            )
            embed.add_field(
                name="Check Out:",
                value="\U0001F4CC #rules\n\U0001F4CC #services\n\U0001F4CC #pricing\n\U0001F4CC #portfolio\n\U0001F4CC #meet-the-team",
                inline=False,
            )
            embed.set_footer(text=f"\u2728 Code. Design. Create. | {config.BRAND_NAME}")
            try:
                await channel.send(f"\U0001F680 Welcome to {config.BRAND_NAME}, {member.mention}!", embed=embed)
            except discord.HTTPException:
                pass

        db.ensure_economy_account(str(member.id))

    async def handle_raid(self, guild: discord.Guild, member: discord.Member):
        embed = discord.Embed(
            title="\U0001F6A8 RAID DETECTED",
            description="Multiple accounts joining rapidly detected!",
            color=config.DANGER_COLOR,
        )
        embed.add_field(name="Latest Joiner", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Account Age", value=f"Created <t:{int(member.created_at.timestamp())}:R>", inline=False)

        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO raid_logs (user_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
            (str(member.id), "RAID_DETECTED", "Raid event triggered", db.now()),
        )

        if config.BAN_ON_RAID:
            try:
                await member.ban(reason="Raid protection - automatic ban")
                embed.add_field(name="Action Taken", value="\u2705 User automatically banned", inline=False)
                c.execute(
                    "INSERT INTO raid_logs (user_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
                    (str(member.id), "AUTO_BAN", "Raid detection auto-ban", db.now()),
                )
            except discord.HTTPException:
                embed.add_field(name="Action Taken", value="\u26A0\uFE0F Could not ban user", inline=False)

        conn.commit()
        conn.close()

        embed.set_footer(text=f"Guild: {guild.name}")
        mod_log = self.bot.get_channel(config.MOD_LOG_CHANNEL)
        if mod_log:
            await mod_log.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = self.bot.get_channel(config.WELCOME_CHANNEL)
        if not channel:
            return
        embed = discord.Embed(
            title="\U0001F4E4 Farewell",
            description=f"{member.name} has left {config.BRAND_NAME}.",
            color=config.BRAND_COLOR,
        )
        embed.set_footer(text="\u2728 Code. Design. Create.")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        now = time.time()

        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count >= config.MENTION_SPAM_THRESHOLD:
            self.mention_tracker[message.author.id].append(now)
            recent = [t for t in self.mention_tracker[message.author.id] if now - t < config.MENTION_SPAM_WINDOW]
            self.mention_tracker[message.author.id] = deque(recent, maxlen=10)

            try:
                await message.delete()
            except discord.HTTPException:
                pass

            await self.log_action(
                message.guild,
                "\U0001F6A8 Mention Spam Detected",
                f"{message.author.mention} mentioned {mention_count} users/roles in a single message.",
                color=config.DANGER_COLOR,
                fields=[("Channel", message.channel.mention)],
            )

            if len(recent) >= 3:
                try:
                    await message.guild.timeout(message.author, discord.utils.utcnow() + timedelta(minutes=10), reason="Repeated mention spam")
                    await self.log_action(
                        message.guild,
                        "\u23F1\uFE0F Auto-Timeout",
                        f"{message.author.mention} was timed out for 10 minutes due to repeated mention spam.",
                        color=config.WARN_COLOR,
                    )
                except discord.HTTPException:
                    pass

        if "discord.gg/" in message.content or "discord.com/invite/" in message.content:
            self.invite_msg_tracker[message.author.id].append(now)
            recent_invites = [t for t in self.invite_msg_tracker[message.author.id] if now - t < config.INVITE_SPAM_WINDOW]
            self.invite_msg_tracker[message.author.id] = deque(recent_invites, maxlen=10)

            if len(recent_invites) >= config.INVITE_SPAM_THRESHOLD:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
                await self.log_action(
                    message.guild,
                    "\U0001F6A8 Invite Spam Detected",
                    f"{message.author.mention} posted {len(recent_invites)} invite links within {config.INVITE_SPAM_WINDOW}s.",
                    color=config.DANGER_COLOR,
                    fields=[("Channel", message.channel.mention)],
                )


# ============================================================
# TICKETS COG - open/claim/unclaim/close + /tickets group.
# ============================================================

def service_label(service_key: str) -> str:
    for value, label in config.TICKET_SERVICE_OPTIONS:
        if value == service_key:
            return label
    return config.SERVICE_CATEGORIES.get(service_key, service_key.title())


class CloseTicketModal(discord.ui.Modal):
    def __init__(self, tickets_cog: "Tickets", ticket_id: int):
        super().__init__(title="Close Support Ticket")
        self.tickets_cog = tickets_cog
        self.ticket_id = ticket_id

        self.reason = discord.ui.TextInput(
            label="Close Reason",
            placeholder="Why are you closing this ticket?",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason.value or "No reason provided"
        await self.tickets_cog.close_ticket(interaction, self.ticket_id, reason)


class TicketButtonView(discord.ui.View):
    def __init__(self, tickets_cog: "Tickets", ticket_id: int):
        super().__init__(timeout=None)
        self.tickets_cog = tickets_cog
        self.ticket_id = ticket_id
        self.claim_ticket.custom_id = f"ticket_claim_{ticket_id}"
        self.unclaim_ticket.custom_id = f"ticket_unclaim_{ticket_id}"
        self.close_ticket.custom_id = f"ticket_close_{ticket_id}"
        self.notify_staff.custom_id = f"ticket_notify_{ticket_id}"

    def _has_staff_role(self, interaction: discord.Interaction) -> bool:
        role_ids = [role.id for role in interaction.user.roles]
        return any(r in role_ids for r in config.STAFF_MANAGE_ROLES)

    def _can_close(self, interaction: discord.Interaction, ticket: dict) -> bool:
        if self._has_staff_role(interaction):
            return True
        return bool(ticket and ticket.get("claimed_by") == str(interaction.user.id))

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, emoji="\U0001F44B")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._has_staff_role(interaction):
            await interaction.response.send_message("\u274C No permission", ephemeral=True)
            return
        await self.tickets_cog.claim(interaction, self.ticket_id)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, emoji="\U0001F504")
    async def unclaim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._has_staff_role(interaction):
            await interaction.response.send_message("\u274C No permission", ephemeral=True)
            return
        await self.tickets_cog.unclaim(interaction, self.ticket_id)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, emoji="\U0001F512")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = self.tickets_cog.get_ticket(self.ticket_id)
        if not self._can_close(interaction, ticket):
            await interaction.response.send_message(
                "\u274C Only the staff member who claimed this ticket, or Development Team and above, can close it.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(CloseTicketModal(self.tickets_cog, self.ticket_id))

    @discord.ui.button(label="Notify Staff", style=discord.ButtonStyle.primary, emoji="\U0001F514", row=1)
    async def notify_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.tickets_cog.notify_staff(interaction, self.ticket_id)


class Tickets(commands.Cog):
    tickets_group = app_commands.Group(name="tickets", description="Manage support tickets")

    NOTIFY_COOLDOWN_SECONDS = 300

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_notify: dict[int, float] = {}

    async def log_mod_action(self, guild: discord.Guild, title: str, description: str, color: int = config.BRAND_COLOR):
        channel = guild.get_channel(config.MOD_LOG_CHANNEL) or self.bot.get_channel(config.MOD_LOG_CHANNEL)
        if channel:
            embed = discord.Embed(title=title, description=description, color=color, timestamp=db.now())
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    def get_ticket(self, ticket_id: int):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_ticket_by_channel(self, channel_id: int):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM support_tickets WHERE channel_id = ?", (str(channel_id),))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    async def open_ticket(self, interaction: discord.Interaction, service: str):
        guild = interaction.guild
        user = interaction.user

        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id FROM support_tickets WHERE user_id = ? AND service = ? AND status = 'open'",
            (str(user.id), service),
        )
        if c.fetchone():
            conn.close()
            await interaction.response.send_message(
                "\u26A0\uFE0F You already have an open ticket for this service.", ephemeral=True
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        visible_role_ids = set(config.SERVICE_ROLES.get(service, config.LEADERSHIP_ROLES))
        visible_role_ids.update(config.ROLES_ABOVE_DEVELOPMENT)
        for role_id in visible_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        support_category = None
        support_channel_ref = guild.get_channel(config.SUPPORT_CHANNEL)
        if isinstance(support_channel_ref, discord.CategoryChannel):
            support_category = support_channel_ref
        elif support_channel_ref is not None:
            support_category = support_channel_ref.category

        safe_name = "".join(ch for ch in user.name.lower() if ch.isalnum()) or "user"
        channel = await guild.create_text_channel(
            name=f"ticket-{safe_name}",
            category=support_category,
            overwrites=overwrites,
            reason=f"Support ticket opened by {user}",
        )

        c.execute(
            """INSERT INTO support_tickets
               (user_id, claimed_by, service, channel_id, status, created_at, helpers, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(user.id), None, service, str(channel.id), "open", db.now(), json.dumps([]), "normal"),
        )
        ticket_id = c.lastrowid
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title=f"\U0001F3AB {service_label(service)} Ticket",
            description=(
                f"Hey {user.mention}! Thanks for reaching out to **{config.BRAND_NAME}**.\n"
                "A team member will be with you shortly. Please describe what you need help with."
            ),
            color=config.BRAND_COLOR,
        )
        embed.add_field(name="Ticket ID", value=f"#{ticket_id}", inline=True)
        embed.add_field(name="Service", value=service_label(service), inline=True)
        embed.add_field(name="Priority", value="Normal", inline=True)
        embed.add_field(
            name="Need attention?",
            value="Press \U0001F514 **Notify Staff** below if nobody has responded yet.",
            inline=False,
        )
        embed.set_footer(text=f"{config.BRAND_NAME} Support")

        view = TicketButtonView(self, ticket_id)
        self.bot.add_view(view)
        msg = await channel.send(content=f"{user.mention}", embed=embed, view=view)

        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO ticket_messages (ticket_id, message_id, channel_id) VALUES (?, ?, ?)",
            (ticket_id, str(msg.id), str(channel.id)),
        )
        conn.commit()
        conn.close()

        await self.log_mod_action(
            guild,
            "\U0001F3AB Ticket Opened",
            f"**User:** {user.mention}\n**Service:** {service_label(service)}\n**Channel:** {channel.mention}\n**Ticket ID:** #{ticket_id}",
        )

        await interaction.response.send_message(f"\u2705 Your ticket has been created: {channel.mention}", ephemeral=True)

    async def claim(self, interaction: discord.Interaction, ticket_id: int):
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            await interaction.response.send_message("\u274C Ticket not found.", ephemeral=True)
            return
        if ticket["claimed_by"]:
            await interaction.response.send_message("\u274C Already claimed!", ephemeral=True)
            return

        conn = db.get_conn()
        c = conn.cursor()
        c.execute("UPDATE support_tickets SET claimed_by = ? WHERE id = ?", (str(interaction.user.id), ticket_id))
        conn.commit()
        conn.close()

        embed = discord.Embed(title="\u2705 Claimed", description=f"By {interaction.user.mention}", color=config.SUCCESS_COLOR)
        await interaction.response.send_message(embed=embed)
        await self.log_mod_action(interaction.guild, "\U0001F4CC Ticket Claimed", f"Ticket #{ticket_id} claimed by {interaction.user.mention}")

    async def notify_staff(self, interaction: discord.Interaction, ticket_id: int):
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            await interaction.response.send_message("\u274C Ticket not found.", ephemeral=True)
            return

        now = time.monotonic()
        last = self._last_notify.get(ticket_id)
        if last and now - last < self.NOTIFY_COOLDOWN_SECONDS:
            remaining = int(self.NOTIFY_COOLDOWN_SECONDS - (now - last))
            await interaction.response.send_message(
                f"\u23F3 Staff was already notified recently. Please wait {remaining}s before notifying again.",
                ephemeral=True,
            )
            return
        self._last_notify[ticket_id] = now

        role_ids = set(config.SERVICE_ROLES.get(ticket["service"], config.LEADERSHIP_ROLES))
        role_ids.update(config.ROLES_ABOVE_DEVELOPMENT)
        mentions = []
        for role_id in role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                mentions.append(role.mention)

        if not mentions:
            await interaction.response.send_message("\u26A0\uFE0F No support roles configured for this ticket.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"\U0001F514 {' '.join(mentions)} \u2014 {interaction.user.mention} needs assistance on ticket #{ticket_id}!",
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        await self.log_mod_action(
            interaction.guild,
            "\U0001F514 Staff Notified",
            f"Ticket #{ticket_id} — {interaction.user.mention} pinged staff for this ticket.",
        )

    async def unclaim(self, interaction: discord.Interaction, ticket_id: int):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("UPDATE support_tickets SET claimed_by = NULL WHERE id = ?", (ticket_id,))
        conn.commit()
        conn.close()

        embed = discord.Embed(title="\U0001F504 Unclaimed", color=config.WARN_COLOR)
        await interaction.response.send_message(embed=embed)
        await self.log_mod_action(interaction.guild, "\U0001F4CC Ticket Unclaimed", f"Ticket #{ticket_id} unclaimed by {interaction.user.mention}")

    async def close_ticket(self, interaction: discord.Interaction, ticket_id: int, reason: str):
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            await interaction.response.send_message("\u274C Ticket not found.", ephemeral=True)
            return

        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE support_tickets SET status = ?, closed_at = ?, close_reason = ?, closed_by = ? WHERE id = ?",
            ("closed", db.now(), reason, str(interaction.user.id), ticket_id),
        )
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="\U0001F512 Ticket Closed",
            description=f"**Closed By:** {interaction.user.mention}\n**Reason:** {reason}",
            color=config.DANGER_COLOR,
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("\u2705 Ticket closed!", ephemeral=True)

        await self.log_mod_action(interaction.guild, "\U0001F512 Ticket Closed", f"Ticket #{ticket_id} closed by {interaction.user.mention}\n**Reason:** {reason}", color=config.DANGER_COLOR)

        survey_cog = self.bot.get_cog("Survey")
        if survey_cog:
            await survey_cog.send_close_dm(interaction.guild, ticket)

        try:
            await interaction.channel.edit(name=f"closed-{interaction.channel.name.replace('ticket-', '')}")
            for target, overwrite in list(interaction.channel.overwrites.items()):
                if isinstance(target, discord.Member) and target.id == int(ticket["user_id"]):
                    await interaction.channel.set_permissions(target, view_channel=True, send_messages=False)
        except discord.HTTPException:
            pass

    def _staff_check(self, interaction: discord.Interaction) -> bool:
        role_ids = [role.id for role in interaction.user.roles]
        return any(r in role_ids for r in config.STAFF_MANAGE_ROLES)

    @tickets_group.command(name="add-helper", description="Add a helper to this ticket")
    @app_commands.describe(member="The staff member to add as a helper")
    async def add_helper(self, interaction: discord.Interaction, member: discord.Member):
        ticket = self.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("\u274C This is not a ticket channel.", ephemeral=True)
            return
        if not self._staff_check(interaction):
            await interaction.response.send_message("\u274C No permission.", ephemeral=True)
            return

        helpers = json.loads(ticket["helpers"] or "[]")
        if str(member.id) in helpers:
            await interaction.response.send_message("\u26A0\uFE0F Already a helper on this ticket.", ephemeral=True)
            return
        helpers.append(str(member.id))

        conn = db.get_conn()
        c = conn.cursor()
        c.execute("UPDATE support_tickets SET helpers = ? WHERE id = ?", (json.dumps(helpers), ticket["id"]))
        conn.commit()
        conn.close()

        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"\u2705 {member.mention} added as a helper.")
        await self.log_mod_action(interaction.guild, "\u2795 Helper Added", f"Ticket #{ticket['id']}: {member.mention} added by {interaction.user.mention}")

    @tickets_group.command(name="remove-helper", description="Remove a helper from this ticket")
    @app_commands.describe(member="The staff member to remove as a helper")
    async def remove_helper(self, interaction: discord.Interaction, member: discord.Member):
        ticket = self.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("\u274C This is not a ticket channel.", ephemeral=True)
            return
        if not self._staff_check(interaction):
            await interaction.response.send_message("\u274C No permission.", ephemeral=True)
            return

        helpers = json.loads(ticket["helpers"] or "[]")
        if str(member.id) not in helpers:
            await interaction.response.send_message("\u26A0\uFE0F That member is not a helper on this ticket.", ephemeral=True)
            return
        helpers.remove(str(member.id))

        conn = db.get_conn()
        c = conn.cursor()
        c.execute("UPDATE support_tickets SET helpers = ? WHERE id = ?", (json.dumps(helpers), ticket["id"]))
        conn.commit()
        conn.close()

        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"\u2705 {member.mention} removed as a helper.")
        await self.log_mod_action(interaction.guild, "\u2796 Helper Removed", f"Ticket #{ticket['id']}: {member.mention} removed by {interaction.user.mention}")

    @tickets_group.command(name="priority", description="Change this ticket's priority")
    @app_commands.describe(level="New priority level")
    @app_commands.choices(level=[
        app_commands.Choice(name="Low", value="low"),
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="High", value="high"),
        app_commands.Choice(name="Urgent", value="urgent"),
    ])
    async def priority(self, interaction: discord.Interaction, level: app_commands.Choice[str]):
        ticket = self.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("\u274C This is not a ticket channel.", ephemeral=True)
            return
        if not self._staff_check(interaction):
            await interaction.response.send_message("\u274C No permission.", ephemeral=True)
            return

        conn = db.get_conn()
        c = conn.cursor()
        c.execute("UPDATE support_tickets SET priority = ? WHERE id = ?", (level.value, ticket["id"]))
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"\u2705 Priority set to **{level.name}**.")
        await self.log_mod_action(interaction.guild, "\u26A1 Priority Changed", f"Ticket #{ticket['id']} priority set to {level.name} by {interaction.user.mention}")

    @tickets_group.command(name="category", description="Change this ticket's service category")
    @app_commands.describe(service="New service category")
    @app_commands.choices(service=[
        app_commands.Choice(name=label, value=value) for value, label in config.TICKET_SERVICE_OPTIONS
    ])
    async def category(self, interaction: discord.Interaction, service: app_commands.Choice[str]):
        ticket = self.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("\u274C This is not a ticket channel.", ephemeral=True)
            return
        if not self._staff_check(interaction):
            await interaction.response.send_message("\u274C No permission.", ephemeral=True)
            return

        conn = db.get_conn()
        c = conn.cursor()
        c.execute("UPDATE support_tickets SET service = ? WHERE id = ?", (service.value, ticket["id"]))
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"\u2705 Category changed to **{service.name}**.")
        await self.log_mod_action(interaction.guild, "\U0001F4C2 Category Changed", f"Ticket #{ticket['id']} category set to {service.name} by {interaction.user.mention}")

    @tickets_group.command(name="edit-embed", description="Edit the ticket's creation embed description")
    @app_commands.describe(description="New description for the ticket embed")
    async def edit_embed(self, interaction: discord.Interaction, description: str):
        ticket = self.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("\u274C This is not a ticket channel.", ephemeral=True)
            return
        if not self._staff_check(interaction):
            await interaction.response.send_message("\u274C No permission.", ephemeral=True)
            return

        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT message_id FROM ticket_messages WHERE ticket_id = ? ORDER BY id DESC LIMIT 1", (ticket["id"],))
        row = c.fetchone()
        conn.close()

        if not row:
            await interaction.response.send_message("\u274C Could not find the ticket message.", ephemeral=True)
            return

        try:
            msg = await interaction.channel.fetch_message(int(row["message_id"]))
            embed = msg.embeds[0]
            embed.description = description
            await msg.edit(embed=embed)
            await interaction.response.send_message("\u2705 Ticket embed updated.")
            await self.log_mod_action(interaction.guild, "\u270F\uFE0F Ticket Embed Edited", f"Ticket #{ticket['id']} embed edited by {interaction.user.mention}")
        except (discord.HTTPException, IndexError):
            await interaction.response.send_message("\u274C Failed to edit the ticket embed.", ephemeral=True)

    @tickets_group.command(name="info", description="View information about this ticket")
    async def info(self, interaction: discord.Interaction):
        ticket = self.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("\u274C This is not a ticket channel.", ephemeral=True)
            return

        helpers = json.loads(ticket["helpers"] or "[]")
        helpers_text = ", ".join(f"<@{h}>" for h in helpers) if helpers else "None"

        embed = discord.Embed(title=f"\U0001F3AB Ticket #{ticket['id']}", color=config.BRAND_COLOR)
        embed.add_field(name="Opened By", value=f"<@{ticket['user_id']}>", inline=True)
        embed.add_field(name="Service", value=service_label(ticket["service"]), inline=True)
        embed.add_field(name="Status", value=ticket["status"].title(), inline=True)
        embed.add_field(name="Priority", value=(ticket["priority"] or "normal").title(), inline=True)
        embed.add_field(name="Claimed By", value=(f"<@{ticket['claimed_by']}>" if ticket["claimed_by"] else "Unclaimed"), inline=True)
        embed.add_field(name="Helpers", value=helpers_text, inline=False)
        embed.add_field(name="Created At", value=str(ticket["created_at"]), inline=False)

        await interaction.response.send_message(embed=embed)


# ============================================================
# ASSISTANCE COG - /assistancepanel service select menu.
# ============================================================

class AssistancePanelView(discord.ui.View):
    """Persistent view holding the service select menu."""

    def __init__(self, tickets_cog):
        super().__init__(timeout=None)
        self.add_item(ServiceSelect(tickets_cog))


class ServiceSelect(discord.ui.Select):
    def __init__(self, tickets_cog):
        self.tickets_cog = tickets_cog
        options = [
            discord.SelectOption(label=label, value=value)
            for value, label in config.TICKET_SERVICE_OPTIONS
        ]
        super().__init__(
            placeholder="Select a service...",
            options=options,
            custom_id="assistance_panel_service_select",
        )

    async def callback(self, interaction: discord.Interaction):
        service = self.values[0]
        await self.tickets_cog.open_ticket(interaction, service)


class Assistance(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        tickets_cog = self.bot.get_cog("Tickets")
        if tickets_cog:
            self.bot.add_view(AssistancePanelView(tickets_cog))

    @app_commands.command(name="assistancepanel", description="Post the P Code Studio assistance/support panel")
    @app_commands.checks.has_any_role(*config.STAFF_MANAGE_ROLES)
    async def assistancepanel(self, interaction: discord.Interaction):
        tickets_cog = self.bot.get_cog("Tickets")
        if not tickets_cog:
            await interaction.response.send_message("Ticket system is not loaded.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"\U0001F6A8 {config.BRAND_NAME} - Support",
            description=(
                "Need help with a bot, a Roblox project, design work, or anything else?\n"
                "Select the service that best matches your request below and a private "
                "ticket will be opened for you."
            ),
            color=config.BRAND_COLOR,
        )
        embed.add_field(
            name="How it works",
            value=(
                "1\uFE0F\u20E3 Pick a service from the dropdown\n"
                "2\uFE0F\u20E3 A private channel is created just for you\n"
                "3\uFE0F\u20E3 Our team will assist you as soon as possible"
            ),
            inline=False,
        )
        embed.set_footer(text=f"\u2728 {config.BRAND_NAME} \u2022 Code. Design. Create.")

        if os.path.exists(config.BANNER_IMAGE_PATH):
            file = discord.File(config.BANNER_IMAGE_PATH, filename="assistance_banner.png")
            embed.set_image(url="attachment://assistance_banner.png")
            await interaction.channel.send(embed=embed, file=file, view=AssistancePanelView(tickets_cog))
        else:
            await interaction.channel.send(embed=embed, view=AssistancePanelView(tickets_cog))

        await interaction.response.send_message("\u2705 Assistance panel posted!", ephemeral=True)


# ============================================================
# SURVEY COG - post-close DM survey + staff ratings.
# ============================================================

def star_row(prefix: str):
    return [discord.ui.Button(label=f"{i} \u2B50", style=discord.ButtonStyle.secondary, custom_id=f"{prefix}_{i}") for i in range(1, 6)]


class StartSurveyView(discord.ui.View):
    def __init__(self, survey_cog: "Survey", ticket_id: int):
        super().__init__(timeout=None)
        self.survey_cog = survey_cog
        self.ticket_id = ticket_id
        self.start_survey.custom_id = f"start_survey_{ticket_id}"

    @discord.ui.button(label="Start Survey", style=discord.ButtonStyle.primary, emoji="\u2B50")
    async def start_survey(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.survey_cog.begin_survey(interaction, self.ticket_id)


class StarRatingView(discord.ui.View):
    """Generic reusable 1-5 star rating view that calls back on_pick(interaction, value)."""

    def __init__(self, on_pick, id_prefix: str, timeout: float = 300):
        super().__init__(timeout=timeout)
        for i in range(1, 6):
            button = discord.ui.Button(label=f"{i} \u2B50", style=discord.ButtonStyle.secondary, custom_id=f"{id_prefix}_{i}")

            async def _callback(interaction: discord.Interaction, value=i):
                await on_pick(interaction, value)

            button.callback = _callback
            self.add_item(button)


class ExpectationsView(discord.ui.View):
    def __init__(self, on_pick, timeout: float = 300):
        super().__init__(timeout=timeout)
        for label, value in [("Yes", "yes"), ("Somewhat", "somewhat"), ("No", "no")]:
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)

            async def _callback(interaction: discord.Interaction, value=value):
                await on_pick(interaction, value)

            button.callback = _callback
            self.add_item(button)


class WrittenFeedbackModal(discord.ui.Modal, title="A couple more questions"):
    liked_most = discord.ui.TextInput(
        label="What did you like most about your experience?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )
    suggestions = discord.ui.TextInput(
        label="Any suggestions or feedback to improve?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(self, survey_cog: "Survey", state: dict):
        super().__init__()
        self.survey_cog = survey_cog
        self.state = state

    async def on_submit(self, interaction: discord.Interaction):
        self.state["liked_most"] = self.liked_most.value or ""
        self.state["suggestions"] = self.suggestions.value or ""
        await self.survey_cog.finish_survey(interaction, self.state)


class Survey(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_close_dm(self, guild: discord.Guild, ticket: dict):
        user = guild.get_member(int(ticket["user_id"])) or self.bot.get_user(int(ticket["user_id"]))
        if not user:
            try:
                user = await self.bot.fetch_user(int(ticket["user_id"]))
            except discord.HTTPException:
                return

        closer_id = ticket.get("closed_by")
        closer_mention = f"<@{closer_id}>" if closer_id else "our team"

        embed = discord.Embed(
            title="\U0001F4EE Your Ticket Has Been Closed",
            description=(
                f"\U0001F499 Thank you for reaching out to **{config.BRAND_NAME}**!\n\n"
                "Your support ticket has been resolved and closed."
            ),
            color=config.BRAND_COLOR,
        )
        embed.add_field(name="\U0001F3F7\uFE0F Closed By", value=closer_mention, inline=False)
        embed.add_field(name="\U0001F4CB Reason", value=ticket.get("close_reason") or "No reason provided", inline=False)
        embed.add_field(
            name="\u2B50 We'd love your feedback!",
            value=(
                "Your honest rating helps us improve our support team and ensure we're "
                "providing the best possible experience for everyone in our community. "
                "It only takes a minute and means a lot to us!"
            ),
            inline=False,
        )
        embed.set_footer(text=f"{config.BRAND_NAME}")

        try:
            await user.send(embed=embed, view=StartSurveyView(self, ticket["id"]))
        except discord.HTTPException:
            pass

    async def begin_survey(self, interaction: discord.Interaction, ticket_id: int):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM surveys WHERE ticket_id = ?", (ticket_id,))
        if c.fetchone():
            conn.close()
            await interaction.response.send_message("\u2705 You've already completed the survey for this ticket. Thank you!", ephemeral=True)
            return
        conn.close()

        state = {"ticket_id": ticket_id, "user_id": str(interaction.user.id)}

        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"\u2B50 {config.BRAND_NAME} Order Feedback Survey",
                description="**1. Overall, how satisfied were you with your order?**",
                color=config.BRAND_COLOR,
            ),
            view=StarRatingView(lambda i, v: self._on_overall_rating(i, v, state), "overall"),
            ephemeral=True,
        )

    async def _on_overall_rating(self, interaction: discord.Interaction, value: int, state: dict):
        state["overall_rating"] = value
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"\u2B50 {config.BRAND_NAME} Order Feedback Survey",
                description="**2. How would you rate our communication throughout the process?**",
                color=config.BRAND_COLOR,
            ),
            view=StarRatingView(lambda i, v: self._on_comm_rating(i, v, state), "comm"),
        )

    async def _on_comm_rating(self, interaction: discord.Interaction, value: int, state: dict):
        state["communication_rating"] = value
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"\u2B50 {config.BRAND_NAME} Order Feedback Survey",
                description="**3. Did your order meet your expectations?**",
                color=config.BRAND_COLOR,
            ),
            view=ExpectationsView(lambda i, v: self._on_expectations(i, v, state)),
        )

    async def _on_expectations(self, interaction: discord.Interaction, value: str, state: dict):
        state["expectations"] = value
        await interaction.response.send_modal(WrittenFeedbackModal(self, state))

    async def finish_survey(self, interaction: discord.Interaction, state: dict):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO surveys
               (ticket_id, user_id, overall_rating, communication_rating, expectations, liked_most, suggestions, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                state["ticket_id"], state["user_id"], state["overall_rating"], state["communication_rating"],
                state["expectations"], state["liked_most"], state["suggestions"], db.now(),
            ),
        )
        c.execute("SELECT * FROM support_tickets WHERE id = ?", (state["ticket_id"],))
        ticket = dict(c.fetchone())
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            "\u2705 Thanks for the feedback! One last step - please rate the staff who helped you.", ephemeral=True
        )

        staff_ids = []
        if ticket["claimed_by"]:
            staff_ids.append(ticket["claimed_by"])
        for helper_id in json.loads(ticket["helpers"] or "[]"):
            if helper_id not in staff_ids:
                staff_ids.append(helper_id)

        if not staff_ids:
            return

        await self._rate_next_staff(interaction, ticket, staff_ids, 0)

    async def _rate_next_staff(self, interaction: discord.Interaction, ticket: dict, staff_ids: list[str], index: int):
        if index >= len(staff_ids):
            return

        staff_id = staff_ids[index]

        async def on_pick(inner_interaction: discord.Interaction, value: int):
            category = config.SERVICE_CATEGORIES.get(ticket["service"], "Other")
            stats = db.record_staff_rating(staff_id, category, value, ticket["id"])
            await self._post_stats_update(staff_id, category, stats)
            await inner_interaction.response.edit_message(
                embed=discord.Embed(description=f"\u2705 Thanks for rating <@{staff_id}>!", color=config.SUCCESS_COLOR),
                view=None,
            )
            await self._rate_next_staff(inner_interaction, ticket, staff_ids, index + 1)

        try:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="\u2B50 Rate Your Support",
                    description=f"Rate <@{staff_id}> on a scale of 1\u20135 stars.",
                    color=config.BRAND_COLOR,
                ),
                view=StarRatingView(on_pick, f"staff_{staff_id}"),
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

    async def _post_stats_update(self, staff_id: str, category: str, stats: dict):
        channel = self.bot.get_channel(config.TEAM_STATS_CHANNEL)
        if not channel:
            return

        total = stats["total_jobs"]
        avg = stats["sum_ratings"] / total if total else 0

        embed = discord.Embed(title="\U0001F4CA Staff Statistics Update", color=config.BRAND_COLOR)
        embed.add_field(name="Staff Member", value=f"<@{staff_id}>", inline=True)
        embed.add_field(name="Category", value=category, inline=True)
        embed.add_field(name="Average Rating", value=f"{avg:.2f} \u2B50 ({total} job{'s' if total != 1 else ''})", inline=True)
        embed.add_field(
            name="Rating Breakdown",
            value=(
                f"5\u2B50: {stats['five_star']}  |  4\u2B50: {stats['four_star']}  |  "
                f"3\u2B50: {stats['three_star']}  |  2\u2B50: {stats['two_star']}  |  1\u2B50: {stats['one_star']}"
            ),
            inline=False,
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass


# ============================================================
# BOT MANAGEMENT COG - /bot-add /bot-status (Developer only).
# ============================================================

STATUS_CHOICES = [
    app_commands.Choice(name="Bot Online", value="online"),
    app_commands.Choice(name="Bot Offline", value="offline"),
    app_commands.Choice(name="Bot Deleted", value="deleted"),
    app_commands.Choice(name="Monthly Payment Needed", value="payment_needed"),
]

STATUS_COLORS = {
    "online": config.SUCCESS_COLOR,
    "offline": config.DANGER_COLOR,
    "deleted": config.DANGER_COLOR,
    "payment_needed": config.WARN_COLOR,
}

STATUS_LABELS = {
    "online": "\U0001F7E2 Online",
    "offline": "\U0001F534 Offline",
    "deleted": "\U0001F5D1\uFE0F Deleted",
    "payment_needed": "\U0001F4B0 Monthly Payment Needed",
}


class BotManagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_developer(self, interaction: discord.Interaction) -> bool:
        role_ids = [role.id for role in interaction.user.roles]
        return config.DEVELOPER_ROLE in role_ids

    @app_commands.command(name="bot-add", description="Register a bot purchased from P Code Studio")
    @app_commands.describe(
        customer="The customer who purchased this bot",
        bot_name="The name of the bot",
        bot_id="The bot's Discord application/user ID",
        github_repo="Link to the bot's GitHub repository",
        render_service="Name/link of the Render (or other host) service",
        purchase_date="Purchase date (e.g. 2026-07-04)",
        renewal_date="Monthly renewal date (e.g. 2026-08-04)",
    )
    async def register_bot(
        self,
        interaction: discord.Interaction,
        customer: discord.Member,
        bot_name: str,
        bot_id: str,
        github_repo: str,
        render_service: str,
        purchase_date: str,
        renewal_date: str,
    ):
        if not self._is_developer(interaction):
            await interaction.response.send_message("\u274C Only Developers can register bots.", ephemeral=True)
            return

        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO bot_hosting
               (customer_id, bot_name, bot_id, github_repo, render_service, purchase_date,
                renewal_date, status, created_at, registered_by, last_notified_sha)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(customer.id), bot_name, bot_id, github_repo, render_service, purchase_date,
                renewal_date, "online", db.now(), str(interaction.user.id), None,
            ),
        )
        record_id = c.lastrowid
        conn.commit()
        conn.close()

        embed = discord.Embed(title="\U0001F916 Bot Registered", color=config.SUCCESS_COLOR)
        embed.add_field(name="Customer", value=customer.mention, inline=True)
        embed.add_field(name="Bot Name", value=bot_name, inline=True)
        embed.add_field(name="Bot ID", value=bot_id, inline=True)
        embed.add_field(name="GitHub Repo", value=github_repo, inline=False)
        embed.add_field(name="Render Service", value=render_service, inline=True)
        embed.add_field(name="Purchase Date", value=purchase_date, inline=True)
        embed.add_field(name="Renewal Date", value=renewal_date, inline=True)
        embed.set_footer(text=f"Registered by {interaction.user} \u2022 Record #{record_id}")

        await interaction.response.send_message(embed=embed)

        log_channel = self.bot.get_channel(config.BOT_LOG_CHANNEL)
        if log_channel:
            await log_channel.send(embed=embed)

    @app_commands.command(name="bot-status", description="Update the status of a registered bot")
    @app_commands.describe(bot_name="The registered bot's name", status="New status")
    @app_commands.choices(status=STATUS_CHOICES)
    async def update_bot_status(self, interaction: discord.Interaction, bot_name: str, status: app_commands.Choice[str]):
        if not self._is_developer(interaction):
            await interaction.response.send_message("\u274C Only Developers can update bot status.", ephemeral=True)
            return

        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM bot_hosting WHERE bot_name = ? ORDER BY id DESC LIMIT 1", (bot_name,))
        row = c.fetchone()
        if not row:
            conn.close()
            await interaction.response.send_message(f"\u274C No registered bot found named `{bot_name}`.", ephemeral=True)
            return

        c.execute("UPDATE bot_hosting SET status = ? WHERE id = ?", (status.value, row["id"]))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="\U0001F504 Bot Status Updated",
            description=f"**{bot_name}** is now **{STATUS_LABELS[status.value]}**",
            color=STATUS_COLORS[status.value],
        )
        embed.add_field(name="Customer", value=f"<@{row['customer_id']}>", inline=True)
        embed.add_field(name="Updated By", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

        log_channel = self.bot.get_channel(config.BOT_LOG_CHANNEL)
        if log_channel:
            await log_channel.send(embed=embed)


# ============================================================
# GITHUB FEED COG - polls registered repos for activity.
# ============================================================

GITHUB_API = "https://api.github.com"


def parse_repo(url_or_slug: str) -> str | None:
    """Extract 'owner/repo' from a GitHub URL or already-formed slug."""
    url_or_slug = url_or_slug.strip()
    match = re.search(r"github\.com/([^/]+)/([^/\s]+)", url_or_slug)
    if match:
        owner, repo = match.group(1), match.group(2)
        return f"{owner}/{repo.removesuffix('.git')}"
    if re.match(r"^[\w.-]+/[\w.-]+$", url_or_slug):
        return url_or_slug
    return None


class GithubFeed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None
        self.last_seen_commit: dict[str, str] = {}
        self.last_seen_release: dict[str, str] = {}
        self.last_seen_pr: dict[str, int] = {}
        self.poll_github.start()

    def cog_unload(self):
        self.poll_github.cancel()

    def _headers(self):
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _registered_repos(self) -> list[str]:
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT github_repo FROM bot_hosting WHERE status != 'deleted'")
        rows = c.fetchall()
        conn.close()
        repos = []
        for row in rows:
            slug = parse_repo(row["github_repo"])
            if slug:
                repos.append(slug)
        return repos

    @tasks.loop(seconds=config.GITHUB_POLL_SECONDS)
    async def poll_github(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(config.GITHUB_CHANNEL)
        if not channel:
            return

        repos = self._registered_repos()
        if not repos:
            return

        if self.session is None:
            self.session = aiohttp.ClientSession()

        for repo in repos:
            try:
                await self._check_commits(repo, channel)
                await self._check_pulls(repo, channel)
                await self._check_releases(repo, channel)
            except Exception as e:
                print(f"[github_feed] error polling {repo}: {e}")

    async def _check_commits(self, repo: str, channel: discord.abc.Messageable):
        async with self.session.get(f"{GITHUB_API}/repos/{repo}/commits", headers=self._headers(), params={"per_page": 5}) as resp:
            if resp.status != 200:
                return
            commits = await resp.json()

        if not commits:
            return

        latest_sha = commits[0]["sha"]
        previous_sha = self.last_seen_commit.get(repo)
        self.last_seen_commit[repo] = latest_sha

        if previous_sha is None:
            return

        new_commits = []
        for commit in commits:
            if commit["sha"] == previous_sha:
                break
            new_commits.append(commit)

        for commit in reversed(new_commits):
            embed = discord.Embed(
                title=f"\U0001F4E6 New Commit in {repo}",
                description=commit["commit"]["message"].split("\n")[0][:200],
                url=commit["html_url"],
                color=config.BRAND_COLOR,
            )
            embed.add_field(name="Author", value=commit["commit"]["author"]["name"], inline=True)
            embed.add_field(name="SHA", value=commit["sha"][:7], inline=True)
            await channel.send(embed=embed)

    async def _check_pulls(self, repo: str, channel: discord.abc.Messageable):
        async with self.session.get(f"{GITHUB_API}/repos/{repo}/pulls", headers=self._headers(), params={"state": "all", "per_page": 5, "sort": "created", "direction": "desc"}) as resp:
            if resp.status != 200:
                return
            pulls = await resp.json()

        if not pulls:
            return

        latest_number = pulls[0]["number"]
        previous_number = self.last_seen_pr.get(repo)
        self.last_seen_pr[repo] = latest_number

        if previous_number is None:
            return

        for pr in pulls:
            if pr["number"] <= previous_number:
                continue
            embed = discord.Embed(
                title=f"\U0001F500 Pull Request #{pr['number']} in {repo}",
                description=pr["title"][:200],
                url=pr["html_url"],
                color=config.BRAND_COLOR,
            )
            embed.add_field(name="Author", value=pr["user"]["login"], inline=True)
            embed.add_field(name="State", value=pr["state"], inline=True)
            await channel.send(embed=embed)

    async def _check_releases(self, repo: str, channel: discord.abc.Messageable):
        async with self.session.get(f"{GITHUB_API}/repos/{repo}/releases", headers=self._headers(), params={"per_page": 3}) as resp:
            if resp.status != 200:
                return
            releases = await resp.json()

        if not releases:
            return

        latest_id = str(releases[0]["id"])
        previous_id = self.last_seen_release.get(repo)
        self.last_seen_release[repo] = latest_id

        if previous_id is None:
            return

        for release in releases:
            if str(release["id"]) == previous_id:
                break
            embed = discord.Embed(
                title=f"\U0001F680 New Release in {repo}",
                description=release.get("name") or release.get("tag_name", ""),
                url=release["html_url"],
                color=config.SUCCESS_COLOR,
            )
            await channel.send(embed=embed)


# ============================================================
# ECONOMY COG - restricted to #commands.
# ============================================================

def in_commands_channel():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.channel_id != config.COMMANDS_CHANNEL:
            await interaction.response.send_message(
                f"\u26A0\uFE0F Economy commands can only be used in <#{config.COMMANDS_CHANNEL}>.", ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)


def get_account(user_id: str) -> dict:
    db.ensure_economy_account(user_id)
    conn = db.get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM economy WHERE user_id = ?", (user_id,))
    row = dict(c.fetchone())
    conn.close()
    return row


def update_balance(user_id: str, delta: float, earned: float = 0.0):
    conn = db.get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE economy SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?",
        (delta, earned, user_id),
    )
    conn.commit()
    conn.close()


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="daily", description="Claim your daily reward")
    @in_commands_channel()
    async def daily(self, interaction: discord.Interaction):
        account = get_account(str(interaction.user.id))
        now = datetime.now()

        if account["last_daily"]:
            last = datetime.fromisoformat(account["last_daily"])
            if now - last < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last)
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes = remainder // 60
                await interaction.response.send_message(
                    f"\u23F3 You already claimed your daily reward. Come back in {hours}h {minutes}m.", ephemeral=True
                )
                return

        streak = account["streak"] or 0
        last_streak_date = account["last_streak_date"]
        if last_streak_date:
            last_date = datetime.fromisoformat(last_streak_date)
            if now - last_date < timedelta(hours=48):
                streak += 1
            else:
                streak = 1
        else:
            streak = 1

        bonus = min(streak * 25, 500)
        reward = config.DAILY_REWARD + bonus

        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            """UPDATE economy SET balance = balance + ?, total_earned = total_earned + ?,
               last_daily = ?, streak = ?, last_streak_date = ? WHERE user_id = ?""",
            (reward, reward, now, streak, now, str(interaction.user.id)),
        )
        conn.commit()
        conn.close()

        embed = discord.Embed(title="\U0001F4B0 Daily Reward Claimed!", color=config.SUCCESS_COLOR)
        embed.add_field(name="Base Reward", value=f"${config.DAILY_REWARD:.2f}", inline=True)
        embed.add_field(name="Streak Bonus", value=f"${bonus:.2f} ({streak} day streak)", inline=True)
        embed.add_field(name="Total", value=f"${reward:.2f}", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="work", description="Work to earn some cash")
    @in_commands_channel()
    async def work(self, interaction: discord.Interaction):
        account = get_account(str(interaction.user.id))
        now = datetime.now()

        if account["last_work"]:
            last = datetime.fromisoformat(account["last_work"])
            elapsed = (now - last).total_seconds()
            if elapsed < config.WORK_COOLDOWN_SECONDS:
                remaining = config.WORK_COOLDOWN_SECONDS - elapsed
                minutes = int(remaining // 60)
                await interaction.response.send_message(f"\u23F3 You're tired. Try again in {minutes} minutes.", ephemeral=True)
                return

        earnings = round(random.uniform(config.WORK_MIN, config.WORK_MAX), 2)
        jobs = [
            "built a Discord bot", "designed a logo", "scripted a Roblox game",
            "fixed a bug", "wrote documentation", "reviewed a pull request",
        ]
        job = random.choice(jobs)

        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE economy SET balance = balance + ?, total_earned = total_earned + ?, last_work = ? WHERE user_id = ?",
            (earnings, earnings, now, str(interaction.user.id)),
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"\U0001F4BC You {job} and earned **${earnings:.2f}**!",
                color=config.SUCCESS_COLOR,
            )
        )

    @app_commands.command(name="balance", description="Check your (or someone else's) balance")
    @app_commands.describe(member="Member to check (defaults to you)")
    @in_commands_channel()
    async def balance(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        account = get_account(str(target.id))
        embed = discord.Embed(title=f"\U0001F4B3 {target.display_name}'s Balance", color=config.BRAND_COLOR)
        embed.add_field(name="Balance", value=f"${account['balance']:.2f}", inline=True)
        embed.add_field(name="Level", value=str(account["level"]), inline=True)
        embed.add_field(name="Total Earned", value=f"${account['total_earned']:.2f}", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pay", description="Pay another member")
    @app_commands.describe(member="Who to pay", amount="Amount to send")
    @in_commands_channel()
    async def pay(self, interaction: discord.Interaction, member: discord.Member, amount: float):
        if member.id == interaction.user.id:
            await interaction.response.send_message("\u274C You can't pay yourself.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("\u274C Amount must be positive.", ephemeral=True)
            return

        sender = get_account(str(interaction.user.id))
        if sender["balance"] < amount:
            await interaction.response.send_message("\u274C Insufficient balance.", ephemeral=True)
            return

        get_account(str(member.id))
        update_balance(str(interaction.user.id), -amount)
        update_balance(str(member.id), amount)

        await interaction.response.send_message(
            embed=discord.Embed(description=f"\U0001F4B8 {interaction.user.mention} paid {member.mention} **${amount:.2f}**", color=config.SUCCESS_COLOR)
        )

    @app_commands.command(name="coinflip", description="Bet on a coin flip")
    @app_commands.describe(amount="Amount to bet", choice="Heads or tails")
    @app_commands.choices(choice=[app_commands.Choice(name="Heads", value="heads"), app_commands.Choice(name="Tails", value="tails")])
    @in_commands_channel()
    async def coinflip(self, interaction: discord.Interaction, amount: float, choice: app_commands.Choice[str]):
        account = get_account(str(interaction.user.id))
        if amount <= 0 or account["balance"] < amount:
            await interaction.response.send_message("\u274C Invalid or insufficient bet amount.", ephemeral=True)
            return

        result = random.choice(["heads", "tails"])
        won = result == choice.value
        delta = amount if won else -amount
        update_balance(str(interaction.user.id), delta, earned=max(delta, 0))

        embed = discord.Embed(
            title=f"\U0001FA99 The coin landed on {result.title()}!",
            description=f"You {'won' if won else 'lost'} **${amount:.2f}**",
            color=config.SUCCESS_COLOR if won else config.DANGER_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="slots", description="Try your luck at the slot machine")
    @app_commands.describe(amount="Amount to bet")
    @in_commands_channel()
    async def slots(self, interaction: discord.Interaction, amount: float):
        account = get_account(str(interaction.user.id))
        if amount <= 0 or account["balance"] < amount:
            await interaction.response.send_message("\u274C Invalid or insufficient bet amount.", ephemeral=True)
            return

        symbols = ["\U0001F352", "\U0001F34A", "\U0001F347", "\U0001F514", "\U0001F48E", "7\uFE0F\u20E3"]
        spin = [random.choice(symbols) for _ in range(3)]

        if spin[0] == spin[1] == spin[2]:
            multiplier = 10 if spin[0] == "7\uFE0F\u20E3" else 5
        elif len(set(spin)) == 2:
            multiplier = 1.5
        else:
            multiplier = 0

        delta = amount * multiplier - amount
        update_balance(str(interaction.user.id), delta, earned=max(delta, 0))

        embed = discord.Embed(
            title=" | ".join(spin),
            description=(f"\U0001F389 You won **${delta:.2f}**!" if delta > 0 else f"\U0001F4A8 You lost **${amount:.2f}**."),
            color=config.SUCCESS_COLOR if delta > 0 else config.DANGER_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="blackjack", description="Play a quick round of blackjack")
    @app_commands.describe(amount="Amount to bet")
    @in_commands_channel()
    async def blackjack(self, interaction: discord.Interaction, amount: float):
        account = get_account(str(interaction.user.id))
        if amount <= 0 or account["balance"] < amount:
            await interaction.response.send_message("\u274C Invalid or insufficient bet amount.", ephemeral=True)
            return

        def draw_hand():
            deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]
            return [random.choice(deck), random.choice(deck)]

        def hand_value(hand):
            value = sum(hand)
            aces = hand.count(11)
            while value > 21 and aces:
                value -= 10
                aces -= 1
            return value

        player = draw_hand()
        dealer = draw_hand()

        while hand_value(dealer) < 17:
            dealer.append(random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]))

        player_value = hand_value(player)
        dealer_value = hand_value(dealer)

        if player_value > 21:
            outcome, delta = "You busted!", -amount
        elif dealer_value > 21 or player_value > dealer_value:
            outcome, delta = "You win!", amount
        elif player_value == dealer_value:
            outcome, delta = "Push - bet returned.", 0
        else:
            outcome, delta = "Dealer wins.", -amount

        update_balance(str(interaction.user.id), delta, earned=max(delta, 0))

        embed = discord.Embed(title="\U0001F0CF Blackjack", description=outcome, color=config.SUCCESS_COLOR if delta > 0 else config.DANGER_COLOR)
        embed.add_field(name="Your Hand", value=f"{player} = {player_value}", inline=True)
        embed.add_field(name="Dealer's Hand", value=f"{dealer} = {dealer_value}", inline=True)
        embed.add_field(name="Result", value=f"${delta:+.2f}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="View the richest members")
    @in_commands_channel()
    async def leaderboard(self, interaction: discord.Interaction):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id, balance FROM economy ORDER BY balance DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message("No economy data yet.", ephemeral=True)
            return

        lines = [f"**{i + 1}.** <@{row['user_id']}> - ${row['balance']:.2f}" for i, row in enumerate(rows)]
        embed = discord.Embed(title="\U0001F3C6 Leaderboard", description="\n".join(lines), color=config.BRAND_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inventory", description="View your inventory")
    @in_commands_channel()
    async def inventory(self, interaction: discord.Interaction):
        account = get_account(str(interaction.user.id))
        inv = json.loads(account["inventory"] or "{}")
        if not inv:
            await interaction.response.send_message(embed=discord.Embed(description="Your inventory is empty. Visit `/shop` to buy items!", color=config.BRAND_COLOR))
            return

        lines = []
        for item_key, qty in inv.items():
            item = config.SHOP_ITEMS.get(item_key)
            if item:
                lines.append(f"{item['emoji']} {item['name']} x{qty}")
        embed = discord.Embed(title=f"\U0001F392 {interaction.user.display_name}'s Inventory", description="\n".join(lines) or "Empty", color=config.BRAND_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shop", description="Browse and buy shop items")
    @app_commands.describe(item="Item to purchase (leave blank to browse)")
    @app_commands.choices(item=[app_commands.Choice(name=v["name"], value=k) for k, v in config.SHOP_ITEMS.items()])
    @in_commands_channel()
    async def shop(self, interaction: discord.Interaction, item: app_commands.Choice[str] | None = None):
        if item is None:
            lines = [f"{v['emoji']} **{v['name']}** - ${v['price']:.2f}" for v in config.SHOP_ITEMS.values()]
            embed = discord.Embed(title="\U0001F6D2 Shop", description="\n".join(lines), color=config.BRAND_COLOR)
            embed.set_footer(text="Use /shop item:<name> to buy")
            await interaction.response.send_message(embed=embed)
            return

        account = get_account(str(interaction.user.id))
        shop_item = config.SHOP_ITEMS[item.value]
        if account["balance"] < shop_item["price"]:
            await interaction.response.send_message("\u274C You can't afford that item.", ephemeral=True)
            return

        inv = json.loads(account["inventory"] or "{}")
        inv[item.value] = inv.get(item.value, 0) + 1

        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE economy SET balance = balance - ?, inventory = ? WHERE user_id = ?",
            (shop_item["price"], json.dumps(inv), str(interaction.user.id)),
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            embed=discord.Embed(description=f"\u2705 Purchased {shop_item['emoji']} **{shop_item['name']}** for ${shop_item['price']:.2f}!", color=config.SUCCESS_COLOR)
        )


# ============================================================
# INVITES COG - logs new invite creation to #invites.
# ============================================================

class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._sync_guild_invites(guild)

    async def _sync_guild_invites(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            return

        conn = db.get_conn()
        c = conn.cursor()
        for invite in invites:
            c.execute(
                """INSERT OR IGNORE INTO invites
                   (guild_id, code, inviter_id, uses, max_uses, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(guild.id), invite.code, str(invite.inviter.id) if invite.inviter else None,
                    invite.uses or 0, invite.max_uses or 0,
                    invite.created_at, invite.expires_at,
                ),
            )
        conn.commit()
        conn.close()

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT OR IGNORE INTO invites
               (guild_id, code, inviter_id, uses, max_uses, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(invite.guild.id), invite.code, str(invite.inviter.id) if invite.inviter else None,
                invite.uses or 0, invite.max_uses or 0,
                invite.created_at, invite.expires_at,
            ),
        )
        conn.commit()
        conn.close()

        is_permanent = not invite.max_age
        expiration = f"<t:{int(invite.expires_at.timestamp())}:R>" if invite.expires_at else "Never"

        embed = discord.Embed(
            title="\U0001F4E9 New Invite Created" + (" (Permanent)" if is_permanent else ""),
            color=config.BRAND_COLOR,
        )
        embed.add_field(name="Invite Creator", value=invite.inviter.mention if invite.inviter else "Unknown", inline=True)
        embed.add_field(name="Invite Code", value=invite.code, inline=True)
        embed.add_field(name="Invite Link", value=invite.url, inline=False)
        embed.add_field(name="Created At", value=f"<t:{int(invite.created_at.timestamp())}:F>", inline=True)
        embed.add_field(name="Expiration", value=expiration, inline=True)
        embed.add_field(name="Max Uses", value=str(invite.max_uses) if invite.max_uses else "Unlimited", inline=True)
        embed.add_field(name="Current Uses", value=str(invite.uses or 0), inline=True)

        channel = self.bot.get_channel(config.INVITES_CHANNEL)
        if channel:
            await channel.send(embed=embed)

        mod_log = self.bot.get_channel(config.MOD_LOG_CHANNEL)
        if mod_log:
            await mod_log.send(embed=discord.Embed(description=f"\U0001F4E9 Invite `{invite.code}` created by {invite.inviter.mention if invite.inviter else 'Unknown'}", color=config.BRAND_COLOR))

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM invites WHERE guild_id = ? AND code = ?", (str(invite.guild.id), invite.code))
        conn.commit()
        conn.close()


# ============================================================
# ENTRY POINT
# ============================================================

async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it in the Secrets tab (or .env when running elsewhere).")

    db.init_db()

    async with bot:
        for cog_cls in (Events, Tickets, Assistance, Survey, BotManagement, GithubFeed, Economy, Invites):
            try:
                await bot.add_cog(cog_cls(bot))
                print(f"Loaded cog: {cog_cls.__name__}")
            except Exception as e:
                print(f"Failed to load cog {cog_cls.__name__}: {e}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

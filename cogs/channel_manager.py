"""
ArcherSniper - Channel Manager & Server Provisioner
Automates the creation and configuration of Announcement channels, DLSU College Feeds, and Admin HQ.
"""

import logging
import discord
from discord.ext import commands

from config import (
    CAT_ANNOUNCEMENTS,
    CAT_COLLEGE_FEEDS,
    CAT_ADMIN_HQ,
    ADMIN_ROLE_NAME,
    ADMIN_USER_IDS,
)
from database import Database
from utils.embeds import (
    create_system_alert_embed,
    create_course_coverage_guide_embed,
)

logger = logging.getLogger("ArcherSniper.ChannelManager")


def is_admin():
    """Custom check to ensure user has admin permissions, is server owner, or has ArcherSniper Admin role."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in ADMIN_USER_IDS:
            return True
        if ctx.guild:
            if ctx.guild.owner_id == ctx.author.id:
                return True
            if isinstance(ctx.author, discord.Member):
                if ctx.author.guild_permissions.administrator:
                    return True
                if any(r.name == ADMIN_ROLE_NAME for r in ctx.author.roles):
                    return True
        if not ADMIN_USER_IDS and not ctx.guild:
            return True
        return False
    return commands.check(predicate)


class ChannelManager(commands.Cog, name="ChannelManager"):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db

    async def _get_or_create_category(
        self,
        guild: discord.Guild,
        name: str,
        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite],
    ) -> discord.CategoryChannel:
        """Finds or creates a category with specific permission overwrites."""
        for cat in guild.categories:
            if cat.name.lower() == name.lower():
                return cat
        return await guild.create_category(name=name, overwrites=overwrites, reason="ArcherSniper auto-setup")

    async def _get_or_create_text_channel(
        self,
        guild: discord.Guild,
        category: discord.CategoryChannel,
        name: str,
        topic: str,
        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] | None = None,
    ) -> discord.TextChannel:
        """Finds or creates a text channel under a specific category."""
        for ch in category.text_channels:
            if ch.name.lower() == name.lower():
                return ch

        return await guild.create_text_channel(
            name=name,
            category=category,
            topic=topic,
            overwrites=overwrites,
            reason="ArcherSniper auto-setup",
        )

    # ==========================================
    # !setupchannels
    # ==========================================

    @commands.hybrid_command(
        name="setupchannels",
        description="(Admin only) Auto-provision Announcements, College Feeds, and Admin HQ channels.",
    )
    @is_admin()
    async def setup_channels_command(self, ctx: commands.Context):
        """
        Auto-provisions the 3 server categories and all required channels with strict permissions.
        Syntax: !setupchannels
        """
        if not ctx.guild:
            await ctx.send("❌ This command can only be executed within a Discord server.")
            return

        if not ctx.guild.me.guild_permissions.manage_channels:
            await ctx.send("❌ Bot is missing the **Manage Channels** permission in this server.")
            return

        await ctx.defer()
        guild = ctx.guild
        msg = await ctx.send("⚙️ **Provisioning ArcherSniper categories and channels...**")

        everyone_role = guild.default_role
        bot_member = guild.me

        # ----------------------------------------------------
        # 1. PUBLIC CATEGORY: ANNOUNCEMENTS & COMMANDS
        # ----------------------------------------------------
        public_read_overwrites = {
            everyone_role: discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                read_message_history=True,
                send_messages=False,
                send_messages_in_threads=False,
                create_public_threads=False,
                create_private_threads=False,
                add_reactions=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                mention_everyone=True,
                add_reactions=True,
            ),
        }

        command_channel_overwrites = {
            everyone_role: discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                use_application_commands=True,
                add_reactions=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                add_reactions=True,
            ),
        }

        cat_announcements = await self._get_or_create_category(guild, CAT_ANNOUNCEMENTS, public_read_overwrites)
        ch_announcements = await self._get_or_create_text_channel(
            guild, cat_announcements, "📢-announcements",
            "ArcherSniper Official Announcements & System Status Alerts (@everyone)",
            public_read_overwrites,
        )

        ch_bot_commands = await self._get_or_create_text_channel(
            guild, cat_announcements, "🤖-bot-commands",
            "Dedicated channel for ArcherSniper student commands (!watch, !unwatch, !watchlist, !search, !stats, !help)",
            command_channel_overwrites,
        )

        # ----------------------------------------------------
        # 2. PUBLIC CATEGORY: DLSU COLLEGE FEEDS (Strictly Read-Only)
        # ----------------------------------------------------
        feed_overwrites = {
            everyone_role: discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                read_message_history=True,
                send_messages=False,
                send_messages_in_threads=False,
                create_public_threads=False,
                create_private_threads=False,
                add_reactions=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                add_reactions=True,
            ),
        }

        cat_feeds = await self._get_or_create_category(guild, CAT_COLLEGE_FEEDS, feed_overwrites)

        channel_map = {
            "announcements": ch_announcements.id,
            "bot_commands": ch_bot_commands.id,
        }

        feed_specs = [
            ("ge_lc", "🎯-ge-lc-feed", "Live Slot Drop Feed for General Education (GE) & Lasallian Core (LC)"),
            ("ccs", "💻-ccs-drops", "College of Computer Studies (CCS) Live Section Drops"),
            ("rvrcob", "💼-rvrcob-drops", "Ramon V. del Rosario College of Business (RVRCOB) Live Drops"),
            ("gcoe", "⚙️-gcoe-drops", "Gokongwei College of Engineering (GCOE) Live Drops"),
            ("cla", "📜-cla-drops", "College of Liberal Arts (CLA) Live Drops"),
            ("cos", "🔬-cos-drops", "College of Science (COS) Live Drops"),
            ("bagced", "📚-bagced-drops", "Br. Andrew Gonzalez College of Education (BAGCED) Live Drops"),
            ("soe", "📈-soe-drops", "School of Economics (SOE) Live Drops"),
        ]

        for key, name, topic in feed_specs:
            ch = await self._get_or_create_text_channel(guild, cat_feeds, name, topic, feed_overwrites)
            channel_map[key] = ch.id

        # ----------------------------------------------------
        # 3. PRIVATE CATEGORY: ADMIN HQ (Strictly Hidden)
        # ----------------------------------------------------
        # Ensure 'ArcherSniper Admin' role exists
        admin_role = None
        if hasattr(guild, "roles") and guild.roles and isinstance(guild.roles, (list, tuple)):
            admin_role = discord.utils.find(lambda r: hasattr(r, "name") and r.name == ADMIN_ROLE_NAME, guild.roles)
        if not admin_role and hasattr(guild, "create_role") and callable(guild.create_role):
            try:
                created = guild.create_role(
                    name=ADMIN_ROLE_NAME,
                    color=discord.Color(0x006837),
                    reason="ArcherSniper Admin Role for administrative access",
                )
                if hasattr(created, "__await__"):
                    admin_role = await created
                else:
                    admin_role = created
            except Exception as e:
                logger.warning(f"Could not create role {ADMIN_ROLE_NAME}: {e}")

        admin_overwrites = {
            everyone_role: discord.PermissionOverwrite(
                read_messages=False,
                send_messages=False,
                view_channel=False,
            ),
            bot_member: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                view_channel=True,
                embed_links=True,
                read_message_history=True,
                manage_messages=True,
            ),
        }

        if admin_role and hasattr(admin_role, "id"):
            admin_overwrites[admin_role] = discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
            )

        cat_admin = await self._get_or_create_category(guild, CAT_ADMIN_HQ, admin_overwrites)

        admin_specs = [
            ("admin_commands", "🔒-admin-commands", "Restricted Admin Command Terminal (!setcurl, !start, !stop, !interval)"),
            ("admin_disconnects", "🚨-admin-disconnects", "Emergency Session Disconnect Alerts & Technical Diagnostics"),
            ("admin_heartbeat", "💓-admin-heartbeat-log", "1-Minute DLSU CourseFinder Keep-Alive Pulse Confirmation Log (Silent)"),
            ("admin_dm_logs", "📬-admin-dm-logs", "Private audit log mirroring student DM slot notifications (Silent)"),
        ]

        for key, name, topic in admin_specs:
            ch = await self._get_or_create_text_channel(guild, cat_admin, name, topic, admin_overwrites)
            channel_map[key] = ch.id

        # Save all channel mappings to SQLite
        await self.db.save_server_channels(guild.id, channel_map)

        # Pre-seed standard GE, LC, and College courses so broadcast feeds are active immediately
        try:
            await self.db.seed_default_courses()
        except Exception as e:
            logger.warning(f"Could not seed default courses: {e}")

        embed = discord.Embed(
            title="🏛️ ArcherSniper Server Channels Provisioned",
            description="Successfully structured all categories and text channels with strict permission controls.",
            color=0x006837,
        )

        embed.add_field(
            name="📢 Announcements & Student Hub",
            value=(
                f"• **Announcements:** <#{channel_map['announcements']}>\n"
                f"• **Student Commands:** <#{channel_map['bot_commands']}>"
            ),
            inline=False,
        )

        embed.add_field(
            name="🏛️ DLSU College Feeds (Read-Only • Zero Pings)",
            value=(
                f"• **GE & LC:** <#{channel_map['ge_lc']}>\n"
                f"• **CCS:** <#{channel_map['ccs']}>\n"
                f"• **RVRCOB:** <#{channel_map['rvrcob']}>\n"
                f"• **GCOE:** <#{channel_map['gcoe']}>\n"
                f"• **CLA:** <#{channel_map['cla']}>\n"
                f"• **COS:** <#{channel_map['cos']}>\n"
                f"• **BAGCED:** <#{channel_map['bagced']}>\n"
                f"• **SOE:** <#{channel_map['soe']}>"
            ),
            inline=False,
        )

        role_mention = f"<@&{admin_role.id}>" if admin_role and hasattr(admin_role, "id") and isinstance(admin_role.id, int) else f"`@{ADMIN_ROLE_NAME}`"
        embed.add_field(
            name=f"🔒 Admin HQ (Private • {role_mention})",
            value=(
                f"• **Admin Terminal:** <#{channel_map['admin_commands']}>\n"
                f"• **Disconnect Alerts:** <#{channel_map['admin_disconnects']}>\n"
                f"• **1-Min Pulse Log:** <#{channel_map['admin_heartbeat']}>\n"
                f"• **DM Mirror Logs:** <#{channel_map['admin_dm_logs']}>\n"
                f"• *Server Owner can toggle roles with `!admin <@member>`*"
            ),
            inline=False,
        )

        embed.set_footer(text="ArcherSniper DLSU • Auto-Setup Complete")
        await msg.edit(content=None, embed=embed)

        # Post official monitoring rules guide into announcements channel
        try:
            guide_embed = create_course_coverage_guide_embed()
            guide_msg = await ch_announcements.send(embed=guide_embed)
            try:
                await guide_msg.pin(reason="ArcherSniper Course Coverage Guide")
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Could not post guide embed to announcements: {e}")

        logger.info(f"Completed channel auto-provisioning for guild: {guild.name} ({guild.id})")


async def setup(bot: commands.Bot):
    db = getattr(bot, "db", None)
    await bot.add_cog(ChannelManager(bot, db))

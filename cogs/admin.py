"""
ArcherSniper - Administrative Management Cog
Handles admin commands: !start, !stop, !setcurl, !startgelc, !stopgelc, !add, !remove, !interval, !health, and !sync.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
import aiosqlite
import discord
from discord.ext import commands

from config import (
    ADMIN_USER_IDS,
    ADMIN_ROLE_NAME,
    SCRAPER_LOG_PATH,
    CATALOG_RAW_DUMP_PATH,
    WATCHDOG_CYCLES_LOG_PATH,
    AUTODISCOVERY_LOG_PATH,
    SLOT_DROPS_LOG_PATH,
    DM_DISPATCH_LOG_PATH,
    HEARTBEAT_LOG_PATH,
)
from database import Database
from engine import WatchdogEngine
from utils.curl_parser import parse_curl
from utils.course_classifier import classify_course
from utils.embeds import (
    create_health_embed,
    create_system_alert_embed,
    create_user_inspection_embed,
    create_admin_course_inspection_embed,
    create_batched_feed_drop_embed,
    create_sweep_results_embed,
    get_courseinfo_page_count,
)

logger = logging.getLogger("ArcherSniper.AdminCog")


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


def is_server_owner():
    """Strict check: Only the Discord Server Owner or master ADMIN_USER_IDS can run this command."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in ADMIN_USER_IDS:
            return True
        if ctx.guild and (ctx.author.id == ctx.guild.owner_id or ctx.author == ctx.guild.owner):
            return True
        return False
    return commands.check(predicate)


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot, db: Database, engine: WatchdogEngine):
        self.bot = bot
        self.db = db
        self.engine = engine

    # ==========================================
    # !start & !stop (BOT ACCESS GATEKEEPER)
    # ==========================================

    @commands.hybrid_command(
        name="start",
        description="(Admin only) Turn ON the bot for all students and activate live feeds.",
    )
    @is_admin()
    async def start_command(self, ctx: commands.Context):
        """
        Activates ArcherSniper for all students, starts live scraping, and announces to #📢-announcements.
        Syntax: !start
        """
        await ctx.defer()
        self.engine.bot_active = True
        self.engine.ge_lc_active = True
        await self.db.set_bot_active(True)
        await self.db.set_ge_lc_active(True)

        # Broadcast announcement to #📢-announcements (@everyone ping)
        await self.engine.broadcast_bot_status(is_online=True, admin_name=ctx.author.display_name)

        embed = create_system_alert_embed(
            title="🟢 ArcherSniper Activated (Online)",
            description=(
                "**The bot is now accessible by all server members.**\n\n"
                "> 🎯 **Student Watchlists:** Active\n"
                "> 🏛️ **College Feeds:** Streaming\n"
                "> 📢 **Announcements:** Broadcasted (@everyone)"
            ),
            level="success",
        )
        await ctx.send(embed=embed)
        logger.info(f"Bot activated by admin {ctx.author.name} ({ctx.author.id})")

    @commands.hybrid_command(
        name="stop",
        description="(Admin only) Turn OFF the bot and pause all student notifications.",
    )
    @is_admin()
    async def stop_command(self, ctx: commands.Context, *, reason: str = "Scheduled Maintenance"):
        """
        Puts ArcherSniper in offline/maintenance mode and announces to #📢-announcements.
        Syntax: !stop [reason]
        """
        await ctx.defer()
        self.engine.bot_active = False
        await self.db.set_bot_active(False)

        # Broadcast announcement to #📢-announcements (@everyone ping)
        await self.engine.broadcast_bot_status(is_online=False, admin_name=ctx.author.display_name, reason=reason)

        embed = create_system_alert_embed(
            title="🔴 ArcherSniper Deactivated (Offline)",
            description=(
                f"**The bot has been set to offline mode.**\n\n"
                f"> **Reason:** `{reason}`\n"
                f"> **Student Access:** Restricted (Gatekeeper Active)\n"
                f"> **Live Scraper:** Paused"
            ),
            level="warning",
        )
        await ctx.send(embed=embed)
        logger.info(f"Bot deactivated by admin {ctx.author.name} ({ctx.author.id})")

    # ==========================================
    # !startgelc & !stopgelc
    # ==========================================

    @commands.hybrid_command(
        name="startgelc",
        description="(Admin only) Enable live slot change broadcasts in #🎯-ge-lc-feed.",
    )
    @is_admin()
    async def start_gelc_command(self, ctx: commands.Context):
        """Enable GE & LC auto-notifications feed."""
        await ctx.defer()
        self.engine.ge_lc_active = True
        await self.db.set_ge_lc_active(True)
        await ctx.send("✅ **GE & LC Live Feed Auto-Notifications:** `🟢 ENABLED`")

    @commands.hybrid_command(
        name="stopgelc",
        description="(Admin only) Disable live slot change broadcasts in #🎯-ge-lc-feed.",
    )
    @is_admin()
    async def stop_gelc_command(self, ctx: commands.Context):
        """Disable GE & LC auto-notifications feed."""
        await ctx.defer()
        self.engine.ge_lc_active = False
        await self.db.set_ge_lc_active(False)
        await ctx.send("⏸️ **GE & LC Live Feed Auto-Notifications:** `🔴 DISABLED`")

    # ==========================================
    # !setcurl <raw_curl_or_cookie>
    # ==========================================

    @commands.hybrid_command(
        name="setcurl",
        aliases=["sercurl", "curl", "cookie", "setcookie", "updatecurl"],
        description="(Admin only) Paste a fresh Master cURL string or cookie to link DLSU session.",
    )
    @is_admin()
    async def setcurl_command(self, ctx: commands.Context, *, raw_curl: str):
        """
        Paste a fresh Master cURL string or cookie to link DLSU session.
        Syntax: !setcurl <raw_curl_or_cookie>
        """
        await ctx.defer()

        parsed = parse_curl(raw_curl)
        if not parsed.is_valid:
            await ctx.send(
                "❌ Could not extract valid cookies or tokens from the provided input.\n"
                "Ensure you copy the full cURL (bash or cmd) from Chrome DevTools on `archershub.dlsu.edu.ph`."
            )
            return

        # Update API client
        self.engine.api.update_auth(parsed.cookies, parsed.headers)

        # Save to database
        await self.db.save_master_auth(
            cookies=parsed.cookies,
            headers=parsed.headers,
            raw_curl=raw_curl,
            status="CONNECTED",
            campus_no=parsed.campus_no or 7,
            academic_session=parsed.academic_session or 155,
        )

        # Test heartbeat
        hb_ok = await self.engine.api.send_heartbeat()

        tokens_summary = "\n".join(
            f"• `{k}`: `{'✅ Found' if v else '❌ Missing'}`"
            for k, v in parsed.key_tokens_present.items()
        )

        if hb_ok:
            await self.engine._on_reconnect_success("Admin !setcurl")
            embed = create_system_alert_embed(
                title="🔑 Master Session Connected Successfully",
                description=(
                    f"Successfully extracted **{len(parsed.cookies)}** cookie(s) and **{len(parsed.headers)}** header(s).\n\n"
                    f"**Key Tokens Status:**\n{tokens_summary}\n\n"
                    f"• **Heartbeat Pulse:** `🟢 Active 24/7 (Every 60s)`\n"
                    f"• **Live Polling:** Active (Every {self.engine.poll_interval}s)"
                ),
                level="success",
            )
        else:
            await self.engine._handle_disconnect("Pasted cURL returned HTTP 401 (Session expired on DLSU)")
            embed = create_system_alert_embed(
                title="⚠️ Tokens Extracted but DLSU Session is Expired (HTTP 401)",
                description=(
                    f"The bot extracted your tokens, but DLSU responded with **401 Unauthorized**.\n\n"
                    f"**Reason:** Your Archer's Hub session in the browser had already timed out before copying.\n\n"
                    f"**Quick Fix:**\n"
                    f"1. In your browser, refresh `https://archershub.dlsu.edu.ph/CourseFinder/` (log in if prompted).\n"
                    f"2. Search for any course to trigger a **fresh** `GetCFData` request.\n"
                    f"3. Right-click ➔ **Copy as cURL** and run `!setcurl <curl>` again."
                ),
                level="warning",
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="removecurl",
        aliases=["clearcurl", "resetauth"],
        description="(Admin only) Clear and wipe stored Master cURL session cookies.",
    )
    @is_admin()
    async def remove_curl_command(self, ctx: commands.Context):
        """
        Wipes stored browser session cookies and resets auth status to DISCONNECTED.
        Syntax: !removecurl
        """
        await ctx.defer()
        await self.db.clear_master_auth()
        self.engine.api.cookies.clear()
        self.engine.api.custom_headers.clear()
        self.engine.is_connected = False
        self.engine.session_expired = True
        await self.engine.update_bot_presence()

        embed = create_system_alert_embed(
            title="🗑️ Master cURL Session Removed",
            description=(
                "Successfully cleared and wiped all stored session cookies and browser tokens.\n\n"
                "> 🔒 **Status:** `🔴 DISCONNECTED`\n"
                "> ⚡ **Next Step:** Paste a new session using `!setcurl <curl>` to reconnect."
            ),
            level="warning",
        )
        await ctx.send(embed=embed)
        logger.info(f"Admin {ctx.author.name} cleared master cURL auth.")

    # ==========================================
    # !bookmarklet (1-CLICK BROWSER WEBHOOK)
    # ==========================================

    @commands.hybrid_command(
        name="bookmarklet",
        description="(Admin only) Get the 1-Click Chrome Bookmarklet to refresh sessions with 1 click.",
    )
    @is_admin()
    async def bookmarklet_command(self, ctx: commands.Context):
        """
        Provides the 1-Click Bookmarklet code for Chrome/Edge/Firefox.
        Syntax: !bookmarklet
        """
        await ctx.defer()
        bookmark_code = (
            "javascript:(function(){fetch('http://localhost:8080/api/update_cookies',{"
            "method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({cookies:document.cookie})})"
            ".then(r=>r.json()).then(d=>alert('🏹 ArcherSniper: '+d.message))"
            ".catch(e=>alert('❌ ArcherSniper Error: '+e));})();"
        )
        embed = discord.Embed(
            title="⚡ 1-Click ArcherSniper Browser Bookmarklet",
            description=(
                "**Refresh your ArcherSniper session in 1 second with a single click!**\n\n"
                "### 📌 How to Set It Up (10 seconds):\n"
                "1. Open Chrome/Edge/Brave and press `Ctrl + Shift + B` to show your **Bookmarks Bar**.\n"
                "2. Right-click the bookmarks bar and click **\"Add Page\"** or **\"Add Bookmark\"**.\n"
                "3. Set the **Name** to: `🏹 ArcherSniper Refresh`\n"
                "4. Paste the code below into the **URL / Location** box and click **Save**.\n\n"
                "### 🚀 How to Use:\n"
                "Whenever you are on [Archer's Hub CourseFinder](https://archershub.dlsu.edu.ph/CourseFinder/), simply **click the bookmark once**! The bot will instantly capture your live cookies and reconnect!"
            ),
            color=0x006837,
        )
        embed.add_field(
            name="📋 Bookmarklet Code (Copy into Bookmark URL)",
            value=f"```javascript\n{bookmark_code}\n```",
            inline=False,
        )
        embed.set_footer(text="ArcherSniper DLSU • Tier 3 1-Click Fast Recovery")
        await ctx.send(embed=embed)

    # ==========================================
    # !interval <seconds_or_minutes>
    # ==========================================

    @commands.hybrid_command(
        name="interval",
        description="(Admin only) Change the scraper poll interval (default: 15s).",
    )
    @is_admin()
    async def interval_command(self, ctx: commands.Context, interval: str):
        """
        Change the polling loop check interval (default: 15s).
        Syntax: !interval 15s or !interval 1m
        """
        await ctx.defer()
        clean_val = interval.strip().lower()

        seconds: float | None = None
        if clean_val.endswith("m"):
            val_str = clean_val[:-1]
            try:
                seconds = float(val_str) * 60.0
            except ValueError:
                pass
        elif clean_val.endswith("s"):
            val_str = clean_val[:-1]
            try:
                seconds = float(val_str)
            except ValueError:
                pass
        else:
            try:
                seconds = float(clean_val)
            except ValueError:
                pass

        if seconds is None or seconds < 2:
            await ctx.send("❌ Invalid interval. Minimum interval is `2` seconds. Examples: `!interval 15s`, `!interval 1m`.")
            return

        self.engine.poll_interval = seconds
        await self.db.set_intervals(poll_interval=seconds)

        embed = create_system_alert_embed(
            title="⏱️ Scraper Polling Frequency Updated",
            description=f"Watchdog scraping loop frequency has been set to **{seconds:.1f} seconds**.",
            level="success",
        )
        await ctx.send(embed=embed)

    # ==========================================
    # !add & !remove
    # ==========================================

    @commands.hybrid_command(
        name="add",
        description="(Admin only) Add course code(s) to global monitoring pool.",
    )
    @is_admin()
    async def add_command(self, ctx: commands.Context, *, courses: str):
        """
        Add course codes to the global monitoring pool.
        Syntax: !add STSWENG CSARCH1 or !add 367 STSWENG
        """
        await ctx.defer()
        tokens = courses.split()
        if not tokens:
            await ctx.send("❌ Please specify course code(s). Example: `!add STSWENG CSARCH1`")
            return

        added = []
        if len(tokens) >= 2 and tokens[0].isdigit() and not tokens[1].isdigit():
            cid, code = tokens[0], tokens[1].upper()
            name = " ".join(tokens[2:]) if len(tokens) > 2 else code
            await self.db.add_monitored_course(cid, code, name, ctx.author.name)
            added.append(f"• **`{code}`** (ID: `{cid}`) — {name}")
        else:
            for token in tokens:
                clean_code = token.strip().upper()
                matches = await self.db.search_catalog(clean_code)
                if matches:
                    best = matches[0]
                    await self.db.add_monitored_course(best["course_id"], best["course_code"], best.get("course_name", ""), ctx.author.name)
                    added.append(f"• **`{best['course_code']}`** (ID: `{best['course_id']}`) — {best.get('course_name', '')}")
                else:
                    await self.db.add_monitored_course(clean_code, clean_code, clean_code, ctx.author.name)
                    added.append(f"• **`{clean_code}`** (Raw Code)")

        embed = create_system_alert_embed(
            title="➕ Course Added to Monitoring Pool",
            description="\n".join(added),
            level="success",
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="remove",
        description="(Admin only) Remove course code from global monitoring pool.",
    )
    @is_admin()
    async def remove_command(self, ctx: commands.Context, course_code: str):
        """Remove a course code from global monitoring."""
        await ctx.defer()
        clean_code = course_code.strip().upper()
        deleted = await self.db.remove_monitored_course(clean_code)
        if deleted:
            await ctx.send(f"🗑️ Successfully removed **`{clean_code}`** from the monitoring pool.")
        else:
            await ctx.send(f"⚠️ Course **`{clean_code}`** was not found in the monitoring pool.")

    # ==========================================
    # !health & !sync
    # ==========================================

    @commands.hybrid_command(
        name="health",
        description="Show Master cURL session status and watchdog diagnostics.",
    )
    @is_admin()
    async def health_command(self, ctx: commands.Context):
        """Show system health and diagnostics."""
        await ctx.defer()
        health_data = self.engine.get_health_data()
        health_data["monitored_courses_count"] = len(await self.db.get_monitored_courses(active_only=True))
        health_data["active_watchers_count"] = await self.db.get_all_active_watchers_count()
        embed = create_health_embed(health_data)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="sync",
        description="(Admin only) Sync full course catalog from DLSU CourseFinder.",
    )
    @is_admin()
    async def sync_command(self, ctx: commands.Context):
        """Sync course catalog from DLSU CourseFinder API."""
        await ctx.defer()
        msg = await ctx.send("🔄 **Fetching DLSU CourseFinder catalog index...**")

        auth = await self.db.get_master_auth()
        campus_no = auth.get("campus_no") or 7 if auth else 7
        academic_session = auth.get("academic_session") or 155 if auth else 155

        try:
            ge_lc_count, college_count = await self.engine.auto_discover_new_courses()
            total_count = ge_lc_count + college_count
            active_pool = len(await self.db.get_monitored_courses(active_only=True))

            # Save raw catalog dump for inspection and debugging
            try:
                auth = await self.db.get_master_auth()
                campus_no = auth.get("campus_no") or 7 if auth else 7
                academic_session = auth.get("academic_session") or 155 if auth else 155
                catalog = await self.engine.api.fetch_course_catalog(campus_no=campus_no, academic_session=academic_session)
                with open(CATALOG_RAW_DUMP_PATH, "w", encoding="utf-8") as f:
                    json.dump({"synced_at": datetime.now(timezone.utc).isoformat(), "total_count": len(catalog), "courses": catalog}, f, indent=2)
            except Exception as dump_err:
                logger.debug(f"Could not write catalog dump: {dump_err}")

            await msg.edit(
                content=(
                    f"✅ **Catalog synchronization complete!**\n"
                    f"> 📚 **Total Courses Indexed:** `{total_count}`\n"
                    f"> 🎯 **24/7 Universal Monitored Pool:** `{ge_lc_count}` GE/LC/SAS/LASARE subjects\n"
                    f"> 🏛️ **College Major Courses:** `{college_count}` subjects indexed (monitored on-demand via `!watch`)\n"
                    f"> ⚡ **Current Active 15s Watchdog Pool:** `{active_pool}` courses"
                )
            )
        except Exception as e:
            logger.error(f"Catalog sync failed: {e}")
            await msg.edit(content=f"❌ **Catalog sync failed:** `{e}`")

    # ==========================================
    # !userstatus <member> (INSPECT MEMBER WATCHLIST)
    # ==========================================

    @commands.hybrid_command(
        name="userstatus",
        aliases=["inspect", "userwatch"],
        description="(Admin only) Inspect a member's watchlist and DM notification status.",
    )
    @is_admin()
    async def user_status_command(self, ctx: commands.Context, member: str):
        """
        Inspect a member's active watchlist, live section capacity, and mute/unmute state.
        Syntax: !userstatus @member or !userstatus 123456789
        """
        await ctx.defer()

        target_user: discord.User | discord.Member | None = None
        target_id: int | None = None

        # Check if mention or ID
        clean_input = member.strip("<@!>")
        if clean_input.isdigit():
            target_id = int(clean_input)
            try:
                target_user = await self.bot.fetch_user(target_id)
            except Exception:
                target_user = None
        elif ctx.guild and hasattr(ctx.guild, "members"):
            clean_search = member.lstrip("@").strip().lower()
            for m in ctx.guild.members:
                m_name = getattr(m, "name", "").lower()
                m_disp = getattr(m, "display_name", "").lower()
                if m_name == clean_search or m_disp == clean_search:
                    target_user = m
                    target_id = m.id
                    break

        if not target_id:
            await ctx.send("❌ Could not find the specified member. Provide a `@mention` or numerical user ID.")
            return

        display_name = target_user.display_name if target_user else f"User {target_id}"
        avatar_url = target_user.display_avatar.url if target_user else None

        watchlist_data = await self.db.get_user_watchlist_detailed(target_id)
        pings_enabled = await self.db.get_user_pings_status(target_id)

        embed = create_user_inspection_embed(
            member_name=display_name,
            member_id=target_id,
            avatar_url=avatar_url,
            watchlist_data=watchlist_data,
            pings_enabled=pings_enabled,
        )
        await ctx.send(embed=embed)

    # ==========================================
    # !prune (END-OF-TERM CLEANUP)
    # ==========================================

    @commands.hybrid_command(
        name="prune",
        aliases=["cleanterm", "resetwatchlists"],
        description="(Admin only) Clear all student watchlist subscriptions for end-of-term cleanup.",
    )
    @is_admin()
    async def prune_command(self, ctx: commands.Context):
        """
        Clears all student watchlist entries across the database while preserving channels and catalog cache.
        Syntax: !prune
        """
        await ctx.defer()
        count = await self.db.prune_all_watchlists()
        embed = create_system_alert_embed(
            title="🧹 End-of-Term Watchlist Cleanup Complete",
            description=(
                f"Successfully wiped **{count}** old student watchlist subscriptions.\n\n"
                "> 🏛️ **Server Channels:** Preserved\n"
                "> 📚 **Course Catalog:** Intact\n"
                "> 🎯 **Status:** Ready for new term course tracking"
            ),
            level="success",
        )
        await ctx.send(embed=embed)
        logger.info(f"Admin {ctx.author.name} ({ctx.author.id}) pruned {count} watchlists.")

    # ==========================================
    # !admin <@member> (OWNER-ONLY ROLE TOGGLE)
    # ==========================================

    @commands.hybrid_command(
        name="admin",
        aliases=["toggleadmin", "setadmin"],
        description="(Server Owner Only) Grant or revoke the ArcherSniper Admin role for a member.",
    )
    @is_server_owner()
    async def admin_toggle_command(self, ctx: commands.Context, *, member: str):
        """
        Grants or revokes the ArcherSniper Admin role for a mentioned member.
        Syntax: !admin @fluffle
        """
        if not ctx.guild:
            await ctx.send("❌ This command can only be used within a Discord server.")
            return

        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ The bot is missing the **Manage Roles** permission to assign admin roles.")
            return

        await ctx.defer()

        # Find or create role
        admin_role = discord.utils.get(ctx.guild.roles, name=ADMIN_ROLE_NAME)
        if not admin_role:
            try:
                admin_role = await ctx.guild.create_role(
                    name=ADMIN_ROLE_NAME,
                    color=discord.Color(0x006837),
                    reason="ArcherSniper Admin Role auto-created by owner !admin command",
                )
            except Exception as e:
                await ctx.send(f"❌ Failed to create the `{ADMIN_ROLE_NAME}` role: {e}")
                return

        # Resolve target member
        target_member: discord.Member | None = None
        clean_input = member.strip("<@!>").strip()
        clean_name = member.lstrip("@").strip().lower()
        if clean_input.isdigit():
            target_member = ctx.guild.get_member(int(clean_input))
            if not target_member:
                try:
                    target_member = await ctx.guild.fetch_member(int(clean_input))
                except Exception:
                    pass
        elif ctx.guild and hasattr(ctx.guild, "members"):
            for m in ctx.guild.members:
                m_name = getattr(m, "name", "").lower()
                m_disp = getattr(m, "display_name", "").lower()
                if m_name == clean_name or m_disp == clean_name:
                    target_member = m
                    break

        if not target_member:
            await ctx.send("❌ Could not find the specified member. Please `@mention` the member or provide their user ID.")
            return

        # Check if member already has the role (Toggle behavior)
        has_role = admin_role in target_member.roles
        if has_role:
            # Revoke role
            try:
                await target_member.remove_roles(admin_role, reason=f"ArcherSniper Admin role revoked by {ctx.author.name}")
            except Exception as e:
                await ctx.send(f"❌ Failed to revoke role from {target_member.mention}: {e}")
                return

            embed = discord.Embed(
                title="🚫 ArcherSniper Admin Role Revoked",
                description=(
                    f"Successfully removed the **{ADMIN_ROLE_NAME}** role from {target_member.mention}.\n\n"
                    f"> 🔒 **Status:** They can no longer access `🔒 ADMIN HQ` or execute admin commands."
                ),
                color=0xE74C3C,
            )
            await ctx.send(embed=embed)
            logger.info(f"Server owner {ctx.author.name} revoked admin role from {target_member.name} ({target_member.id})")
        else:
            # Grant role
            try:
                await target_member.add_roles(admin_role, reason=f"ArcherSniper Admin role granted by {ctx.author.name}")
            except Exception as e:
                await ctx.send(f"❌ Failed to assign role to {target_member.mention}: {e}")
                return

            embed = discord.Embed(
                title="✅ ArcherSniper Admin Role Granted",
                description=(
                    f"Successfully granted the **{ADMIN_ROLE_NAME}** role to {target_member.mention}!\n\n"
                    f"> 🔓 **Access Granted:**\n"
                    f"> • View and use `🔒 ADMIN HQ` channels\n"
                    f"> • Run administrative commands (`!setcurl`, `!start`, `!stop`, `!userstatus`, etc.)"
                ),
                color=0x006837,
            )
            await ctx.send(embed=embed)
            logger.info(f"Server owner {ctx.author.name} granted admin role to {target_member.name} ({target_member.id})")

    # ==========================================
    # !scraperlog (VIEW 15s SCRAPER LOGS)
    # ==========================================

    @commands.hybrid_command(
        name="scraperlog",
        aliases=["scraperlogs", "fetchlog"],
        description="(Admin only) View recent scraper fetch logs from the 15-second loop.",
    )
    @is_admin()
    async def scraper_log_command(self, ctx: commands.Context, lines: int = 25):
        """View latest scraper polling loop logs."""
        await ctx.defer()
        if not SCRAPER_LOG_PATH.exists():
            await ctx.send("📋 No scraper logs recorded yet. Start the bot and watchdog to generate logs.")
            return

        try:
            with open(SCRAPER_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()

            last_lines = all_lines[-min(lines, 40):]
            chunk = "".join(last_lines)
            if len(chunk) > 1900:
                chunk = chunk[-1900:]

            await ctx.send(f"📋 **Latest 15s Scraper Fetches (Log Output):**\n```text\n{chunk}\n```")
        except Exception as e:
            await ctx.send(f"❌ Failed to read scraper log: {e}")

    # ==========================================
    # !sweep / !rescan (BROADCAST ALL OPEN SLOTS NOW)
    # ==========================================

    @commands.hybrid_command(
        name="sweep",
        aliases=["rescan", "broadcastdrops"],
        description="(Admin only) Immediately scans and broadcasts all currently open sections to feeds & DMs.",
    )
    @is_admin()
    async def sweep_command(self, ctx: commands.Context):
        """
        Scans all courses in database that have open slots (>0) and broadcasts them live across Discord feeds and student DMs.
        Syntax: !sweep
        """
        await ctx.defer()
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT course_id, course_code, section_name, capacity, enlisted, open_slots, teacher, schedule
                FROM section_states
                WHERE open_slots > 0
                ORDER BY course_code, section_name;
            """) as cursor:
                open_sections = await cursor.fetchall()

        if not open_sections:
            await ctx.send("ℹ️ No sections with open slots found in the database. Run `!sync` or wait for the scraper.")
            return

        cycle_feed_changes: dict[str, list[dict]] = {}

        for sec in open_sections:
            code = sec["course_code"]
            sec_name = sec["section_name"]
            open_s = sec["open_slots"]
            cap = sec["capacity"]
            enl = sec["enlisted"]
            teacher = sec["teacher"] or "TBA"
            sched = sec["schedule"] or "TBA"

            # 1. Dispatch DM alerts to students watching this course
            await self.engine._dispatch_personal_dms(
                course_code=code,
                course_name="",
                section_name=sec_name,
                open_slots=open_s,
                capacity=cap,
                enlisted=enl,
                teacher=teacher,
                schedule=sched,
                prev_open_slots=0,
            )

            # 2. Collect for public feed channels
            classification = classify_course(code)
            change_item = {
                "course_code": code,
                "course_name": "",
                "section_name": sec_name,
                "open_slots": open_s,
                "capacity": cap,
                "enlisted": enl,
                "teacher": teacher,
                "schedule": sched,
                "prev_open_slots": 0,
                "category_label": classification.college_name or "DLSU Feed",
            }
            target_channels = set()
            if classification.is_ge_lc and self.engine.ge_lc_active:
                target_channels.add("ge_lc")
            col_key = classification.feed_channel_key
            if col_key and col_key != "ge_lc":
                target_channels.add(col_key)

            for ch_k in target_channels:
                cycle_feed_changes.setdefault(ch_k, []).append(change_item)

        # Broadcast consolidated batch embeds to each feed channel (chunked so all open sections are delivered)
        guild_ids = await self.db.get_all_configured_guilds()
        if cycle_feed_changes:
            for feed_key, changes in cycle_feed_changes.items():
                if not changes:
                    continue
                label = changes[0].get("category_label", "DLSU Feed")
                # Split changes into chunks of 12 items so every open section is sent without hitting Discord limits
                for i in range(0, len(changes), 12):
                    chunk = changes[i:i + 12]
                    page_no = (i // 12) + 1
                    tot_p = (len(changes) + 11) // 12
                    suffix = f" (Part {page_no}/{tot_p})" if tot_p > 1 else ""
                    batch_embed = create_batched_feed_drop_embed(f"{label}{suffix}", chunk)

                    for g_id in guild_ids:
                        channels = await self.db.get_server_channels(g_id)
                        ch_id = channels.get(feed_key)
                        if ch_id:
                            ch = self.bot.get_channel(ch_id)
                            if not ch:
                                try:
                                    ch = await self.bot.fetch_channel(ch_id)
                                except Exception:
                                    ch = None
                            if ch:
                                try:
                                    await ch.send(embed=batch_embed, allowed_mentions=discord.AllowedMentions.none())
                                    logger.info(f"📢 Broadcasted sweep chunk to #{getattr(ch, 'name', ch_id)} ({feed_key})")
                                except Exception as ex:
                                    logger.warning(f"Could not send sweep batch to {ch_id}: {ex}")

        # Render interactive paginated view with Next/Prev buttons for the admin
        dict_open_sections = [dict(s) for s in open_sections]
        view = SweepPaginationView(
            open_sections=dict_open_sections,
            feeds_updated=len(cycle_feed_changes),
            user_id=ctx.author.id,
            current_page=1,
            per_page=10,
        )
        embed = create_sweep_results_embed(
            open_sections=dict_open_sections,
            page=1,
            per_page=10,
            feeds_updated=len(cycle_feed_changes),
        )
        await ctx.send(embed=embed, view=view)


class SweepPaginationView(discord.ui.View):
    """Interactive Next/Previous button pagination view for !sweep command."""
    def __init__(
        self,
        open_sections: list[dict],
        feeds_updated: int,
        user_id: int | None = None,
        current_page: int = 1,
        per_page: int = 10,
    ):
        super().__init__(timeout=300)
        import math
        self.open_sections = open_sections
        self.feeds_updated = feeds_updated
        self.user_id = user_id
        self.current_page = current_page
        self.per_page = per_page
        self.total_pages = max(1, math.ceil(len(open_sections) / per_page))
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()
        if self.total_pages <= 1:
            return

        btn_first = discord.ui.Button(emoji="⏮️", style=discord.ButtonStyle.secondary, disabled=self.current_page <= 1, row=0)
        btn_first.callback = self._on_first

        btn_prev = discord.ui.Button(label="Prev", emoji="◀️", style=discord.ButtonStyle.primary, disabled=self.current_page <= 1, row=0)
        btn_prev.callback = self._on_prev

        btn_page = discord.ui.Button(label=f"Page {self.current_page} / {self.total_pages}", style=discord.ButtonStyle.secondary, disabled=True, row=0)

        btn_next = discord.ui.Button(label="Next", emoji="▶️", style=discord.ButtonStyle.primary, disabled=self.current_page >= self.total_pages, row=0)
        btn_next.callback = self._on_next

        btn_last = discord.ui.Button(emoji="⏭️", style=discord.ButtonStyle.secondary, disabled=self.current_page >= self.total_pages, row=0)
        btn_last.callback = self._on_last

        self.add_item(btn_first)
        self.add_item(btn_prev)
        self.add_item(btn_page)
        self.add_item(btn_next)
        self.add_item(btn_last)

    async def _render_page(self, interaction: discord.Interaction):
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your menu.", ephemeral=True)
            return

        self._update_buttons()
        embed = create_sweep_results_embed(
            open_sections=self.open_sections,
            page=self.current_page,
            per_page=self.per_page,
            feeds_updated=self.feeds_updated,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_first(self, interaction: discord.Interaction):
        self.current_page = 1
        await self._render_page(interaction)

    async def _on_prev(self, interaction: discord.Interaction):
        self.current_page = max(1, self.current_page - 1)
        await self._render_page(interaction)

    async def _on_next(self, interaction: discord.Interaction):
        self.current_page = min(self.total_pages, self.current_page + 1)
        await self._render_page(interaction)

    async def _on_last(self, interaction: discord.Interaction):
        self.current_page = self.total_pages
        await self._render_page(interaction)

    # ==========================================
    # !logs / !viewlogs (REAL-TIME LOG INSPECTOR)
    # ==========================================

    @commands.hybrid_command(
        name="logs",
        aliases=["viewlogs", "viewlog", "showlogs"],
        description="(Admin only) View recent real-time log entries from the server.",
    )
    @is_admin()
    async def view_logs_command(
        self,
        ctx: commands.Context,
        param1: str | None = "watchdog",
        param2: int | None = 15,
    ):
        """
        Displays recent log file lines for watchdog, autodiscovery, drops, dms, heartbeats, or scraper.
        Syntax: !logs, !logs 20, !logs drops, !logs drops 20
        """
        await ctx.defer()
        log_map = {
            "watchdog": ("⚡ Watchdog Cycles Benchmark Log", WATCHDOG_CYCLES_LOG_PATH),
            "autodiscovery": ("🔍 Auto-Discovery Subject Log", AUTODISCOVERY_LOG_PATH),
            "drops": ("🟢 Live Slot Drops Log", SLOT_DROPS_LOG_PATH),
            "dms": ("📬 Student DM Dispatches Log", DM_DISPATCH_LOG_PATH),
            "heartbeat": ("💓 Keep-Alive Heartbeat Log", HEARTBEAT_LOG_PATH),
            "scraper": ("📊 Scraper Fetches Log", SCRAPER_LOG_PATH),
        }

        # Flexible argument handling (e.g. !logs 20 or !logs drops 20)
        p1 = (param1 or "watchdog").strip().lower()
        if p1.isdigit():
            target_log = "watchdog"
            lines_count = int(p1)
        else:
            target_log = p1
            lines_count = param2 if param2 else 15

        if target_log not in log_map:
            valid_types = ", ".join([f"`{k}`" for k in log_map.keys()])
            await ctx.send(
                f"❌ Invalid log type `{target_log}`.\n"
                f"> **Available Log Files:** {valid_types}\n"
                f"> **Example:** `!logs watchdog 15` or `!logs drops 10`"
            )
            return

        title, file_path = log_map[target_log]
        lines_count = max(1, min(lines_count, 30))

        if not file_path.exists() or file_path.stat().st_size == 0:
            await ctx.send(
                f"ℹ️ **{title}** is currently initializing.\n"
                f"> New entries will appear automatically after the next 15-second cycle."
            )
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = [l.rstrip() for l in f.readlines() if l.strip()]

            if not all_lines:
                await ctx.send(f"ℹ️ **{title}** is currently empty.")
                return

            recent = all_lines[-lines_count:]
            content = "\n".join(recent)
            if len(content) > 1850:
                content = content[-1850:]

            embed = discord.Embed(
                title=f"📜 {title}",
                description=f"Showing last **{len(recent)}** entries:\n```text\n{content}\n```",
                color=0x006837,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="ArcherSniper Cloud • Type !logs <type> <lines> (e.g. !logs drops 10)")
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Error reading log file: `{e}`")


async def setup(bot: commands.Bot):
    db = getattr(bot, "db", None)
    engine = getattr(bot, "engine", None)
    await bot.add_cog(AdminCog(bot, db, engine))

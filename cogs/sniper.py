"""
ArcherSniper - Student Sniper Cog
Handles student commands: !watch, !unwatch, !watchlist, !monitored, !mute, !unmute, !status, and !check.
Includes gatekeeper access controls, strict unwatch scope rules, and Direct Message (DM) alert management.
"""

import logging
from typing import Any
import discord
from discord.ext import commands

from config import ADMIN_USER_IDS
from database import Database
from engine import WatchdogEngine
from utils.embeds import (
    create_status_embed,
    create_watchlist_detailed_embed,
    get_watchlist_page_count,
    create_monitored_summary_embed,
    create_system_alert_embed,
    create_drop_analytics_embed,
    create_course_search_embed,
    create_monitored_courses_embed,
    get_monitored_courses_page_count,
    create_admin_course_inspection_embed,
    get_courseinfo_page_count,
    create_system_status_overview_embed,
)
from utils.course_classifier import classify_course

logger = logging.getLogger("ArcherSniper.SniperCog")


def check_gatekeeper():
    """Ensures bot is active unless user is an administrator."""
    async def predicate(ctx: commands.Context) -> bool:
        engine: WatchdogEngine = getattr(ctx.bot, "engine", None)
        if engine and engine.bot_active:
            return True

        # Allow administrators even when offline
        if ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author == ctx.guild.owner):
            return True
        if ctx.author.id in ADMIN_USER_IDS:
            return True

        await ctx.send(
            "🛑 **ArcherSniper is currently OFFLINE (Maintenance Mode).**\n"
            "An administrator must activate the bot using `!start` before student commands are enabled."
        )
        return False
    return commands.check(predicate)


class WatchlistPaginationView(discord.ui.View):
    """Interactive pagination button view for multi-section student watchlists."""
    def __init__(
        self,
        username: str,
        watchlist_data: list[dict],
        pings_enabled: bool = True,
        current_page: int = 1,
        per_page: int = 15,
        user_id: int | None = None,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.username = username
        self.watchlist_data = watchlist_data
        self.pings_enabled = pings_enabled
        self.current_page = current_page
        self.per_page = per_page
        self.user_id = user_id
        self.total_pages = get_watchlist_page_count(watchlist_data, per_page)
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
            await interaction.response.send_message("❌ This is not your watchlist pagination menu.", ephemeral=True)
            return

        self._update_buttons()
        embed = create_watchlist_detailed_embed(
            username=self.username,
            watchlist_data=self.watchlist_data,
            pings_enabled=self.pings_enabled,
            page=self.current_page,
            per_page=self.per_page,
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


class MonitoredCoursesPaginationView(discord.ui.View):
    """Interactive pagination button view for public monitored courses catalog."""
    def __init__(
        self,
        courses: list[dict],
        current_page: int = 1,
        per_page: int = 15,
        user_id: int | None = None,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.courses = courses
        self.current_page = current_page
        self.per_page = per_page
        self.user_id = user_id
        self.total_pages = get_monitored_courses_page_count(courses, per_page)
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
        embed = create_monitored_courses_embed(
            courses=self.courses,
            page=self.current_page,
            per_page=self.per_page,
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


class CourseInfoPaginationView(discord.ui.View):
    """Interactive pagination button view for course section inspection."""
    def __init__(
        self,
        course_code: str,
        course_name: str,
        course_id: str,
        sections: list[dict],
        current_page: int = 1,
        per_page: int = 12,
        user_id: int | None = None,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.course_code = course_code
        self.course_name = course_name
        self.course_id = course_id
        self.sections = sections
        self.current_page = current_page
        self.per_page = per_page
        self.user_id = user_id
        self.total_pages = get_courseinfo_page_count(sections, per_page)
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
        embed = create_admin_course_inspection_embed(
            course_code=self.course_code,
            course_name=self.course_name,
            course_id=self.course_id,
            sections=self.sections,
            page=self.current_page,
            per_page=self.per_page,
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


class SniperCog(commands.Cog, name="Sniper"):
    def __init__(self, bot: commands.Bot, db: Database, engine: WatchdogEngine):
        self.bot = bot
        self.db = db
        self.engine = engine

    # ==========================================
    # !watch <COURSE> [SECTION]
    # ==========================================

    @commands.hybrid_command(
        name="watch",
        description="Subscribe to instant slot drop notifications (e.g. !watch STSWENG or !watch STSWENG S04).",
    )
    @check_gatekeeper()
    async def watch_command(self, ctx: commands.Context, course_code: str, section: str | None = None):
        """
        Subscribe to slot drop pings for a course or specific subject/section.
        Syntax: !watch STSWENG (watches all sections) or !watch STSWENG S04 (watches specific section)
        """
        await ctx.defer()
        clean_code = course_code.strip().upper()
        clean_sec = section.strip().upper() if section and section.strip() not in ("*", "ALL") else "*"
        scope = "COURSE" if clean_sec == "*" else "SECTION"

        # Resolve course in monitored pool or catalog
        course = await self.db.get_monitored_course(clean_code)
        if not course:
            catalog_match = await self.db.search_catalog(clean_code)
            if not catalog_match and self.engine and hasattr(self.engine, "api"):
                try:
                    catalog = await self.engine.api.fetch_course_catalog()
                    for item in catalog:
                        await self.db.upsert_catalog_course(item["course_id"], item["course_code"], item.get("course_name", ""))
                    catalog_match = await self.db.search_catalog(clean_code)
                except Exception:
                    pass

            if catalog_match:
                best = catalog_match[0]
                await self.db.add_monitored_course(
                    course_id=best["course_id"],
                    course_code=best["course_code"],
                    course_name=best.get("course_name", ""),
                    added_by=f"AutoWatch by {ctx.author.name}",
                )
                course = await self.db.get_monitored_course(clean_code)
            else:
                # Add with clean code
                await self.db.add_monitored_course(
                    course_id=clean_code,
                    course_code=clean_code,
                    course_name=clean_code,
                    added_by=f"Watch by {ctx.author.name}",
                )
                course = await self.db.get_monitored_course(clean_code)

        cid = course["course_id"]
        code = course["course_code"]
        name = course.get("course_name", "")

        # Save to database
        await self.db.add_user_watch(
            user_id=ctx.author.id,
            discord_username=ctx.author.name,
            course_id=cid,
            course_code=code,
            section_name=clean_sec,
            scope=scope,
        )

        sec_label = "ALL SECTIONS (Whole Course)" if scope == "COURSE" else f"Section `{clean_sec}`"

        # Send test DM to confirm user's DMs are open
        dm_ok = True
        try:
            test_embed = discord.Embed(
                title="🎯 ArcherSniper Subscription Active",
                description=(
                    f"You have subscribed to slot notifications for **`{code}`** ({sec_label}).\n\n"
                    "> 📬 **Alert Destination:** Direct Message (DM)\n"
                    "> ⚡ **Trigger:** Instant ping whenever a slot opens up\n"
                    "> 🔕 **Pause Pings:** Type `!mute` to temporarily pause notifications"
                ),
                color=0x006837,
            )
            await ctx.author.send(embed=test_embed)
        except Exception:
            dm_ok = False

        embed = discord.Embed(
            title="🎯 Watchlist Subscription Confirmed",
            description=(
                f"Successfully added **`{code}`** ({sec_label}) to your watchlist.\n\n"
                f"> 📬 **DM Notifications:** `{'🟢 Enabled & Verified' if dm_ok else '⚠️ Warning: Your DMs are closed! Please open your Discord DMs.'}`\n"
                f"> 📋 **View Watchlist:** Use `!watchlist` to see live section slots\n"
                f"> 🔕 **Pause Pings:** Use `!mute` / `!unmute` anytime"
            ),
            color=0x006837 if dm_ok else 0xF59E0B,
        )
        embed.set_footer(text="ArcherSniper DLSU • Animo La Salle 🏹")
        await ctx.send(embed=embed)

    # ==========================================
    # !unwatch <COURSE> [SECTION]
    # ==========================================

    @commands.hybrid_command(
        name="unwatch",
        description="Remove a course or subject from your watchlist (e.g. !unwatch STSWENG).",
    )
    @check_gatekeeper()
    async def unwatch_command(self, ctx: commands.Context, course_code: str, section: str | None = None):
        """
        Stop drop pings and remove from watchlist following strict scope rules.
        Syntax: !unwatch STSWENG or !unwatch STSWENG S04
        """
        await ctx.defer()
        clean_code = course_code.strip().upper()

        success, reason, remaining = await self.db.remove_user_watch(
            user_id=ctx.author.id,
            course_code=clean_code,
            section_name=section,
        )

        if not success and reason == "BLOCKED_COURSE_SCOPE":
            embed = discord.Embed(
                title="❌ Action Not Allowed",
                description=(
                    f"You are currently tracking the **entire course `{clean_code}`** (all sections).\n\n"
                    f"• You cannot remove individual sections while tracking the whole course.\n"
                    f"• To stop tracking `{clean_code}`, please unwatch the entire course using:\n"
                    f"  `!unwatch {clean_code}`"
                ),
                color=0xEF4444,
            )
            await ctx.send(embed=embed)
            return

        if not success:
            await ctx.send(f"⚠️ `{clean_code}` was not found in your active watchlist. Use `!watchlist` to check.")
            return

        sec_label = "ALL Sections" if not section or section.strip() in ("*", "ALL") else f"Section `{section.strip().upper()}`"
        embed = discord.Embed(
            title="🛑 Unwatch Confirmed",
            description=(
                f"Successfully removed **`{clean_code}`** ({sec_label}) from your watchlist.\n\n"
                f"• Remaining active subscriptions: **{remaining}**\n"
                f"• Use `!watchlist` to view your updated list."
            ),
            color=0xF59E0B,
        )
        await ctx.send(embed=embed)




    # ==========================================
    # !watchlist / !mywatch (EXPANDED SECTIONS)
    # ==========================================

    @commands.hybrid_command(
        name="watchlist",
        aliases=["mywatch"],
        description="Show your watched subjects and live slot availability (e.g. 44/45).",
    )
    @check_gatekeeper()
    async def watchlist_command(self, ctx: commands.Context):
        """
        Displays all watched subjects with current live capacity and open slots.
        Expands all sections if the whole course was added with multi-page interactive pagination.
        Syntax: !watchlist
        """
        await ctx.defer()
        watchlist_data = await self.db.get_user_watchlist_detailed(ctx.author.id)
        pings_enabled = await self.db.get_user_pings_status(ctx.author.id)

        total_pages = get_watchlist_page_count(watchlist_data, per_page=15)
        embed = create_watchlist_detailed_embed(
            username=ctx.author.display_name,
            watchlist_data=watchlist_data,
            pings_enabled=pings_enabled,
            page=1,
            per_page=15,
        )

        if total_pages > 1:
            view = WatchlistPaginationView(
                username=ctx.author.display_name,
                watchlist_data=watchlist_data,
                pings_enabled=pings_enabled,
                current_page=1,
                per_page=15,
                user_id=ctx.author.id,
            )
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)

    # ==========================================
    # !monitored / !list (CONCISE SUMMARY)
    # ==========================================

    @commands.hybrid_command(
        name="monitored",
        aliases=["list"],
        description="Show a concise summary list of what you are currently tracking.",
    )
    @check_gatekeeper()
    async def monitored_command(self, ctx: commands.Context):
        """
        Shows a concise list of your course subscriptions without section clutter.
        Syntax: !monitored
        """
        await ctx.defer()
        summary = await self.db.get_user_monitored_summary(ctx.author.id)
        pings_enabled = await self.db.get_user_pings_status(ctx.author.id)

        embed = create_monitored_summary_embed(
            username=ctx.author.display_name,
            summary_data=summary,
            pings_enabled=pings_enabled,
        )
        await ctx.send(embed=embed)

    # ==========================================
    # !mute & !unmute (TOGGLE PERSONAL PINGS)
    # ==========================================

    @commands.hybrid_command(
        name="mute",
        aliases=["pause"],
        description="Temporarily pause personal DM alerts without removing your watchlist.",
    )
    @check_gatekeeper()
    async def mute_command(self, ctx: commands.Context):
        """Pause personal DM notifications while keeping saved courses."""
        await ctx.defer()
        count = await self.db.toggle_user_pings(ctx.author.id, enabled=False)
        if count == 0:
            await ctx.send("ℹ️ You do not have any courses in your watchlist yet. Use `!watch <code>` to start.")
            return

        embed = discord.Embed(
            title="🔕 DM Notifications Paused",
            description=(
                f"Personal drop notifications for your **{count}** course subscription(s) are now **PAUSED**.\n\n"
                f"• Your saved watchlist remains intact.\n"
                f"• Type `!unmute` anytime to resume notifications."
            ),
            color=0xF59E0B,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="unmute",
        aliases=["resume"],
        description="Resume personal DM drop alerts for your watchlist.",
    )
    @check_gatekeeper()
    async def unmute_command(self, ctx: commands.Context):
        """Resume personal DM notifications."""
        await ctx.defer()
        count = await self.db.toggle_user_pings(ctx.author.id, enabled=True)
        if count == 0:
            await ctx.send("ℹ️ You do not have any courses in your watchlist yet. Use `!watch <code>` to start.")
            return

        embed = discord.Embed(
            title="🔔 DM Notifications Resumed",
            description=(
                f"Personal drop notifications for your **{count}** course subscription(s) are now **ACTIVE**.\n\n"
                f"• You will receive a direct message the moment a slot opens."
            ),
            color=0x006837,
        )
        await ctx.send(embed=embed)

    # ==========================================
    # !status [courses...]
    # ==========================================

    @commands.hybrid_command(
        name="status",
        description="Show live enrollment status and capacity cards for courses.",
    )
    @check_gatekeeper()
    async def status_command(self, ctx: commands.Context, *, courses: str = ""):
        """View live enrollment cards."""
        await ctx.defer()
        codes = [c.strip().upper() for c in courses.split() if c.strip()]

        if codes:
            target_courses = []
            for code in codes:
                course = await self.db.get_monitored_course(code)
                if course:
                    target_courses.append(course)
                else:
                    matches = await self.db.search_catalog(code)
                    if matches:
                        target_courses.append(matches[0])
                    else:
                        await ctx.send(f"⚠️ Course code `{code}` was not found in the pool or catalog.")

            if not target_courses:
                return

            for course in target_courses[:5]:
                cid = course.get("course_id")
                code = course.get("course_code")
                name = course.get("course_name", "")
                sections = await self.db.get_all_section_states(code)
                if not sections and self.engine.is_connected:
                    try:
                        sections = await self.engine.api.fetch_section_data(cid)
                    except Exception:
                        pass

                embed = create_status_embed(code, name, sections)
                await ctx.send(embed=embed)
        else:
            # High-level clean status summary
            all_monitored = await self.db.get_monitored_courses(active_only=True)
            total_monitored = len(all_monitored)
            ge_lc_count = sum(1 for c in all_monitored if classify_course(c.get("course_code", "")).is_ge_lc)
            college_count = max(0, total_monitored - ge_lc_count)

            all_sections = await self.db.get_all_section_states()
            total_sections_count = len(all_sections)
            open_sections_count = sum(1 for s in all_sections if s.get("open_slots", 0) > 0)

            embed = create_system_status_overview_embed(
                bot_active=self.engine.bot_active,
                poll_interval=self.engine.poll_interval,
                total_monitored=total_monitored,
                ge_lc_count=ge_lc_count,
                college_count=college_count,
                open_sections_count=open_sections_count,
                total_sections_count=total_sections_count,
            )
            await ctx.send(embed=embed)

    # ==========================================
    # !stats / !analytics
    # ==========================================

    @commands.hybrid_command(
        name="stats",
        aliases=["analytics"],
        description="Show DLSU Course Drop Analytics, peak drop windows, and demand leaderboard.",
    )
    @check_gatekeeper()
    async def stats_command(self, ctx: commands.Context):
        """
        Displays drop analytics: peak activity windows, most contested courses, and recent drop events.
        Syntax: !stats
        """
        await ctx.defer()
        analytics_data = await self.db.get_drop_analytics()
        embed = create_drop_analytics_embed(analytics_data)
        await ctx.send(embed=embed)

    # ==========================================
    # !search <query> (IN-DISCORD COURSE FINDER)
    # ==========================================

    @commands.hybrid_command(
        name="search",
        aliases=["find", "catalog"],
        description="Search DLSU courses by code or title keywords (e.g. !search web dev).",
    )
    @check_gatekeeper()
    async def search_command(self, ctx: commands.Context, *, query: str):
        """
        Searches CourseFinder catalog by code or keywords.
        Syntax: !search CCPROG or !search database
        """
        await ctx.defer()
        clean_query = query.strip()
        results = await self.db.search_catalog_extended(clean_query)
        embed = create_course_search_embed(clean_query, results)
        await ctx.send(embed=embed)

    # ==========================================
    # !courses / !allmonitored (PUBLIC MONITORED POOL)
    # ==========================================

    @commands.hybrid_command(
        name="courses",
        aliases=["allmonitored", "monitoredcourses", "pool", "activecourses"],
        description="View all courses currently being monitored.",
    )
    @check_gatekeeper()
    async def courses_command(self, ctx: commands.Context):
        """
        Shows the full multi-page catalog of courses actively polled every 15 seconds.
        Syntax: !courses
        """
        await ctx.defer()
        courses = await self.db.get_monitored_courses(active_only=True)
        total_pages = get_monitored_courses_page_count(courses, per_page=15)

        embed = create_monitored_courses_embed(
            courses=courses,
            page=1,
            per_page=15,
        )

        if total_pages > 1:
            view = MonitoredCoursesPaginationView(
                courses=courses,
                current_page=1,
                per_page=15,
                user_id=ctx.author.id,
            )
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)

    # ==========================================
    # !courseinfo / !sections (PUBLIC SECTION INSPECTOR)
    # ==========================================

    @commands.hybrid_command(
        name="courseinfo",
        aliases=["sections", "inspectcourse", "sectioninfo"],
        description="Inspect sections, capacities, professors, and schedules for any DLSU course.",
    )
    @check_gatekeeper()
    async def course_info_command(self, ctx: commands.Context, course_code: str):
        """
        Inspect live section breakdown for any course.
        Syntax: !courseinfo STSWENG or !courseinfo SAS2000
        """
        await ctx.defer()
        clean_code = course_code.strip().upper()

        course = await self.db.get_monitored_course(clean_code)
        if not course or not str(course.get("course_id", "")).isdigit():
            catalog_match = await self.db.search_catalog(clean_code)
            if not catalog_match and self.engine and hasattr(self.engine, "api"):
                try:
                    auth = await self.db.get_master_auth()
                    campus_no = auth.get("campus_no") or 7 if auth else 7
                    academic_session = auth.get("academic_session") or 155 if auth else 155
                    catalog = await self.engine.api.fetch_course_catalog(campus_no=campus_no, academic_session=academic_session)
                    for item in catalog:
                        await self.db.upsert_catalog_course(item["course_id"], item["course_code"], item.get("course_name", ""))
                    catalog_match = await self.db.search_catalog(clean_code)
                except Exception:
                    pass

            if catalog_match and str(catalog_match[0]["course_id"]).isdigit():
                best = catalog_match[0]
                course = {
                    "course_id": str(best["course_id"]).strip(),
                    "course_code": best["course_code"],
                    "course_name": best.get("course_name", ""),
                }
                await self.db.add_monitored_course(
                    course_id=course["course_id"],
                    course_code=course["course_code"],
                    course_name=course["course_name"],
                    added_by="StudentCourseInfoResolver",
                )
            else:
                course = {
                    "course_id": clean_code,
                    "course_code": clean_code,
                    "course_name": clean_code,
                }

        cid = course["course_id"]
        code = course["course_code"]
        name = course.get("course_name", "")

        try:
            sections = await self.engine.api.fetch_section_data(cid)
            if sections:
                for sec in sections:
                    await self.db.upsert_section_state(
                        course_id=cid,
                        course_code=code,
                        section_name=sec.get("section_name", ""),
                        capacity=sec.get("capacity", 0),
                        enlisted=sec.get("enlisted", 0),
                        open_slots=sec.get("open_slots", 0),
                        teacher=sec.get("teacher", ""),
                        schedule=sec.get("schedule", ""),
                    )

            total_pages = get_courseinfo_page_count(sections, per_page=12)
            embed = create_admin_course_inspection_embed(
                course_code=code,
                course_name=name,
                course_id=cid,
                sections=sections,
                page=1,
                per_page=12,
            )

            if total_pages > 1:
                view = CourseInfoPaginationView(
                    course_code=code,
                    course_name=name,
                    course_id=cid,
                    sections=sections,
                    current_page=1,
                    per_page=12,
                    user_id=ctx.author.id,
                )
                await ctx.send(embed=embed, view=view)
            else:
                await ctx.send(embed=embed)
        except PermissionError as pe:
            await ctx.send(f"⚠️ **Session Disconnected:** `{pe}`\nAn administrator must refresh cookies.")
        except Exception as e:
            await ctx.send(f"❌ Failed to fetch sections for **`{clean_code}`**: `{e}`")


async def setup(bot: commands.Bot):
    db = getattr(bot, "db", None)
    engine = getattr(bot, "engine", None)
    await bot.add_cog(SniperCog(bot, db, engine))

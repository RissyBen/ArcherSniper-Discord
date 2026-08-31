"""
ArcherSniper - Role-Aware Interactive Help System
Dynamically adjusts command listings and navigation buttons based on whether the user is an Administrator or a Student.
"""

from datetime import datetime, timezone
import discord
from discord.ext import commands

from config import (
    COLOR_DLSU_GREEN,
    COMMAND_PREFIX,
    DLSU_LOGO_URL,
    ANIMO_SYS_URL,
    MLS_URL,
    DLSU_BASE_URL,
    ADMIN_ROLE_NAME,
    ADMIN_USER_IDS,
)


def user_is_owner(user: discord.User | discord.Member, guild: discord.Guild | None) -> bool:
    """Helper to check if a user is the server owner or master admin."""
    if user.id in ADMIN_USER_IDS:
        return True
    if guild and (user.id == guild.owner_id or user == guild.owner):
        return True
    return False


def user_is_admin(user: discord.User | discord.Member, guild: discord.Guild | None) -> bool:
    """Helper to check if a user is an administrator or has the ArcherSniper Admin role."""
    if user.id in ADMIN_USER_IDS:
        return True
    if guild:
        if guild.owner_id == user.id or user == guild.owner:
            return True
        if isinstance(user, discord.Member):
            if user.guild_permissions.administrator:
                return True
            if any(r.name == ADMIN_ROLE_NAME for r in user.roles):
                return True
    return False


# ==========================================
# EMBED BUILDERS
# ==========================================

def get_student_overview_embed() -> discord.Embed:
    """Clean landing embed for normal student members (No admin commands visible)."""
    embed = discord.Embed(
        title="🏹 ArcherSniper — Student Command Center",
        description=(
            "**Real-time slot monitor for DLSU CourseFinder.**\n"
            "Get instantly pinged in your private DMs the moment slots drop.\n\n"
            f"`Prefix:` **`{COMMAND_PREFIX}`**   •   `Slash:` **`/`**   •   `Heartbeat:` **`24/7 Active`**"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🎯 Student Commands",
        value=(
            f"> `{COMMAND_PREFIX}watch <course> [sec]` — Subscribe to instant DM drop alerts\n"
            f"> `{COMMAND_PREFIX}unwatch <course> [sec]` — Remove from watchlist\n"
            f"> `{COMMAND_PREFIX}watchlist` — View live capacity (e.g. `44/45 [1 Open]`)\n"
            f"> `{COMMAND_PREFIX}courses` — Browse all server-monitored courses\n"
            f"> `{COMMAND_PREFIX}courseinfo <course>` — Inspect sections, profs & schedule\n"
            f"> `{COMMAND_PREFIX}search <query>` — Search courses across DLSU catalog\n"
            f"> `{COMMAND_PREFIX}stats` — View drop analytics & peak hours\n"
            f"> `{COMMAND_PREFIX}mute` / `{COMMAND_PREFIX}unmute` — Pause or resume DM alerts\n"
            f"> `{COMMAND_PREFIX}status [code]` — Live enrollment overview & bot ping"
        ),
        inline=False,
    )

    embed.add_field(
        name="💡 Quick Start",
        value=(
            f"**1.** Search courses: `{COMMAND_PREFIX}search CCPROG`\n"
            f"**2.** Track course: `{COMMAND_PREFIX}watch STSWENG` or `{COMMAND_PREFIX}watch STSWENG S04`\n"
            f"**3.** Check your list: `{COMMAND_PREFIX}watchlist`\n"
            f"**4.** ArcherSniper will DM you the instant a slot opens!"
        ),
        inline=False,
    )

    embed.set_thumbnail(url=DLSU_LOGO_URL)
    embed.set_footer(text="ArcherSniper DLSU • Click buttons below to browse guides")
    return embed


def get_admin_overview_embed(is_owner: bool = False) -> discord.Embed:
    """Full command center embed for administrators."""
    embed = discord.Embed(
        title="🏹 ArcherSniper — Admin Command Center",
        description=(
            "**Real-time slot monitor for DLSU CourseFinder.**\n"
            "Full command center with student features and administrative engine controls.\n\n"
            f"`Prefix:` **`{COMMAND_PREFIX}`**   •   `Slash:` **`/`**   •   `Heartbeat:` **`60s Pulse`**"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🎯 Student Commands",
        value=(
            f"> `{COMMAND_PREFIX}watch <course> [sec]` — Subscribe to DM alerts\n"
            f"> `{COMMAND_PREFIX}unwatch <course> [sec]` — Remove from watchlist\n"
            f"> `{COMMAND_PREFIX}watchlist` — View live capacity\n"
            f"> `{COMMAND_PREFIX}courses` — Browse all server-monitored courses\n"
            f"> `{COMMAND_PREFIX}courseinfo <course>` — Inspect sections, profs & sched\n"
            f"> `{COMMAND_PREFIX}search <query>` — CourseFinder catalog search\n"
            f"> `{COMMAND_PREFIX}stats` — View drop analytics & peak windows\n"
            f"> `{COMMAND_PREFIX}mute` / `{COMMAND_PREFIX}unmute` — Toggle DM alerts"
        ),
        inline=False,
    )

    embed.add_field(
        name="⚙️ Admin & Engine Controls",
        value=(
            f"> `{COMMAND_PREFIX}setupchannels` — Auto-provision categories & feeds\n"
            f"> `{COMMAND_PREFIX}start` / `{COMMAND_PREFIX}stop` — Turn ON/OFF bot access\n"
            f"> `{COMMAND_PREFIX}sweep [filter]` — Interactive open sections browser\n"
            f"> `{COMMAND_PREFIX}logs [type] [n]` — Real-time logs (`watchdog`, `drops`, `dms`, `autodiscovery`)\n"
            f"> `{COMMAND_PREFIX}fetchdata [code]` — Inspect parsed JSON data from CourseFinder\n"
            f"> `{COMMAND_PREFIX}session` / `{COMMAND_PREFIX}cookies` — Inspect active cookies & headers\n"
            f"> `{COMMAND_PREFIX}sync` — Auto-discover & sync DLSU course catalog\n"
            f"> `{COMMAND_PREFIX}startgelc` / `{COMMAND_PREFIX}stopgelc` — Toggle GE/LC feeds\n"
            f"> `{COMMAND_PREFIX}userstatus <@member>` — Inspect member watchlist & mute state\n"
            f"> `{COMMAND_PREFIX}prune` — End-of-term watchlist cleanup & vacuum\n"
            f"> `{COMMAND_PREFIX}setcurl <curl>` / `{COMMAND_PREFIX}cookie <str>` — Link master browser session\n"
            f"> `{COMMAND_PREFIX}bookmarklet` — Get 1-click Chrome refresh bookmark\n"
            f"> `{COMMAND_PREFIX}health` — Live diagnostics & benchmark dashboard"
        ),
        inline=False,
    )

    if is_owner:
        embed.add_field(
            name="👑 Server Owner Controls",
            value=f"> `{COMMAND_PREFIX}admin <@member>` — Grant or revoke the ArcherSniper Admin role",
            inline=False,
        )

    embed.set_thumbnail(url=DLSU_LOGO_URL)
    embed.set_footer(text="Administrator Access Active • ArcherSniper")
    return embed


def get_student_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎯 Student Commands Guide",
        description=(
            "**Commands available to all students for tracking courses and receiving live DM alerts.**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🔔 !watch <course> [section]",
        value=(
            "Subscribe to instant slot drop notifications in your private DMs.\n"
            "• Track whole course: `!watch STSWENG`\n"
            "• Track specific subject: `!watch STSWENG S04`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🔕 !unwatch <course> [section]",
        value=(
            "Remove a course or subject from your watchlist.\n"
            "• Unwatch course: `!unwatch STSWENG`\n"
            "• Unwatch subject: `!unwatch STSWENG S04`\n"
            "*(Note: If you watched the whole course, unwatch using `!unwatch STSWENG`)*"
        ),
        inline=False,
    )

    embed.add_field(
        name="📊 !watchlist",
        value="View all your watched subjects with live section capacities and open slots (e.g. `44/45 [1 Open]`).\n`!watchlist`",
        inline=False,
    )

    embed.add_field(
        name="📚 !courses",
        value="Browse all courses currently monitored 24/7 with interactive multi-page navigation.\n`!courses`",
        inline=True,
    )

    embed.add_field(
        name="🏛️ !courseinfo <course>",
        value="Inspect all sections, capacities, professors, and schedules for any DLSU subject.\n`!courseinfo SAS2000`",
        inline=True,
    )

    embed.add_field(
        name="🔍 !search <query>",
        value="Search DLSU courses by code or title keywords without opening a browser.\n`!search web dev`",
        inline=True,
    )

    embed.add_field(
        name="📈 !stats",
        value="View peak drop activity hours, demand leaderboards, and recent fill speeds.\n`!stats`",
        inline=True,
    )

    embed.add_field(
        name="🔕 !mute / !unmute",
        value="Temporarily pause or resume DM notifications without losing your watchlist.\n`!mute` / `!unmute`",
        inline=True,
    )

    embed.add_field(
        name="📊 !status [courses...]",
        value="View live capacity progress bars for any course.\n`!status STSWENG CSARCH1`",
        inline=True,
    )

    embed.set_footer(text="ArcherSniper DLSU • Animo La Salle 🏹")
    return embed


def get_admin_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Admin & Engine Controls Guide",
        description=(
            "**Administrative commands for managing the watchdog, server channels, session, and member watchlists.**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xF59E0B,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🏛️ !setupchannels",
        value=(
            "Auto-provisions categories, feeds, and channels:\n"
            "• **Announcements & Hub:** `#📢-announcements`, `#🤖-bot-commands`\n"
            "• **College Feeds:** `#🎯-ge-lc-feed`, `#💻-ccs-drops`, `#💼-rvrcob-drops`, etc.\n"
            "• **Admin HQ:** `#🔒-admin-commands`, `#🚨-admin-disconnects`, `#💓-admin-heartbeat-log`, `#📬-admin-dm-logs`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🟢 !start & 🔴 !stop",
        value=(
            "• `!start`: Activates bot for all members & announces in `#📢-announcements`.\n"
            "• `!stop`: Deactivates bot (maintenance mode) & announces in `#📢-announcements`."
        ),
        inline=False,
    )

    embed.add_field(
        name="🏛️ !courseinfo <course>",
        value="Live search a course to view all sections, capacities, professors, and schedules.\n`!courseinfo STSWENG`",
        inline=False,
    )

    embed.add_field(
        name="🔍 !userstatus <@member>",
        value="Inspect a member's active watchlist, live section capacity, and mute/unmute state.\n`!userstatus @fluffle`",
        inline=False,
    )

    embed.add_field(
        name="📊 !fetchdata [course]",
        value="Inspect exact parsed JSON sections or full cycle dump from CourseFinder API.\n`!fetchdata STSWENG` or `!fetchdata`",
        inline=False,
    )

    embed.add_field(
        name="🔑 !session / !cookies",
        value="Inspect stored master session cookies, tokens, and active request headers.\n`!session` or `!cookies`",
        inline=False,
    )

    embed.add_field(
        name="⚡ !sweep [filter]",
        value="Interactive 1-message open sections browser with clickable pagination.\n`!sweep` or `!sweep CCS`",
        inline=True,
    )

    embed.add_field(
        name="📜 !logs [type] [lines]",
        value="View real-time text logs (`watchdog`, `autodiscovery`, `drops`, `dms`, `scraper`).\n`!logs watchdog 15`",
        inline=True,
    )

    embed.add_field(
        name="🔄 !sync",
        value="Auto-discover & sync DLSU CourseFinder catalog into SQLite.\n`!sync`",
        inline=True,
    )

    embed.add_field(
        name="🔍 !inspectcourse <course>",
        value="Admin deep-dive into database section states & enrolled counts.\n`!inspectcourse STSWENG`",
        inline=True,
    )

    embed.add_field(
        name="🧹 !prune",
        value="End-of-term watchlist cleanup and SQLite database vacuum.\n`!prune`",
        inline=True,
    )

    embed.add_field(
        name="🍪 !cookie <string> & 🔑 !setcurl <curl>",
        value="Link master browser session via direct cookie string or full cURL.\n`!cookie ASP.NET_SessionId=...`\n`!setcurl curl ...`",
        inline=False,
    )

    embed.add_field(
        name="⚡ !bookmarklet",
        value="Get 1-Click Chrome Bookmarklet for instant 1-second session refreshes.\n`!bookmarklet`",
        inline=True,
    )

    embed.add_field(
        name="🗑️ !removecurl",
        value="Clear and wipe stored Master cURL browser session cookies.\n`!removecurl`",
        inline=True,
    )

    embed.add_field(
        name="🎯 !startgelc / !stopgelc",
        value="Toggle universal 24/7 GE/LC background monitoring stream.\n`!startgelc` / `!stopgelc`",
        inline=True,
    )

    embed.add_field(
        name="🛡️ !health",
        value="View live watchdog diagnostics, token status, and keep-alive metrics.\n`!health`",
        inline=True,
    )

    embed.set_footer(text="ArcherSniper Admin Controls")
    return embed


def get_curl_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔑 Session Authentication & Cookie Guide",
        description=(
            "**How to link or refresh your Archer's Hub session in ArcherSniper.**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x3B82F6,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🥇 Method 1: Direct Cookie Copy (Fastest — 5 Seconds)",
        value=(
            "1. Open [archershub.dlsu.edu.ph/CourseFinder/](https://archershub.dlsu.edu.ph/CourseFinder/) in Chrome.\n"
            "2. Press `F12` (or right-click ➔ **Inspect**) and click the **Network** tab.\n"
            "3. Search any subject (e.g. `STSWENG`) to trigger `GetCFData`.\n"
            "4. Click `GetCFData` ➔ under **Request Headers**, copy the text next to `Cookie:`.\n"
            "5. In `#🔒-admin-commands`, paste:\n"
            "```text\n!cookie ASP.NET_SessionId=...; .ASPXAUTH=...\n```"
        ),
        inline=False,
    )

    embed.add_field(
        name="⚡ Method 2: 1-Click Chrome Bookmarklet (1 Click)",
        value=(
            "Type `!bookmarklet` in Discord, copy the JavaScript snippet into a Chrome Bookmark, "
            "and simply click the bookmark while on Archer's Hub to refresh in 1 second!"
        ),
        inline=False,
    )

    embed.add_field(
        name="📜 Method 3: Full cURL Copy",
        value=(
            "In Chrome Network tab, right-click `GetCFData` ➔ **Copy as cURL (bash)** *(or cmd)*.\n"
            "Then paste in `#🔒-admin-commands`:\n"
            "```text\n!setcurl <paste_your_copied_curl_here>\n```"
        ),
        inline=False,
    )

    embed.set_footer(text="ArcherSniper Tier 1 & Tier 2 keep your session alive 24/7 automatically!")
    return embed


# ==========================================
# INTERACTIVE BUTTON VIEWS
# ==========================================

class StudentHelpButtonView(discord.ui.View):
    """Button view for student members — no admin buttons present."""
    def __init__(self, current_tab: str = "overview"):
        super().__init__(timeout=300)
        self.current_tab = current_tab
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()

        btn_overview = discord.ui.Button(
            label="Overview",
            style=discord.ButtonStyle.primary if self.current_tab == "overview" else discord.ButtonStyle.secondary,
            emoji="📖",
            custom_id="student_tab_overview",
            row=0,
        )
        btn_student = discord.ui.Button(
            label="Student Guide",
            style=discord.ButtonStyle.primary if self.current_tab == "student" else discord.ButtonStyle.secondary,
            emoji="🎯",
            custom_id="student_tab_student",
            row=0,
        )

        btn_overview.callback = self._on_overview
        btn_student.callback = self._on_student

        self.add_item(btn_overview)
        self.add_item(btn_student)

        # Quick Portal Links
        self.add_item(discord.ui.Button(label="CourseFinder", url=f"{DLSU_BASE_URL}/CourseFinder/", emoji="🎯", row=1))
        self.add_item(discord.ui.Button(label="Archer's Hub", url=f"{DLSU_BASE_URL}/", emoji="🏹", row=1))
        self.add_item(discord.ui.Button(label="My.DLSU", url=MLS_URL, emoji="🎓", row=1))

    async def _on_overview(self, interaction: discord.Interaction):
        self.current_tab = "overview"
        self._build_buttons()
        await interaction.response.edit_message(embed=get_student_overview_embed(), view=self)

    async def _on_student(self, interaction: discord.Interaction):
        self.current_tab = "student"
        self._build_buttons()
        await interaction.response.edit_message(embed=get_student_embed(), view=self)


class AdminHelpButtonView(discord.ui.View):
    """Button view for administrators — full access to Admin controls and cURL guide."""
    def __init__(self, current_tab: str = "overview"):
        super().__init__(timeout=300)
        self.current_tab = current_tab
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()

        btn_overview = discord.ui.Button(
            label="Overview",
            style=discord.ButtonStyle.primary if self.current_tab == "overview" else discord.ButtonStyle.secondary,
            emoji="📖",
            custom_id="admin_tab_overview",
            row=0,
        )
        btn_student = discord.ui.Button(
            label="Student Guide",
            style=discord.ButtonStyle.primary if self.current_tab == "student" else discord.ButtonStyle.secondary,
            emoji="🎯",
            custom_id="admin_tab_student",
            row=0,
        )
        btn_admin = discord.ui.Button(
            label="Admin Controls",
            style=discord.ButtonStyle.primary if self.current_tab == "admin" else discord.ButtonStyle.secondary,
            emoji="⚙️",
            custom_id="admin_tab_admin",
            row=0,
        )
        btn_curl = discord.ui.Button(
            label="Auth & Cookies",
            style=discord.ButtonStyle.primary if self.current_tab == "curl" else discord.ButtonStyle.secondary,
            emoji="🔑",
            custom_id="admin_tab_curl",
            row=0,
        )

        btn_overview.callback = self._on_overview
        btn_student.callback = self._on_student
        btn_admin.callback = self._on_admin
        btn_curl.callback = self._on_curl

        self.add_item(btn_overview)
        self.add_item(btn_student)
        self.add_item(btn_admin)
        self.add_item(btn_curl)

        # Quick Portal Links
        self.add_item(discord.ui.Button(label="CourseFinder", url=f"{DLSU_BASE_URL}/CourseFinder/", emoji="🎯", row=1))
        self.add_item(discord.ui.Button(label="Archer's Hub", url=f"{DLSU_BASE_URL}/", emoji="🏹", row=1))
        self.add_item(discord.ui.Button(label="My.DLSU", url=MLS_URL, emoji="🎓", row=1))

    async def _on_overview(self, interaction: discord.Interaction):
        self.current_tab = "overview"
        self._build_buttons()
        await interaction.response.edit_message(embed=get_admin_overview_embed(), view=self)

    async def _on_student(self, interaction: discord.Interaction):
        self.current_tab = "student"
        self._build_buttons()
        await interaction.response.edit_message(embed=get_student_embed(), view=self)

    async def _on_admin(self, interaction: discord.Interaction):
        self.current_tab = "admin"
        self._build_buttons()
        await interaction.response.edit_message(embed=get_admin_embed(), view=self)

    async def _on_curl(self, interaction: discord.Interaction):
        self.current_tab = "curl"
        self._build_buttons()
        await interaction.response.edit_message(embed=get_curl_embed(), view=self)


# ==========================================
# HELP COG
# ==========================================

class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="help",
        aliases=["adminhelp", "commands", "guide", "sniperhelp"],
        description="Open the ArcherSniper command center and user guides.",
    )
    async def help_command(self, ctx: commands.Context, category: str | None = None):
        """Open the role-aware interactive ArcherSniper command guide."""
        is_admin = user_is_admin(ctx.author, ctx.guild)
        is_owner = user_is_owner(ctx.author, ctx.guild)

        invoked_cmd = ctx.invoked_with.lower() if ctx.invoked_with else ""
        if invoked_cmd == "adminhelp" and not category:
            category = "admin"

        if category:
            cat = category.strip().lower()
            if cat in ("student", "sniper", "watch", "user"):
                view = AdminHelpButtonView("student") if is_admin else StudentHelpButtonView("student")
                await ctx.send(embed=get_student_embed(), view=view)
            elif is_admin and cat in ("admin", "setup", "config"):
                await ctx.send(embed=get_admin_embed(), view=AdminHelpButtonView("admin"))
            elif is_admin and cat in ("curl", "token", "guide", "auth"):
                await ctx.send(embed=get_curl_embed(), view=AdminHelpButtonView("curl"))
            elif not is_admin and cat in ("admin", "setup", "config", "curl", "token"):
                await ctx.send("🔒 **Admin guides are only accessible to server administrators.**", ephemeral=True)
            else:
                embed = get_admin_overview_embed(is_owner=is_owner) if is_admin else get_student_overview_embed()
                view = AdminHelpButtonView("overview") if is_admin else StudentHelpButtonView("overview")
                await ctx.send(embed=embed, view=view)
        else:
            embed = get_admin_overview_embed(is_owner=is_owner) if is_admin else get_student_overview_embed()
            view = AdminHelpButtonView("overview") if is_admin else StudentHelpButtonView("overview")
            await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    bot.help_command = None
    await bot.add_cog(HelpCog(bot))

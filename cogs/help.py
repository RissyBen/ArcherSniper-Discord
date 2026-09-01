"""
ArcherSniper - Role-Aware Interactive Help System
Dynamically adjusts command listings and navigation buttons based on whether the user is an Administrator or a Student.
"""

from datetime import datetime, timezone
import discord
from discord.ext import commands

from config import (
    COLOR_DLSU_GREEN,
    COLOR_GOLD,
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
            "Get instantly notified in your private DMs the moment slots open up.\n\n"
            f"> `Command Prefix:` **`{COMMAND_PREFIX}`**   •   `Slash Commands:` **`/`**\n"
            f"> `Scraper Engine:` **`15s Scrape Cadence`**   •   `Status:` **`🟢 24/7 Active`**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🎯 Student Quick Commands",
        value=(
            f"• `{COMMAND_PREFIX}watch <course> [sec]` — Subscribe to instant DM drop alerts\n"
            f"• `{COMMAND_PREFIX}unwatch <course> [sec]` — Remove from your personal watchlist\n"
            f"• `{COMMAND_PREFIX}watchlist` — View live capacity progress bars (e.g. `44/45 [1 Open]`)\n"
            f"• `{COMMAND_PREFIX}courses` — Browse all server-monitored courses\n"
            f"• `{COMMAND_PREFIX}courseinfo <course>` — Inspect section lists, profs, & schedules\n"
            f"• `{COMMAND_PREFIX}search <query>` — Search courses across the DLSU catalog\n"
            f"• `{COMMAND_PREFIX}stats` — View drop analytics & peak enlistment windows\n"
            f"• `{COMMAND_PREFIX}status` — View watchdog status & live open section counts\n"
            f"• `{COMMAND_PREFIX}ping` — View bot WebSocket latency\n"
            f"• `{COMMAND_PREFIX}mute` / `{COMMAND_PREFIX}unmute` — Pause or resume DM alerts"
        ),
        inline=False,
    )

    embed.add_field(
        name="💡 Quick Start Tutorial (4 Steps)",
        value=(
            f"**1.** Search for a course code: `{COMMAND_PREFIX}search CCPROG`\n"
            f"**2.** Track whole course or section: `{COMMAND_PREFIX}watch STSWENG` or `{COMMAND_PREFIX}watch STSWENG S04`\n"
            f"**3.** Check your active list: `{COMMAND_PREFIX}watchlist`\n"
            f"**4.** ArcherSniper will DM you the instant a slot opens!"
        ),
        inline=False,
    )

    embed.set_thumbnail(url=DLSU_LOGO_URL)
    embed.set_footer(text="ArcherSniper DLSU • Use the dropdown menu below to explore guides")
    return embed


def get_admin_overview_embed(is_owner: bool = False) -> discord.Embed:
    """Spacious high-level command center landing embed for administrators."""
    embed = discord.Embed(
        title="🛡️ ArcherSniper — Admin Command Center",
        description=(
            "**DLSU CourseFinder 24/7 Watchdog & Administration Hub.**\n"
            "Full command center with categorized modules for engine controls, logs, auth, and channels.\n\n"
            f"> `Command Prefix:` **`{COMMAND_PREFIX}`**   •   `Slash Commands:` **`/`**\n"
            f"> `Engine Cadence:` **`15s Polling Loop`**   •   `Heartbeat:` **`60s Keep-Alive Pulse`**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="📂 Available Administrative Modules",
        value=(
            "Use the **Interactive Dropdown Menu** below to view detailed syntax and examples:\n\n"
            "• ⚙️ **Engine & Watchdog Suite** — `!start`, `!stop`, `!sweep`, `!startgelc`, `!interval`, `!sync`\n"
            "• 📊 **Logs & Data Inspection** — `!fetchdata`, `!logs`, `!scraperlog`, `!userstatus`, `!inspectcourse`\n"
            "• 🔑 **Session Auth & Tokens** — `!session`, `!cookies`, `!setcurl`, `!bookmarklet`, `!removecurl`\n"
            "• 🏛️ **Server Provisioning & Roles** — `!setupchannels`, `!prune`, `!health`, `!admin`\n"
            "• 🎯 **Student Commands Guide** — All 8 public student commands"
        ),
        inline=False,
    )

    if is_owner:
        embed.add_field(
            name="👑 Server Owner Controls",
            value=f"> `{COMMAND_PREFIX}admin <@member>` — Grant or revoke the ArcherSniper Admin role dynamically.",
            inline=False,
        )

    embed.set_thumbnail(url=DLSU_LOGO_URL)
    embed.set_footer(text="Administrator Access Active • Select a category from the dropdown below")
    return embed


def get_student_embed() -> discord.Embed:
    """Spacious, detailed command guide for all student features."""
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
            "> • Whole Course: `!watch STSWENG` *(Alerts for ANY section)*\n"
            "> • Specific Section: `!watch STSWENG S04` *(Alerts only for S04)*"
        ),
        inline=False,
    )

    embed.add_field(
        name="🔕 !unwatch <course> [section]",
        value=(
            "Remove a course or specific section from your watchlist.\n"
            "> • Unwatch Course: `!unwatch STSWENG`\n"
            "> • Unwatch Section: `!unwatch STSWENG S04`\n"
            "> • Wipe All: `!unwatch all`"
        ),
        inline=False,
    )

    embed.add_field(
        name="📊 !watchlist (or !mycourses)",
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
        name="📈 !stats (or !analytics)",
        value="View peak drop activity hours, demand leaderboards, and recent fill speeds.\n`!stats`",
        inline=True,
    )

    embed.add_field(
        name="🔕 !mute / !unmute",
        value="Temporarily pause or resume DM notifications without losing your watchlist.\n`!mute` / `!unmute`",
        inline=True,
    )

    embed.set_footer(text="ArcherSniper DLSU • Animo La Salle 🏹")
    return embed


def get_admin_engine_embed() -> discord.Embed:
    """Spacious command guide for Engine & Watchdog controls."""
    embed = discord.Embed(
        title="⚙️ Module: Engine & Watchdog Controls",
        description=(
            "**Core commands for managing the 24/7 background scraper, cycle intervals, and catalog sync.**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x3B82F6,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🟢 !start  &  🔴 !stop",
        value=(
            "Master gatekeeper toggle for bot functionality:\n"
            "> • `!start` — Activates background polling and opens user access.\n"
            "> • `!stop` — Pauses scraper and puts bot in maintenance mode."
        ),
        inline=False,
    )

    embed.add_field(
        name="⚡ !sweep [filter]",
        value=(
            "Interactive open sections browser with clickable pagination buttons.\n"
            "> • Sweep All: `!sweep`\n"
            "> • Filter by College/Course: `!sweep CCS` or `!sweep GEWORLD`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🎯 !startgelc  &  !stopgelc",
        value="Toggle universal 24/7 GE/LC background monitoring stream.\n`!startgelc` / `!stopgelc`",
        inline=True,
    )

    embed.add_field(
        name="⏱️ !interval <time>",
        value="Change the scraper poll interval (default: 15s).\n`!interval 15s` or `!interval 1m`",
        inline=True,
    )

    embed.add_field(
        name="🔄 !sync",
        value="Auto-discover & sync all 2,600+ DLSU courses into SQLite (locks real active IDs).\n`!sync`",
        inline=True,
    )

    embed.add_field(
        name="🧪 !simulate <course> <sec> <open> [prev]",
        value="Simulate synthetic slot deltas to test instant DM alerts, feed cards, & logs.\n`!simulate GEMATMW A54D 2 1`",
        inline=False,
    )

    embed.add_field(
        name="➕ !add <course>  &  ➖ !remove <course>",
        value="Manually add or remove a specific course from 24/7 background monitoring.\n`!add CSARCH1` / `!remove CSARCH1`",
        inline=False,
    )

    embed.set_footer(text="ArcherSniper Engine Suite • DLSU CourseFinder")
    return embed


def get_admin_data_embed() -> discord.Embed:
    """Spacious command guide for Logs & Data Inspection."""
    embed = discord.Embed(
        title="📊 Module: Logs & Data Inspection",
        description=(
            "**Real-time log readers, parsed JSON data inspectors, and member watchlist audits.**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x10B981,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="📊 !fetchdata [course] (or !rawdata)",
        value=(
            "Inspect live or latest parsed JSON section data fetched from DLSU CourseFinder:\n"
            "> • Single Subject: `!fetchdata STSWENG` *(Outputs exact capacity, enrolled, open, profs)*\n"
            "> • Full Cycle Dump: `!fetchdata` *(Summarizes latest 15s cycle & attaches full JSON)*"
        ),
        inline=False,
    )

    embed.add_field(
        name="📜 !logs [type] [lines]",
        value=(
            "Direct in-Discord real-time log inspector:\n"
            "> • `!logs watchdog 15` — Polling loop speeds and cycle timings\n"
            "> • `!logs drops 10` — Live slot drop events history\n"
            "> • `!logs dms 10` — Student DM dispatch log\n"
            "> • `!logs autodiscovery 5` — Course catalog discovery sync log\n"
            "> • `!logs heartbeat 10` — 60-second keep-alive pulse log"
        ),
        inline=False,
    )

    embed.add_field(
        name="📋 !scraperlog [lines]",
        value="View raw 15s scraper loop fetch lines.\n`!scraperlog 20`",
        inline=True,
    )

    embed.add_field(
        name="🔍 !userstatus <@member>",
        value="Inspect member's active watchlist, live capacities, and mute state.\n`!userstatus @member`",
        inline=True,
    )

    embed.add_field(
        name="🏛️ !inspectcourse <course>",
        value="Admin deep-dive into database section states & enrolled counts.\n`!inspectcourse STSWENG`",
        inline=True,
    )

    embed.set_footer(text="ArcherSniper Diagnostics • Real-Time Data Pipeline")
    return embed


def get_admin_auth_embed() -> discord.Embed:
    """Spacious command guide for Master Session Authentication & Cookies."""
    embed = discord.Embed(
        title="🔑 Module: Session Auth & Token Management",
        description=(
            "**Tools for managing browser cookies, cURL headers, and keep-alive session health.**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xF59E0B,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🔑 !session  (or !cookies, !authinfo)",
        value=(
            "Inspect stored master session cookies, active request headers, and connection age.\n"
            "> Shows masked `.ASPXAUTH`, `ASP.NET_SessionId`, `RequestVerificationToken`, and latency."
        ),
        inline=False,
    )

    embed.add_field(
        name="🍪 !cookie <string>  &  🔑 !setcurl <curl>",
        value=(
            "Link a fresh Master Browser Session from Archer's Hub:\n"
            "> • Cookie String: `!cookie ASP.NET_SessionId=...; .ASPXAUTH=...`\n"
            "> • Full cURL: `!setcurl curl 'https://archershub.dlsu.edu.ph/CourseFinder/GetCFData/' ...`"
        ),
        inline=False,
    )

    embed.add_field(
        name="⚡ !bookmarklet",
        value="Get the 1-Click Chrome/Edge Bookmarklet for instant 1-second session refreshes.\n`!bookmarklet`",
        inline=True,
    )

    embed.add_field(
        name="🗑️ !removecurl",
        value="Clear and wipe stored Master cURL browser session cookies from SQLite.\n`!removecurl`",
        inline=True,
    )

    embed.set_footer(text="ArcherSniper Master Auth • 4-Tier Autonomous Recovery")
    return embed


def get_admin_server_embed(is_owner: bool = False) -> discord.Embed:
    """Spacious command guide for Server Provisioning & Maintenance."""
    embed = discord.Embed(
        title="🏛️ Module: Server Provisioning & Roles",
        description=(
            "**Channel auto-provisioning, system health diagnostics, and role delegation.**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x8B5CF6,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🏛️ !setupchannels",
        value=(
            "Auto-provisions clean channel categories and locks permissions:\n"
            "> • **📢 ANNOUNCEMENTS:** `#📢-announcements`, `#🤖-bot-commands`\n"
            "> • **🏛️ COLLEGE FEEDS:** `#🎯-ge-lc-feed`, `#💻-ccs-drops`, `#💼-rvrcob-drops`, etc.\n"
            "> • **🔒 ADMIN HQ:** `#🔒-admin-commands`, `#🚨-admin-disconnects`, `#💓-admin-heartbeat-log`, `#📬-admin-dm-logs`"
        ),
        inline=False,
    )

    embed.add_field(
        name="🧹 !prune",
        value="End-of-term maintenance: Cleans up empty watchlists and runs SQLite `VACUUM`.\n`!prune`",
        inline=True,
    )

    embed.add_field(
        name="📊 !poll (or !health)",
        value="View live engine telemetry, uptime, gateway latency, and per-course polling timestamps.\n`!poll`",
        inline=True,
    )

    if is_owner:
        embed.add_field(
            name="👑 !admin <@member> (Server Owner Only)",
            value="Dynamically grant or revoke the `@ArcherSniper Admin` role for trusted moderators.\n`!admin @member`",
            inline=False,
        )

    embed.set_footer(text="ArcherSniper Server Management • DLSU Discord Bot")
    return embed


def get_curl_embed() -> discord.Embed:
    """Comprehensive step-by-step authentication guide."""
    embed = discord.Embed(
        title="🔑 Master Session & cURL Setup Guide",
        description=(
            "**ArcherSniper requires active session credentials from DLSU Archer's Hub to monitor courses.**\n\n"
            "Choose any of the 3 quick methods below to link your browser session:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_GOLD,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🍪 Method 1: Direct Cookie String (Fastest — 5 Seconds)",
        value=(
            "1. Open [Archer's Hub CourseFinder](https://archershub.dlsu.edu.ph/CourseFinder/) in Chrome.\n"
            "2. Press `F12` ➔ Go to **Console** tab.\n"
            "3. Paste `document.cookie` and press Enter.\n"
            "4. Copy the output and run in `#🔒-admin-commands`:\n"
            "```text\n!cookie <paste_your_cookies_here>\n```"
        ),
        inline=False,
    )

    embed.add_field(
        name="⚡ Method 2: 1-Click Chrome Bookmarklet (Instant Refresh)",
        value=(
            "Type `!bookmarklet` to get the JavaScript bookmarklet code.\n"
            "Save it as a Chrome bookmark, then simply click it on Archer's Hub to refresh tokens in 1 second!"
        ),
        inline=False,
    )

    embed.add_field(
        name="📜 Method 3: Full cURL Copy",
        value=(
            "In Chrome Network tab, right-click `GetCFData` ➔ **Copy as cURL (bash)**.\n"
            "Then paste in `#🔒-admin-commands`:\n"
            "```text\n!setcurl <paste_your_copied_curl_here>\n```"
        ),
        inline=False,
    )

    embed.set_footer(text="ArcherSniper Tier 1 & Tier 2 keep your session alive 24/7 automatically!")
    return embed


def get_admin_embed() -> discord.Embed:
    """Alias for engine embed for backward compatibility."""
    return get_admin_engine_embed()



# ==========================================
# INTERACTIVE SELECT & BUTTON VIEWS
# ==========================================

class StudentHelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Overview & Quick Start",
                value="overview",
                emoji="📖",
                description="Student command center summary and 4-step quick start.",
                default=True,
            ),
            discord.SelectOption(
                label="Student Commands Guide",
                value="student",
                emoji="🎯",
                description="Detailed guide for !watch, !unwatch, !watchlist, and !search.",
            ),
        ]
        super().__init__(placeholder="📂 Select a Help Guide Category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        for opt in self.options:
            opt.default = (opt.value == selected)

        if selected == "student":
            embed = get_student_embed()
        else:
            embed = get_student_overview_embed()

        await interaction.response.edit_message(embed=embed, view=self.view)


class StudentHelpSelectView(discord.ui.View):
    """Clean interactive select view for student members."""
    def __init__(self, default_tab: str = "overview"):
        super().__init__(timeout=300)
        select = StudentHelpSelect()
        for opt in select.options:
            opt.default = (opt.value == default_tab)
        self.add_item(select)

        # Quick Portal Links in Row 1
        self.add_item(discord.ui.Button(label="CourseFinder", url=f"{DLSU_BASE_URL}/CourseFinder/", emoji="🎯", row=1))
        self.add_item(discord.ui.Button(label="Archer's Hub", url=f"{DLSU_BASE_URL}/", emoji="🏹", row=1))
        self.add_item(discord.ui.Button(label="My.DLSU", url=MLS_URL, emoji="🎓", row=1))


class AdminHelpSelect(discord.ui.Select):
    def __init__(self, is_owner: bool = False):
        self.is_owner = is_owner
        options = [
            discord.SelectOption(
                label="Command Center Overview",
                value="overview",
                emoji="📖",
                description="Admin landing dashboard, prefix, and system summary.",
                default=True,
            ),
            discord.SelectOption(
                label="Engine & Watchdog Suite",
                value="engine",
                emoji="⚙️",
                description="!start, !stop, !sweep, !interval, !sync, !startgelc.",
            ),
            discord.SelectOption(
                label="Logs & Data Inspection",
                value="data",
                emoji="📊",
                description="!fetchdata, !logs, !scraperlog, !userstatus, !inspectcourse.",
            ),
            discord.SelectOption(
                label="Session Auth & Tokens",
                value="auth",
                emoji="🔑",
                description="!session, !cookies, !setcurl, !bookmarklet, !removecurl.",
            ),
            discord.SelectOption(
                label="Server Provisioning & Roles",
                value="server",
                emoji="🏛️",
                description="!setupchannels, !prune, !health, and !admin delegation.",
            ),
            discord.SelectOption(
                label="Student Commands Guide",
                value="student",
                emoji="🎯",
                description="All public student commands: !watch, !watchlist, !search.",
            ),
            discord.SelectOption(
                label="cURL & Bookmarklet Guide",
                value="curl",
                emoji="⚡",
                description="Step-by-step Chrome authentication tutorial.",
            ),
        ]
        super().__init__(placeholder="📂 Select an Admin Category to Inspect...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        for opt in self.options:
            opt.default = (opt.value == selected)

        if selected == "engine":
            embed = get_admin_engine_embed()
        elif selected == "data":
            embed = get_admin_data_embed()
        elif selected == "auth":
            embed = get_admin_auth_embed()
        elif selected == "server":
            embed = get_admin_server_embed(is_owner=self.is_owner)
        elif selected == "student":
            embed = get_student_embed()
        elif selected == "curl":
            embed = get_curl_embed()
        else:
            embed = get_admin_overview_embed(is_owner=self.is_owner)

        await interaction.response.edit_message(embed=embed, view=self.view)


class AdminHelpSelectView(discord.ui.View):
    """Clean interactive select view for administrators."""
    def __init__(self, default_tab: str = "overview", is_owner: bool = False):
        super().__init__(timeout=300)
        self.is_owner = is_owner
        select = AdminHelpSelect(is_owner=is_owner)
        for opt in select.options:
            opt.default = (opt.value == default_tab)
        self.add_item(select)

        # Quick Portal Links in Row 1
        self.add_item(discord.ui.Button(label="CourseFinder", url=f"{DLSU_BASE_URL}/CourseFinder/", emoji="🎯", row=1))
        self.add_item(discord.ui.Button(label="Archer's Hub", url=f"{DLSU_BASE_URL}/", emoji="🏹", row=1))
        self.add_item(discord.ui.Button(label="My.DLSU", url=MLS_URL, emoji="🎓", row=1))


# ==========================================
# HELP COG
# ==========================================

class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="help",
        aliases=["adminhelp", "commands", "guide", "sniperhelp"],
        description="Open the ArcherSniper command center and interactive user guides.",
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
                embed = get_student_embed()
                view = AdminHelpSelectView("student", is_owner=is_owner) if is_admin else StudentHelpSelectView("student")
                await ctx.send(embed=embed, view=view)
            elif is_admin and cat in ("engine", "watchdog"):
                await ctx.send(embed=get_admin_engine_embed(), view=AdminHelpSelectView("engine", is_owner=is_owner))
            elif is_admin and cat in ("data", "logs", "fetchdata"):
                await ctx.send(embed=get_admin_data_embed(), view=AdminHelpSelectView("data", is_owner=is_owner))
            elif is_admin and cat in ("auth", "cookies", "session"):
                await ctx.send(embed=get_admin_auth_embed(), view=AdminHelpSelectView("auth", is_owner=is_owner))
            elif is_admin and cat in ("server", "setup", "channels"):
                await ctx.send(embed=get_admin_server_embed(is_owner=is_owner), view=AdminHelpSelectView("server", is_owner=is_owner))
            elif is_admin and cat in ("admin", "overview"):
                await ctx.send(embed=get_admin_overview_embed(is_owner=is_owner), view=AdminHelpSelectView("overview", is_owner=is_owner))
            elif is_admin and cat in ("curl", "token", "guide", "bookmarklet"):
                await ctx.send(embed=get_curl_embed(), view=AdminHelpSelectView("curl", is_owner=is_owner))
            elif not is_admin and cat in ("admin", "setup", "config", "curl", "token", "engine", "data", "auth", "server"):
                await ctx.send("🔒 **Admin guides are only accessible to server administrators.**", ephemeral=True)
            else:
                embed = get_admin_overview_embed(is_owner=is_owner) if is_admin else get_student_overview_embed()
                view = AdminHelpSelectView("overview", is_owner=is_owner) if is_admin else StudentHelpSelectView("overview")
                await ctx.send(embed=embed, view=view)
        else:
            embed = get_admin_overview_embed(is_owner=is_owner) if is_admin else get_student_overview_embed()
            view = AdminHelpSelectView("overview", is_owner=is_owner) if is_admin else StudentHelpSelectView("overview")
            await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    bot.help_command = None
    await bot.add_cog(HelpCog(bot))

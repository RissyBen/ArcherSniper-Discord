"""
ArcherSniper - Discord Embed Builder Module
Generates branded, modern, spacious Discord embeds for announcements, college feeds, DM alerts, and watchlists.
"""

from datetime import datetime, timezone
import discord
from config import (
    COLOR_DLSU_GREEN,
    COLOR_GOLD,
    COLOR_ALERT_RED,
    COLOR_OPEN_GREEN,
    COLOR_INFO_BLUE,
    DLSU_LOGO_URL,
    ANIMO_SYS_URL,
    MLS_URL,
    DLSU_BASE_URL,
)


def make_progress_bar(enlisted: int, capacity: int, length: int = 10) -> str:
    """Generates an ASCII progress bar for course section capacity."""
    if capacity <= 0:
        return f"[{'░' * length}]"
    ratio = min(max(enlisted / capacity, 0.0), 1.0)
    filled_len = int(round(length * ratio))
    bar = "█" * filled_len + "░" * (length - filled_len)
    return f"[{bar}]"


# ==========================================
# PUBLIC ANNOUNCEMENTS & SYSTEM ALERTS
# ==========================================

def create_bot_status_announcement(
    is_online: bool,
    admin_name: str = "Administrator",
    reason: str | None = None,
) -> discord.Embed:
    """Creates a formatted public announcement embed for #📢-announcements."""
    if is_online:
        embed = discord.Embed(
            title="🟢 ArcherSniper is now ONLINE!",
            description=(
                "**The DLSU Course Sniper bot has been activated.**\n\n"
                "> 🎯 **Student Watchlists:** Active & Monitoring\n"
                "> 🏛️ **College Feeds:** Live Drops Streaming\n"
                "> ⚡ **DM Alerts:** Real-Time Slot Drop Pings\n\n"
                "Use `!watch <COURSE> [SECTION]` (e.g. `!watch STSWENG S01`) to start tracking."
            ),
            color=COLOR_OPEN_GREEN,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Activated by {admin_name} • ArcherSniper DLSU 🏹")
    else:
        desc = (
            f"**Reason:** `{reason}`\n\n" if reason else ""
        ) + (
            "> ⏸️ **Student Watchlists:** Paused\n"
            "> 🔇 **Notifications:** Temporarily Muted\n\n"
            "An administrator will reactivate the bot shortly. Thank you for your patience!"
        )
        embed = discord.Embed(
            title="🔴 ArcherSniper is currently OFFLINE",
            description=desc,
            color=COLOR_ALERT_RED,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="ArcherSniper System Announcement")

    return embed


def create_disconnect_announcement() -> discord.Embed:
    """Public technical difficulty announcement when cURL session disconnects."""
    embed = discord.Embed(
        title="⚠️ Technical Difficulty — Session Timeout",
        description=(
            "**ArcherSniper is temporarily paused.**\n\n"
            "> 🔄 **Status:** DLSU CourseFinder master session expired.\n"
            "> 🛠️ **Action:** Administrators have been notified to refresh the connection.\n"
            "> 🔇 **Safe-Mode:** Personal alerts are paused to prevent false notifications.\n\n"
            "The bot will automatically resume as soon as the session is refreshed."
        ),
        color=COLOR_ALERT_RED,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="ArcherSniper Watchdog")
    return embed


# ==========================================
# DIRECT MESSAGE (DM) PERSONAL ALERTS
# ==========================================

def format_clean_schedule(raw_sched: str) -> str:
    """Formats raw CourseFinder schedule strings into clean, human-readable text."""
    if not raw_sched or raw_sched.strip() in ("", "TBA", "TBD"):
        return "TBA"
    parts = [p.strip(" []\t\r\n") for p in raw_sched.split("|") if p.strip(" []\t\r\n")]
    cleaned = []
    for p in parts:
        p_clean = " ".join(p.split())
        p_clean = p_clean.replace(" : Room - ", " (Room ").replace(" : Online", " (Online)")
        if " (Room " in p_clean and not p_clean.endswith(")"):
            p_clean += ")"
        cleaned.append(p_clean)
    if not cleaned:
        return "TBA"
    if len(cleaned) == 1:
        return cleaned[0]
    return " | ".join(cleaned)


def create_student_dm_alert(
    course_code: str,
    course_name: str,
    section_name: str,
    open_slots: int,
    capacity: int,
    enlisted: int,
    teacher: str = "TBA",
    schedule: str = "TBA",
    prev_open_slots: int = 0,
) -> discord.Embed:
    """
    Builds a high-priority green/gold DM notification sent directly to the student's private messages.
    """
    is_slot_open = open_slots > 0
    prev_enlisted = max(0, capacity - prev_open_slots) if capacity > 0 else enlisted
    clean_sched = format_clean_schedule(schedule)

    if is_slot_open and prev_open_slots == 0:
        headline = f"🚨 **SLOT OPENED: {open_slots} OPEN {'SLOT' if open_slots == 1 else 'SLOTS'}!**"
        delta_str = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (🟢 **+{open_slots} Open Available!**)"
        color = COLOR_OPEN_GREEN
    elif is_slot_open and open_slots > prev_open_slots:
        diff = open_slots - prev_open_slots
        headline = f"🟢 **ADDITIONAL SLOT AVAILABLE: {open_slots} OPEN!**"
        delta_str = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (🟢 **+{diff} Open!**)"
        color = COLOR_OPEN_GREEN
    elif is_slot_open and open_slots < prev_open_slots:
        taken = prev_open_slots - open_slots
        headline = f"⚡ **SLOT TAKEN / ENLISTED: {open_slots} REMAINING!**"
        delta_str = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (⚠️ **-{taken} Taken • {open_slots} Open Left**)"
        color = COLOR_GOLD
    else:
        headline = "🔒 **SECTION IS NOW FULL / CLOSED**"
        delta_str = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (🔴 **FULL — 0 Open Left**)"
        color = COLOR_ALERT_RED

    embed = discord.Embed(
        title=f"🎯 Slot Alert: {course_code} {section_name}",
        description=(
            f"{headline}\n\n"
            f"> **Course:** `{course_code}` — {course_name or course_code}\n"
            f"> **Section:** `{section_name}`\n"
            f"> **Slot Change:** {delta_str}"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    prog_bar = make_progress_bar(enlisted, capacity)
    embed.add_field(
        name="📊 Capacity & Enlistment",
        value=f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` {prog_bar} (**{open_slots}** Open)",
        inline=False,
    )
    embed.add_field(
        name="👤 Instructor",
        value=f"`{teacher.strip() or 'TBA'}`",
        inline=True,
    )
    embed.add_field(
        name="🕒 Schedule",
        value=f"`{clean_sched}`",
        inline=True,
    )
    embed.add_field(
        name="⚡ Direct Portal Access",
        value=f"[Archer's Hub CourseFinder]({DLSU_BASE_URL}/CourseFinder/) • [My.DLSU Portal]({MLS_URL})",
        inline=False,
    )
    embed.set_footer(text="ArcherSniper Personal DM Alert • Animo La Salle 🏹")
    return embed


# ==========================================
# COLLEGE & GE/LC FEED CHANNEL BROADCASTS
# ==========================================

def create_college_feed_drop_embed(
    course_code: str,
    course_name: str,
    section_name: str,
    open_slots: int,
    capacity: int,
    enlisted: int,
    teacher: str = "TBA",
    schedule: str = "TBA",
    category_label: str = "College Drop",
    prev_open_slots: int = 0,
) -> discord.Embed:
    """
    Builds a broadcast card for single slot drop updates.
    """
    is_open = open_slots > 0
    prev_enlisted = max(0, capacity - prev_open_slots) if capacity > 0 else enlisted
    clean_sched = format_clean_schedule(schedule)

    if is_open and prev_open_slots == 0:
        status_icon = "🟢"
        color = COLOR_OPEN_GREEN
        headline = f"🟢 **SLOT OPENED: {open_slots} OPEN {'SLOT' if open_slots == 1 else 'SLOTS'}!**"
        slot_delta = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (🟢 **+{open_slots} Open**)"
    elif is_open and open_slots > prev_open_slots:
        diff = open_slots - prev_open_slots
        status_icon = "🟢"
        color = COLOR_OPEN_GREEN
        headline = f"🟢 **SLOTS INCREASED: {open_slots} OPEN!**"
        slot_delta = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (🟢 **+{diff} Open**)"
    elif is_open and open_slots < prev_open_slots:
        taken = prev_open_slots - open_slots
        status_icon = "⚡"
        color = COLOR_GOLD
        headline = f"⚡ **SLOT TAKEN: {open_slots} OPEN REMAINING**"
        slot_delta = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (⚠️ **-{taken} Taken • {open_slots} Left**)"
    elif not is_open and prev_open_slots > 0:
        status_icon = "🔴"
        color = COLOR_ALERT_RED
        headline = "🔴 **SECTION IS NOW FULL / CLOSED**"
        slot_delta = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (🔴 **FULL — 0 Open**)"
    else:
        status_icon = "🟢" if is_open else "🔴"
        color = COLOR_OPEN_GREEN if is_open else COLOR_ALERT_RED
        status_text = f"**{open_slots} OPEN**" if is_open else "**FULL**"
        headline = f"{status_icon} **{status_text}**"
        slot_delta = f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` (`{open_slots}` Open)"

    embed = discord.Embed(
        title=f"{status_icon} [{category_label}] {course_code} — Section {section_name}",
        description=(
            f"**{course_name or course_code}**\n\n"
            f"> ⚡ **Slot Change:** {slot_delta}\n"
            f"> 👤 **Instructor:** `{teacher.strip() or 'TBA'}`\n"
            f"> 🕒 **Schedule:** `{clean_sched}`"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    prog_bar = make_progress_bar(enlisted, capacity, length=8)
    embed.add_field(
        name="📊 Capacity",
        value=f"`{prev_enlisted}/{capacity}` ➔ `{enlisted}/{capacity}` {prog_bar}",
        inline=True,
    )
    embed.add_field(
        name="⚡ Portal",
        value=f"[Archer's Hub]({DLSU_BASE_URL}/CourseFinder/)",
        inline=True,
    )
    embed.set_footer(text=f"ArcherSniper DLSU • {category_label}")
    return embed


def create_batched_feed_drop_embed(
    category_label: str,
    changes: list[dict],
) -> discord.Embed:
    """
    Builds a spacious consolidated batch update embed for a 15-second polling cycle.
    Formats Instructor and Schedule on clean, dedicated lines.
    """
    # Deduplicate entries by (course_code, section_name) to guarantee 0 repeats inside the same embed
    unique_changes = []
    seen = set()
    for item in changes:
        k = (str(item.get("course_code", "")).strip().upper(), str(item.get("section_name", "")).strip().upper())
        if k not in seen:
            seen.add(k)
            unique_changes.append(item)
    changes = unique_changes

    if len(changes) == 1:
        c = changes[0]
        return create_college_feed_drop_embed(
            course_code=c["course_code"],
            course_name=c.get("course_name", ""),
            section_name=c["section_name"],
            open_slots=c.get("open_slots", 0),
            capacity=c.get("capacity", 0),
            enlisted=c.get("enlisted", 0),
            teacher=c.get("teacher", "TBA"),
            schedule=c.get("schedule", "TBA"),
            category_label=category_label,
            prev_open_slots=c.get("prev_open_slots", 0),
        )

    has_any_open = any(c.get("open_slots", 0) > 0 for c in changes)
    icon = "🟢" if has_any_open else "🔴"
    color = COLOR_OPEN_GREEN if has_any_open else COLOR_ALERT_RED

    embed = discord.Embed(
        title=f"{icon} [{category_label}] Live Slot Updates (15s Interval)",
        description=f"**{len(changes)} Section Slot Update{'s' if len(changes) > 1 else ''} Detected**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    for item in changes[:15]:
        code = item["course_code"]
        sec = item["section_name"]
        enl = item.get("enlisted", 0)
        cap = item.get("capacity", 0)
        open_s = item.get("open_slots", 0)
        prev_open = item.get("prev_open_slots", 0)
        prev_enl = max(0, cap - prev_open) if cap > 0 else enl
        teacher = item.get("teacher", "TBA").strip() or "TBA"
        raw_sched = item.get("schedule", "TBA").strip() or "TBA"
        clean_sched = format_clean_schedule(raw_sched)
        prog = make_progress_bar(enl, cap, length=6)

        if open_s > 0:
            if prev_open == 0:
                badge = f"🟢 **{open_s} OPEN**"
            elif open_s > prev_open:
                badge = f"🟢 **+{open_s - prev_open} OPEN** ({open_s} total)"
            elif open_s < prev_open:
                taken = prev_open - open_s
                badge = f"⚠️ **-{taken} TAKEN ({open_s} Left)**"
            else:
                badge = f"🟢 **{open_s} OPEN**"
        else:
            badge = "🔴 **FULL (0 Open)**"

        field_title = f"{code} — Section {sec} ({badge})"
        field_body = (
            f"> ⚡ **Slots:** `{prev_enl}/{cap}` ➔ `{enl}/{cap}` {prog}\n"
            f"> 👤 **Instructor:** `{teacher}`\n"
            f"> 🕒 **Schedule:** `{clean_sched}`"
        )
        embed.add_field(name=field_title, value=field_body, inline=False)

    embed.add_field(
        name="⚡ Direct Portal Access",
        value=f"[Archer's Hub CourseFinder]({DLSU_BASE_URL}/CourseFinder/) • [My.DLSU Portal]({MLS_URL})",
        inline=False,
    )
    embed.set_footer(text=f"ArcherSniper DLSU • {category_label}")
    return embed


def create_status_embed(
    course_code: str,
    course_name: str,
    sections: list[dict],
) -> discord.Embed:
    """Builds a course enrollment overview embed with section cards and capacity bars."""
    total_capacity = sum(s.get("capacity", 0) for s in sections)
    total_enlisted = sum(s.get("enlisted", 0) for s in sections)
    total_open = sum(s.get("open_slots", 0) for s in sections)

    overall_status = f"🟢 **{total_open} Total Open Slots**" if total_open > 0 else "🔴 **All Sections Full**"

    embed = discord.Embed(
        title=f"📋 Enrollment Status: {course_code}",
        description=(
            f"**{course_name or course_code}**\n"
            f"{overall_status} • Total Enlisted: `{total_enlisted}/{total_capacity}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN if total_open > 0 else COLOR_ALERT_RED,
        timestamp=datetime.now(timezone.utc),
    )

    if not sections:
        embed.add_field(
            name="No Section Data",
            value="No sections currently found or fetched for this course.",
            inline=False,
        )
    else:
        for sec in sections[:25]:
            sec_name = sec.get("section_name", "Unknown")
            cap = sec.get("capacity", 0)
            enl = sec.get("enlisted", 0)
            open_s = sec.get("open_slots", 0)
            teacher = sec.get("teacher", "TBA")
            sched = sec.get("schedule", "TBA")

            status_icon = "🟢" if open_s > 0 else "🔴"
            slot_text = f"**{open_s} Open**" if open_s > 0 else "FULL"
            bar = make_progress_bar(enl, cap, length=8)

            field_val = (
                f"{status_icon} `{enl:>2}/{cap:<2}` {bar} {slot_text}\n"
                f"👤 `{teacher}`\n"
                f"🕒 `{sched}`"
            )
            embed.add_field(
                name=f"Section {sec_name}",
                value=field_val,
                inline=True,
            )

    embed.set_footer(text=f"ArcherSniper • {len(sections)} sections tracked", icon_url=DLSU_LOGO_URL)
    return embed


def get_courseinfo_page_count(sections: list[dict], per_page: int = 12) -> int:
    """Calculates total pages needed for course section inspection."""
    import math
    if not sections:
        return 1
    return max(1, math.ceil(len(sections) / per_page))


def create_admin_course_inspection_embed(
    course_code: str,
    course_name: str,
    course_id: str,
    sections: list[dict],
    page: int = 1,
    per_page: int = 12,
) -> discord.Embed:
    """
    Builds a comprehensive course inspector card for admins showing all sections, capacity bars, professors, and time schedules with pagination.
    """
    import math
    total_capacity = sum(s.get("capacity", 0) for s in sections)
    total_enlisted = sum(s.get("enlisted", 0) for s in sections)
    total_open = sum(s.get("open_slots", 0) for s in sections)

    overall_badge = f"🟢 **{total_open} Total Open Slots**" if total_open > 0 else "🔴 **All Sections Full (0 Open)**"
    color = COLOR_OPEN_GREEN if total_open > 0 else COLOR_ALERT_RED

    total_pages = max(1, math.ceil(len(sections) / per_page))
    cur_page = max(1, min(page, total_pages))
    start_idx = (cur_page - 1) * per_page
    end_idx = start_idx + per_page
    page_sections = sections[start_idx:end_idx] if sections else []

    embed = discord.Embed(
        title=f"🏛️ Course Section Inspector: {course_code}",
        description=(
            f"**{course_name or course_code}**\n"
            f"> 🆔 **CourseFinder ID:** `{course_id}`\n"
            f"> 📊 **Enrollment Status:** {overall_badge} (`{total_enlisted}/{total_capacity}` Enlisted)\n"
            f"> 📚 **Total Sections:** `{len(sections)}` sections\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    if not sections:
        embed.add_field(
            name="⚠️ No Sections Found",
            value=(
                "No live sections returned from CourseFinder.\n"
                "• The course might not be offered this term, or the course ID might need synchronization (`!sync`)."
            ),
            inline=False,
        )
    else:
        for sec in page_sections:
            sec_name = sec.get("section_name", "Unknown")
            cap = sec.get("capacity", 0)
            enl = sec.get("enlisted", 0)
            open_s = sec.get("open_slots", 0)
            teacher = sec.get("teacher", "").strip() or "TBA"
            raw_sched = sec.get("schedule", "").strip() or "TBA"
            clean_sched = format_clean_schedule(raw_sched)

            status_icon = "🟢" if open_s > 0 else "🔴"
            slot_text = f"**{open_s} Open**" if open_s > 0 else "FULL"
            bar = make_progress_bar(enl, cap, length=8)

            field_val = (
                f"{status_icon} `{enl:>2}/{cap:<2}` {bar} {slot_text}\n"
                f"👤 **Instructor:** `{teacher}`\n"
                f"🕒 **Schedule:** `{clean_sched}`"
            )
            embed.add_field(
                name=f"Section {sec_name}",
                value=field_val,
                inline=True,
            )

    if total_pages > 1:
        embed.set_footer(text=f"Page {cur_page}/{total_pages} ({len(sections)} total sections) • Use arrows to flip pages • ArcherSniper DLSU")
    else:
        embed.set_footer(text=f"ArcherSniper • {len(sections)} sections tracked", icon_url=DLSU_LOGO_URL)
    return embed


def get_monitored_courses_page_count(courses: list[dict], per_page: int = 15) -> int:
    """Calculates total pages needed for public monitored courses pool."""
    import math
    if not courses:
        return 1
    return max(1, math.ceil(len(courses) / per_page))


def create_monitored_courses_embed(
    courses: list[dict],
    page: int = 1,
    per_page: int = 15,
) -> discord.Embed:
    """
    Builds the public multi-page catalog of all currently monitored courses.
    Accessible to all students via !courses / !allmonitored.
    """
    import math
    from utils.course_classifier import classify_course

    total_courses = len(courses)
    total_pages = max(1, math.ceil(total_courses / per_page))
    cur_page = max(1, min(page, total_pages))

    embed = discord.Embed(
        title="📚 ArcherSniper — Live Monitored Courses Pool",
        description=(
            "**All courses currently being polled every 15 seconds.**\n"
            "• **All GE & LC courses** are tracked 24/7 automatically.\n"
            "• **College Courses** are added dynamically when any student types `!watch <COURSE>`.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    if not courses:
        embed.description = "No courses are currently in the active monitoring pool. Use `!watch <COURSE>` to add one!"
        return embed

    start_idx = (cur_page - 1) * per_page
    end_idx = start_idx + per_page
    page_courses = courses[start_idx:end_idx]

    lines = []
    for c in page_courses:
        code = c.get("course_code", "UNKNOWN").upper()
        name = c.get("course_name", "")
        classification = classify_course(code)

        if classification.is_ge_lc:
            badge = "🎯 `GE/LC`"
        elif classification.college_code:
            badge = f"🏛️ `{classification.college_code}`"
        else:
            badge = "📚 `COLLEGE`"

        name_snippet = f" — *{name[:28]}...*" if len(name) > 28 else (f" — *{name}*" if name else "")
        lines.append(f"• **`{code:<8}`** {badge}{name_snippet}")

    chunk = "\n".join(lines)
    embed.add_field(
        name=f"📋 Monitored Courses ({start_idx + 1}–{min(end_idx, total_courses)} of {total_courses})",
        value=chunk or "No courses",
        inline=False,
    )

    if total_pages > 1:
        embed.set_footer(text=f"Page {cur_page}/{total_pages} (Total: {total_courses} Courses) • Use arrows to flip pages • Type !watch <COURSE> to track")
    else:
        embed.set_footer(text=f"ArcherSniper DLSU • Total {total_courses} Active Courses • Type !watch <COURSE> to track")

    return embed


def create_course_coverage_guide_embed() -> discord.Embed:
    """
    Builds the official student announcement card explaining GE/LC vs College Subject monitoring rules.
    """
    embed = discord.Embed(
        title="🏹 ArcherSniper — Course Monitoring Guide & Rules",
        description=(
            "**How ArcherSniper tracks courses across DLSU and sends you instant drop alerts.**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="🎯 1. General Education (GE) & Lasallian Core (LC) Courses",
        value=(
            "• **Always Monitored 24/7:** **ALL** GE and LC subjects are automatically tracked.\n"
            "• *Examples:* `GERPHIS`, `GEUSELF`, `GEMATMW`, `GEARTAP`, `GEETHIC`, `GELITEV`, `GEPCOMM`, `GESTSOC`, `LCFILIB`, `LCLWOOB`, `LCFAITH`, `LCASEAN`, etc.\n"
            "• **Live Broadcasts:** Every single open slot drop streams live to <#🎯-ge-lc-feed>!"
        ),
        inline=False,
    )

    embed.add_field(
        name="🏛️ 2. College & Major Courses (CCS, RVRCOB, GCOE, CLA, COS, BAGCED, SOE)",
        value=(
            "• **On-Demand High-Speed Monitoring:** To maintain ultra-fast **15-second response speeds**, not all 2,000+ college courses are polled simultaneously.\n"
            "• **How to Watch:** If you want a college major tracked, simply type:\n"
            "  ```text\n  !watch <COURSE> (e.g. !watch STSWENG or !watch CCPROG1 S11)\n  ```\n"
            "• Once watched, the course is **instantly added to the 15-second monitoring pool**, streams to its College channel (e.g. `#💻-ccs-drops`), and DMs you the moment a slot opens!"
        ),
        inline=False,
    )

    embed.add_field(
        name="🔍 3. Useful Commands for Everyone",
        value=(
            "• `!watch <COURSE> [sec]` — Subscribe to instant private DM drop alerts\n"
            "• `!unwatch <COURSE>` — Remove a subject from your watchlist\n"
            "• `!watchlist` — View all your watched sections with live capacities & flip pages\n"
            "• `!courses` — Browse all currently monitored courses across the server\n"
            "• `!search <query>` — Search the full 2,622-course DLSU catalog\n"
            "• `!stats` — View peak drop activity hours and demand leaderboards"
        ),
        inline=False,
    )

    embed.set_footer(text="ArcherSniper DLSU • Animo La Salle 🏹")
    return embed


# ==========================================
# STUDENT WATCHLIST & MONITORED SUMMARY
# ==========================================

def get_watchlist_page_count(watchlist_data: list[dict], per_page: int = 15) -> int:
    """Calculates total pages needed for user watchlist pagination."""
    if not watchlist_data:
        return 1
    total_sections = 0
    for item in watchlist_data:
        secs = item.get("sections", [])
        total_sections += max(1, len(secs))
    import math
    return max(1, math.ceil(total_sections / per_page))


def create_watchlist_detailed_embed(
    username: str,
    watchlist_data: list[dict],
    pings_enabled: bool = True,
    page: int = 1,
    per_page: int = 15,
) -> discord.Embed:
    """
    Builds the detailed !watchlist / !mywatch card showing live slot counts and expanding courses with pagination.
    """
    import math
    ping_badge = "🔔 **DM Pings: ACTIVE**" if pings_enabled else "🔕 **DM Pings: PAUSED** (Use `!unmute` to resume)"

    embed = discord.Embed(
        title=f"🎯 Personal Watchlist — {username}",
        description=f"{ping_badge}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=COLOR_DLSU_GREEN if pings_enabled else COLOR_GOLD,
        timestamp=datetime.now(timezone.utc),
    )

    if not watchlist_data:
        embed.description = (
            f"{ping_badge}\n\n"
            "You have no courses in your watchlist.\n"
            "• Use `!watch <COURSE>` to track an entire course (e.g. `!watch STSWENG`)\n"
            "• Use `!watch <COURSE> <SEC>` to track a specific subject (e.g. `!watch STSWENG S04`)"
        )
        return embed

    # Flatten all section rows across watched courses to support full multi-page pagination
    flat_items = []
    for item in watchlist_data:
        code = item["course_code"]
        scope = item["scope"]
        sec_rule = item.get("section_name", "*")
        sections = item.get("sections", [])
        if not sections:
            flat_items.append({
                "course_code": code,
                "scope": scope,
                "section_name_rule": sec_rule,
                "section_data": None,
            })
        else:
            for s in sections:
                flat_items.append({
                    "course_code": code,
                    "scope": scope,
                    "section_name_rule": sec_rule,
                    "section_data": s,
                })

    total_pages = max(1, math.ceil(len(flat_items) / per_page))
    cur_page = max(1, min(page, total_pages))
    start_idx = (cur_page - 1) * per_page
    end_idx = start_idx + per_page
    page_items = flat_items[start_idx:end_idx]

    # Group page items by course for clean presentation
    grouped = {}
    for entry in page_items:
        key = (entry["course_code"], entry["scope"], entry["section_name_rule"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(entry["section_data"])

    for (code, scope, sec_rule), secs in grouped.items():
        if scope == "COURSE":
            scope_badge = "🌐 `ALL SECTIONS`"
        else:
            scope_badge = f"🎯 `Section {sec_rule}`"

        sec_lines = []
        for s in secs:
            if s is None:
                sec_lines.append("*(Fetching latest live section data...)*")
            else:
                s_name = s.get("section_name", "")
                cap = s.get("capacity", 0)
                enl = s.get("enlisted", 0)
                open_s = s.get("open_slots", 0)
                bar = make_progress_bar(enl, cap, length=6)
                badge = "🟢" if open_s > 0 else "🔴"
                sec_lines.append(f"{badge} `{s_name:>4}` `{enl:>2}/{cap:<2}` {bar} (**{open_s}** Open)")

        chunk = "\n".join(sec_lines)
        embed.add_field(
            name=f"📚 {code} ({scope_badge})",
            value=chunk or "No section data",
            inline=False,
        )

    if total_pages > 1:
        embed.set_footer(text=f"Page {cur_page}/{total_pages} (Total: {len(flat_items)} Sections) • Use arrows to flip pages • !unwatch <COURSE> to remove")
    else:
        embed.set_footer(text="ArcherSniper • Use !unwatch <COURSE> to remove • !mute to pause pings")
    return embed


def create_monitored_summary_embed(
    username: str,
    summary_data: list[dict],
    pings_enabled: bool = True,
) -> discord.Embed:
    """
    Builds the high-level !monitored / !list summary embed for a student.
    """
    ping_badge = "🔔 **Pings Active**" if pings_enabled else "🔕 **Pings Paused**"

    embed = discord.Embed(
        title=f"📋 Monitored Subscriptions — {username}",
        description=(
            f"{ping_badge} • Total Subscriptions: **{len(summary_data)}**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    if not summary_data:
        embed.description = "You have no active course subscriptions. Use `!watch <code>` to add."
        return embed

    lines = []
    for idx, item in enumerate(summary_data, 1):
        code = item["course_code"]
        scope = item["scope"]
        sec = item["section_name"]

        if scope == "COURSE" or sec == "*":
            lines.append(f"**{idx}.** `{code}` — `ALL SECTIONS` (Whole Course)")
        else:
            lines.append(f"**{idx}.** `{code}` — `Section {sec}` (Specific Subject)")

    embed.add_field(name="Tracked Courses & Subjects", value="\n".join(lines), inline=False)
    embed.set_footer(text="Use !watchlist to view live section slots • ArcherSniper")
    return embed


# ==========================================
# ADMIN & WATCHDOG EMBEDS
# ==========================================

def create_heartbeat_pulse_embed(
    status_code: int,
    latency_ms: float,
    active_courses: int,
    active_watchers: int,
) -> discord.Embed:
    """Compact 1-minute keep-alive confirmation embed for #💓-admin-heartbeat-log."""
    now_str = datetime.now(timezone.utc).strftime("%I:%M:%S %p UTC")
    is_ok = status_code == 200

    embed = discord.Embed(
        title=f"💓 Keep-Alive Pulse {'OK' if is_ok else 'FAILED'} [{now_str}]",
        description=(
            f"> **Status:** `HTTP {status_code}`\n"
            f"> **Latency:** `{latency_ms:.0f}ms`\n"
            f"> **Tracked Courses:** `{active_courses}` | **Active Watchers:** `{active_watchers}`"
        ),
        color=COLOR_OPEN_GREEN if is_ok else COLOR_ALERT_RED,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="ArcherSniper 60s Heartbeat Log")
    return embed


def create_health_embed(health_data: dict) -> discord.Embed:
    """Builds a comprehensive health & watchdog diagnostics embed."""
    is_connected = health_data.get("is_connected", False)
    status_str = "🟢 CONNECTED (Active 24/7)" if is_connected else "🔴 DISCONNECTED (Tokens Expired)"
    color = COLOR_DLSU_GREEN if is_connected else COLOR_ALERT_RED

    embed = discord.Embed(
        title="🛡️ ArcherSniper System Health & Watchdog",
        description=f"**Master Session:** {status_str}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    poll_int = health_data.get("poll_interval", 15)
    hb_int = health_data.get("heartbeat_interval", 60)
    last_hb = health_data.get("last_heartbeat_time")
    last_hb_str = f"<t:{int(last_hb.timestamp())}:R>" if last_hb else "Never"

    embed.add_field(
        name="⏱️ Polling & Timing",
        value=(
            f"• **Scraper Cycle:** `{poll_int}s`\n"
            f"• **Heartbeat Cadence:** `{hb_int}s`\n"
            f"• **Last Keep-Alive:** {last_hb_str}\n"
            f"• **Bot Active Gatekeeper:** `{'🟢 ON' if health_data.get('bot_active') else '🔴 OFF'}`"
        ),
        inline=True,
    )

    tokens_present = health_data.get("tokens_present", {})
    tok_check = "\n".join(
        f"{'✅' if v else '❌'} `{k}`" for k, v in tokens_present.items()
    ) or "No tokens stored"

    embed.add_field(
        name="🔑 Master Auth Tokens",
        value=tok_check,
        inline=True,
    )

    embed.add_field(
        name="📊 Live Engine Metrics",
        value=(
            f"• **Monitored Courses:** `{health_data.get('monitored_courses_count', 0)}`\n"
            f"• **Active Watchers:** `{health_data.get('active_watchers_count', 0)}`\n"
            f"• **Total Poll Cycles:** `{health_data.get('total_poll_cycles', 0):,}`\n"
            f"• **Alerts Dispatched:** `{health_data.get('total_alerts_sent', 0):,}`"
        ),
        inline=False,
    )

    embed.set_footer(text="ArcherSniper DLSU Watchdog Engine")
    return embed


def create_system_alert_embed(
    title: str,
    description: str,
    level: str = "info",
) -> discord.Embed:
    """Generic system alert embed."""
    color_map = {
        "success": COLOR_OPEN_GREEN,
        "info": COLOR_INFO_BLUE,
        "warning": COLOR_GOLD,
        "error": COLOR_ALERT_RED,
    }
    embed = discord.Embed(
        title=title,
        description=description,
        color=color_map.get(level, COLOR_INFO_BLUE),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="ArcherSniper System Alert")
    return embed


def create_admin_dm_mirror_embed(
    username: str,
    user_id: int,
    course_code: str,
    section_name: str,
    open_slots: int,
    capacity: int,
    enlisted: int,
    prev_open_slots: int,
) -> discord.Embed:
    """
    Mirror log embed posted silently to #📬-admin-dm-logs whenever a student receives a DM.
    """
    is_open = open_slots > 0
    delta_str = f"`{prev_open_slots}` ➔ `🟢 {open_slots} Open`" if is_open else f"`{prev_open_slots}` ➔ `🔴 FULL (0 Open)`"
    color = COLOR_OPEN_GREEN if is_open else COLOR_ALERT_RED

    embed = discord.Embed(
        title=f"📬 DM Dispatched ➔ {username}",
        description=(
            f"> **Recipient:** `{username}` (`{user_id}`)\n"
            f"> **Subject:** `{course_code} {section_name}`\n"
            f"> **Delta:** {delta_str} (`{enlisted}/{capacity}`)"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="ArcherSniper Admin DM Mirror Log (Silent)")
    return embed


def create_user_inspection_embed(
    member_name: str,
    member_id: int,
    avatar_url: str | None,
    watchlist_data: list[dict],
    pings_enabled: bool,
) -> discord.Embed:
    """
    Builds the admin inspection card for !userstatus <@member>.
    """
    ping_badge = "🔔 **ACTIVE (Unmuted)**" if pings_enabled else "🔕 **PAUSED (Muted)**"

    embed = discord.Embed(
        title=f"🔍 Member Audit — {member_name}",
        description=(
            f"> **User ID:** `{member_id}`\n"
            f"> **Notification Status:** {ping_badge}\n"
            f"> **Total Subscriptions:** **{len(watchlist_data)}**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN if pings_enabled else COLOR_GOLD,
        timestamp=datetime.now(timezone.utc),
    )

    if avatar_url:
        embed.set_thumbnail(url=avatar_url)

    if not watchlist_data:
        embed.add_field(
            name="Watchlist",
            value="*This member currently has no active subscriptions.*",
            inline=False,
        )
        return embed

    for item in watchlist_data[:15]:
        code = item["course_code"]
        scope = item["scope"]
        sections = item.get("sections", [])

        scope_badge = "🌐 `ALL SECTIONS`" if scope == "COURSE" else f"🎯 `Section {item['section_name']}`"

        sec_lines = []
        if sections:
            for s in sections[:8]:
                s_name = s.get("section_name", "")
                cap = s.get("capacity", 0)
                enl = s.get("enlisted", 0)
                open_s = s.get("open_slots", 0)
                bar = make_progress_bar(enl, cap, length=6)
                badge = "🟢" if open_s > 0 else "🔴"
                sec_lines.append(f"{badge} `{s_name:>3}` `{enl:>2}/{cap:<2}` {bar} (**{open_s}** Open)")
        else:
            sec_lines.append("*(No live section states recorded)*")

        chunk = "\n".join(sec_lines)
        embed.add_field(
            name=f"📚 {code} ({scope_badge})",
            value=chunk or "No section data",
            inline=False,
        )

    embed.set_footer(text="ArcherSniper Admin Inspector")
    return embed


def create_drop_analytics_embed(data: dict) -> discord.Embed:
    """
    Builds the beautiful Drop Analytics (!stats) embed with peak windows, top demand courses, and recent fill speeds.
    """
    embed = discord.Embed(
        title="📊 ArcherSniper — Course Drop Analytics",
        description=(
            "**Live Watchdog Slot Activity & Peak Hours Report**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    # 1. Global Metrics
    total_drops = data.get("total_drops", 0)
    active_watchers = data.get("active_watchers", 0)
    active_courses = data.get("active_courses", 0)

    embed.add_field(
        name="📈 Global Sniping Metrics",
        value=(
            f"• **Total Drops Caught:** `{total_drops:,}` drops\n"
            f"• **Active Tracked Courses:** `{active_courses}` subjects\n"
            f"• **Registered Students:** `{active_watchers}` watchers"
        ),
        inline=False,
    )

    # 2. Top Contested Courses
    top_courses = data.get("top_courses", [])
    if top_courses:
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        course_lines = []
        for idx, c in enumerate(top_courses[:5]):
            medal = medals[idx] if idx < len(medals) else "•"
            code = c.get("course_code", "UNKNOWN")
            watchers = c.get("watcher_count", 0)
            drops = c.get("drops_caught", 0)
            course_lines.append(f"{medal} **`{code}`** • `👥 {watchers} Watchers` • `⚡ {drops} Drops`")
        embed.add_field(
            name="🔥 Most Contested Courses (Top Demand)",
            value="\n".join(course_lines),
            inline=False,
        )

    # 3. Peak Activity Windows
    morning = data.get("morning_drops", 0)
    afternoon = data.get("afternoon_drops", 0)
    evening = data.get("evening_drops", 0)
    other = data.get("other_drops", 0)
    total_windowed = morning + afternoon + evening + other or 1

    def make_pct_bar(count: int, total: int) -> str:
        ratio = count / total if total > 0 else 0
        filled = int(round(12 * ratio))
        pct = int(round(ratio * 100))
        bar = "█" * filled + "░" * (12 - filled)
        return f"`[{bar}]` ({pct}%)"

    peak_text = (
        f"**08:00 AM – 10:00 AM** {make_pct_bar(morning, total_windowed)} • Morning Enlistment\n"
        f"**01:00 PM – 03:00 PM** {make_pct_bar(afternoon, total_windowed)} • Inter-College Shifts\n"
        f"**06:00 PM – 08:00 PM** {make_pct_bar(evening, total_windowed)} • Evening Drop Rush\n"
        f"**Other Hours**         {make_pct_bar(other, total_windowed)}"
    )

    embed.add_field(
        name="⏰ Peak Drop Activity Windows (DLSU)",
        value=peak_text,
        inline=False,
    )

    # 4. Recent Slot Drops
    recent = data.get("recent_drops", [])
    if recent:
        recent_lines = []
        for r in recent[:3]:
            c_code = r.get("course_code", "")
            s_name = r.get("section_name", "")
            o_slots = r.get("open_slots", 0)
            cap = r.get("capacity", 0)
            enl = r.get("enlisted", 0)
            dur = r.get("duration_seconds")
            dur_str = f"Filled in {dur}s" if dur else "Open now"
            recent_lines.append(f"• **`{c_code} {s_name}`** ➔ `{o_slots} Open` (`{enl}/{cap}`) • *{dur_str}*")

        embed.add_field(
            name="⚡ Recent Slot Drop Events",
            value="\n".join(recent_lines),
            inline=False,
        )

    embed.set_footer(text="ArcherSniper Drop Analytics • Data refreshed live from Archer's Hub", icon_url=DLSU_LOGO_URL)
    return embed


def create_course_search_embed(query: str, results: list[dict]) -> discord.Embed:
    """
    Builds the search results card for !search <keyword>.
    """
    embed = discord.Embed(
        title=f"🔍 CourseFinder Search: \"{query}\"",
        description=f"Found **{len(results)}** matching course(s) on DLSU CourseFinder.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    if not results:
        embed.description = (
            f"No courses found matching **\"{query}\"**.\n"
            "Try searching by course code (e.g. `!search CCPROG`) or title keywords (e.g. `!search database`)."
        )
        return embed

    for idx, r in enumerate(results[:10], 1):
        code = r.get("course_code", "")
        name = r.get("course_name", "")
        cid = r.get("course_id", "")
        embed.add_field(
            name=f"{idx}. {code} (ID: `{cid}`)",
            value=f"{name}\n> Type `!watch {code}` to subscribe",
            inline=False,
        )

    embed.set_footer(text="ArcherSniper DLSU • Use !watch <COURSE> to track")
    return embed


def create_sweep_results_embed(
    open_sections: list[dict],
    page: int = 1,
    per_page: int = 10,
    feeds_updated: int = 0,
) -> discord.Embed:
    """
    Builds the interactive paginated sweep embed for browsing all sections with open seats.
    """
    import math
    total_count = len(open_sections)
    total_pages = max(1, math.ceil(total_count / per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_items = open_sections[start_idx:end_idx]

    embed = discord.Embed(
        title="⚡ DLSU Open Sections Sweep (Live Availability)",
        description=(
            f"Found **{total_count} section{'s' if total_count != 1 else ''}** with open slots across DLSU CourseFinder!\n"
            f"> 🏛️ **Feeds Updated:** `{feeds_updated} channels`   •   `Page:` **`{page}/{total_pages}`**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOR_DLSU_GREEN,
        timestamp=datetime.now(timezone.utc),
    )

    for sec in page_items:
        code = sec["course_code"]
        s_name = sec["section_name"]
        open_s = sec["open_slots"]
        cap = sec["capacity"]
        enl = sec["enlisted"]
        teacher = (sec.get("teacher") or "TBA").strip()
        sched = (sec.get("schedule") or "TBA").strip()
        clean_sched = format_clean_schedule(sched)
        bar = make_progress_bar(enl, cap, length=6)

        field_name = f"🟢 {code} — Section {s_name}"
        field_val = (
            f"**{open_s} Open Slot{'s' if open_s != 1 else ''}** • `{enl:>2}/{cap:<2}` {bar}\n"
            f"👤 `{teacher}`\n"
            f"🕒 `{clean_sched}`"
        )
        embed.add_field(name=field_name, value=field_val, inline=False)

    embed.set_footer(
        text=f"Page {page}/{total_pages} ({total_count} total open sections) • Use arrows below to browse",
        icon_url=DLSU_LOGO_URL,
    )
    return embed


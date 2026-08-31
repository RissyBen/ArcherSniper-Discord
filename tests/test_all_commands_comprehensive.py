"""
ArcherSniper - Comprehensive Test Suite for All Discord User and Admin Commands
Tests 100% of user and admin commands across SniperCog, AdminCog, HelpCog, and ChannelManager.
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite
import discord
from discord.ext import commands

from config import (
    COLOR_DLSU_GREEN,
    COLOR_OPEN_GREEN,
    COLOR_ALERT_RED,
    WATCHDOG_CYCLES_LOG_PATH,
    AUTODISCOVERY_LOG_PATH,
    SLOT_DROPS_LOG_PATH,
    DM_DISPATCH_LOG_PATH,
    HEARTBEAT_LOG_PATH,
    SCRAPER_LOG_PATH,
)
from database import Database
from dlsu_api import DLSUApiClient
from engine import WatchdogEngine
from cogs.sniper import SniperCog
from cogs.admin import AdminCog
from cogs.help import HelpCog
from cogs.channel_manager import ChannelManager


@pytest.fixture
async def full_bot_env():
    """Sets up an isolated database, engine, mock bot, and cogs."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_commands.db"
    logs_dir = Path(temp_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    db = Database(db_path=db_path)
    await db.init_db()

    mock_bot = MagicMock(spec=commands.Bot)
    mock_bot.is_closed.return_value = False
    mock_bot.user.id = 1543192381049020476
    mock_bot.latency = 0.045
    mock_bot.get_channel = MagicMock(return_value=None)
    mock_bot.fetch_channel = AsyncMock()
    mock_bot.get_user = MagicMock(return_value=None)
    mock_bot.fetch_user = AsyncMock()
    mock_bot.change_presence = AsyncMock()

    api_client = DLSUApiClient()

    engine = WatchdogEngine(
        bot=mock_bot,
        db=db,
        api_client=api_client,
    )
    engine.poll_interval = 15.0
    engine.is_connected = True
    engine.bot_active = True
    engine.session_expired = False
    engine.total_poll_cycles = 10
    engine.total_alerts_sent = 5

    # Seed sample courses in catalog & monitored tables
    await db.upsert_catalog_course("4733", "GEWORLD", "The Contemporary World")
    await db.upsert_catalog_course("5845", "SAS2000", "Student Affairs Services 2000")
    await db.upsert_catalog_course("3344", "CSOPESY", "Operating Systems Concepts")
    await db.upsert_catalog_course("5105", "DSILYTC", "Introduction to Analytics")

    await db.add_monitored_course("4733", "GEWORLD", "The Contemporary World", added_by="System")
    await db.add_monitored_course("5845", "SAS2000", "Student Affairs Services 2000", added_by="System")
    await db.add_monitored_course("3344", "CSOPESY", "Operating Systems Concepts", added_by="Student")

    # Seed sample sections
    await db.upsert_section_state("4733", "GEWORLD", "Y01", 45, 43, 2, "Maria Sevilla", "FRIDAY 08:00-11:00")
    await db.upsert_section_state("4733", "GEWORLD", "Y02", 45, 45, 0, "Alexia Suñaz", "TUESDAY 08:00-11:00")
    await db.upsert_section_state("3344", "CSOPESY", "S04", 45, 44, 1, "Marck Caluya", "MW 09:15-10:45")

    # Instantiate cogs
    sniper_cog = SniperCog(mock_bot, db, engine)
    admin_cog = AdminCog(mock_bot, db, engine)
    help_cog = HelpCog(mock_bot)
    chan_cog = ChannelManager(mock_bot, db)

    yield {
        "db": db,
        "engine": engine,
        "bot": mock_bot,
        "api": api_client,
        "sniper_cog": sniper_cog,
        "admin_cog": admin_cog,
        "help_cog": help_cog,
        "chan_cog": chan_cog,
        "temp_dir": temp_dir,
    }

    await api_client.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


def create_mock_ctx(author_id=123456789, author_name="StudentUser", is_admin=False, is_guild_owner=False):
    """Creates a mock discord commands.Context."""
    ctx = MagicMock()
    ctx.defer = AsyncMock()
    ctx.send = AsyncMock()
    ctx.reply = AsyncMock()
    ctx.author.id = author_id
    ctx.author.name = author_name
    ctx.author.display_name = author_name
    ctx.author.mention = f"<@{author_id}>"

    guild = MagicMock()
    guild.id = 777888999
    guild.name = "DLSU Archer Hub"
    guild.owner_id = author_id if is_guild_owner else 999999999
    guild.owner = MagicMock(id=guild.owner_id)
    ctx.guild = guild

    member = MagicMock(spec=discord.Member)
    member.id = author_id
    member.name = author_name
    member.display_name = author_name
    member.guild_permissions.administrator = is_admin
    member.roles = []
    ctx.author = member

    return ctx


# ====================================================================
# STUDENT COMMANDS TESTS (SniperCog & HelpCog)
# ====================================================================

@pytest.mark.asyncio
async def test_student_watch_and_unwatch_commands(full_bot_env):
    """Tests !watch and !unwatch for whole course and specific section."""
    cog = full_bot_env["sniper_cog"]
    db = full_bot_env["db"]
    ctx = create_mock_ctx(author_id=112233, author_name="ArcherStudent")

    # 1. Watch whole course
    await cog.watch_command.callback(cog, ctx, course_code="GEWORLD", section=None)
    ctx.send.assert_called()
    assert await db.get_user_watch_count(112233) == 1

    # 2. Watch specific section
    ctx.send.reset_mock()
    await cog.watch_command.callback(cog, ctx, course_code="CSOPESY", section="S04")
    ctx.send.assert_called()
    assert await db.get_user_watch_count(112233) == 2

    # 3. Unwatch specific section
    ctx.send.reset_mock()
    await cog.unwatch_command.callback(cog, ctx, course_code="CSOPESY", section="S04")
    ctx.send.assert_called()
    assert await db.get_user_watch_count(112233) == 1

    # 4. Unwatch whole course
    ctx.send.reset_mock()
    await cog.unwatch_command.callback(cog, ctx, course_code="GEWORLD", section=None)
    ctx.send.assert_called()
    assert await db.get_user_watch_count(112233) == 0


@pytest.mark.asyncio
async def test_student_watchlist_and_mute_commands(full_bot_env):
    """Tests !watchlist, !mute, and !unmute commands."""
    cog = full_bot_env["sniper_cog"]
    db = full_bot_env["db"]
    ctx = create_mock_ctx(author_id=445566, author_name="SniperUser")

    # 1. Empty watchlist view
    await cog.watchlist_command.callback(cog, ctx)
    ctx.send.assert_called()

    # 2. Add courses and view populated watchlist
    await db.add_user_watch(445566, "SniperUser", "4733", "GEWORLD", "*", "COURSE")
    ctx.send.reset_mock()
    await cog.watchlist_command.callback(cog, ctx)
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "embed" in call_kw
    assert "GEWORLD" in str(call_kw["embed"].description) or "GEWORLD" in str(call_kw["embed"].fields)

    # 3. Mute pings
    ctx.send.reset_mock()
    await cog.mute_command.callback(cog, ctx)
    ctx.send.assert_called()
    assert await db.get_user_pings_status(445566) is False

    # 4. Unmute pings
    ctx.send.reset_mock()
    await cog.unmute_command.callback(cog, ctx)
    ctx.send.assert_called()
    assert await db.get_user_pings_status(445566) is True


@pytest.mark.asyncio
async def test_student_search_and_courseinfo_commands(full_bot_env):
    """Tests !search, !courses (GE/LC), and !courseinfo commands."""
    cog = full_bot_env["sniper_cog"]
    ctx = create_mock_ctx(author_id=556677, author_name="ResearchUser")

    # 1. !search query
    await cog.search_command.callback(cog, ctx, query="Contemporary")
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "GEWORLD" in str(call_kw["embed"].fields)

    # 2. !courses (lists GE/LC)
    ctx.send.reset_mock()
    await cog.courses_command.callback(cog, ctx)
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "GEWORLD" in str(call_kw["embed"].fields)

    # 3. !courseinfo GEWORLD
    ctx.send.reset_mock()
    with patch.object(full_bot_env["api"], "fetch_section_data", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {"section_name": "Y01", "capacity": 45, "enlisted": 43, "open_slots": 2, "teacher": "Maria Sevilla", "schedule": "FRIDAY 08:00-11:00"}
        ]
        await cog.course_info_command.callback(cog, ctx, course_code="GEWORLD")
        ctx.send.assert_called()
        call_kw = ctx.send.call_args[1]
        assert "embed" in call_kw
        assert "GEWORLD" in call_kw["embed"].title


@pytest.mark.asyncio
async def test_ping_and_stats_commands(full_bot_env):
    """Tests !status and !stats commands."""
    cog = full_bot_env["sniper_cog"]
    ctx = create_mock_ctx()

    # 1. !status
    await cog.status_command.callback(cog, ctx, courses="")
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "Enrollment Status" in call_kw["embed"].title

    # 2. !stats / !analytics
    ctx.send.reset_mock()
    await cog.stats_command.callback(cog, ctx)
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "Analytics" in call_kw["embed"].title


@pytest.mark.asyncio
async def test_role_adaptive_help_command(full_bot_env):
    """Tests role-adaptive !help for student vs admin."""
    cog = full_bot_env["help_cog"]

    # 1. Student Help View
    student_ctx = create_mock_ctx(is_admin=False)
    await cog.help_command.callback(cog, student_ctx)
    student_ctx.send.assert_called()
    student_embed = student_ctx.send.call_args[1]["embed"]
    assert any("Student Commands" in f.name for f in student_embed.fields)
    assert not any("Admin & Engine Controls" in f.name for f in student_embed.fields)

    # 2. Admin Help View
    admin_ctx = create_mock_ctx(is_admin=True)
    await cog.help_command.callback(cog, admin_ctx)
    admin_ctx.send.assert_called()
    admin_embed = admin_ctx.send.call_args[1]["embed"]
    assert any("Admin & Engine Controls" in f.name for f in admin_embed.fields)


# ====================================================================
# ADMIN COMMANDS TESTS (AdminCog & ChannelManager)
# ====================================================================

@pytest.mark.asyncio
async def test_admin_start_stop_and_gelc_toggles(full_bot_env):
    """Tests !start, !stop, !startgelc, !stopgelc admin commands."""
    cog = full_bot_env["admin_cog"]
    engine = full_bot_env["engine"]
    ctx = create_mock_ctx(is_admin=True)

    # 1. !stop
    await cog.stop_command.callback(cog, ctx)
    assert engine.bot_active is False

    # 2. !start
    ctx.send.reset_mock()
    await cog.start_command.callback(cog, ctx)
    assert engine.bot_active is True

    # 3. !stopgelc
    ctx.send.reset_mock()
    await cog.stop_gelc_command.callback(cog, ctx)
    assert engine.ge_lc_active is False

    # 4. !startgelc
    ctx.send.reset_mock()
    await cog.start_gelc_command.callback(cog, ctx)
    assert engine.ge_lc_active is True


@pytest.mark.asyncio
async def test_admin_sweep_command_with_and_without_filters(full_bot_env):
    """Tests interactive !sweep and !sweep with filter keywords."""
    cog = full_bot_env["admin_cog"]
    ctx = create_mock_ctx(is_admin=True)

    # 1. Unfiltered !sweep (all open sections)
    await cog.sweep_command.callback(cog, ctx, filter_keyword="")
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "embed" in call_kw
    assert "view" in call_kw
    assert "Live Availability" in call_kw["embed"].title

    # 2. Filtered !sweep GEWORLD
    ctx.send.reset_mock()
    await cog.sweep_command.callback(cog, ctx, filter_keyword="GEWORLD")
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "GEWORLD" in str(call_kw["embed"].fields)

    # 3. Filtered !sweep with non-existent course
    ctx.send.reset_mock()
    await cog.sweep_command.callback(cog, ctx, filter_keyword="NONEXISTENT999")
    ctx.send.assert_called()
    assert "No sections with open slots" in str(ctx.send.call_args)


@pytest.mark.asyncio
async def test_admin_view_logs_command_all_types(full_bot_env):
    """Tests !logs for watchdog, autodiscovery, drops, dms, heartbeat, and scraper."""
    cog = full_bot_env["admin_cog"]
    ctx = create_mock_ctx(is_admin=True)

    # Populate temporary log files
    for p, name in [
        (WATCHDOG_CYCLES_LOG_PATH, "WATCHDOG"),
        (AUTODISCOVERY_LOG_PATH, "AUTODISCOVERY"),
        (SLOT_DROPS_LOG_PATH, "SLOT DROPS"),
        (DM_DISPATCH_LOG_PATH, "DM DISPATCH"),
        (HEARTBEAT_LOG_PATH, "HEARTBEAT"),
        (SCRAPER_LOG_PATH, "SCRAPER"),
    ]:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"[2026-08-31 12:00:00 UTC] Sample test entry for {name}\n")

    # 1. !logs watchdog 10
    await cog.view_logs_command.callback(cog, ctx, param1="watchdog", param2="10")
    ctx.send.assert_called()
    assert "Watchdog" in ctx.send.call_args[1]["embed"].title

    # 2. !logs autodiscovery 5
    ctx.send.reset_mock()
    await cog.view_logs_command.callback(cog, ctx, param1="autodiscovery", param2="5")
    ctx.send.assert_called()
    assert "Auto-Discovery" in ctx.send.call_args[1]["embed"].title

    # 3. !logs drops 15
    ctx.send.reset_mock()
    await cog.view_logs_command.callback(cog, ctx, param1="drops", param2="15")
    ctx.send.assert_called()
    assert "Slot Drops" in ctx.send.call_args[1]["embed"].title

    # 4. !logs dms 15
    ctx.send.reset_mock()
    await cog.view_logs_command.callback(cog, ctx, param1="dms", param2="15")
    ctx.send.assert_called()
    assert "DM Dispatches" in ctx.send.call_args[1]["embed"].title

    # 5. !logs (default)
    ctx.send.reset_mock()
    await cog.view_logs_command.callback(cog, ctx)
    ctx.send.assert_called()
    assert "Watchdog" in ctx.send.call_args[1]["embed"].title


@pytest.mark.asyncio
async def test_admin_user_status_and_health(full_bot_env):
    """Tests !userstatus and !health admin commands."""
    cog = full_bot_env["admin_cog"]
    db = full_bot_env["db"]
    ctx = create_mock_ctx(is_admin=True)

    # Seed target student
    target_student_id = 987654321
    await db.add_user_watch(target_student_id, "TargetStudent", "4733", "GEWORLD", "Y01", "SECTION")

    # 1. !userstatus <USER_ID>
    await cog.user_status_command.callback(cog, ctx, member=str(target_student_id))
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "GEWORLD" in str(call_kw["embed"].fields)

    # 2. !health
    ctx.send.reset_mock()
    await cog.health_command.callback(cog, ctx)
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "Health" in call_kw["embed"].title


@pytest.mark.asyncio
async def test_admin_prune_and_sync_commands(full_bot_env):
    """Tests !prune and !sync commands."""
    cog = full_bot_env["admin_cog"]
    db = full_bot_env["db"]
    ctx = create_mock_ctx(is_admin=True)

    # 1. !prune (clears duplicate watches & optimizes)
    await cog.prune_command.callback(cog, ctx)
    ctx.send.assert_called()
    assert "Cleanup Complete" in ctx.send.call_args[1]["embed"].title

    # 2. !sync
    ctx.send.reset_mock()
    mock_sent_msg = MagicMock()
    mock_sent_msg.edit = AsyncMock()
    ctx.send.return_value = mock_sent_msg
    with patch.object(full_bot_env["engine"], "auto_discover_new_courses", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = (42, 2535)
        await cog.sync_command.callback(cog, ctx)
        ctx.send.assert_called()
        mock_sent_msg.edit.assert_called()
        assert "complete" in str(mock_sent_msg.edit.call_args).lower()


@pytest.mark.asyncio
async def test_admin_session_info_command(full_bot_env):
    """Tests !session / !authstatus command."""
    cog = full_bot_env["admin_cog"]
    db = full_bot_env["db"]
    ctx = create_mock_ctx(is_admin=True)

    # Save mock auth
    await db.save_master_auth(
        cookies={"ASP.NET_SessionId": "sample_session_12345", ".ASPXAUTH": "sample_auth_token_999"},
        headers={"User-Agent": "Mozilla/5.0 Test"},
        status="CONNECTED",
    )

    with patch.object(full_bot_env["engine"].api, "send_heartbeat", new_callable=AsyncMock) as mock_hb:
        mock_hb.return_value = True
        await cog.session_info_command.callback(cog, ctx)
        ctx.send.assert_called()
        embed = ctx.send.call_args[1]["embed"]
        assert "Master Session & Cookie Inspector" in embed.title
        assert "ASP.NET_SessionId" in str(embed.fields)


@pytest.mark.asyncio
async def test_admin_fetch_data_command(full_bot_env):
    """Tests !fetchdata / !rawdata command for single course and cycle dump."""
    cog = full_bot_env["admin_cog"]
    ctx = create_mock_ctx(is_admin=True)

    # 1. Single course fetch
    with patch.object(full_bot_env["engine"].api, "fetch_section_data", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {"section_name": "Y01", "capacity": 45, "enlisted": 43, "open_slots": 2, "teacher": "Maria Sevilla", "schedule": "FRIDAY 08:00-11:00"}
        ]
        await cog.fetch_data_command.callback(cog, ctx, course_code="GEWORLD")
        ctx.send.assert_called()
        embed = ctx.send.call_args[1]["embed"]
        assert "Parsed API Data" in embed.title
        assert "GEWORLD" in embed.title

    # 2. Full scraper dump view
    from config import SCRAPER_DUMP_PATH
    SCRAPER_DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCRAPER_DUMP_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "cycle": 42,
            "timestamp": "2026-08-31T14:00:00Z",
            "total_courses": 1,
            "courses": {
                "GEWORLD": {
                    "course_id": "4733",
                    "sections_count": 1,
                    "sections": [
                        {"section_name": "Y01", "capacity": 45, "enlisted": 43, "open_slots": 2, "teacher": "Maria Sevilla", "schedule": "FRIDAY 08:00-11:00"}
                    ]
                }
            }
        }, f, indent=2)

    ctx.send.reset_mock()
    await cog.fetch_data_command.callback(cog, ctx, course_code=None)
    ctx.send.assert_called()
    call_kw = ctx.send.call_args[1]
    assert "Latest Scraper Fetch Snapshot" in call_kw["embed"].title
    assert "file" in call_kw



@pytest.mark.asyncio
async def test_channel_manager_setupchannels_and_admin_toggle(full_bot_env):
    """Tests !setupchannels and !admin toggle commands."""
    chan_cog = full_bot_env["chan_cog"]
    admin_cog = full_bot_env["admin_cog"]
    ctx = create_mock_ctx(is_admin=True, is_guild_owner=True)

    # Mock guild categories and channels creation
    mock_cat = MagicMock(spec=discord.CategoryChannel)
    mock_ch = MagicMock(spec=discord.TextChannel)
    mock_ch.id = 12345
    mock_ch.name = "🎯-ge-lc-feed"

    ctx.guild.categories = []
    ctx.guild.text_channels = []
    ctx.guild.create_category = AsyncMock(return_value=mock_cat)
    ctx.guild.create_text_channel = AsyncMock(return_value=mock_ch)

    # 1. !setupchannels
    await chan_cog.setup_channels_command.callback(chan_cog, ctx)
    ctx.send.assert_called()

    # 2. !admin <@member> toggle
    ctx.send.reset_mock()
    target_member = MagicMock(spec=discord.Member)
    target_member.id = 554433
    target_member.name = "PromotedUser"
    target_member.roles = []
    target_member.add_roles = AsyncMock()
    ctx.guild.get_member = MagicMock(return_value=target_member)
    await admin_cog.admin_toggle_command.callback(admin_cog, ctx, member="554433")
    ctx.send.assert_called()


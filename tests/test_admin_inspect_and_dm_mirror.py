"""
Unit Tests for Admin Inspection (!userstatus) and DM Mirror Logging
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
import discord

from database import Database
from engine import WatchdogEngine
from dlsu_api import DLSUApiClient
from utils.embeds import create_user_inspection_embed, create_admin_dm_mirror_embed


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    db_file = tmp_path / "test_inspect.db"
    db = Database(db_path=db_file)
    await db.init_db()
    return db


@pytest.mark.asyncio
async def test_user_inspection_embed_creation(temp_db):
    user_id = 987654
    username = "test_student"

    await temp_db.add_user_watch(user_id, username, "101", "STSWENG", section_name="S04", scope="SECTION")
    await temp_db.upsert_section_state("101", "STSWENG", "S04", capacity=45, enlisted=44, open_slots=1)

    watchlist_data = await temp_db.get_user_watchlist_detailed(user_id)
    pings_enabled = await temp_db.get_user_pings_status(user_id)

    embed = create_user_inspection_embed(
        member_name=username,
        member_id=user_id,
        avatar_url=None,
        watchlist_data=watchlist_data,
        pings_enabled=pings_enabled,
    )

    assert "test_student" in embed.title
    assert "987654" in embed.description
    assert "ACTIVE (Unmuted)" in embed.description
    assert len(embed.fields) == 1
    assert "STSWENG" in embed.fields[0].name


def test_dm_mirror_embed_structure():
    embed = create_admin_dm_mirror_embed(
        username="bEn",
        user_id=123456,
        course_code="STSWENG",
        section_name="S04",
        open_slots=1,
        capacity=45,
        enlisted=44,
        prev_open_slots=0,
    )

    assert "bEn" in embed.title
    assert "STSWENG S04" in embed.description
    assert "1 Open" in embed.description
    assert "Silent" in embed.footer.text


@pytest.mark.asyncio
async def test_dm_dispatch_mirrors_to_admin_logs(tmp_path):
    db_file = tmp_path / "test_mirror_engine.db"
    db = Database(db_path=db_file)
    await db.init_db()

    mock_bot = MagicMock()
    mock_bot.wait_until_ready = AsyncMock()
    mock_bot.is_closed = MagicMock(return_value=False)

    mock_dm_channel = MagicMock()
    mock_dm_channel.send = AsyncMock()
    mock_user = MagicMock()
    mock_user.display_name = "bEn"
    mock_user.send = AsyncMock()

    mock_bot.fetch_user = AsyncMock(return_value=mock_user)
    mock_bot.get_channel = MagicMock(return_value=mock_dm_channel)

    api_client = DLSUApiClient()
    engine = WatchdogEngine(bot=mock_bot, db=db, api_client=api_client)
    await engine.initialize()
    engine.bot_active = True
    engine.is_connected = True
    engine.session_expired = False

    # Configure admin_dm_logs channel
    await db.save_server_channels(guild_id=999, channel_map={"admin_dm_logs": 888888})

    # Add watcher
    await db.add_user_watch(123456, "bEn", "101", "STSWENG", section_name="S04", scope="SECTION")

    # Dispatch DM
    await engine._dispatch_personal_dms(
        course_code="STSWENG",
        course_name="Software Engineering",
        section_name="S04",
        open_slots=1,
        capacity=45,
        enlisted=44,
        teacher="Briane Samson",
        schedule="Fri 11:00",
        prev_open_slots=0,
    )

    # Verify student received DM
    mock_user.send.assert_called_once()

    # Verify mirror log was sent to admin channel with zero pings
    mock_dm_channel.send.assert_called_once()
    args, kwargs = mock_dm_channel.send.call_args
    am = kwargs.get("allowed_mentions")
    assert am is not None
    assert am.everyone is False
    assert am.roles is False
    assert am.users is False


def test_admin_course_inspection_embed():
    from utils.embeds import create_admin_course_inspection_embed
    sections = [
        {"section_name": "S11", "capacity": 45, "enlisted": 44, "open_slots": 1, "teacher": "Prof. Cruz", "schedule": "MW 09:15-10:45"},
        {"section_name": "S12", "capacity": 45, "enlisted": 45, "open_slots": 0, "teacher": "Prof. Santos", "schedule": "TH 11:00-12:30"},
    ]

    embed = create_admin_course_inspection_embed(
        course_code="STSWENG",
        course_name="Software Engineering",
        course_id="367",
        sections=sections,
    )

    assert "STSWENG" in embed.title
    assert "367" in embed.description
    assert "1 Total Open Slots" in embed.description
    assert len(embed.fields) == 2
    assert "Section S11" in embed.fields[0].name
    assert "Prof. Cruz" in embed.fields[0].value
    assert "MW 09:15-10:45" in embed.fields[0].value
    assert "Section S12" in embed.fields[1].name
    assert "FULL" in embed.fields[1].value


@pytest.mark.asyncio
async def test_view_logs_command_variations(tmp_path):
    from cogs.admin import AdminCog
    from config import WATCHDOG_CYCLES_LOG_PATH

    # Create dummy watchdog log
    WATCHDOG_CYCLES_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHDOG_CYCLES_LOG_PATH, "w", encoding="utf-8") as f:
        f.write("[2026-08-31 12:00:00 UTC] Cycle #0001 | Polled 42 courses in 1.2s\n")
        f.write("[2026-08-31 12:00:15 UTC] Cycle #0002 | Polled 42 courses in 1.1s\n")

    mock_bot = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.defer = AsyncMock()
    mock_ctx.send = AsyncMock()
    mock_ctx.author.id = 673532405134655509

    cog = AdminCog(mock_bot, None, None)

    # 1. Test !logs (defaults)
    await cog.view_logs_command.callback(cog, mock_ctx, "watchdog", "15")
    mock_ctx.send.assert_called()
    embed = mock_ctx.send.call_args[1]["embed"]
    assert "Cycle" in embed.description

    # 2. Test !logs 10
    mock_ctx.send.reset_mock()
    await cog.view_logs_command.callback(cog, mock_ctx, "10", "15")
    mock_ctx.send.assert_called()

    # 3. Test !logs watchdog 10
    mock_ctx.send.reset_mock()
    await cog.view_logs_command.callback(cog, mock_ctx, "watchdog", "10")
    mock_ctx.send.assert_called()


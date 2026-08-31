"""
Unit Tests for Channel Permissions Overwrites, Zero-Ping Feeds, and Bot Presence Updates
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from database import Database
from engine import WatchdogEngine
from dlsu_api import DLSUApiClient
from cogs.channel_manager import ChannelManager


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    db_file = tmp_path / "test_permissions.db"
    db = Database(db_path=db_file)
    await db.init_db()
    return db


@pytest.mark.asyncio
async def test_setupchannels_creates_locked_feeds_and_interactive_bot_commands(temp_db):
    mock_bot = MagicMock()
    cog = ChannelManager(mock_bot, temp_db)

    mock_guild = MagicMock(spec=discord.Guild)
    mock_guild.id = 12345
    mock_guild.name = "DLSU Server"
    mock_guild.categories = []
    mock_guild.default_role = MagicMock(spec=discord.Role)
    mock_guild.me = MagicMock(spec=discord.Member)
    mock_guild.me.guild_permissions.manage_channels = True

    created_channels = {}

    async def mock_create_category(name, overwrites=None, reason=None):
        cat = MagicMock(spec=discord.CategoryChannel)
        cat.name = name
        cat.text_channels = []
        cat.overwrites = overwrites or {}
        return cat

    async def mock_create_text_channel(name, category=None, topic="", overwrites=None, reason=None):
        ch = MagicMock(spec=discord.TextChannel)
        ch.name = name
        ch.topic = topic
        ch.overwrites = overwrites or {}
        ch.id = len(created_channels) + 1000
        created_channels[name] = ch
        return ch

    mock_guild.create_category = AsyncMock(side_effect=mock_create_category)
    mock_guild.create_text_channel = AsyncMock(side_effect=mock_create_text_channel)

    mock_ctx = MagicMock()
    mock_ctx.guild = mock_guild
    mock_ctx.defer = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.edit = AsyncMock()
    mock_ctx.send = AsyncMock(return_value=mock_msg)

    # Execute setupchannels
    await cog.setup_channels_command.callback(cog, mock_ctx)

    # 1. Verify #🤖-bot-commands was created with interactive send_messages=True
    assert "🤖-bot-commands" in created_channels
    bot_cmd_ch = created_channels["🤖-bot-commands"]
    everyone_ov = bot_cmd_ch.overwrites[mock_guild.default_role]
    assert everyone_ov.view_channel is True
    assert everyone_ov.read_messages is True
    assert everyone_ov.send_messages is True

    # 2. Verify announcements and feeds have send_messages=False for @everyone
    assert "📢-announcements" in created_channels
    ann_ch = created_channels["📢-announcements"]
    ann_everyone_ov = ann_ch.overwrites[mock_guild.default_role]
    assert ann_everyone_ov.send_messages is False
    assert ann_everyone_ov.create_public_threads is False

    assert "🎯-ge-lc-feed" in created_channels
    ge_lc_ch = created_channels["🎯-ge-lc-feed"]
    ge_lc_everyone_ov = ge_lc_ch.overwrites[mock_guild.default_role]
    assert ge_lc_everyone_ov.send_messages is False
    assert ge_lc_everyone_ov.create_public_threads is False

    assert "💻-ccs-drops" in created_channels
    ccs_ch = created_channels["💻-ccs-drops"]
    ccs_everyone_ov = ccs_ch.overwrites[mock_guild.default_role]
    assert ccs_everyone_ov.send_messages is False

    # 3. Verify mappings saved in database
    saved_channels = await temp_db.get_server_channels(12345)
    assert saved_channels["bot_commands"] == bot_cmd_ch.id
    assert saved_channels["announcements"] == ann_ch.id
    assert saved_channels["ccs"] == ccs_ch.id


@pytest.mark.asyncio
async def test_feed_broadcast_uses_zero_pings(temp_db):
    mock_bot = MagicMock()
    mock_bot.wait_until_ready = AsyncMock()
    mock_bot.is_closed = MagicMock(return_value=False)

    mock_feed_ch = MagicMock()
    mock_feed_ch.send = AsyncMock()
    mock_bot.get_channel = MagicMock(return_value=mock_feed_ch)

    api_client = DLSUApiClient()
    engine = WatchdogEngine(bot=mock_bot, db=temp_db, api_client=api_client)
    await engine.initialize()
    engine.bot_active = True
    engine.is_connected = True
    engine.ge_lc_active = True

    await temp_db.save_server_channels(999, {"ccs": 777, "ge_lc": 888})

    # Broadcast CCS course
    await engine._broadcast_to_feeds(
        course_code="STSWENG",
        course_name="Software Engineering",
        section_name="S04",
        open_slots=1,
        capacity=45,
        enlisted=44,
        teacher="Briane Samson",
        schedule="Fri 11:00",
    )

    mock_feed_ch.send.assert_called_once()
    args, kwargs = mock_feed_ch.send.call_args
    am = kwargs.get("allowed_mentions")
    assert am is not None
    assert am.everyone is False
    assert am.roles is False
    assert am.users is False


@pytest.mark.asyncio
async def test_update_bot_presence(temp_db):
    mock_bot = MagicMock()
    mock_bot.change_presence = AsyncMock()

    api_client = DLSUApiClient()
    engine = WatchdogEngine(bot=mock_bot, db=temp_db, api_client=api_client)
    await engine.initialize()

    # 1. Maintenance mode
    engine.bot_active = False
    await engine.update_bot_presence()
    assert mock_bot.change_presence.call_count == 1
    args, kwargs = mock_bot.change_presence.call_args
    assert kwargs.get("status") == discord.Status.idle

    # 2. Disconnected state
    engine.bot_active = True
    engine.is_connected = False
    engine.session_expired = True
    await engine.update_bot_presence()
    assert mock_bot.change_presence.call_count == 2
    args, kwargs = mock_bot.change_presence.call_args
    assert kwargs.get("status") == discord.Status.dnd

    # 3. Active online state
    engine.is_connected = True
    engine.session_expired = False
    engine.section_slot_cache[("STSWENG", "S01")] = 1
    await engine.update_bot_presence()
    assert mock_bot.change_presence.call_count == 3
    args, kwargs = mock_bot.change_presence.call_args
    assert kwargs.get("status") == discord.Status.online
    act = kwargs.get("activity")
    assert "Courses" in act.name

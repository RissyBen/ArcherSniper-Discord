"""
Unit Tests for Smart Delta Alerting & Anti-Spam Logic
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from database import Database
from engine import WatchdogEngine
from dlsu_api import DLSUApiClient


@pytest_asyncio.fixture
async def mock_engine(tmp_path):
    db_file = tmp_path / "test_engine.db"
    db = Database(db_path=db_file)
    await db.init_db()

    mock_bot = MagicMock()
    mock_bot.wait_until_ready = AsyncMock()
    mock_bot.is_closed = MagicMock(return_value=False)
    mock_bot.get_channel = MagicMock(return_value=None)
    mock_bot.fetch_user = AsyncMock(return_value=None)

    api_client = DLSUApiClient()
    engine = WatchdogEngine(bot=mock_bot, db=db, api_client=api_client)
    await engine.initialize()
    engine.bot_active = True
    engine.is_connected = True
    engine.session_expired = False
    return engine


@pytest.mark.asyncio
async def test_baseline_establishment(mock_engine):
    """Initial check establishes baseline without firing alert."""
    mock_engine._dispatch_personal_dms = AsyncMock()
    mock_engine._broadcast_to_feeds = AsyncMock()

    sec_data = {
        "section_name": "S01",
        "capacity": 45,
        "enlisted": 45,
        "open_slots": 0,
        "teacher": "Test Teacher",
        "schedule": "TTH 09:00",
    }

    await mock_engine._process_section_delta("101", "STSWENG", "Software Engineering", sec_data)

    assert mock_engine.section_slot_cache.get(("STSWENG", "S01")) == 0
    mock_engine._dispatch_personal_dms.assert_not_called()
    mock_engine._broadcast_to_feeds.assert_not_called()


@pytest.mark.asyncio
async def test_full_to_open_triggers_alert(mock_engine):
    """Transition from 0 -> 1 open slot triggers an alert."""
    mock_engine._dispatch_personal_dms = AsyncMock()
    mock_engine._broadcast_to_feeds = AsyncMock()

    # Step 1: Set baseline at 0
    mock_engine.section_slot_cache[("STSWENG", "S01")] = 0

    # Step 2: Slot opens (45 enlisted -> 44 enlisted = 1 open slot)
    sec_data = {
        "section_name": "S01",
        "capacity": 45,
        "enlisted": 44,
        "open_slots": 1,
        "teacher": "Test Teacher",
        "schedule": "TTH 09:00",
    }

    await mock_engine._process_section_delta("101", "STSWENG", "Software Engineering", sec_data)

    assert mock_engine.section_slot_cache.get(("STSWENG", "S01")) == 1
    mock_engine._dispatch_personal_dms.assert_called_once()
    mock_engine._broadcast_to_feeds.assert_called_once()
    args, kwargs = mock_engine._dispatch_personal_dms.call_args
    assert kwargs["open_slots"] == 1
    assert kwargs["prev_open_slots"] == 0


@pytest.mark.asyncio
async def test_slot_increase_triggers_alert(mock_engine):
    """Transition from 1 -> 2 open slots triggers an alert."""
    mock_engine._dispatch_personal_dms = AsyncMock()
    mock_engine._broadcast_to_feeds = AsyncMock()

    # Baseline: 1 open slot
    mock_engine.section_slot_cache[("STSWENG", "S01")] = 1

    # Increase to 2 open slots
    sec_data = {
        "section_name": "S01",
        "capacity": 45,
        "enlisted": 43,
        "open_slots": 2,
        "teacher": "Test Teacher",
        "schedule": "TTH 09:00",
    }

    await mock_engine._process_section_delta("101", "STSWENG", "Software Engineering", sec_data)

    assert mock_engine.section_slot_cache.get(("STSWENG", "S01")) == 2
    mock_engine._dispatch_personal_dms.assert_called_once()
    mock_engine._broadcast_to_feeds.assert_called_once()
    args, kwargs = mock_engine._dispatch_personal_dms.call_args
    assert kwargs["open_slots"] == 2
    assert kwargs["prev_open_slots"] == 1


@pytest.mark.asyncio
async def test_unchanged_slots_are_suppressed(mock_engine):
    """If slots remain identical (e.g. 1 -> 1 or 0 -> 0), duplicate alerts are strictly suppressed."""
    mock_engine._dispatch_personal_dms = AsyncMock()
    mock_engine._broadcast_to_feeds = AsyncMock()

    # Baseline: 1 open slot
    mock_engine.section_slot_cache[("STSWENG", "S01")] = 1

    sec_data = {
        "section_name": "S01",
        "capacity": 45,
        "enlisted": 44,
        "open_slots": 1,
        "teacher": "Test Teacher",
        "schedule": "TTH 09:00",
    }

    await mock_engine._process_section_delta("101", "STSWENG", "Software Engineering", sec_data)
    mock_engine._dispatch_personal_dms.assert_not_called()
    mock_engine._broadcast_to_feeds.assert_not_called()


@pytest.mark.asyncio
async def test_disconnected_session_suppresses_alerts(mock_engine):
    """When session is disconnected/expired, fail-safe mutes student drop alerts."""
    mock_engine._dispatch_personal_dms = AsyncMock()
    mock_engine._broadcast_to_feeds = AsyncMock()
    mock_engine.is_connected = False
    mock_engine.session_expired = True

    # Baseline: 0 open slots
    mock_engine.section_slot_cache[("STSWENG", "S01")] = 0

    sec_data = {
        "section_name": "S01",
        "capacity": 45,
        "enlisted": 40,
        "open_slots": 5,
        "teacher": "Test Teacher",
        "schedule": "TTH 09:00",
    }

    await mock_engine._process_section_delta("101", "STSWENG", "Software Engineering", sec_data)
    mock_engine._dispatch_personal_dms.assert_not_called()
    mock_engine._broadcast_to_feeds.assert_not_called()


@pytest.mark.asyncio
async def test_brand_new_section_triggers_alert_after_baseline(mock_engine):
    """When a brand-new section is added mid-enlistment (after Cycle 1) with open slots, it alerts immediately."""
    mock_engine._dispatch_personal_dms = AsyncMock()
    mock_engine._broadcast_to_feeds = AsyncMock()
    mock_engine.total_poll_cycles = 5  # Beyond initial baseline cycle

    new_sec_data = {
        "section_name": "S15",
        "capacity": 45,
        "enlisted": 0,
        "open_slots": 45,
        "teacher": "New Instructor",
        "schedule": "MW 14:30",
    }

    await mock_engine._process_section_delta("101", "STSWENG", "Software Engineering", new_sec_data)
    mock_engine._dispatch_personal_dms.assert_called_once()
    mock_engine._broadcast_to_feeds.assert_called_once()


@pytest.mark.asyncio
async def test_5min_delayed_disconnect_notifier(mock_engine):
    """Verifies that disconnect alerts wait 5 minutes before pinging, and cancel if auto-reconnect succeeds."""
    mock_engine.disconnect_grace_period_seconds = 0.05
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_engine.bot.get_channel = MagicMock(return_value=mock_channel)
    mock_engine.db.get_all_configured_guilds = AsyncMock(return_value=[12345])
    mock_engine.db.get_server_channels = AsyncMock(return_value={"admin_disconnects": 999, "announcements": 888})

    # 1. Disconnect occurs -> grace task starts, NO pings sent immediately
    await mock_engine._handle_disconnect("HTTP 401 Session Expired")
    assert mock_engine.disconnect_alert_task is not None
    mock_channel.send.assert_not_called()

    # 2. Reconnect succeeds quickly within grace window -> timer cancelled, zero pings sent!
    await mock_engine._on_reconnect_success("Tier 2 Playwright")
    await asyncio.sleep(0.08)
    mock_channel.send.assert_not_called()
    assert mock_engine.disconnect_alert_sent is False

    # 3. If disconnected and NOT reconnected past grace period -> alerts dispatched
    await mock_engine._handle_disconnect("HTTP 401 Session Expired")
    await asyncio.sleep(0.08)
    assert mock_channel.send.call_count >= 1
    assert mock_engine.disconnect_alert_sent is True



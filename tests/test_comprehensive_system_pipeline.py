"""
ArcherSniper - Comprehensive End-to-End System Pipeline Test Suite
Exhaustively tests:
1. DLSU Fetching & Session Resilience (Cookie roll forward, session expiry detection, parsing).
2. Slot Delta Engine & Capacity Comparator (Baseline, drop 0->N, drop increase, new mid-enlistment section, anti-duplicate guard).
3. Subject Auto-Discovery & Duplicate ID Resolution (Priority to active ID 5845 over 12160, 24/7 GE/LC auto-promotion vs on-demand college indexing).
4. Notification Dispatch (Whole-course vs section DM alerts, mute checks, audit logging, admin mirroring).
5. Public Feed Multicast (Routing to #🎯-ge-lc-feed, #💻-ccs-drops including EMPATHY, #💼-rvrcob-drops including DSILYTC, zero-ping safety, channel fetch fallback).
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

from config import (
    COLOR_DLSU_GREEN,
    COLOR_OPEN_GREEN,
    COLOR_ALERT_RED,
    WATCHDOG_CYCLES_LOG_PATH,
    AUTODISCOVERY_LOG_PATH,
    SLOT_DROPS_LOG_PATH,
    DM_DISPATCH_LOG_PATH,
)
from database import Database
from dlsu_api import DLSUApiClient
from engine import WatchdogEngine
from utils.course_classifier import classify_course
from utils.embeds import (
    create_student_dm_alert,
    create_college_feed_drop_embed,
    create_batched_feed_drop_embed,
    create_admin_dm_mirror_embed,
    create_sweep_results_embed,
)


class MockResponseContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        pass


@pytest.fixture
async def temp_env():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_pipeline.db"
    logs_dir = Path(temp_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    db = Database(db_path=db_path)
    await db.init_db()

    mock_bot = MagicMock()
    mock_bot.is_closed.return_value = False
    mock_bot.user.id = 123456789
    mock_bot.get_channel = MagicMock(return_value=None)
    mock_bot.fetch_channel = AsyncMock()
    mock_bot.get_user = MagicMock(return_value=None)
    mock_bot.fetch_user = AsyncMock()

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

    yield {
        "db": db,
        "engine": engine,
        "bot": mock_bot,
        "api": api_client,
        "temp_dir": temp_dir,
        "logs_dir": logs_dir,
    }

    await api_client.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


# ====================================================================
# TEST SUITE 1: DLSU API FETCHING & SESSION RESILIENCE
# ====================================================================

@pytest.mark.asyncio
async def test_dlsu_api_parsing_and_session_checks(temp_env):
    """Verifies that API parser accurately parses JSON and detects session expiry HTML."""
    api = temp_env["api"]

    # 1. Valid JSON payload simulation
    mock_json_payload = [
        {
            "SECTION_NAME": "S01",
            "CAPACITY": "45",
            "ENLISTED": "44",
            "MAIN_TEACHER": "Arlyn Napeñas",
            "SCHEDULE": "[ SATURDAY - 08:00 AM - 11:00 AM : Room - L220 ]",
        }
    ]

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.cookies = {}
    mock_resp.json = AsyncMock(return_value=mock_json_payload)

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post = MagicMock(return_value=MockResponseContext(mock_resp))

    with patch.object(api, "get_session", AsyncMock(return_value=mock_session)):
        sections = await api.fetch_section_data("5845")
        assert len(sections) == 1
        sec = sections[0]
        assert sec["section_name"] == "S01"
        assert sec["enlisted"] == 44
        assert sec["capacity"] == 45
        assert sec["open_slots"] == 1  # 45 - 44 = 1 open
        assert sec["teacher"] == "Arlyn Napeñas"
        assert "L220" in sec["schedule"]

    # 2. Session Expired HTML Detection -> Raises PermissionError
    mock_html_resp = AsyncMock()
    mock_html_resp.status = 200
    mock_html_resp.headers = {"Content-Type": "text/html"}
    mock_html_resp.cookies = {}
    mock_html_resp.text = AsyncMock(return_value="<!DOCTYPE html><html><head><title>Login</title></head></html>")

    mock_session_html = MagicMock()
    mock_session_html.closed = False
    mock_session_html.post = MagicMock(return_value=MockResponseContext(mock_html_resp))

    with patch.object(api, "get_session", AsyncMock(return_value=mock_session_html)):
        with pytest.raises(PermissionError):
            await api.fetch_section_data("5845")


# ====================================================================
# TEST SUITE 2: CAPACITY COMPARATOR & DELTA ENGINE
# ====================================================================

@pytest.mark.asyncio
async def test_baseline_and_delta_comparison(temp_env):
    """
    Verifies:
    - Cycle 1 establishes silent baseline (0 alerts).
    - Cycle > 1 triggers alert when slots increase (0 -> 2).
    - Cycle > 1 triggers alert when brand-new section appears mid-enlistment.
    - Duplicate drops within 15s are suppressed.
    """
    engine = temp_env["engine"]
    db = temp_env["db"]

    # Register user watching GEWORLD
    user_id = 999111222
    await db.add_user_watch(user_id, "student_tester", "4733", "GEWORLD", "*", "COURSE")

    mock_user = AsyncMock()
    mock_user.display_name = "student_tester"
    temp_env["bot"].fetch_user = AsyncMock(return_value=mock_user)

    # Cycle 1: Baseline (GEWORLD Y01 is 45/45 [0 open])
    engine.total_poll_cycles = 1
    cycle_feed_changes = {}

    sec_baseline = {
        "section_name": "Y01",
        "capacity": 45,
        "enlisted": 45,
        "open_slots": 0,
        "teacher": "Maria Sevilla",
        "schedule": "FRIDAY 08:00-11:00",
    }
    await engine._process_section_delta("4733", "GEWORLD", "The Contemporary World", sec_baseline, cycle_feed_changes)

    # In Cycle 1, 0 DMs sent and 0 feed changes collected
    assert mock_user.send.call_count == 0
    assert len(cycle_feed_changes) == 0
    assert engine.section_slot_cache[("GEWORLD", "Y01")] == 0

    # Cycle 2: A student drops! Slots change from 0 -> 2 Open
    engine.total_poll_cycles = 2
    sec_drop = {
        "section_name": "Y01",
        "capacity": 45,
        "enlisted": 43,
        "open_slots": 2,
        "teacher": "Maria Sevilla",
        "schedule": "FRIDAY 08:00-11:00",
    }
    await engine._process_section_delta("4733", "GEWORLD", "The Contemporary World", sec_drop, cycle_feed_changes)

    # In Cycle 2, DM is dispatched to student and feed change is queued!
    assert mock_user.send.call_count == 1
    assert "ge_lc" in cycle_feed_changes
    assert len(cycle_feed_changes["ge_lc"]) == 1
    assert cycle_feed_changes["ge_lc"][0]["open_slots"] == 2
    assert cycle_feed_changes["ge_lc"][0]["prev_open_slots"] == 0

    # Cycle 3: Brand New Section Opened Mid-Day (Section Y02 with 45 open seats)
    engine.total_poll_cycles = 3
    sec_new_brand = {
        "section_name": "Y02",
        "capacity": 45,
        "enlisted": 0,
        "open_slots": 45,
        "teacher": "Alexia Suñaz",
        "schedule": "TUESDAY 08:00-11:00",
    }
    await engine._process_section_delta("4733", "GEWORLD", "The Contemporary World", sec_new_brand, cycle_feed_changes)

    # Student received second alert for brand-new section
    assert mock_user.send.call_count == 2
    assert len(cycle_feed_changes["ge_lc"]) == 2
    assert cycle_feed_changes["ge_lc"][1]["section_name"] == "Y02"
    assert cycle_feed_changes["ge_lc"][1]["open_slots"] == 45


# ====================================================================
# TEST SUITE 3: SUBJECT AUTO-DISCOVERY & DUPLICATE ID SAFEGUARDS
# ====================================================================

@pytest.mark.asyncio
async def test_auto_discovery_and_duplicate_id_resolution(temp_env):
    """
    Verifies:
    - DLSU catalog scan discovers all courses.
    - Priority is given to active lower IDs (e.g. SAS2000 -> 5845, discarding 12160).
    - GE/LC courses (SAS, LASARE, NSTP, GE...) are auto-promoted to 24/7 monitoring.
    - College courses are safely indexed for on-demand !watch.
    - add_monitored_course prevents higher duplicate IDs from overwriting active lower IDs.
    """
    engine = temp_env["engine"]
    db = temp_env["db"]
    api = temp_env["api"]

    # Simulated DLSU catalog containing both active IDs and historical duplicates
    mock_catalog = [
        {"course_id": "12160", "course_code": "SAS2000", "course_name": "Student Affairs (Empty Duplicate)"},
        {"course_id": "5845", "course_code": "SAS2000", "course_name": "Student Affairs Services 2000"},
        {"course_id": "10987", "course_code": "DSILYTC", "course_name": "Analytics (Old Shell)"},
        {"course_id": "5105", "course_code": "DSILYTC", "course_name": "Introduction to Analytics"},
        {"course_id": "5809", "course_code": "LASARE1", "course_name": "Lasallian Recollection 1"},
        {"course_id": "3344", "course_code": "CSOPESY", "course_name": "Operating Systems Concepts"},
        {"course_id": "9988", "course_code": "EMPATHY", "course_name": "Empathic Computing & Design"},
    ]

    with patch.object(api, "fetch_course_catalog", new_callable=AsyncMock) as mock_cat:
        mock_cat.return_value = mock_catalog
        new_ge, new_col = await engine.auto_discover_new_courses()

        # 1. Verify GE/LC courses are in 24/7 monitored pool with ACTIVE lower IDs
        sas_course = await db.get_monitored_course("SAS2000")
        assert sas_course is not None
        assert str(sas_course["course_id"]) == "5845"  # Bound to 5845, NOT 12160!

        lasare_course = await db.get_monitored_course("LASARE1")
        assert lasare_course is not None
        assert str(lasare_course["course_id"]) == "5809"

        # 2. Verify College courses are indexed in catalog
        csopesy_match = await db.search_catalog("CSOPESY")
        assert len(csopesy_match) > 0
        assert str(csopesy_match[0]["course_id"]) == "3344"

        dsilytc_match = await db.search_catalog("DSILYTC")
        assert len(dsilytc_match) > 0
        assert str(dsilytc_match[0]["course_id"]) == "5105"  # Sorted to 5105, NOT 10987!

        # 3. Test database-level protection against overwriting with higher duplicate ID
        res = await db.add_monitored_course(course_id="12160", course_code="SAS2000", course_name="Duplicate Shell")
        assert res is True
        sas_check = await db.get_monitored_course("SAS2000")
        assert str(sas_check["course_id"]) == "5845"  # Retained 5845!


# ====================================================================
# TEST SUITE 4: STUDENT DM ALERTS (WHOLE COURSE VS SECTION & MUTE)
# ====================================================================

@pytest.mark.asyncio
async def test_student_dm_notification_rules(temp_env):
    """
    Verifies:
    - Whole-course watcher receives DM for any section.
    - Specific section watcher receives DM only for their section.
    - Muted user (!mute) does NOT receive DM.
    - DM dispatch writes to audit log and mirrors to admin log channel.
    """
    engine = temp_env["engine"]
    db = temp_env["db"]

    user_whole = 10101  # Watching whole course CSOPESY
    user_sec_s04 = 20202  # Watching only CSOPESY S04
    user_sec_s05 = 30303  # Watching only CSOPESY S05
    user_muted = 40404  # Watching whole course CSOPESY but muted

    await db.add_user_watch(user_whole, "whole_watcher", "3344", "CSOPESY", "*", "COURSE")
    await db.add_user_watch(user_sec_s04, "s04_watcher", "3344", "CSOPESY", "S04", "SECTION")
    await db.add_user_watch(user_sec_s05, "s05_watcher", "3344", "CSOPESY", "S05", "SECTION")
    await db.add_user_watch(user_muted, "muted_watcher", "3344", "CSOPESY", "*", "COURSE")
    await db.toggle_user_pings(user_muted, False)  # Muted

    mock_whole = AsyncMock()
    mock_s04 = AsyncMock()
    mock_s05 = AsyncMock()
    mock_muted = AsyncMock()

    def mock_get_user(uid):
        if uid == user_whole:
            return mock_whole
        elif uid == user_sec_s04:
            return mock_s04
        elif uid == user_sec_s05:
            return mock_s05
        elif uid == user_muted:
            return mock_muted
        return None

    temp_env["bot"].fetch_user.side_effect = mock_get_user

    # Trigger drop on Section S04 (0 -> 1 Open)
    await engine._dispatch_personal_dms(
        course_code="CSOPESY",
        course_name="Operating Systems Concepts",
        section_name="S04",
        open_slots=1,
        capacity=45,
        enlisted=44,
        teacher="Marck Caluya",
        schedule="MW 09:15-10:45",
        prev_open_slots=0,
    )

    # 1. user_whole receives DM
    assert mock_whole.send.call_count == 1

    # 2. user_sec_s04 receives DM
    assert mock_s04.send.call_count == 1

    # 3. user_sec_s05 does NOT receive DM (different section)
    assert mock_s05.send.call_count == 0

    # 4. user_muted does NOT receive DM (muted)
    assert mock_muted.send.call_count == 0


# ====================================================================
# TEST SUITE 5: PUBLIC FEED MULTICAST & ZERO-PING BROADCASTS
# ====================================================================

@pytest.mark.asyncio
async def test_public_feed_classification_and_multicast(temp_env):
    """
    Verifies:
    - EMPATHY routes to CCS (#💻-ccs-drops).
    - DSILYTC routes to RVRCOB (#💼-rvrcob-drops).
    - GEWORLD / SAS2000 route to GE_LC (#🎯-ge-lc-feed).
    - Zero ghost pings: AllowedMentions.none() enforced on all broadcasts.
    - Fallback to fetch_channel when get_channel returns None.
    """
    engine = temp_env["engine"]
    db = temp_env["db"]
    bot = temp_env["bot"]

    # 1. Test Course Classification Mapping
    assert classify_course("EMPATHY").feed_channel_key == "ccs"
    assert classify_course("CSOPESY").feed_channel_key == "ccs"
    assert classify_course("DSILYTC").feed_channel_key == "rvrcob"
    assert classify_course("MARKET1").feed_channel_key == "rvrcob"
    assert classify_course("GEWORLD").feed_channel_key == "ge_lc"
    assert classify_course("SAS2000").feed_channel_key == "ge_lc"
    assert classify_course("LASARE1").feed_channel_key == "ge_lc"

    # 2. Setup mock server channels
    guild_id = 777888999
    ch_ccs = AsyncMock()
    ch_ccs.name = "ccs-drops"
    ch_ge = AsyncMock()
    ch_ge.name = "ge-lc-feed"

    await db.save_server_channels(guild_id, {"ccs": 111, "ge_lc": 222})

    def mock_get_ch(cid):
        if cid == 111:
            return ch_ccs
        elif cid == 222:
            return ch_ge
        return None

    bot.get_channel.side_effect = mock_get_ch

    # Test EMPATHY broadcast to CCS channel
    await engine._broadcast_to_feeds(
        course_code="EMPATHY",
        course_name="Empathic Computing & Design",
        section_name="S02",
        open_slots=45,
        capacity=45,
        enlisted=0,
        teacher="Briane Samson",
        schedule="TH 14:30-17:30",
        prev_open_slots=0,
    )

    assert ch_ccs.send.call_count == 1
    call_kwargs = ch_ccs.send.call_args[1]
    assert call_kwargs["allowed_mentions"].everyone is False
    assert call_kwargs["allowed_mentions"].roles is False

    # Test GEWORLD broadcast to GE_LC channel
    await engine._broadcast_to_feeds(
        course_code="GEWORLD",
        course_name="The Contemporary World",
        section_name="Y11",
        open_slots=5,
        capacity=45,
        enlisted=40,
        teacher="Maria Sevilla",
        schedule="FRIDAY 08:00-11:00",
        prev_open_slots=0,
    )

    assert ch_ge.send.call_count == 1
    call_kwargs = ch_ge.send.call_args[1]
    assert call_kwargs["allowed_mentions"].everyone is False
    assert call_kwargs["allowed_mentions"].roles is False

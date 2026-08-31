"""
Unit Tests for Exact Watchlist Rules, Scopes, Unwatch Restrictions, and Mute/Unmute
"""

import pytest
import pytest_asyncio
from database import Database


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    db_file = tmp_path / "test_watchlist_rules.db"
    db = Database(db_path=db_file)
    await db.init_db()
    return db


@pytest.mark.asyncio
async def test_watch_whole_course_vs_section(temp_db):
    user_id = 123456
    username = "archer_dev"

    # 1. Add whole course (scope='COURSE')
    await temp_db.add_user_watch(user_id, username, "101", "STSWENG", section_name="*", scope="COURSE")

    summary = await temp_db.get_user_monitored_summary(user_id)
    assert len(summary) == 1
    assert summary[0]["course_code"] == "STSWENG"
    assert summary[0]["scope"] == "COURSE"
    assert summary[0]["section_name"] == "*"

    # 2. Add specific section (scope='SECTION')
    await temp_db.add_user_watch(user_id, username, "102", "CCPROG2", section_name="S11", scope="SECTION")

    summary = await temp_db.get_user_monitored_summary(user_id)
    assert len(summary) == 2
    codes = {s["course_code"]: s for s in summary}
    assert "CCPROG2" in codes
    assert codes["CCPROG2"]["scope"] == "SECTION"
    assert codes["CCPROG2"]["section_name"] == "S11"
    assert "STSWENG" in codes
    assert codes["STSWENG"]["scope"] == "COURSE"
    assert codes["STSWENG"]["section_name"] == "*"


@pytest.mark.asyncio
async def test_unwatch_scope_enforcement_rule(temp_db):
    """
    CRITICAL RULE TEST:
    If a user is watching the entire course (e.g. STSWENG), and tries to unwatch
    a specific section (e.g. STSWENG S04), it MUST be blocked and rejected!
    """
    user_id = 123456
    username = "archer_dev"

    # User watches whole course STSWENG
    await temp_db.add_user_watch(user_id, username, "101", "STSWENG", section_name="*", scope="COURSE")

    # Attempt to unwatch a specific section S04
    success, reason, remaining = await temp_db.remove_user_watch(user_id, "STSWENG", section_name="S04")
    assert success is False
    assert reason == "BLOCKED_COURSE_SCOPE"
    assert remaining == 1

    # Attempt to unwatch the entire course STSWENG
    success, reason, remaining = await temp_db.remove_user_watch(user_id, "STSWENG", section_name=None)
    assert success is True
    assert reason == "SUCCESS"
    assert remaining == 0


@pytest.mark.asyncio
async def test_unwatch_specific_section_success(temp_db):
    """User watching a specific section can remove that specific section."""
    user_id = 123456
    username = "archer_dev"

    # User watches specific section S04
    await temp_db.add_user_watch(user_id, username, "101", "STSWENG", section_name="S04", scope="SECTION")

    # Removing S04 succeeds
    success, reason, remaining = await temp_db.remove_user_watch(user_id, "STSWENG", section_name="S04")
    assert success is True
    assert reason == "SUCCESS"
    assert remaining == 0


@pytest.mark.asyncio
async def test_mute_and_unmute_pings(temp_db):
    """Muting/unmuting toggles pings_enabled without deleting watchlist items."""
    user_id = 123456
    username = "archer_dev"

    await temp_db.add_user_watch(user_id, username, "101", "STSWENG", section_name="*", scope="COURSE")
    await temp_db.add_user_watch(user_id, username, "102", "CCPROG2", section_name="S11", scope="SECTION")

    assert await temp_db.get_user_pings_status(user_id) is True

    # Mute pings
    count = await temp_db.toggle_user_pings(user_id, enabled=False)
    assert count == 2
    assert await temp_db.get_user_pings_status(user_id) is False

    # Watchlist items are still intact
    summary = await temp_db.get_user_monitored_summary(user_id)
    assert len(summary) == 2

    # Active watchers check for alerts returns empty because pings_enabled == 0
    watchers = await temp_db.get_active_watchers_for_section("STSWENG", "S01")
    assert len(watchers) == 0

    # Unmute pings
    await temp_db.toggle_user_pings(user_id, enabled=True)
    assert await temp_db.get_user_pings_status(user_id) is True

    # Active watchers check now returns the user
    watchers = await temp_db.get_active_watchers_for_section("STSWENG", "S01")
    assert len(watchers) == 1


@pytest.mark.asyncio
async def test_watchlist_detailed_expansion(temp_db):
    """If a whole course was watched, detailed watchlist expands to all section states."""
    user_id = 123456
    username = "archer_dev"

    # Seed section states
    await temp_db.upsert_section_state("101", "STSWENG", "S01", capacity=45, enlisted=44, open_slots=1)
    await temp_db.upsert_section_state("101", "STSWENG", "S02", capacity=45, enlisted=45, open_slots=0)
    await temp_db.upsert_section_state("101", "STSWENG", "S03", capacity=40, enlisted=38, open_slots=2)

    # Watch whole course
    await temp_db.add_user_watch(user_id, username, "101", "STSWENG", section_name="*", scope="COURSE")

    detailed = await temp_db.get_user_watchlist_detailed(user_id)
    assert len(detailed) == 1
    assert detailed[0]["course_code"] == "STSWENG"
    assert detailed[0]["scope"] == "COURSE"
    assert len(detailed[0]["sections"]) == 3
    assert detailed[0]["sections"][0]["section_name"] == "S01"
    assert detailed[0]["sections"][0]["open_slots"] == 1


@pytest.mark.asyncio
async def test_watchlist_persistence_across_restart_and_stop(tmp_path):
    """
    Verifies that all user watchlists and monitored courses persist and resume checking
    when the bot is stopped via command or process shutdown, and restarted.
    """
    db_file = tmp_path / "test_persistence.db"
    
    # 1. Initial bot session: User subscribes to courses
    db1 = Database(db_path=db_file)
    await db1.init_db()
    await db1.add_monitored_course("101", "STSWENG", "Software Engineering")
    await db1.add_monitored_course("102", "LCFILIB", "Filipino")
    await db1.add_user_watch(111, "Student1", "101", "STSWENG", section_name="*", scope="COURSE")
    await db1.add_user_watch(222, "Student2", "102", "LCFILIB", section_name="S11", scope="SECTION")
    await db1.set_bot_active(True)
    
    # Verify watches exist
    assert len(await db1.get_active_watchers_for_section("STSWENG", "S01")) == 1
    assert len(await db1.get_active_watchers_for_section("LCFILIB", "S11")) == 1

    # 2. Bot gets stopped (via !stop or Ctrl+C)
    await db1.set_bot_active(False)
    del db1

    # 3. Bot process starts up again (python bot.py -> !start)
    db2 = Database(db_path=db_file)
    await db2.init_db()
    await db2.set_bot_active(True)

    # 4. Confirm all watchlists and monitoring continue seamlessly
    watchers_stsweng = await db2.get_active_watchers_for_section("STSWENG", "S01")
    watchers_lcfilib = await db2.get_active_watchers_for_section("LCFILIB", "S11")
    
    assert len(watchers_stsweng) == 1
    assert watchers_stsweng[0]["user_id"] == 111
    assert len(watchers_lcfilib) == 1
    assert watchers_lcfilib[0]["user_id"] == 222

    # Verify monitored course pool also retained
    monitored = await db2.get_monitored_courses()
    monitored_codes = {m["course_code"] for m in monitored}
    assert "STSWENG" in monitored_codes
    assert "LCFILIB" in monitored_codes

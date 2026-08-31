"""
Unit Tests for Database Persistence Layer
"""

import pytest
import pytest_asyncio
from database import Database


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    db_file = tmp_path / "test_archersniper.db"
    db = Database(db_path=db_file)
    await db.init_db()
    return db


@pytest.mark.asyncio
async def test_master_auth_persistence(temp_db):
    cookies = {"__RequestVerificationToken": "tok_abc", "__Secure-SID": "sid_xyz"}
    headers = {"User-Agent": "TestBot"}

    await temp_db.save_master_auth(cookies=cookies, headers=headers, status="CONNECTED")
    auth = await temp_db.get_master_auth()

    assert auth is not None
    assert auth["cookies"]["__RequestVerificationToken"] == "tok_abc"
    assert auth["headers"]["User-Agent"] == "TestBot"
    assert auth["status"] == "CONNECTED"

    # Update status only
    await temp_db.update_auth_status("DISCONNECTED")
    auth_updated = await temp_db.get_master_auth()
    assert auth_updated["status"] == "DISCONNECTED"
    assert auth_updated["cookies"]["__RequestVerificationToken"] == "tok_abc"


@pytest.mark.asyncio
async def test_system_state_and_server_channels(temp_db):
    # System state
    state = await temp_db.get_system_state()
    assert state["bot_active"] is False

    await temp_db.set_bot_active(True)
    state_updated = await temp_db.get_system_state()
    assert state_updated["bot_active"] is True

    await temp_db.set_intervals(poll_interval=12.0, heartbeat_interval=45.0)
    state_timing = await temp_db.get_system_state()
    assert state_timing["poll_interval"] == 12.0
    assert state_timing["heartbeat_interval"] == 45.0

    # Server channels
    channel_map = {
        "announcements": 111111,
        "ge_lc": 222222,
        "ccs": 333333,
        "admin_commands": 444444,
    }
    await temp_db.save_server_channels(guild_id=9999, channel_map=channel_map)

    saved = await temp_db.get_server_channels(guild_id=9999)
    assert saved["announcements"] == 111111
    assert saved["ccs"] == 333333

    assert await temp_db.get_server_channel(9999, "ge_lc") == 222222
    assert await temp_db.get_server_channel(9999, "non_existent") is None


@pytest.mark.asyncio
async def test_monitored_courses(temp_db):
    await temp_db.add_monitored_course("101", "STSWENG", "Software Engineering", "Admin")
    await temp_db.add_monitored_course("102", "CSARCH1", "Computer Architecture", "Admin")

    courses = await temp_db.get_monitored_courses()
    assert len(courses) == 2
    codes = [c["course_code"] for c in courses]
    assert "STSWENG" in codes
    assert "CSARCH1" in codes

    # Lookup by code
    found = await temp_db.get_monitored_course("stsweng")
    assert found is not None
    assert found["course_id"] == "101"

    # Remove
    deleted = await temp_db.remove_monitored_course("STSWENG")
    assert deleted is True
    assert len(await temp_db.get_monitored_courses()) == 1


@pytest.mark.asyncio
async def test_section_states(temp_db):
    await temp_db.upsert_section_state("101", "STSWENG", "S01", capacity=45, enlisted=44, open_slots=1, teacher="Briane", schedule="M/W")

    state = await temp_db.get_section_state("101", "S01")
    assert state is not None
    assert state["capacity"] == 45
    assert state["enlisted"] == 44
    assert state["open_slots"] == 1
    assert state["teacher"] == "Briane"


@pytest.mark.asyncio
async def test_course_catalog(temp_db):
    await temp_db.upsert_catalog_course("201", "LBYARCH", "Computer Architecture Lab", 155)

    results = await temp_db.search_catalog("lbyarch")
    assert len(results) == 1
    assert results[0]["course_id"] == "201"

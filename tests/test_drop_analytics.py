"""
Unit Tests for Drop Analytics and Statistics Module
"""

import pytest
import pytest_asyncio
from database import Database
from utils.embeds import create_drop_analytics_embed


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    db_file = tmp_path / "test_analytics.db"
    db = Database(db_path=db_file)
    await db.init_db()
    return db


@pytest.mark.asyncio
async def test_record_and_aggregate_drop_analytics(temp_db):
    # Seed courses and watchlists
    await temp_db.add_monitored_course("101", "STSWENG", "Software Engineering")
    await temp_db.add_monitored_course("102", "CCPROG2", "Programming 2")

    await temp_db.add_user_watch(1, "alice", "101", "STSWENG", "S01", "SECTION")
    await temp_db.add_user_watch(2, "bob", "101", "STSWENG", "S02", "SECTION")
    await temp_db.add_user_watch(3, "charlie", "102", "CCPROG2", "*", "COURSE")

    # Record drops across different hours
    await temp_db.record_drop_event("STSWENG", "S01", open_slots=1, capacity=45, enlisted=44, hour_of_day=9)
    await temp_db.record_drop_event("STSWENG", "S02", open_slots=2, capacity=45, enlisted=43, hour_of_day=14)
    await temp_db.record_drop_event("CCPROG2", "S11", open_slots=1, capacity=40, enlisted=39, hour_of_day=19)

    # Update fill duration for STSWENG S01
    await temp_db.update_drop_event_duration("STSWENG", "S01", duration_seconds=35)

    # Get analytics
    stats = await temp_db.get_drop_analytics()

    assert stats["total_drops"] == 3
    assert stats["active_watchers"] == 3
    assert stats["active_courses"] == 2
    assert stats["morning_drops"] == 1
    assert stats["afternoon_drops"] == 1
    assert stats["evening_drops"] == 1

    # Check top courses
    assert len(stats["top_courses"]) == 2
    assert stats["top_courses"][0]["course_code"] == "STSWENG"
    assert stats["top_courses"][0]["watcher_count"] == 2
    assert stats["top_courses"][0]["drops_caught"] == 2

    # Check recent drops
    assert len(stats["recent_drops"]) == 3
    stsweng_drop = [r for r in stats["recent_drops"] if r["course_code"] == "STSWENG" and r["section_name"] == "S01"][0]
    assert stsweng_drop["duration_seconds"] == 35

    # Test embed generation
    embed = create_drop_analytics_embed(stats)
    assert "Course Drop Analytics" in embed.title
    assert "STSWENG" in str(embed.fields)

"""
Unit Tests for Course Catalog Extended Search and Term Pruner
"""

import pytest
import pytest_asyncio
from database import Database
from utils.embeds import create_course_search_embed


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    db_file = tmp_path / "test_search_prune.db"
    db = Database(db_path=db_file)
    await db.init_db()
    return db


@pytest.mark.asyncio
async def test_search_catalog_extended(temp_db):
    await temp_db.upsert_catalog_course("101", "STSWENG", "Object-Oriented Software Engineering")
    await temp_db.upsert_catalog_course("102", "CCAPDEV", "Web Application Development")
    await temp_db.upsert_catalog_course("103", "CCPROG2", "Programming with Structured Data Types")
    await temp_db.upsert_catalog_course("104", "CCINFO", "Information Management and Databases")

    # Search by code
    res1 = await temp_db.search_catalog_extended("STSWENG")
    assert len(res1) == 1
    assert res1[0]["course_code"] == "STSWENG"

    # Search by multi-word keyword
    res2 = await temp_db.search_catalog_extended("software engineering")
    assert len(res2) == 1
    assert res2[0]["course_code"] == "STSWENG"

    # Search by general keyword
    res3 = await temp_db.search_catalog_extended("web application")
    assert len(res3) == 1
    assert res3[0]["course_code"] == "CCAPDEV"

    # Test embed formatting
    embed = create_course_search_embed("web application", res3)
    assert "CCAPDEV" in str(embed.fields)


@pytest.mark.asyncio
async def test_prune_all_watchlists(temp_db):
    # Seed server channels and watchlists
    await temp_db.save_server_channels(999, {"announcements": 111, "ccs": 222})
    await temp_db.add_user_watch(1, "student1", "101", "STSWENG", "S01", "SECTION")
    await temp_db.add_user_watch(2, "student2", "102", "CCPROG2", "*", "COURSE")

    assert await temp_db.get_all_active_watchers_count() == 2

    # Prune watchlists
    deleted = await temp_db.prune_all_watchlists()
    assert deleted == 2
    assert await temp_db.get_all_active_watchers_count() == 0

    # Ensure channels remain completely intact
    channels = await temp_db.get_server_channels(999)
    assert channels["announcements"] == 111
    assert channels["ccs"] == 222

"""
Unit tests for the 4-Tier Zero-Touch Authentication & Session Recovery Hierarchy:
- Tier 2: PlaywrightSessionRefresher
- Tier 3: HealthWebServer Webhook Endpoints (/api/update_cookies, /api/update_curl)
- Tier 4: Engine Reconnection with New Auth
"""

import pytest
from aiohttp import web
from unittest.mock import AsyncMock, MagicMock

from utils.session_refresher import PlaywrightSessionRefresher
from utils.web_server import HealthWebServer
from database import Database
from engine import WatchdogEngine


@pytest.mark.asyncio
async def test_session_refresher_init():
    refresher = PlaywrightSessionRefresher(target_url="https://archershub.dlsu.edu.ph/CourseFinder/")
    assert refresher.target_url == "https://archershub.dlsu.edu.ph/CourseFinder/"
    assert not refresher.is_running


@pytest.mark.asyncio
async def test_web_server_options_cors():
    mock_bot = MagicMock()
    server = HealthWebServer(bot=mock_bot, port=8080)
    
    # Test handle_options
    mock_req = MagicMock()
    resp = await server.handle_options(mock_req)
    assert resp.status == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"


@pytest.mark.asyncio
async def test_web_server_update_cookies_endpoint(tmp_path):
    db_path = tmp_path / "test_auth.db"
    db = Database(db_path=db_path)
    await db.init_db()

    mock_bot = MagicMock()
    mock_bot.db = db
    mock_engine = MagicMock()
    mock_engine.reconnect_with_new_auth = AsyncMock(return_value=True)
    mock_bot.engine = mock_engine

    server = HealthWebServer(bot=mock_bot, port=8080)

    # Mock web.Request with cookies JSON payload
    req = MagicMock()
    req.text = AsyncMock(return_value='{"cookies": "ASP.NET_SessionId=abcdef12345; .ASPXAUTH=XYZ789;"}')

    resp = await server.handle_update_cookies(req)
    assert resp.status == 200
    
    auth = await db.get_master_auth()
    assert auth is not None
    assert auth["cookies"].get("ASP.NET_SessionId") == "abcdef12345"
    assert auth["cookies"].get(".ASPXAUTH") == "XYZ789"
    assert mock_engine.reconnect_with_new_auth.called


@pytest.mark.asyncio
async def test_engine_reconnect_with_new_auth(tmp_path):
    db_path = tmp_path / "test_engine_auth.db"
    db = Database(db_path=db_path)
    await db.init_db()

    mock_api = MagicMock()
    mock_api.send_heartbeat = AsyncMock(return_value=True)
    mock_api.update_auth = MagicMock()
    mock_api.cookies = {"ASP.NET_SessionId": "test_cookie"}

    engine = WatchdogEngine(bot=MagicMock(), db=db, api_client=mock_api)
    await engine.initialize()

    result = await engine.reconnect_with_new_auth(
        new_cookies={"ASP.NET_SessionId": "new_cookie_val"},
        source_label="Unit Test",
    )

    assert result is True
    assert engine.is_connected is True
    assert engine.session_expired is False

"""
Unit Tests for DLSU CourseFinder API Client
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from dlsu_api import DLSUApiClient


class MockResponseContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        pass


@pytest.mark.asyncio
async def test_api_client_initialization_and_auth_update():
    cookies = {"__RequestVerificationToken": "tok1", "__Secure-SID": "sid1"}
    headers = {"User-Agent": "CustomUA"}
    client = DLSUApiClient(cookies=cookies, headers=headers)

    assert client.cookies["__RequestVerificationToken"] == "tok1"
    assert client.custom_headers["User-Agent"] == "CustomUA"

    # Update auth
    client.update_auth({"ApplicationGatewayAffinity": "affinity1"})
    assert client.cookies["ApplicationGatewayAffinity"] == "affinity1"
    assert client.cookies["__RequestVerificationToken"] == "tok1"

    await client.close()


@pytest.mark.asyncio
async def test_fetch_section_data_parsing():
    raw_mock_json = [
        {
            "SECTION_NAME": "S01",
            "CAPACITY": "45",
            "ENLISTED": "43",
            "MAIN_TEACHER": "Briane Samson",
            "SCHEDULE": "[ FRIDAY - 11:00 AM - 12:30 PM : Room - G204 ]",
        },
        {
            "SECTION_NAME": "S02",
            "CAPACITY": "40",
            "ENLISTED": "40",
            "MAIN_TEACHER": "TBA",
            "SCHEDULE": "[ TUESDAY - 11:00 AM - 12:30 PM : Online ]",
        },
    ]

    client = DLSUApiClient()

    # Mock response
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Type": "application/json; charset=utf-8"}
    mock_resp.cookies = {}
    mock_resp.json = AsyncMock(return_value=raw_mock_json)

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post = MagicMock(return_value=MockResponseContext(mock_resp))

    with patch.object(client, "get_session", AsyncMock(return_value=mock_session)):
        sections = await client.fetch_section_data("12345")

        assert len(sections) == 2
        assert sections[0]["section_name"] == "S01"
        assert sections[0]["capacity"] == 45
        assert sections[0]["enlisted"] == 43
        assert sections[0]["open_slots"] == 2
        assert sections[0]["teacher"] == "Briane Samson"

        assert sections[1]["section_name"] == "S02"
        assert sections[1]["capacity"] == 40
        assert sections[1]["enlisted"] == 40
        assert sections[1]["open_slots"] == 0


@pytest.mark.asyncio
async def test_fetch_section_data_session_expired_html():
    client = DLSUApiClient()

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.cookies = {}
    mock_resp.text = AsyncMock(return_value="<!DOCTYPE html><html><head><title>Login</title></head></html>")

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post = MagicMock(return_value=MockResponseContext(mock_resp))

    with patch.object(client, "get_session", AsyncMock(return_value=mock_session)):
        with pytest.raises(PermissionError):
            await client.fetch_section_data("12345")

"""
Unit Tests for Server Owner !admin Toggle Command & ArcherSniper Admin Role
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
import discord

from database import Database
from engine import WatchdogEngine
from dlsu_api import DLSUApiClient
from cogs.admin import AdminCog
from cogs.help import user_is_admin, user_is_owner, get_admin_overview_embed
from config import ADMIN_ROLE_NAME


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    db_file = tmp_path / "test_owner_admin.db"
    db = Database(db_path=db_file)
    await db.init_db()
    return db


def test_user_is_admin_with_custom_role():
    guild = MagicMock(spec=discord.Guild)
    guild.owner = None

    admin_role = MagicMock(spec=discord.Role)
    admin_role.name = ADMIN_ROLE_NAME

    member_with_role = MagicMock(spec=discord.Member)
    member_with_role.id = 55555
    member_with_role.guild_permissions.administrator = False
    member_with_role.roles = [admin_role]

    assert user_is_admin(member_with_role, guild) is True

    member_without_role = MagicMock(spec=discord.Member)
    member_without_role.id = 66666
    member_without_role.guild_permissions.administrator = False
    member_without_role.roles = []

    assert user_is_admin(member_without_role, guild) is False


def test_user_is_owner():
    guild = MagicMock(spec=discord.Guild)
    owner_member = MagicMock(spec=discord.Member)
    owner_member.id = 11111
    guild.owner = owner_member

    assert user_is_owner(owner_member, guild) is True

    other_member = MagicMock(spec=discord.Member)
    other_member.id = 22222

    assert user_is_owner(other_member, guild) is False


def test_admin_help_overview_shows_owner_field_only_to_owner():
    # Non-owner admin embed
    embed_admin = get_admin_overview_embed(is_owner=False)
    field_names_admin = [f.name for f in embed_admin.fields]
    assert "👑 Server Owner Controls" not in field_names_admin

    # Owner admin embed
    embed_owner = get_admin_overview_embed(is_owner=True)
    field_names_owner = [f.name for f in embed_owner.fields]
    assert "👑 Server Owner Controls" in field_names_owner


@pytest.mark.asyncio
async def test_admin_toggle_grant_and_revoke(temp_db):
    mock_bot = MagicMock()
    api_client = DLSUApiClient()
    engine = WatchdogEngine(bot=mock_bot, db=temp_db, api_client=api_client)
    cog = AdminCog(mock_bot, temp_db, engine)

    # Setup guild and roles
    mock_guild = MagicMock(spec=discord.Guild)
    mock_guild.id = 12345
    mock_guild.me = MagicMock(spec=discord.Member)
    mock_guild.me.guild_permissions.manage_roles = True

    admin_role = MagicMock(spec=discord.Role)
    admin_role.name = ADMIN_ROLE_NAME
    mock_guild.roles = [admin_role]

    target_member = MagicMock(spec=discord.Member)
    target_member.name = "fluffle"
    target_member.display_name = "fluffle"
    target_member.id = 999888
    target_member.roles = []
    target_member.mention = "<@999888>"
    target_member.add_roles = AsyncMock()
    target_member.remove_roles = AsyncMock()

    mock_guild.get_member = MagicMock(return_value=target_member)
    mock_guild.members = [target_member]

    mock_ctx = MagicMock()
    mock_ctx.guild = mock_guild
    mock_ctx.author = MagicMock(spec=discord.Member)
    mock_ctx.author.name = "ServerOwner"
    mock_ctx.author.id = 11111
    mock_ctx.defer = AsyncMock()
    mock_ctx.send = AsyncMock()

    # 1. Grant Role Test
    await cog.admin_toggle_command.callback(cog, mock_ctx, member="@fluffle")

    target_member.add_roles.assert_called_once_with(admin_role, reason="ArcherSniper Admin role granted by ServerOwner")
    mock_ctx.send.assert_called_once()
    args, kwargs = mock_ctx.send.call_args
    embed = kwargs.get("embed")
    assert "Granted" in embed.title

    # 2. Revoke Role Test
    target_member.roles = [admin_role]  # Now user has the role
    target_member.add_roles.reset_mock()
    mock_ctx.send.reset_mock()

    await cog.admin_toggle_command.callback(cog, mock_ctx, member="@fluffle")

    target_member.remove_roles.assert_called_once_with(admin_role, reason="ArcherSniper Admin role revoked by ServerOwner")
    mock_ctx.send.assert_called_once()
    args, kwargs = mock_ctx.send.call_args
    embed = kwargs.get("embed")
    assert "Revoked" in embed.title

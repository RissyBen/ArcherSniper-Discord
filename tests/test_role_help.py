"""
Unit Tests for Role-Aware Help System
"""

from unittest.mock import MagicMock, AsyncMock
import pytest
import discord
from cogs.help import (
    user_is_admin,
    get_student_overview_embed,
    get_admin_overview_embed,
    StudentHelpSelectView,
    AdminHelpSelectView,
)


def test_user_is_admin():
    # Admin via guild permissions
    guild = MagicMock(spec=discord.Guild)
    guild.owner = None
    admin_member = MagicMock(spec=discord.Member)
    admin_member.id = 999
    admin_member.guild_permissions.administrator = True

    assert user_is_admin(admin_member, guild) is True

    # Regular member
    reg_member = MagicMock(spec=discord.Member)
    reg_member.id = 111
    reg_member.guild_permissions.administrator = False

    assert user_is_admin(reg_member, guild) is False


def test_student_overview_hides_admin_commands():
    embed = get_student_overview_embed()
    field_names = [f.name for f in embed.fields]

    assert "🎯 Student Quick Commands" in field_names
    assert "💡 Quick Start Tutorial (4 Steps)" in field_names
    # Admin controls MUST NOT be present
    assert "⚙️ Admin & Engine Controls" not in field_names
    assert "📂 Available Administrative Modules" not in field_names

    # Check select view
    view = StudentHelpSelectView()
    select_items = [item for item in view.children if isinstance(item, discord.ui.Select)]
    assert len(select_items) == 1
    select_opts = [opt.value for opt in select_items[0].options]
    assert "overview" in select_opts
    assert "student" in select_opts
    assert "engine" not in select_opts
    assert "auth" not in select_opts


def test_admin_overview_shows_all_controls():
    embed = get_admin_overview_embed()
    field_names = [f.name for f in embed.fields]

    assert "📂 Available Administrative Modules" in field_names

    # Check select view
    view = AdminHelpSelectView()
    select_items = [item for item in view.children if isinstance(item, discord.ui.Select)]
    assert len(select_items) == 1
    select_opts = [opt.value for opt in select_items[0].options]
    assert "overview" in select_opts
    assert "engine" in select_opts
    assert "data" in select_opts
    assert "auth" in select_opts
    assert "server" in select_opts
    assert "student" in select_opts
    assert "curl" in select_opts


@pytest.mark.asyncio
async def test_help_command_categories_and_aliases():
    import pytest
    from unittest.mock import AsyncMock
    from cogs.help import HelpCog, get_student_embed, get_admin_embed, get_curl_embed

    mock_bot = MagicMock()
    cog = HelpCog(mock_bot)

    # 1. Student runs !help
    student_ctx = MagicMock()
    student_ctx.send = AsyncMock()
    student_ctx.author.id = 111222
    student_ctx.invoked_with = "help"
    student_member = MagicMock(spec=discord.Member)
    student_member.id = 111222
    student_member.guild_permissions.administrator = False
    student_member.roles = []
    student_ctx.author = student_member
    student_ctx.guild = MagicMock(owner_id=999999)

    await cog.help_command.callback(cog, student_ctx, category=None)
    student_ctx.send.assert_called()
    embed = student_ctx.send.call_args[1]["embed"]
    assert "Student Command Center" in embed.title

    # 2. Student runs !help student
    student_ctx.send.reset_mock()
    await cog.help_command.callback(cog, student_ctx, category="student")
    student_ctx.send.assert_called()
    assert "Student Commands Guide" in student_ctx.send.call_args[1]["embed"].title

    # 3. Student tries !help admin -> blocked
    student_ctx.send.reset_mock()
    await cog.help_command.callback(cog, student_ctx, category="admin")
    student_ctx.send.assert_called()
    assert "only accessible to server administrators" in str(student_ctx.send.call_args)

    # 4. Admin runs !adminhelp
    admin_ctx = MagicMock()
    admin_ctx.send = AsyncMock()
    admin_ctx.author.id = 333444
    admin_ctx.invoked_with = "adminhelp"
    admin_member = MagicMock(spec=discord.Member)
    admin_member.id = 333444
    admin_member.guild_permissions.administrator = True
    admin_member.roles = []
    admin_ctx.author = admin_member
    admin_ctx.guild = MagicMock(owner_id=999999)

    await cog.help_command.callback(cog, admin_ctx, category=None)
    admin_ctx.send.assert_called()
    assert "Admin Command Center" in admin_ctx.send.call_args[1]["embed"].title

    # 5. Admin runs !help curl
    admin_ctx.send.reset_mock()
    await cog.help_command.callback(cog, admin_ctx, category="curl")
    admin_ctx.send.assert_called()
    assert "Master Session & cURL" in admin_ctx.send.call_args[1]["embed"].title


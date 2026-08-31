"""
Unit Tests for Role-Aware Help System
"""

from unittest.mock import MagicMock
import discord
from cogs.help import (
    user_is_admin,
    get_student_overview_embed,
    get_admin_overview_embed,
    StudentHelpButtonView,
    AdminHelpButtonView,
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

    assert "🎯 Student Commands" in field_names
    assert "💡 Quick Start" in field_names
    # Admin controls MUST NOT be present
    assert "⚙️ Admin & Engine Controls" not in field_names

    # Check button view
    view = StudentHelpButtonView()
    labels = [b.label for b in view.children if hasattr(b, "label")]
    assert "Overview" in labels
    assert "Student Guide" in labels
    assert "Admin Controls" not in labels
    assert "cURL Guide" not in labels


def test_admin_overview_shows_all_controls():
    embed = get_admin_overview_embed()
    field_names = [f.name for f in embed.fields]

    assert "🎯 Student Commands" in field_names
    assert "⚙️ Admin & Engine Controls" in field_names

    # Check button view
    view = AdminHelpButtonView()
    labels = [b.label for b in view.children if hasattr(b, "label")]
    assert "Overview" in labels
    assert "Student Guide" in labels
    assert "Admin Controls" in labels
    assert "Auth & Cookies" in labels

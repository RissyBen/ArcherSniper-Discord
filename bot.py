"""
ArcherSniper - Main Discord Bot Entry Point
DLSU CourseFinder Section Sniper & Real-Time Alert System.
"""

import asyncio
import logging
import sys
import discord
from discord.ext import commands

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import (
    DISCORD_TOKEN,
    COMMAND_PREFIX,
    ALERT_CHANNEL_ID,
    WEB_PORT,
    INITIAL_COOKIES,
    INITIAL_CURL,
    SYSTEM_LOG_PATH,
)
from database import Database
from dlsu_api import DLSUApiClient
from engine import WatchdogEngine
from utils.curl_parser import parse_curl, parse_cookie_string
from utils.web_server import HealthWebServer

# Configure logging to both console and data/logs/bot_system.log (with 5MB rotation, keeping 3 backups)
from logging.handlers import RotatingFileHandler

file_handler = RotatingFileHandler(
    SYSTEM_LOG_PATH,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[stream_handler, file_handler],
)
logger = logging.getLogger("ArcherSniper.Bot")


class ArcherSniperBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(COMMAND_PREFIX),
            intents=intents,
            help_command=None,
        )

        self.db = Database()
        self.api_client = DLSUApiClient(on_cookie_update=self._on_cookie_update)
        self.engine = WatchdogEngine(
            bot=self,
            db=self.db,
            api_client=self.api_client,
            alert_channel_id=ALERT_CHANNEL_ID,
        )
        self.web_server: HealthWebServer | None = None

    async def _on_cookie_update(self, updated_cookies: dict[str, str]):
        """Persists dynamically rolled forward session cookies to database."""
        logger.debug(f"Rolling forward {len(updated_cookies)} session cookies to database...")
        auth = await self.db.get_master_auth()
        headers = auth.get("headers") if auth else None
        await self.db.save_master_auth(
            cookies=updated_cookies,
            headers=headers,
            status="CONNECTED" if self.engine.is_connected else "DISCONNECTED",
        )

    async def setup_hook(self):
        """Initializes database, credentials, cogs, watchdog, and slash commands."""
        logger.info("Initializing ArcherSniper database and engine...")
        await self.db.init_db()

        # Check if environment provided initial cookies or cURL
        if INITIAL_CURL:
            parsed = parse_curl(INITIAL_CURL)
            if parsed.is_valid:
                logger.info("Ingesting master auth from DLSU_CURL environment variable...")
                await self.db.save_master_auth(
                    cookies=parsed.cookies,
                    headers=parsed.headers,
                    raw_curl=INITIAL_CURL,
                    status="CONNECTED",
                    campus_no=parsed.campus_no or 7,
                    academic_session=parsed.academic_session or 155,
                )
        elif INITIAL_COOKIES:
            parsed_cookies = parse_cookie_string(INITIAL_COOKIES)
            if parsed_cookies:
                logger.info("Ingesting master auth from DLSU_COOKIES environment variable...")
                await self.db.save_master_auth(
                    cookies=parsed_cookies,
                    status="CONNECTED",
                )

        # Initialize engine from DB
        await self.engine.initialize()

        # Load Cogs
        cogs_to_load = [
            "cogs.channel_manager",
            "cogs.sniper",
            "cogs.admin",
            "cogs.help",
        ]
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                logger.error(f"Failed to load extension {cog}: {e}")

        # Sync hybrid / slash command tree with Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} application (slash) commands with Discord.")
        except Exception as e:
            logger.warning(f"Could not sync slash commands: {e}")

        # Start optional cloud health web server
        if WEB_PORT:
            self.web_server = HealthWebServer(bot=self, port=WEB_PORT)
            await self.web_server.start()

        # Start 24/7 background polling and keep-alive watchdog
        self.engine.start_tasks()

    async def on_ready(self):
        """Triggered when bot connects to Discord gateway."""
        logger.info(f"==================================================")
        logger.info(f"🏹 ArcherSniper Bot Logged in as: {self.user.name} ({self.user.id})")
        logger.info(f"🏹 Connected Guilds: {len(self.guilds)}")
        logger.info(f"🏹 Command Prefix: '{COMMAND_PREFIX}'")
        logger.info(f"==================================================")

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"DLSU CourseFinder 🏹 | {COMMAND_PREFIX}watch",
        )
        await self.change_presence(activity=activity, status=discord.Status.online)

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global command error handler for friendly feedback."""
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(
                f"❌ **Permission Denied:** You need Administrator permissions or your Discord ID "
                f"(`{ctx.author.id}`) added to `ADMIN_USER_IDS` in `.env` to run this command."
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `{COMMAND_PREFIX}help {ctx.command.name}` for syntax.")
        else:
            logger.error(f"Error in command '{ctx.command}': {error}", exc_info=error)
            await ctx.send(f"⚠️ **Command Error:** `{error}`")

    async def close(self):
        """Gracefully closes all engine tasks, web server, and client sessions."""
        logger.info("Shutting down ArcherSniper...")
        await self.engine.stop_tasks()
        await self.api_client.close()
        if self.web_server:
            await self.web_server.stop()
        await super().close()


async def main():
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN environment variable is missing! Please set it in .env.")
        print("\n[ERROR] DISCORD_TOKEN is missing. Please configure .env file first.")
        print("See .env.example for guidance.\n")
        return

    bot = ArcherSniperBot()
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("ArcherSniper terminated by user.")

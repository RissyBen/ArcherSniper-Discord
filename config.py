"""
ArcherSniper - Configuration Module
Manages environment variables, defaults, system paths, and UI theme colors.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

# Base project paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "archersniper.db"
COURSES_CACHE_PATH = DATA_DIR / "courses_cache.json"
SYSTEM_LOG_PATH = LOGS_DIR / "bot_system.log"
SCRAPER_LOG_PATH = LOGS_DIR / "scraper_fetches.log"
SCRAPER_DUMP_PATH = LOGS_DIR / "latest_scraper_dump.json"
SLOT_DROPS_LOG_PATH = LOGS_DIR / "slot_drops.log"
DM_DISPATCH_LOG_PATH = LOGS_DIR / "dm_dispatches.log"
HEARTBEAT_LOG_PATH = LOGS_DIR / "session_heartbeats.log"
API_DEBUG_LOG_PATH = LOGS_DIR / "api_raw_responses.log"
CATALOG_RAW_DUMP_PATH = LOGS_DIR / "last_catalog_raw.json"
DUPLICATES_LOG_PATH = LOGS_DIR / "duplicate_alerts.log"
AUTODISCOVERY_LOG_PATH = LOGS_DIR / "auto_discovery.log"
WATCHDOG_CYCLES_LOG_PATH = LOGS_DIR / "watchdog_cycles.log"

# Ensure all log files exist on disk for tail commands
for _p in (
    SYSTEM_LOG_PATH,
    SCRAPER_LOG_PATH,
    SLOT_DROPS_LOG_PATH,
    DM_DISPATCH_LOG_PATH,
    HEARTBEAT_LOG_PATH,
    AUTODISCOVERY_LOG_PATH,
    WATCHDOG_CYCLES_LOG_PATH,
):
    _p.touch(exist_ok=True)

# Discord Bot Settings
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!").strip()

# Admin IDs parsed from comma-separated string
_admin_raw = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS: set[int] = {
    int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()
}

_alert_channel_raw = os.getenv("ALERT_CHANNEL_ID", "")
ALERT_CHANNEL_ID: int | None = (
    int(_alert_channel_raw.strip()) if _alert_channel_raw.strip().isdigit() else None
)

WATCHLIST_CATEGORY_NAME = os.getenv("WATCHLIST_CATEGORY_NAME", "🎯 ArcherSniper Channels").strip()

# DLSU API Endpoints & Defaults
DLSU_BASE_URL = "https://archershub.dlsu.edu.ph"
DLSU_CF_DATA_URL = f"{DLSU_BASE_URL}/CourseFinder/GetCFData/"
DLSU_HEARTBEAT_URL = f"{DLSU_BASE_URL}/CourseFinder/GetAllDropDownList/"
DLSU_COURSE_LIST_URL = f"{DLSU_BASE_URL}/CourseFinder/GetCourseList/"
DLSU_PORTAL_URL = f"{DLSU_BASE_URL}/CourseFinder/"

DEFAULT_CAMPUS_NO = int(os.getenv("DEFAULT_CAMPUS_NO", "7"))
DEFAULT_ACADEMIC_SESSION = int(os.getenv("DEFAULT_ACADEMIC_SESSION", "155"))

# Polling & Heartbeat Timing (in seconds)
DEFAULT_POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "15"))
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "60"))
RECONNECT_STAGE_1_DELAY = 10.0      # 10s fast retry
RECONNECT_STAGE_2_INTERVAL = 600.0   # 10 minutes periodic retry

# Channel Category Names & Roles
CAT_ANNOUNCEMENTS = "📢 ARCHERSNIPER ANNOUNCEMENTS"
CAT_COLLEGE_FEEDS = "🏛️ DLSU COLLEGE FEEDS"
CAT_ADMIN_HQ = "🔒 ADMIN HQ"
ADMIN_ROLE_NAME = "ArcherSniper Admin"

# Web Server (for Chrome Extension relay and cloud healthchecks)
PORT_RAW = os.getenv("PORT", "8080")
WEB_PORT: int = int(PORT_RAW) if PORT_RAW.isdigit() else 8080

# Pre-seeded credentials from environment if provided
INITIAL_COOKIES = os.getenv("DLSU_COOKIES", "").strip()
INITIAL_CURL = os.getenv("DLSU_CURL", "").strip()

# Color Theme Palette
COLOR_DLSU_GREEN = 0x006837
COLOR_GOLD = 0xF59E0B
COLOR_ALERT_RED = 0xEF4444
COLOR_OPEN_GREEN = 0x10B981
COLOR_INFO_BLUE = 0x3B82F6

# DLSU Animo branding assets / URLs
DLSU_LOGO_URL = "https://upload.wikimedia.org/wikipedia/en/thumb/c/c2/De_La_Salle_University_Seal.svg/300px-De_La_Salle_University_Seal.svg.png"
ANIMO_SYS_URL = "https://animosys.dlsu.edu.ph"
MLS_URL = "https://my.dlsu.edu.ph"

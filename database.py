"""
ArcherSniper - Database Layer
Asynchronous SQLite database persistence using aiosqlite.
Manages master auth, system state, server channels, monitored courses, user watchlists, and section states.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import aiosqlite

from config import DB_PATH

logger = logging.getLogger("ArcherSniper.Database")


class Database:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = str(db_path)

    async def init_db(self):
        """Initializes database tables and indexes with automated migrations."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA foreign_keys=ON;")

            # Master Auth table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS master_auth (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cookies_json TEXT NOT NULL,
                    headers_json TEXT,
                    raw_curl TEXT,
                    status TEXT DEFAULT 'DISCONNECTED',
                    campus_no INTEGER DEFAULT 7,
                    academic_session INTEGER DEFAULT 155,
                    last_synced TIMESTAMP
                );
            """)

            # System State (Bot Active Gatekeeper & Settings)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    bot_active INTEGER DEFAULT 0,
                    ge_lc_active INTEGER DEFAULT 1,
                    poll_interval REAL DEFAULT 15.0,
                    heartbeat_interval REAL DEFAULT 60.0,
                    last_started_at TIMESTAMP,
                    last_stopped_at TIMESTAMP
                );
            """)
            # Ensure single row exists
            await db.execute("""
                INSERT OR IGNORE INTO system_state (id, bot_active, ge_lc_active, poll_interval, heartbeat_interval)
                VALUES (1, 0, 1, 15.0, 60.0);
            """)

            # Server Channels Configuration (Announcements, College Feeds, Admin HQ)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_channels (
                    guild_id INTEGER NOT NULL,
                    channel_key TEXT NOT NULL,
                    channel_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, channel_key)
                );
            """)

            # Monitored Courses Pool
            await db.execute("""
                CREATE TABLE IF NOT EXISTS monitored_courses (
                    course_id TEXT PRIMARY KEY,
                    course_code TEXT NOT NULL,
                    course_name TEXT,
                    is_active INTEGER DEFAULT 1,
                    added_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_monitored_code ON monitored_courses(course_code);")

            # User Watchlist with Scope ('COURSE' vs 'SECTION') & Ping Toggle
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    discord_username TEXT,
                    course_id TEXT NOT NULL,
                    course_code TEXT NOT NULL DEFAULT '',
                    section_name TEXT NOT NULL DEFAULT '*',
                    scope TEXT NOT NULL DEFAULT 'SECTION',
                    pings_enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, course_code, section_name)
                );
            """)

            # Section States (Live Capacity & Delta Tracking)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS section_states (
                    course_id TEXT NOT NULL,
                    course_code TEXT NOT NULL DEFAULT '',
                    section_name TEXT NOT NULL,
                    capacity INTEGER DEFAULT 0,
                    enlisted INTEGER DEFAULT 0,
                    open_slots INTEGER DEFAULT 0,
                    teacher TEXT DEFAULT '',
                    schedule TEXT DEFAULT '',
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (course_id, section_name)
                );
            """)

            # Full Catalog Cache Table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS course_catalog (
                    course_id TEXT PRIMARY KEY,
                    course_code TEXT NOT NULL,
                    course_name TEXT,
                    academic_session INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Drop Events History Table (Analytics & Peak Window Tracking)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS drop_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_code TEXT NOT NULL,
                    section_name TEXT NOT NULL,
                    open_slots INTEGER NOT NULL,
                    capacity INTEGER DEFAULT 0,
                    enlisted INTEGER DEFAULT 0,
                    hour_of_day INTEGER NOT NULL,
                    duration_seconds INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # ----------------------------------------------------
            # AUTOMATIC SCHEMA MIGRATIONS (For Existing DB Files)
            # ----------------------------------------------------
            async def ensure_column(table: str, col_name: str, col_type: str):
                try:
                    async with db.execute(f"PRAGMA table_info({table});") as cursor:
                        cols = [row[1] for row in await cursor.fetchall()]
                        if cols and col_name not in cols:
                            logger.info(f"Database Migration: Adding missing column '{col_name}' to '{table}'")
                            await db.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type};")
                except Exception as ex:
                    logger.debug(f"Migration check for {table}.{col_name}: {ex}")

            await ensure_column("user_watchlist", "discord_username", "TEXT")
            await ensure_column("user_watchlist", "course_code", "TEXT NOT NULL DEFAULT ''")
            await ensure_column("user_watchlist", "scope", "TEXT NOT NULL DEFAULT 'SECTION'")
            await ensure_column("user_watchlist", "pings_enabled", "INTEGER DEFAULT 1")
            await ensure_column("section_states", "course_code", "TEXT NOT NULL DEFAULT ''")
            await ensure_column("section_states", "teacher", "TEXT DEFAULT ''")
            await ensure_column("section_states", "schedule", "TEXT DEFAULT ''")

            # Backfill course_code in user_watchlist if missing
            try:
                await db.execute("""
                    UPDATE user_watchlist
                    SET course_code = (
                        SELECT course_code FROM monitored_courses 
                        WHERE monitored_courses.course_id = user_watchlist.course_id
                    )
                    WHERE (course_code IS NULL OR course_code = '') 
                      AND EXISTS (SELECT 1 FROM monitored_courses WHERE monitored_courses.course_id = user_watchlist.course_id);
                """)
            except Exception:
                pass

            # Create Indexes Safely
            await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_watchlist_user_course_sec ON user_watchlist(user_id, course_code, section_name);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_user ON user_watchlist(user_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_code ON user_watchlist(course_code);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_section_code ON section_states(course_code);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_catalog_code ON course_catalog(course_code);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_drop_code ON drop_events(course_code);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_drop_time ON drop_events(created_at);")

            await db.commit()
        logger.info(f"Database initialized successfully at {self.db_path}")

    async def seed_default_courses(self) -> int:
        """Seeds verified active DLSU GE, LC, and institutional courses into the global monitoring pool for live feeds."""
        default_feed_courses = [
            # GE Core Curriculum
            ("564", "GEARTAP", "Art Appreciation"),
            ("1888", "GEETHIC", "Ethics"),
            ("3475", "GEMATMW", "Mathematics in the Modern World"),
            ("3857", "GEPCOMM", "Purposive Communication"),
            ("524", "GERIZAL", "The Life and Works of Rizal"),
            ("3271", "GERPHIS", "Readings in Philippine History"),
            ("4025", "GESTSOC", "Science, Technology, and Society"),
            ("4736", "GEUSELF", "Understanding the Self"),
            ("4733", "GEWORLD", "The Contemporary World"),
            ("3210", "GELITPH", "Literatures of the Philippines"),
            ("3218", "GELITWO", "Literatures of the World"),
            ("2109", "GEOPLGL", "Geopolitics and International Law"),
            ("2411", "GELECST", "G.E. Elective Science and Technology"),
            # Physical Education & Wellness
            ("3553", "GEFTWEL", "Physical Fitness and Wellness"),
            ("3884", "GEDANCE", "Physical Fitness and Wellness in Dance"),
            ("3874", "GESPORT", "Physical Fitness and Wellness in Individual/Dual Sports"),
            ("3882", "GETEAMS", "Physical Fitness and Wellness in Team Sports"),
            # Lasallian Core (LC) Curriculum
            ("4847", "LCASEAN", "The Filipino and ASEAN"),
            ("1748", "LCENWRD", "Encountering the Word in the World"),
            ("1924", "LCFAITH", "Faith Worth Living"),
            ("2630", "LCFILIA", "Introduksyon sa Filipinolohiya at Araling Pilipinas"),
            ("2831", "LCFILIB", "Komunikasyon ng Pananaliksik"),
            ("2821", "LCFILIC", "Kultura, Media at Teknolohiya"),
            ("2944", "LCLSONE", "Lasallian Studies 1"),
            ("2952", "LCLSTWO", "Lasallian Studies 2"),
            ("2785", "LCLSTRI", "Lasallian Studies 3"),
            # Institutional Foundations
            ("5809", "LASARE1", "Lasallian Recollection 1"),
            ("5812", "LASARE2", "Lasallian Recollection 2"),
            ("5814", "LASARE3", "Lasallian Recollection 3"),
            ("3400", "NSTP101", "National Service Training Program 1"),
            ("5850", "SAS1000", "Student Affairs Services 1000"),
            ("5845", "SAS2000", "Student Affairs Services 2000"),
            ("5837", "SAS3000", "Student Affairs Services 3000"),
        ]

        count = 0
        async with aiosqlite.connect(self.db_path) as db:
            for cid, code, name in default_feed_courses:
                await db.execute("""
                    INSERT INTO monitored_courses (course_id, course_code, course_name, is_active, added_by)
                    VALUES (?, ?, ?, 1, 'Auto Seed')
                    ON CONFLICT(course_id) DO UPDATE SET
                        course_code = excluded.course_code,
                        course_name = excluded.course_name,
                        is_active = 1;
                """, (cid, code, name))
                count += 1
            await db.commit()
        logger.info(f"Seeded {count} default GE/LC courses into monitoring pool.")
        return count

    # ==========================================
    # SYSTEM STATE & GATEKEEPER
    # ==========================================

    async def get_system_state(self) -> dict:
        """Retrieves global bot active state, GE/LC state, and intervals."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM system_state WHERE id = 1;") as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "bot_active": bool(row["bot_active"]),
                        "ge_lc_active": bool(row["ge_lc_active"]),
                        "poll_interval": float(row["poll_interval"]),
                        "heartbeat_interval": float(row["heartbeat_interval"]),
                        "last_started_at": row["last_started_at"],
                        "last_stopped_at": row["last_stopped_at"],
                    }
                return {
                    "bot_active": False,
                    "ge_lc_active": True,
                    "poll_interval": 15.0,
                    "heartbeat_interval": 60.0,
                    "last_started_at": None,
                    "last_stopped_at": None,
                }

    async def set_bot_active(self, active: bool):
        """Toggles the master bot activation gatekeeper."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            if active:
                await db.execute("""
                    UPDATE system_state SET bot_active = 1, last_started_at = ? WHERE id = 1;
                """, (now,))
            else:
                await db.execute("""
                    UPDATE system_state SET bot_active = 0, last_stopped_at = ? WHERE id = 1;
                """, (now,))
            await db.commit()

    async def set_ge_lc_active(self, active: bool):
        """Toggles the GE/LC live feed auto-notifications."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE system_state SET ge_lc_active = ? WHERE id = 1;
            """, (1 if active else 0,))
            await db.commit()

    async def set_intervals(self, poll_interval: float | None = None, heartbeat_interval: float | None = None):
        """Updates timing intervals in system_state."""
        async with aiosqlite.connect(self.db_path) as db:
            if poll_interval is not None:
                await db.execute("UPDATE system_state SET poll_interval = ? WHERE id = 1;", (poll_interval,))
            if heartbeat_interval is not None:
                await db.execute("UPDATE system_state SET heartbeat_interval = ? WHERE id = 1;", (heartbeat_interval,))
            await db.commit()

    # ==========================================
    # SERVER CHANNELS CONFIGURATION
    # ==========================================

    async def save_server_channels(self, guild_id: int, channel_map: dict[str, int]):
        """Persists server channel IDs for a specific Discord guild."""
        async with aiosqlite.connect(self.db_path) as db:
            for key, ch_id in channel_map.items():
                await db.execute("""
                    INSERT INTO server_channels (guild_id, channel_key, channel_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, channel_key) DO UPDATE SET channel_id = excluded.channel_id;
                """, (guild_id, key, ch_id))
            await db.commit()

    async def get_server_channels(self, guild_id: int) -> dict[str, int]:
        """Returns all configured channel IDs for a guild."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT channel_key, channel_id FROM server_channels WHERE guild_id = ?;", (guild_id,)) as cursor:
                rows = await cursor.fetchall()
                return {row["channel_key"]: row["channel_id"] for row in rows}

    async def get_server_channel(self, guild_id: int, channel_key: str) -> int | None:
        """Retrieves a single configured channel ID."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT channel_id FROM server_channels WHERE guild_id = ? AND channel_key = ?;",
                (guild_id, channel_key),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def get_all_configured_guilds(self) -> list[int]:
        """Returns list of distinct guild IDs that have configured channels."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT DISTINCT guild_id FROM server_channels;") as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    # ==========================================
    # MASTER AUTH & SESSION PERSISTENCE
    # ==========================================

    async def get_master_auth(self) -> dict | None:
        """Retrieves stored master auth cookies, headers, and status."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM master_auth WHERE id = 1;") as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return {
                    "cookies": json.loads(row["cookies_json"]) if row["cookies_json"] else {},
                    "headers": json.loads(row["headers_json"]) if row["headers_json"] else {},
                    "raw_curl": row["raw_curl"],
                    "status": row["status"],
                    "campus_no": row["campus_no"],
                    "academic_session": row["academic_session"],
                    "last_synced": row["last_synced"],
                }

    async def save_master_auth(
        self,
        cookies: dict[str, str],
        headers: dict[str, str] | None = None,
        raw_curl: str | None = None,
        status: str = "CONNECTED",
        campus_no: int = 7,
        academic_session: int = 155,
    ):
        """Persists updated auth tokens, cookies, and session status."""
        now = datetime.now(timezone.utc).isoformat()
        cookies_json = json.dumps(cookies or {})
        headers_json = json.dumps(headers or {})

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO master_auth (id, cookies_json, headers_json, raw_curl, status, campus_no, academic_session, last_synced)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    cookies_json = excluded.cookies_json,
                    headers_json = COALESCE(excluded.headers_json, master_auth.headers_json),
                    raw_curl = COALESCE(excluded.raw_curl, master_auth.raw_curl),
                    status = excluded.status,
                    campus_no = COALESCE(excluded.campus_no, master_auth.campus_no),
                    academic_session = COALESCE(excluded.academic_session, master_auth.academic_session),
                    last_synced = excluded.last_synced;
            """, (cookies_json, headers_json, raw_curl, status, campus_no, academic_session, now))
            await db.commit()

    async def update_auth_status(self, status: str):
        """Updates only the status field of master auth."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE master_auth SET status = ?, last_synced = ? WHERE id = 1;
            """, (status, now))
            await db.commit()

    async def clear_master_auth(self):
        """Clears all stored authentication cookies, headers, and resets status to DISCONNECTED."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE master_auth
                SET cookies_json = '{}', headers_json = '{}', raw_curl = NULL, status = 'DISCONNECTED', last_synced = ?
                WHERE id = 1;
            """, (now,))
            await db.commit()

    # ==========================================
    # MONITORED COURSES POOL
    # ==========================================

    async def add_monitored_course(
        self,
        course_id: str,
        course_code: str,
        course_name: str = "",
        added_by: str = "System",
    ) -> bool:
        """Adds a course to the active monitoring pool, preventing higher duplicate IDs from overwriting active IDs."""
        clean_code = course_code.strip().upper()
        clean_id = str(course_id).strip()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT course_id FROM monitored_courses WHERE UPPER(course_code) = ?;", (clean_code,)) as cur:
                existing = await cur.fetchone()
                if existing:
                    existing_id = str(existing["course_id"]).strip()
                    if existing_id.isdigit() and clean_id.isdigit():
                        if int(clean_id) > int(existing_id):
                            # Retain active lower ID; ignore duplicate higher historical ID
                            return True

            # Delete any existing row with matching course_code but different course_id
            await db.execute("""
                DELETE FROM monitored_courses WHERE UPPER(course_code) = ? AND course_id != ?;
            """, (clean_code, clean_id))
            await db.execute("""
                INSERT INTO monitored_courses (course_id, course_code, course_name, is_active, added_by)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(course_id) DO UPDATE SET
                    course_code = excluded.course_code,
                    course_name = CASE WHEN excluded.course_name != '' THEN excluded.course_name ELSE monitored_courses.course_name END,
                    is_active = 1;
            """, (clean_id, clean_code, course_name.strip(), str(added_by)))
            await db.commit()
            return True

    async def remove_monitored_course(self, course_code_or_id: str) -> bool:
        """Removes a course from the active monitoring pool."""
        query_val = course_code_or_id.strip().upper()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM monitored_courses
                WHERE UPPER(course_code) = ? OR course_id = ?;
            """, (query_val, course_code_or_id.strip()))
            deleted = cursor.rowcount > 0
            if deleted:
                await db.execute("DELETE FROM section_states WHERE UPPER(course_code) = ? OR course_id = ?;", (query_val, course_code_or_id.strip()))
            await db.commit()
            return deleted

    async def get_monitored_courses(self, active_only: bool = True) -> list[dict]:
        """Returns all monitored courses in the pool, deduplicated by course code."""
        sql = "SELECT * FROM monitored_courses WHERE is_active = 1 GROUP BY UPPER(course_code) ORDER BY course_code ASC;" if active_only else "SELECT * FROM monitored_courses GROUP BY UPPER(course_code) ORDER BY course_code ASC;"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_monitored_course(self, course_code_or_id: str) -> dict | None:
        """Looks up a monitored course by code or ID."""
        query_val = course_code_or_id.strip().upper()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM monitored_courses
                WHERE UPPER(course_code) = ? OR course_id = ?
                LIMIT 1;
            """, (query_val, course_code_or_id.strip())) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    # ==========================================
    # USER WATCHLIST & EXACT RULES
    # ==========================================

    async def add_user_watch(
        self,
        user_id: int,
        discord_username: str,
        course_id: str,
        course_code: str,
        section_name: str = "*",
        scope: str = "SECTION",
    ) -> bool:
        """
        Adds a watch entry for a user on a course or section.
        scope: 'COURSE' (all sections) or 'SECTION' (specific section).
        """
        code_clean = course_code.strip().upper()
        sec_clean = "*" if scope == "COURSE" or section_name in ("*", "ALL") else section_name.strip().upper()
        scope_clean = "COURSE" if sec_clean == "*" else "SECTION"

        async with aiosqlite.connect(self.db_path) as db:
            # If watching entire course, clear individual section watches for this course to avoid duplicate pings
            if scope_clean == "COURSE":
                await db.execute("""
                    DELETE FROM user_watchlist
                    WHERE user_id = ? AND course_code = ?;
                """, (user_id, code_clean))

            await db.execute("""
                INSERT INTO user_watchlist (user_id, discord_username, course_id, course_code, section_name, scope, pings_enabled)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id, course_code, section_name) DO UPDATE SET
                    discord_username = excluded.discord_username,
                    course_id = excluded.course_id,
                    scope = excluded.scope;
            """, (user_id, discord_username, str(course_id), code_clean, sec_clean, scope_clean))
            await db.commit()
            return True

    async def remove_user_watch(
        self,
        user_id: int,
        course_code: str,
        section_name: str | None = None,
    ) -> tuple[bool, str, int]:
        """
        Removes a course or section watch following strict scope rules.
        Returns (success: bool, reason: str, remaining_count: int).
        
        Rule: If user is watching entire course (scope='COURSE'), and tries to unwatch a specific section like 'S04',
        it is blocked and returns (False, 'BLOCKED_COURSE_SCOPE', count).
        """
        code_clean = course_code.strip().upper()
        sec_clean = section_name.strip().upper() if section_name and section_name.strip() not in ("*", "ALL") else None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Check existing watches for this user on this course
            async with db.execute("""
                SELECT * FROM user_watchlist
                WHERE user_id = ? AND course_code = ?;
            """, (user_id, code_clean)) as cursor:
                watches = await cursor.fetchall()

            if not watches:
                remaining = await self.get_user_watch_count(user_id)
                return False, "NOT_FOUND", remaining

            # Check if user has a whole course watch (scope='COURSE' or section_name='*')
            has_course_scope = any(w["scope"] == "COURSE" or w["section_name"] == "*" for w in watches)

            if has_course_scope and sec_clean is not None:
                # User is tracking entire course, but tried to unwatch a specific section
                remaining = await self.get_user_watch_count(user_id)
                return False, "BLOCKED_COURSE_SCOPE", remaining

            # Execute removal
            if sec_clean is None or has_course_scope:
                # Remove all entries for this course
                await db.execute("""
                    DELETE FROM user_watchlist
                    WHERE user_id = ? AND course_code = ?;
                """, (user_id, code_clean))
            else:
                # Remove specific section
                await db.execute("""
                    DELETE FROM user_watchlist
                    WHERE user_id = ? AND course_code = ? AND section_name = ?;
                """, (user_id, code_clean, sec_clean))

            await db.commit()

        remaining = await self.get_user_watch_count(user_id)
        return True, "SUCCESS", remaining

    async def toggle_user_pings(self, user_id: int, enabled: bool) -> int:
        """Toggles personal pings (mute / unmute) for a user without modifying their watchlist."""
        val = 1 if enabled else 0
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE user_watchlist SET pings_enabled = ? WHERE user_id = ?;
            """, (val, user_id))
            await db.commit()
            return cursor.rowcount

    async def get_user_pings_status(self, user_id: int) -> bool:
        """Checks if personal pings are enabled for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT pings_enabled FROM user_watchlist WHERE user_id = ? LIMIT 1;
            """, (user_id,)) as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else True

    async def get_all_watchlisted_course_codes(self) -> set[str]:
        """Returns set of all distinct uppercase course codes currently watched by students."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT DISTINCT UPPER(course_code) FROM user_watchlist;
            """) as cursor:
                rows = await cursor.fetchall()
                return {r[0] for r in rows if r[0]}

    async def get_user_watchlist_detailed(self, user_id: int) -> list[dict]:
        """
        Retrieves user's watchlist with live section states.
        If user added whole course ('COURSE'), expands to return all sections of that course.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM user_watchlist WHERE user_id = ? ORDER BY course_code ASC, section_name ASC;
            """, (user_id,)) as cursor:
                watches = [dict(r) for r in await cursor.fetchall()]

            results = []
            for w in watches:
                code = w["course_code"]
                scope = w["scope"]
                sec = w["section_name"]

                if scope == "COURSE" or sec == "*":
                    # Expand all sections for this course from section_states
                    async with db.execute("""
                        SELECT * FROM section_states WHERE UPPER(course_code) = ? ORDER BY section_name ASC;
                    """, (code,)) as s_cursor:
                        sections = [dict(r) for r in await s_cursor.fetchall()]
                    results.append({
                        "course_code": code,
                        "scope": "COURSE",
                        "section_name": "*",
                        "pings_enabled": bool(w.get("pings_enabled", 1)),
                        "sections": sections,
                    })
                else:
                    # Specific section
                    async with db.execute("""
                        SELECT * FROM section_states WHERE UPPER(course_code) = ? AND section_name = ? LIMIT 1;
                    """, (code, sec)) as s_cursor:
                        s_row = await s_cursor.fetchone()
                        sec_dict = dict(s_row) if s_row else {
                            "course_code": code,
                            "section_name": sec,
                            "capacity": 0,
                            "enlisted": 0,
                            "open_slots": 0,
                            "teacher": "TBA",
                            "schedule": "TBA",
                        }
                    results.append({
                        "course_code": code,
                        "scope": "SECTION",
                        "section_name": sec,
                        "pings_enabled": bool(w.get("pings_enabled", 1)),
                        "sections": [sec_dict],
                    })

            return results

    async def get_user_monitored_summary(self, user_id: int) -> list[dict]:
        """
        Retrieves a concise list of what the user is tracking.
        If whole course added, shows 'STSWENG (ALL Sections)'.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT course_code, scope, section_name, pings_enabled, created_at
                FROM user_watchlist
                WHERE user_id = ?
                ORDER BY course_code ASC, section_name ASC;
            """, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_user_watch_count(self, user_id: int) -> int:
        """Returns the total number of watch entries for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM user_watchlist WHERE user_id = ?;", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_all_active_watchers_count(self) -> int:
        """Returns total distinct users watching courses."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM user_watchlist;") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_active_watchers_for_section(self, course_code: str, section_name: str) -> list[dict]:
        """
        Returns all users subscribed to this section where pings are enabled.
        Includes both specific section watchers and whole course ('*') watchers.
        """
        code_clean = course_code.strip().upper()
        sec_clean = section_name.strip().upper()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM user_watchlist
                WHERE course_code = ? AND (section_name = ? OR section_name = '*' OR scope = 'COURSE')
                  AND pings_enabled = 1;
            """, (code_clean, sec_clean)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    # ==========================================
    # SECTION STATES (SMART DELTA TRACKING)
    # ==========================================

    async def get_section_state(self, course_id: str, section_name: str) -> dict | None:
        """Retrieves last recorded state for a section."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM section_states
                WHERE (course_id = ? OR UPPER(course_code) = ?) AND section_name = ?
                LIMIT 1;
            """, (str(course_id), str(course_id).upper(), section_name.strip().upper())) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_all_section_states(self, course_code_or_id: str | None = None) -> list[dict]:
        """Retrieves all section states (optionally filtered by course)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if course_code_or_id:
                query_val = str(course_code_or_id).strip().upper()
                async with db.execute("""
                    SELECT * FROM section_states
                    WHERE course_id = ? OR UPPER(course_code) = ?
                    ORDER BY section_name ASC;
                """, (str(course_code_or_id).strip(), query_val)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
            else:
                async with db.execute("SELECT * FROM section_states ORDER BY course_code, section_name ASC;") as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]

    async def upsert_section_state(
        self,
        course_id: str,
        course_code: str,
        section_name: str,
        capacity: int,
        enlisted: int,
        open_slots: int,
        teacher: str = "",
        schedule: str = "",
    ):
        """Updates or inserts the current state for a course section."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO section_states (course_id, course_code, section_name, capacity, enlisted, open_slots, teacher, schedule, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(course_id, section_name) DO UPDATE SET
                    course_code = CASE WHEN excluded.course_code != '' THEN excluded.course_code ELSE section_states.course_code END,
                    capacity = excluded.capacity,
                    enlisted = excluded.enlisted,
                    open_slots = excluded.open_slots,
                    teacher = excluded.teacher,
                    schedule = excluded.schedule,
                    last_updated = excluded.last_updated;
            """, (str(course_id), course_code.strip().upper(), section_name.strip().upper(), capacity, enlisted, open_slots, teacher, schedule, now))
            await db.commit()

    # ==========================================
    # COURSE CATALOG
    # ==========================================

    async def upsert_catalog_course(
        self,
        course_id: str,
        course_code: str,
        course_name: str = "",
        academic_session: int = 155,
    ):
        """Saves a course in the catalog index."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO course_catalog (course_id, course_code, course_name, academic_session, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(course_id) DO UPDATE SET
                    course_code = excluded.course_code,
                    course_name = excluded.course_name,
                    academic_session = excluded.academic_session,
                    updated_at = excluded.updated_at;
            """, (str(course_id), course_code.strip().upper(), course_name.strip(), academic_session, now))
            await db.commit()

    async def bulk_upsert_catalog_courses(
        self,
        courses: list[dict],
        academic_session: int = 155,
    ):
        """Bulk saves thousands of catalog courses in a single 0.03s SQLite transaction."""
        if not courses:
            return
        now = datetime.now(timezone.utc).isoformat()
        records = [
            (
                str(c["course_id"]).strip(),
                str(c["course_code"]).strip().upper(),
                str(c.get("course_name", "")).strip(),
                academic_session,
                now,
            )
            for c in courses
            if "course_id" in c and "course_code" in c
        ]
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany("""
                INSERT INTO course_catalog (course_id, course_code, course_name, academic_session, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(course_id) DO UPDATE SET
                    course_code = excluded.course_code,
                    course_name = excluded.course_name,
                    academic_session = excluded.academic_session,
                    updated_at = excluded.updated_at;
            """, records)
            await db.commit()

    async def search_catalog(self, query: str) -> list[dict]:
        """Searches course catalog by code or name, prioritizing active lower Course IDs."""
        q = f"%{query.strip().upper()}%"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM course_catalog
                WHERE UPPER(course_code) LIKE ? OR UPPER(course_name) LIKE ? OR course_id = ?
                ORDER BY CAST(course_id AS INTEGER) ASC
                LIMIT 25;
            """, (q, q, query.strip())) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def search_catalog_extended(self, query: str) -> list[dict]:
        """Performs multi-keyword matching across code and course title, prioritizing active Course IDs."""
        keywords = [k.strip().upper() for k in query.strip().split() if k.strip()]
        if not keywords:
            return await self.search_catalog(query)

        conditions = []
        params = []
        for kw in keywords:
            conditions.append("(UPPER(course_code) LIKE ? OR UPPER(course_name) LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%"])

        sql = f"SELECT * FROM course_catalog WHERE {' AND '.join(conditions)} ORDER BY CAST(course_id AS INTEGER) ASC LIMIT 20;"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ==========================================
    # DROP ANALYTICS & STATS
    # ==========================================

    async def record_drop_event(
        self,
        course_code: str,
        section_name: str,
        open_slots: int,
        capacity: int = 0,
        enlisted: int = 0,
        hour_of_day: int = 0,
    ) -> int:
        """Records a slot drop occurrence in drop_events table."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO drop_events (course_code, section_name, open_slots, capacity, enlisted, hour_of_day, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (course_code.strip().upper(), section_name.strip().upper(), open_slots, capacity, enlisted, hour_of_day, now))
            await db.commit()
            return cursor.lastrowid

    async def update_drop_event_duration(self, course_code: str, section_name: str, duration_seconds: int):
        """Updates the latest open drop event with the time taken before it filled back up."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE drop_events
                SET duration_seconds = ?
                WHERE id = (
                    SELECT id FROM drop_events
                    WHERE course_code = ? AND section_name = ? AND duration_seconds IS NULL
                    ORDER BY id DESC LIMIT 1
                );
            """, (duration_seconds, course_code.strip().upper(), section_name.strip().upper()))
            await db.commit()

    async def get_drop_analytics(self) -> dict:
        """Computes aggregate analytics: total drops, top contested courses, peak hours, and recent drops."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. Total drop count
            async with db.execute("SELECT COUNT(*) as total FROM drop_events;") as c:
                row = await c.fetchone()
                total_drops = row["total"] if row else 0

            # 2. Top contested courses (ranked by drop occurrences and watcher counts)
            async with db.execute("""
                SELECT 
                    m.course_code,
                    COALESCE(d.drop_count, 0) as drops_caught,
                    (SELECT COUNT(DISTINCT user_id) FROM user_watchlist w WHERE w.course_code = m.course_code) as watcher_count
                FROM monitored_courses m
                LEFT JOIN (
                    SELECT course_code, COUNT(*) as drop_count
                    FROM drop_events
                    GROUP BY course_code
                ) d ON m.course_code = d.course_code
                ORDER BY watcher_count DESC, drops_caught DESC
                LIMIT 5;
            """) as c:
                top_courses = [dict(r) for r in await c.fetchall()]

            # 3. Peak activity windows by time brackets
            async with db.execute("""
                SELECT
                    SUM(CASE WHEN hour_of_day BETWEEN 8 AND 10 THEN 1 ELSE 0 END) as morning_drops,
                    SUM(CASE WHEN hour_of_day BETWEEN 13 AND 15 THEN 1 ELSE 0 END) as afternoon_drops,
                    SUM(CASE WHEN hour_of_day BETWEEN 18 AND 20 THEN 1 ELSE 0 END) as evening_drops,
                    COUNT(*) as total_windowed
                FROM drop_events;
            """) as c:
                p_row = await c.fetchone()
                morning = p_row["morning_drops"] or 0 if p_row else 0
                afternoon = p_row["afternoon_drops"] or 0 if p_row else 0
                evening = p_row["evening_drops"] or 0 if p_row else 0
                total_win = p_row["total_windowed"] or 0 if p_row else 0
                other = max(0, total_win - (morning + afternoon + evening))

            # 4. Recent drops
            async with db.execute("""
                SELECT course_code, section_name, open_slots, capacity, enlisted, duration_seconds, created_at
                FROM drop_events
                ORDER BY id DESC
                LIMIT 4;
            """) as c:
                recent_drops = [dict(r) for r in await c.fetchall()]

            # 5. Active counters
            async with db.execute("SELECT COUNT(DISTINCT user_id) as total_watchers FROM user_watchlist;") as c:
                w_row = await c.fetchone()
                active_watchers = w_row["total_watchers"] if w_row else 0

            async with db.execute("SELECT COUNT(*) as total_courses FROM monitored_courses WHERE is_active = 1;") as c:
                m_row = await c.fetchone()
                active_courses = m_row["total_courses"] if m_row else 0

            return {
                "total_drops": total_drops,
                "active_watchers": active_watchers,
                "active_courses": active_courses,
                "top_courses": top_courses,
                "morning_drops": morning,
                "afternoon_drops": afternoon,
                "evening_drops": evening,
                "other_drops": other,
                "recent_drops": recent_drops,
            }

    # ==========================================
    # TERM PRUNING
    # ==========================================

    async def prune_all_watchlists(self) -> int:
        """Clears all student watchlist subscriptions for end-of-term maintenance."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM user_watchlist;")
            deleted = cursor.rowcount
            await db.commit()
            return deleted

"""
ArcherSniper - Core Engine & Watchdog
Orchestrates 24/7 background polling (15s default), 60s heartbeat keep-alive logging,
gatekeeper access management, multi-channel college/GE/LC feeds, DM alerts, and disconnect announcements.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
import discord

from config import (
    DEFAULT_POLL_INTERVAL,
    HEARTBEAT_INTERVAL,
    RECONNECT_STAGE_1_DELAY,
    RECONNECT_STAGE_2_INTERVAL,
    SCRAPER_LOG_PATH,
    SCRAPER_DUMP_PATH,
    SLOT_DROPS_LOG_PATH,
    DM_DISPATCH_LOG_PATH,
    HEARTBEAT_LOG_PATH,
    API_DEBUG_LOG_PATH,
    DUPLICATES_LOG_PATH,
    AUTODISCOVERY_LOG_PATH,
    WATCHDOG_CYCLES_LOG_PATH,
    COURSE_CADENCE_LOG_PATH,
)
from database import Database
from dlsu_api import DLSUApiClient
from utils.course_classifier import classify_course
from utils.embeds import (
    create_student_dm_alert,
    create_college_feed_drop_embed,
    create_batched_feed_drop_embed,
    create_heartbeat_pulse_embed,
    create_disconnect_announcement,
    create_bot_status_announcement,
    create_system_alert_embed,
    create_admin_dm_mirror_embed,
)
from utils.session_refresher import PlaywrightSessionRefresher

logger = logging.getLogger("ArcherSniper.Engine")


def _append_log_line(file_path, line: str):
    """Appends a timestamped line to a dedicated log file safely."""
    try:
        from pathlib import Path
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8", errors="ignore") as f:
            f.write(line.strip() + "\n")
    except Exception as ex:
        logger.warning(f"Log write error for {file_path}: {ex}")


class WatchdogEngine:
    def __init__(
        self,
        bot: Any,
        db: Database,
        api_client: DLSUApiClient,
        alert_channel_id: int | None = None,
    ):
        self.bot = bot
        self.db = db
        self.api = api_client
        self.alert_channel_id = alert_channel_id

        # Engine State
        self.bot_active = False
        self.ge_lc_active = True
        self.poll_interval = DEFAULT_POLL_INTERVAL
        self.heartbeat_interval = HEARTBEAT_INTERVAL
        self.is_connected = False
        self.session_expired = False
        self.auto_reconnect_enabled = True
        self.is_reconnecting = False

        # In-memory baseline cache: (course_code, section_name) -> open_slots
        self.section_slot_cache: dict[tuple[str, str], int] = {}
        self.drop_start_times: dict[tuple[str, str], float] = {}
        self.recent_alerts: dict[tuple[str, str], tuple[int, float]] = {}
        self.recent_dm_dispatches: dict[tuple[int, str, str], tuple[int, float]] = {}
        self.session_connected_time: float = time.time()
        self.has_sent_6h_warning = False

        # Statistics
        self.total_poll_cycles = 0
        self.total_alerts_sent = 0
        self.heartbeat_count = 0
        self.consecutive_errors = 0
        self.last_heartbeat_time: datetime | None = None
        self.last_poll_time: datetime | None = None
        self.start_time = datetime.now(timezone.utc)
        self.course_last_polled: dict[str, float] = {}
        self.course_last_sections: dict[str, int] = {}
        self.course_last_status: dict[str, str] = {}
        self.course_last_latency: dict[str, float] = {}

        # Background Tasks & Grace Timers
        self.polling_task: asyncio.Task | None = None
        self.heartbeat_task: asyncio.Task | None = None
        self.disconnect_alert_task: asyncio.Task | None = None
        self.disconnect_alert_sent: bool = False
        self.disconnect_grace_period_seconds: int = 300  # 5 minutes grace period before pinging admins

        # Tier 2 Headless Browser 24/7 Persistent Session Keeper
        self.session_refresher = PlaywrightSessionRefresher(
            on_cookie_update=self._handle_keeper_cookie_update,
        )

    async def _handle_keeper_cookie_update(self, fresh_cookies: dict[str, str]):
        """Callback from PlaywrightSessionRefresher when fresh cookies are harvested from the browser."""
        if not fresh_cookies:
            return
        logger.info(f"🤖 [Engine] Received {len(fresh_cookies)} rolled cookies from Playwright Session Keeper.")
        self.api.update_auth(fresh_cookies)
        await self.db.update_master_cookies(fresh_cookies)
        if not self.is_connected:
            self.is_connected = True
            self.session_expired = False
            self.session_connected_time = time.time()
            await self._on_reconnect_success("Playwright Headless Session Keeper")

    async def initialize(self):
        """Loads cached states, system configuration, and master auth."""
        state = await self.db.get_system_state()
        self.bot_active = state["bot_active"]
        self.ge_lc_active = state["ge_lc_active"]
        self.poll_interval = state["poll_interval"]
        self.heartbeat_interval = state["heartbeat_interval"]

        # Populate memory cache from SQLite
        states = await self.db.get_all_section_states()
        for s in states:
            code = s.get("course_code") or s.get("course_id")
            key = (code.upper(), s["section_name"].upper())
            self.section_slot_cache[key] = s["open_slots"]

        # Check existing master auth
        auth = await self.db.get_master_auth()
        if auth and auth.get("cookies"):
            self.api.update_auth(auth["cookies"], auth.get("headers"))
            self.is_connected = auth.get("status") == "CONNECTED"
        else:
            self.is_connected = False
            self.session_expired = True

        logger.info(
            f"WatchdogEngine initialized: bot_active={self.bot_active}, ge_lc_active={self.ge_lc_active}, "
            f"poll_interval={self.poll_interval}s, status={'CONNECTED' if self.is_connected else 'DISCONNECTED'}"
        )

    def start_tasks(self):
        """Starts 24/7 background polling and keep-alive tasks."""
        if self.polling_task is None or self.polling_task.done():
            self.polling_task = asyncio.create_task(self._polling_loop(), name="ArcherSniper_Poller")
        if self.heartbeat_task is None or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="ArcherSniper_Heartbeat")
        if self.is_connected and self.bot_active:
            asyncio.create_task(self._start_keeper_from_db())
        logger.info("Background watchdog polling and keep-alive loops started.")
        ts_init = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        _append_log_line(
            WATCHDOG_CYCLES_LOG_PATH,
            f"[{ts_init}] SYSTEM -> Watchdog Engine started (Interval: {self.poll_interval}s, Active: {self.bot_active}, Session: {'CONNECTED' if self.is_connected else 'DISCONNECTED'})"
        )

    async def _start_keeper_from_db(self):
        """Helper to start the persistent session keeper using current DB auth."""
        auth = await self.db.get_master_auth()
        if auth and auth.get("cookies") and not self.session_refresher.is_running:
            await self.session_refresher.inject_and_start_keeper(auth["cookies"], auth.get("headers"))

    async def stop_tasks(self):
        """Stops background tasks gracefully."""
        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
        if self.session_refresher and self.session_refresher.is_running:
            await self.session_refresher.close()
        logger.info("Background watchdog tasks stopped.")

    # ==========================================
    # 60-SECOND HEARTBEAT & PULSE LOGGING
    # ==========================================

    async def _heartbeat_loop(self):
        """Sends keep-alive probe every 60s and logs pulse in #💓-admin-heartbeat-log."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                if self.is_connected and not self.session_expired:
                    t0 = time.perf_counter()
                    success = await self.api.send_heartbeat()
                    latency_ms = (time.perf_counter() - t0) * 1000.0

                    if success:
                        self.heartbeat_count += 1
                        self.last_heartbeat_time = datetime.now(timezone.utc)
                        self.consecutive_errors = 0
                        await self._log_heartbeat_pulse(200, latency_ms)

                        # Periodic Auto-Discovery of New Courses from DLSU (every 30 heartbeats = 30 minutes)
                        if self.heartbeat_count % 30 == 0:
                            asyncio.create_task(self.auto_discover_new_courses())

                        # Proactive 6-Hour Session Age Notice
                        if time.time() - self.session_connected_time > 21600 and not self.has_sent_6h_warning:
                            self.has_sent_6h_warning = True
                            await self._send_proactive_session_notice()
                    else:
                        logger.warning("Keep-alive heartbeat failed.")
                        await self._log_heartbeat_pulse(401, latency_ms)
                        await self._handle_disconnect("Heartbeat responded with 401 Unauthorized")
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await self._handle_disconnect(f"Heartbeat exception: {e}")

            await asyncio.sleep(self.heartbeat_interval)

    async def auto_discover_new_courses(self) -> tuple[int, int]:
        """
        Background Auto-Discovery Engine:
        Fetches full catalog from DLSU CourseFinder.
        - Automatically saves all courses in course_catalog.
        - If GE, LC, SAS, LASARE, NSTP (is_ge_lc == True), adds to 24/7 active monitoring pool.
        - If college major (is_ge_lc == False), saves in catalog and only activates in 15s pool if on a user watchlist.
        Returns: (new_ge_lc_count, new_college_count)
        """
        if not self.is_connected or self.session_expired:
            return 0, 0

        auth = await self.db.get_master_auth()
        campus_no = auth.get("campus_no") or 7 if auth else 7
        academic_session = auth.get("academic_session") or 155 if auth else 155

        t0 = time.perf_counter()
        try:
            catalog = await self.api.fetch_course_catalog(campus_no=campus_no, academic_session=academic_session)
            if not catalog:
                return 0, 0

            watchlisted_codes = await self.db.get_all_watchlisted_course_codes()
            ge_lc_count = 0
            college_count = 0

            # Sort catalog by integer course_id ASC to ensure active lower IDs are processed first
            sorted_catalog = sorted(
                catalog,
                key=lambda x: int(x["course_id"]) if str(x.get("course_id", "")).isdigit() else 999999
            )

            # Bulk upsert all 2,600+ courses into catalog in a single 0.03s SQLite transaction
            await self.db.bulk_upsert_catalog_courses(sorted_catalog, academic_session)

            seen_discovery_codes = set()
            for item in sorted_catalog:
                cid = str(item["course_id"]).strip()
                code = str(item["course_code"]).strip().upper()
                name = str(item.get("course_name", "")).strip()

                if code in seen_discovery_codes:
                    continue
                seen_discovery_codes.add(code)

                classification = classify_course(code)
                if classification.is_ge_lc:
                    # 24/7 Universal Monitoring Pool (Guaranteed Active ID)
                    await self.db.add_monitored_course(cid, code, name, added_by="AutoDiscovery (24/7 GE/LC)")
                    ge_lc_count += 1
                elif code in watchlisted_codes:
                    # On-Demand Student Watchlist (Guaranteed Active ID)
                    await self.db.add_monitored_course(cid, code, name, added_by="AutoWatchlistResolver")
                    college_count += 1
                else:
                    college_count += 1

            t_dur = time.perf_counter() - t0
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            _append_log_line(
                AUTODISCOVERY_LOG_PATH,
                f"[{ts}] AUTO-DISCOVERY -> Scanned {len(catalog)} catalog courses in {t_dur:.2f}s | {ge_lc_count} GE/LC (24/7 Monitored) | {college_count} College (Indexed)"
            )
            logger.info(f"Auto-Discovery sync complete: {ge_lc_count} GE/LC courses, {college_count} college courses ({t_dur:.2f}s).")
            return ge_lc_count, college_count
        except Exception as e:
            logger.debug(f"Auto-discovery check error: {e}")
            return 0, 0

    async def _get_target_guild_ids(self) -> list[int]:
        """Returns list of distinct integer guild IDs from database and active bot guilds."""
        ids = set()
        configured = await self.db.get_all_configured_guilds()
        for c in configured:
            try:
                ids.add(int(c))
            except Exception:
                pass
        if hasattr(self.bot, "guilds") and isinstance(self.bot.guilds, (list, tuple)):
            for g in self.bot.guilds:
                gid = getattr(g, "id", None)
                if isinstance(gid, int):
                    ids.add(gid)
        return list(ids)

    async def _resolve_feed_channel(self, guild_id: int, feed_key: str) -> discord.TextChannel | None:
        """Resolves a channel for a guild ID from DB cache, falling back to name-based discovery in bot.guilds."""
        if not isinstance(guild_id, int):
            try:
                guild_id = int(guild_id)
            except Exception:
                return None

        channels = await self.db.get_server_channels(guild_id)
        aliases = {
            "dm_logs": ["dm_logs", "admin_dm_logs", "dmlogs"],
            "admin_dm_logs": ["admin_dm_logs", "dm_logs", "dmlogs"],
            "admin_disconnects": ["admin_disconnects", "disconnects", "disconnect_alerts"],
            "admin_heartbeat": ["admin_heartbeat", "heartbeat_log", "heartbeat"],
            "admin_commands": ["admin_commands", "admin_cmd"],
            "bot_commands": ["bot_commands", "commands"],
            "ge_lc": ["ge_lc", "gelc"],
        }
        lookup_keys = aliases.get(feed_key, [feed_key])
        ch_id = None
        for k in lookup_keys:
            if k in channels:
                ch_id = channels[k]
                break

        if ch_id:
            ch = self.bot.get_channel(ch_id)
            if not ch and hasattr(self.bot, "fetch_channel"):
                try:
                    ch = await self.bot.fetch_channel(ch_id)
                except Exception:
                    ch = None
            if ch:
                return ch

        # Auto-discover by name if bot is currently in the guild
        guild = None
        if hasattr(self.bot, "get_guild"):
            try:
                guild = self.bot.get_guild(guild_id)
            except Exception:
                guild = None
        if not guild and hasattr(self.bot, "guilds") and isinstance(self.bot.guilds, (list, tuple)):
            for g in self.bot.guilds:
                if getattr(g, "id", None) == guild_id:
                    guild = g
                    break

        if guild:
            key_patterns = {
                "ge_lc": ["ge-lc", "ge_lc", "gelc", "ge-feed", "ge_feed"],
                "ccs": ["ccs-drops", "ccs_drops", "ccs"],
                "rvrcob": ["rvrcob-drops", "rvrcob_drops", "rvrcob", "cob"],
                "gcoe": ["gcoe-drops", "gcoe_drops", "gcoe", "engg"],
                "cla": ["cla-drops", "cla_drops", "cla"],
                "cos": ["cos-drops", "cos_drops", "cos", "science"],
                "bagced": ["bagced-drops", "bagced_drops", "bagced", "ced"],
                "soe": ["soe-drops", "soe_drops", "soe", "econ"],
                "announcements": ["announcement", "announcements"],
                "admin_disconnects": ["disconnect", "admin-disconnect"],
                "admin_heartbeat": ["heartbeat", "heartbeat-log", "admin-heartbeat"],
                "dm_logs": ["dm-log", "dm_log", "admin-dm", "admin_dm_logs"],
                "bot_commands": ["bot-command", "bot_command", "commands"],
                "admin_commands": ["admin-command", "admin_command"],
            }
            patterns = key_patterns.get(feed_key, [feed_key])
            text_channels = getattr(guild, "text_channels", [])
            if isinstance(text_channels, (list, tuple)):
                for tc in text_channels:
                    clean_name = str(getattr(tc, "name", "")).lower().replace(" ", "-")
                    if any(p in clean_name for p in patterns):
                        tc_id = getattr(tc, "id", None)
                        if isinstance(tc_id, int):
                            await self.db.save_server_channels(guild_id, {feed_key: tc_id})
                        return tc
        return None

    async def _send_proactive_session_notice(self):
        """Sends an early notice to #🚨-admin-disconnects when cookies are 6+ hours old."""
        embed = create_system_alert_embed(
            title="ℹ️ Master cURL Session Age Notice (6+ Hours)",
            description=(
                "**Current Archer's Hub browser session has been active for over 6 hours.**\n\n"
                "> 🛡️ **Status:** Keep-alive is active and responsive.\n"
                "> 💡 **Tip:** Consider updating via `!setcurl <curl>` before major morning enlistment rushes to ensure seamless continuity."
            ),
            level="info",
        )
        target_guild_ids = await self._get_target_guild_ids()
        for g_id in target_guild_ids:
            ch = await self._resolve_feed_channel(g_id, "admin_disconnects")
            if ch:
                try:
                    await ch.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except Exception:
                    pass

    async def _log_heartbeat_pulse(self, status_code: int, latency_ms: float):
        """Sends compact pulse log to #💓-admin-heartbeat-log channel and writes to data/logs/session_heartbeats.log."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        active_w = await self.db.get_all_active_watchers_count()
        active_c = len({k[0] for k in self.section_slot_cache.keys()})
        _append_log_line(
            HEARTBEAT_LOG_PATH,
            f"[{ts}] HEARTBEAT #{self.heartbeat_count:04d} -> Status: {status_code} | Latency: {latency_ms:.1f}ms | Courses: {active_c} | Watchers: {active_w} | Session: {'CONNECTED' if self.is_connected else 'DISCONNECTED'}"
        )

        target_guild_ids = await self._get_target_guild_ids()
        if not target_guild_ids:
            # Fallback to ALERT_CHANNEL_ID if configured
            if self.alert_channel_id:
                ch = self.bot.get_channel(self.alert_channel_id)
                if ch:
                    embed = create_heartbeat_pulse_embed(
                        status_code=status_code,
                        latency_ms=latency_ms,
                        active_courses=len({k[0] for k in self.section_slot_cache.keys()}),
                        active_watchers=await self.db.get_all_active_watchers_count(),
                    )
                    try:
                        await ch.send(embed=embed)
                    except Exception:
                        pass
            return

        for g_id in target_guild_ids:
            channel = await self._resolve_feed_channel(g_id, "admin_heartbeat")
            if channel:
                embed = create_heartbeat_pulse_embed(
                    status_code=status_code,
                    latency_ms=latency_ms,
                    active_courses=len({k[0] for k in self.section_slot_cache.keys()}),
                    active_watchers=await self.db.get_all_active_watchers_count(),
                )
                try:
                    await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except Exception as e:
                    logger.debug(f"Could not send pulse to #{getattr(channel, 'name', channel.id)}: {e}")

    # ==========================================
    # 15-SECOND COURSE SCRAPER POLLING LOOP
    # ==========================================

    async def _polling_loop(self):
        """Runs continuous scraping of monitored courses strictly every 15s."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            t_loop_start = time.perf_counter()
            try:
                # Only execute live polling if bot is ACTIVE and session CONNECTED
                if self.bot_active and self.is_connected and not self.session_expired:
                    await self._execute_poll_cycle()
                    await self.update_bot_presence()
                elif not self.is_connected and not self.is_reconnecting:
                    await self.update_bot_presence()
                    if self.auto_reconnect_enabled:
                        asyncio.create_task(self._run_two_stage_reconnect())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                self.consecutive_errors += 1
                if self.consecutive_errors >= 3:
                    await self._handle_disconnect(f"3 consecutive poll errors: {e}")

            elapsed = time.perf_counter() - t_loop_start
            sleep_time = max(0.5, self.poll_interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def _execute_poll_cycle(self):
        """Iterates over all monitored courses and detects capacity changes."""
        monitored = await self.db.get_monitored_courses(active_only=True)
        if not monitored:
            return

        # Deduplicate courses by code to guarantee each course is queried at most once per cycle
        seen_codes = set()
        unique_monitored = []
        for c in monitored:
            code_u = c["course_code"].strip().upper()
            if code_u not in seen_codes:
                seen_codes.add(code_u)
                unique_monitored.append(c)

        # Filter for the active 15-second watchdog pool:
        # 1. All universal GE & LC courses (always monitored 24/7)
        # 2. All student-watchlisted courses (monitored whenever watched)
        # 3. Explicitly added courses by admin/user/system
        try:
            watchlisted_codes = await self.db.get_all_watchlisted_course_codes()
        except Exception:
            watchlisted_codes = set()

        active_poll_courses = []
        for c in unique_monitored:
            code = c["course_code"].strip().upper()
            is_ge = classify_course(code).is_ge_lc
            is_watched = code in watchlisted_codes
            is_manual = (
                str(c.get("added_by", "")).startswith("Admin")
                or str(c.get("added_by", "")).startswith("User")
                or str(c.get("added_by", "")).startswith("Watch by")
                or str(c.get("added_by", "")).startswith("AutoWatch")
            )
            if is_ge or is_watched or is_manual:
                active_poll_courses.append(c)

        t_cycle_start = time.perf_counter()
        monitored = active_poll_courses

        self.last_poll_time = datetime.now(timezone.utc)
        self.total_poll_cycles += 1

        # Periodic Auto-Discovery of New Subjects from DLSU (on Cycle #1 and every 120 cycles = ~30 mins)
        if self.total_poll_cycles == 1 or self.total_poll_cycles % 120 == 0:
            asyncio.create_task(self.auto_discover_new_courses())

        # Log cycle header to course_refetch_cadence.log
        watched_count = sum(1 for c in monitored if c["course_code"].strip().upper() in watchlisted_codes)
        ge_count = len(monitored) - watched_count
        ts_hdr = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        _append_log_line(
            COURSE_CADENCE_LOG_PATH,
            f"\n--- [Cycle #{self.total_poll_cycles:04d} | {ts_hdr}] Pool: {len(monitored)} active subjects ({watched_count} Watched, {ge_count} GE/LC) ---"
        )

        cycle_lines = []
        cycle_dump = {
            "cycle": self.total_poll_cycles,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_courses": len(monitored),
            "courses": {},
        }
        cycle_feed_changes: dict[str, list[dict]] = {}

        sem = asyncio.Semaphore(8)
        lock = asyncio.Lock()

        async def _fetch_course(course: dict):
            cid = str(course["course_id"]).strip()
            code = course["course_code"]
            name = course.get("course_name", "")

            # If course_id is not numeric, resolve numeric Course Creation ID from local SQLite catalog
            if not cid.isdigit():
                catalog_match = await self.db.search_catalog(code)
                if catalog_match and str(catalog_match[0]["course_id"]).isdigit():
                    cid = str(catalog_match[0]["course_id"]).strip()
                    name = catalog_match[0].get("course_name", name)
                    # Upgrade in database so future polls use numeric ID directly
                    await self.db.add_monitored_course(
                        course_id=cid,
                        course_code=code,
                        course_name=name,
                        added_by="AutoCatalogResolver",
                    )
                else:
                    async with lock:
                        cycle_lines.append(f"  • [{code}] -> NOT OFFERED: Course ID not active in current term")
                    ts_pnd = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    _append_log_line(COURSE_CADENCE_LOG_PATH, f"[{ts_pnd}] [{code:<8}] ⚠️ NOT OFFERED / NO ACTIVE SECTIONS THIS TERM")
                    return

            async with sem:
                try:
                    t_fetch_start = time.perf_counter()
                    sections = await self.api.fetch_section_data(cid)
                    fetch_dur_ms = (time.perf_counter() - t_fetch_start) * 1000.0
                    code_clean = code.strip().upper()
                    now_ts = time.time()
                    prev_ts = self.course_last_polled.get(code_clean)
                    self.course_last_polled[code_clean] = now_ts
                    self.course_last_sections[code_clean] = len(sections)
                    self.course_last_status[code_clean] = "200 OK"
                    self.course_last_latency[code_clean] = fetch_dur_ms

                    # Log exact refetch gap to data/logs/course_refetch_cadence.log
                    tot_open = sum(s.get("open_slots", 0) for s in sections)
                    ts_log = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    if prev_ts is not None:
                        gap_sec = now_ts - prev_ts
                        cadence_msg = f"[{ts_log}] [{code_clean:<8}] Refetched in {fetch_dur_ms:>5.1f}ms | Gap since last fetch: {gap_sec:>5.1f}s | Sections: {len(sections):>2} ({tot_open} open)"
                    else:
                        cadence_msg = f"[{ts_log}] [{code_clean:<8}] Initial baseline in {fetch_dur_ms:>5.1f}ms | Gap since last fetch: FIRST POLL | Sections: {len(sections):>2} ({tot_open} open)"
                    _append_log_line(COURSE_CADENCE_LOG_PATH, cadence_msg)

                    # Batch upsert all section states to SQLite in 1 unified transaction (0.005s)
                    await self.db.bulk_upsert_section_states(cid, code_clean, sections)

                    sec_items = []
                    for sec in sections:
                        s_name = sec.get("section_name", "")
                        enl = sec.get("enlisted", 0)
                        cap = sec.get("capacity", 0)
                        sec_items.append(f"{s_name}:{enl}/{cap}")

                        await self._process_section_delta(
                            course_id=cid,
                            course_code=code,
                            course_name=name,
                            section_data=sec,
                            cycle_feed_changes=cycle_feed_changes,
                        )

                    sec_str = ", ".join(sec_items) if sec_items else "0 sections"
                    async with lock:
                        cycle_lines.append(f"  • [{code}] (ID: {cid}) -> {len(sections)} sections ({sec_str})")
                        cycle_dump["courses"][code] = {
                            "course_id": cid,
                            "sections_count": len(sections),
                            "sections": sections,
                        }
                except PermissionError as pe:
                    async with lock:
                        cycle_lines.append(f"  • [{code}] (ID: {cid}) -> AUTH ERROR: {pe}")
                    ts_err = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    _append_log_line(COURSE_CADENCE_LOG_PATH, f"[{ts_err}] [{code:<8}] ⚠️ AUTH ERROR: {pe}")
                    logger.warning(f"Permission / session error on {code} ({cid}): {pe}")
                    # Verify if master session is truly expired or if this was just a transient single-course glitch
                    try:
                        is_master_alive = await self.api.send_heartbeat()
                    except Exception:
                        is_master_alive = False

                    if not is_master_alive:
                        await self._handle_disconnect(str(pe))
                except Exception as e:
                    async with lock:
                        cycle_lines.append(f"  • [{code}] (ID: {cid}) -> FETCH ERROR: {e}")
                    ts_err = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    _append_log_line(COURSE_CADENCE_LOG_PATH, f"[{ts_err}] [{code:<8}] ⚠️ FETCH ERROR: {e}")
                    logger.debug(f"Error fetching {code} ({cid}): {e}")

        # Fetch all active courses concurrently with Semaphore pool
        await asyncio.gather(*[_fetch_course(c) for c in monitored], return_exceptions=True)

        # Save cycle log to data/logs/scraper_fetches.log (keep last 500 lines)
        try:
            timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            header = f"\n[Cycle #{self.total_poll_cycles:04d} | {timestamp_str} | Polled {len(monitored)} courses]"
            log_block = header + "\n" + "\n".join(cycle_lines) + "\n"

            # Read existing to prevent uncontrolled log bloat
            existing_lines = []
            if SCRAPER_LOG_PATH.exists():
                try:
                    with open(SCRAPER_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                        existing_lines = f.readlines()
                except Exception:
                    existing_lines = []

            # Keep latest 1000 lines
            trimmed_lines = existing_lines[-800:] + [log_block]
            with open(SCRAPER_LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(trimmed_lines)

            # Dump JSON snapshot
            with open(SCRAPER_DUMP_PATH, "w", encoding="utf-8") as f:
                json.dump(cycle_dump, f, indent=2)
        except Exception as ex:
            logger.debug(f"Scraper file log write error: {ex}")

        # Write cycle benchmark metric to WATCHDOG_CYCLES_LOG_PATH
        try:
            t_cycle_dur = time.perf_counter() - t_cycle_start
            ts_cycle = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            ge_lc_mon = sum(1 for c in monitored if classify_course(c['course_code']).is_ge_lc)
            watched_mon = len(monitored) - ge_lc_mon
            _append_log_line(
                WATCHDOG_CYCLES_LOG_PATH,
                f"[{ts_cycle}] Cycle #{self.total_poll_cycles:04d} -> Polled {len(monitored)} courses ({ge_lc_mon} GE/LC, {watched_mon} Watched) | Exec Time: {t_cycle_dur:.2f}s | Deltas: {len(cycle_feed_changes)} | Status: OK"
            )
        except Exception as ex:
            logger.debug(f"Watchdog cycle log write error: {ex}")

    # ==========================================
    # SMART DELTA & MULTICAST DISPATCHING
    # ==========================================

    async def _process_section_delta(
        self,
        course_id: str,
        course_code: str,
        course_name: str,
        section_data: dict,
        cycle_feed_changes: dict[str, list[dict]] | None = None,
    ):
        """
        Delta-Based Notification Engine:
          - Evaluates slot delta: Full -> Open, Open -> Full, or Slot Count change.
          - Dispatches DM personal alerts to all subscribed students.
          - Groups slot drops for batched 15-second broadcast to public feed channels.
        """
        sec_name = section_data.get("section_name", "").strip().upper()
        cap = section_data.get("capacity", 0)
        enl = section_data.get("enlisted", 0)
        new_open = section_data.get("open_slots", 0)
        teacher = section_data.get("teacher", "TBA")
        sched = section_data.get("schedule", "TBA")

        cache_key = (course_code.upper(), sec_name)
        prev_open = self.section_slot_cache.get(cache_key)

        # Update in-memory slot cache
        self.section_slot_cache[cache_key] = new_open

        # Silence all alerts on Cycle 1 (baseline establishment on startup / restart)
        if self.total_poll_cycles <= 1:
            return

        # If a brand-new section appears in subsequent cycles with open slots, treat as a new drop from 0.
        if prev_open is None:
            if new_open > 0:
                prev_open = 0
            else:
                return

        # Fail-safe check
        if self.session_expired or not self.is_connected or not self.bot_active:
            return

        # Check if slot count changed
        if new_open != prev_open:
            now_ts = time.time()
            last_alert = self.recent_alerts.get(cache_key)
            # Duplicate suppression check (within 15s with same open slot count)
            if last_alert and last_alert[0] == new_open and (now_ts - last_alert[1]) < 15.0:
                ts_dup = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                _append_log_line(
                    DUPLICATES_LOG_PATH,
                    f"[{ts_dup}] SUPPRESSED DUPLICATE DELTA: {course_code} {sec_name} ({new_open} open) - Already alerted {now_ts - last_alert[1]:.1f}s ago"
                )
                return

            self.recent_alerts[cache_key] = (new_open, now_ts)
            logger.info(f"⚡ SLOT DELTA: {course_code} {sec_name} changed ({prev_open} ➔ {new_open} open)")
            ts_drop = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            _append_log_line(
                SLOT_DROPS_LOG_PATH,
                f"[{ts_drop}] SLOT DELTA: {course_code} {sec_name} | Slots: {prev_open} ➔ {new_open} Open ({enl}/{cap} Enlisted) | Teacher: {teacher} | Sched: {sched}"
            )

            # Record in Drop Analytics
            if new_open > prev_open:
                now_hour = datetime.now(timezone.utc).hour
                await self.db.record_drop_event(
                    course_code=course_code,
                    section_name=sec_name,
                    open_slots=new_open,
                    capacity=cap,
                    enlisted=enl,
                    hour_of_day=now_hour,
                )
                self.drop_start_times[cache_key] = time.time()
            elif new_open == 0 and prev_open > 0:
                t_start = self.drop_start_times.pop(cache_key, None)
                if t_start:
                    dur = max(1, int(time.time() - t_start))
                    await self.db.update_drop_event_duration(course_code, sec_name, dur)

            # 1. Personal Direct Message (DM) Alerts to Subscribed Students
            await self._dispatch_personal_dms(
                course_code=course_code,
                course_name=course_name,
                section_name=sec_name,
                open_slots=new_open,
                capacity=cap,
                enlisted=enl,
                teacher=teacher,
                schedule=sched,
                prev_open_slots=prev_open,
            )

            # 2. Immediate Broadcast to Public Feed Channels (GE/LC Feed & College Feeds)
            if cycle_feed_changes is not None:
                classification = classify_course(course_code)
                change_item = {
                    "course_code": course_code,
                    "course_name": course_name,
                    "section_name": sec_name,
                    "open_slots": new_open,
                    "capacity": cap,
                    "enlisted": enl,
                    "teacher": teacher,
                    "schedule": sched,
                    "prev_open_slots": prev_open,
                    "category_label": classification.college_name or "DLSU Feed",
                }
                target_channels = set()
                if classification.is_ge_lc and self.ge_lc_active:
                    target_channels.add("ge_lc")
                col_key = classification.feed_channel_key
                if col_key and col_key != "ge_lc":
                    target_channels.add(col_key)

                for ch_k in target_channels:
                    cycle_feed_changes.setdefault(ch_k, []).append(change_item)

            await self._broadcast_to_feeds(
                course_code=course_code,
                course_name=course_name,
                section_name=sec_name,
                open_slots=new_open,
                capacity=cap,
                enlisted=enl,
                teacher=teacher,
                schedule=sched,
                prev_open_slots=prev_open,
            )

    async def _broadcast_to_feeds(
        self,
        course_code: str,
        course_name: str,
        section_name: str,
        open_slots: int,
        capacity: int,
        enlisted: int,
        teacher: str,
        schedule: str,
        prev_open_slots: int = 0,
    ):
        """Broadcasts a single drop card to #🎯-ge-lc-feed and respective College Feeds."""
        classification = classify_course(course_code)
        feed_embed = create_college_feed_drop_embed(
            course_code=course_code,
            course_name=course_name,
            section_name=section_name,
            open_slots=open_slots,
            capacity=capacity,
            enlisted=enlisted,
            teacher=teacher,
            schedule=schedule,
            category_label=classification.college_name or "DLSU Feed",
            prev_open_slots=prev_open_slots,
        )

        target_guild_ids = await self._get_target_guild_ids()
        for g_id in target_guild_ids:
            # Broadcast to GE & LC Feed
            if classification.is_ge_lc and self.ge_lc_active:
                ch = await self._resolve_feed_channel(g_id, "ge_lc")
                if ch:
                    try:
                        await ch.send(embed=feed_embed, allowed_mentions=discord.AllowedMentions.none())
                        logger.info(f"📢 Broadcasted single drop to #{getattr(ch, 'name', ch.id)} (ge_lc)")
                    except Exception as ex:
                        logger.warning(f"Could not send feed drop to #{getattr(ch, 'name', ch.id)}: {ex}")

            # Broadcast to respective College Feed
            col_key = classification.feed_channel_key
            if col_key and col_key != "ge_lc":
                ch_col = await self._resolve_feed_channel(g_id, col_key)
                if ch_col:
                    try:
                        await ch_col.send(embed=feed_embed, allowed_mentions=discord.AllowedMentions.none())
                        logger.info(f"📢 Broadcasted single drop to #{getattr(ch_col, 'name', ch_col.id)} ({col_key})")
                    except Exception as ex:
                        logger.warning(f"Could not send feed drop to #{getattr(ch_col, 'name', ch_col.id)}: {ex}")

    async def _dispatch_personal_dms(
        self,
        course_code: str,
        course_name: str,
        section_name: str,
        open_slots: int,
        capacity: int,
        enlisted: int,
        teacher: str,
        schedule: str,
        prev_open_slots: int,
    ):
        """Sends rich DM notifications to every subscribed student whose pings are enabled."""
        watchers = await self.db.get_active_watchers_for_section(course_code, section_name)
        if not watchers:
            return

        dm_embed = create_student_dm_alert(
            course_code=course_code,
            course_name=course_name,
            section_name=section_name,
            open_slots=open_slots,
            capacity=capacity,
            enlisted=enlisted,
            teacher=teacher,
            schedule=schedule,
            prev_open_slots=prev_open_slots,
        )

        async def _send_to_watcher(watcher: dict):
            user_id = watcher["user_id"]
            username = watcher.get("discord_username") or f"User_{user_id}"
            dm_key = (user_id, course_code.upper(), section_name.upper())
            now_ts = time.time()
            last_dm = self.recent_dm_dispatches.get(dm_key)

            # Duplicate DM suppression (within 15s with same open slot count)
            if last_dm and last_dm[0] == open_slots and (now_ts - last_dm[1]) < 15.0:
                ts_dm_dup = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                _append_log_line(
                    DUPLICATES_LOG_PATH,
                    f"[{ts_dm_dup}] SUPPRESSED REPEAT DM: User {user_id} on {course_code} {section_name} ({open_slots} open)"
                )
                return

            self.recent_dm_dispatches[dm_key] = (open_slots, now_ts)
            ts_dm = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            try:
                user = None
                if hasattr(self.bot, "fetch_user"):
                    res = self.bot.fetch_user(user_id)
                    user = await res if asyncio.iscoroutine(res) or hasattr(res, "__await__") else res
                elif hasattr(self.bot, "get_user"):
                    user = self.bot.get_user(user_id)

                if user:
                    if open_slots == 0:
                        status_text = "🔒 **Section is now FULL / Sniped (0 Open)**"
                    elif open_slots < prev_open_slots:
                        taken = prev_open_slots - open_slots
                        status_text = f"⚡ **Slot Taken (-{taken}) • {open_slots} Open Left!**"
                    elif prev_open_slots == 0:
                        status_text = f"🚨 **{open_slots} Open Slots Available!**"
                    else:
                        status_text = f"🟢 **+{open_slots - prev_open_slots} Slots Added ({open_slots} Open)!**"

                    await user.send(
                        content=f"🔔 **ArcherSniper Notification:** `{course_code} {section_name}` — {status_text}",
                        embed=dm_embed,
                    )
                    self.total_alerts_sent += 1
                    _append_log_line(
                        DM_DISPATCH_LOG_PATH,
                        f"[{ts_dm}] DM DELIVERED: @{user.display_name} (ID: {user_id}) -> {course_code} {section_name} ({open_slots} Open) [SUCCESS]"
                    )

                    # Silently mirror to #📬-admin-dm-logs across all configured guilds
                    await self._mirror_dm_to_admin_logs(
                        username=user.display_name,
                        user_id=user_id,
                        course_code=course_code,
                        section_name=section_name,
                        open_slots=open_slots,
                        capacity=capacity,
                        enlisted=enlisted,
                        prev_open_slots=prev_open_slots,
                    )
            except Exception as e:
                logger.warning(f"Could not send DM to student {user_id}: {e}")
                _append_log_line(
                    DM_DISPATCH_LOG_PATH,
                    f"[{ts_dm}] DM FAILED: @{username} (ID: {user_id}) -> {course_code} {section_name} [ERROR: {e}]"
                )

        await asyncio.gather(*[_send_to_watcher(w) for w in watchers], return_exceptions=True)

    async def _mirror_dm_to_admin_logs(
        self,
        username: str,
        user_id: int,
        course_code: str,
        section_name: str,
        open_slots: int,
        capacity: int,
        enlisted: int,
        prev_open_slots: int,
    ):
        """Silently logs dispatched student DM alerts in #📬-admin-dm-logs."""
        mirror_embed = create_admin_dm_mirror_embed(
            username=username,
            user_id=user_id,
            course_code=course_code,
            section_name=section_name,
            open_slots=open_slots,
            capacity=capacity,
            enlisted=enlisted,
            prev_open_slots=prev_open_slots,
        )

        target_guild_ids = await self._get_target_guild_ids()
        for g_id in target_guild_ids:
            ch = await self._resolve_feed_channel(g_id, "dm_logs")
            if ch:
                try:
                    await ch.send(embed=mirror_embed, allowed_mentions=discord.AllowedMentions.none())
                except Exception as e:
                    logger.debug(f"Could not send DM mirror log to #{getattr(ch, 'name', ch.id)}: {e}")

    # ==========================================
    # BOT ACTIVITY & PRESENCE
    # ==========================================

    async def update_bot_presence(self):
        """Updates Discord bot presence dynamically according to system state."""
        try:
            if not self.bot or not hasattr(self.bot, "change_presence"):
                return
            if not self.bot_active:
                activity = discord.CustomActivity(name="⏸️ ArcherSniper (Maintenance)")
                await self.bot.change_presence(status=discord.Status.idle, activity=activity)
            elif self.session_expired or not self.is_connected:
                activity = discord.CustomActivity(name="⚠️ DLSU Session Expired")
                await self.bot.change_presence(status=discord.Status.dnd, activity=activity)
            else:
                active_courses = len({k[0] for k in self.section_slot_cache.keys()}) or len(await self.db.get_monitored_courses(active_only=True))
                poll_sec = int(self.poll_interval)
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{active_courses} Courses • {poll_sec}s Scrape",
                )
                await self.bot.change_presence(status=discord.Status.online, activity=activity)
        except Exception as e:
            logger.debug(f"Could not update bot presence: {e}")

    # ==========================================
    # DISCONNECT HANDLER & ANNOUNCEMENTS
    # ==========================================

    async def _handle_disconnect(self, reason: str):
        """
        Handles session disconnect: updates internal state, pauses drop DMs (Safe-Mode),
        and starts 5-minute grace period before sending any Discord pings or announcements.
        """
        if not self.is_connected and self.session_expired:
            return

        logger.warning(f"Watchdog detected session disconnect: {reason}")
        self.is_connected = False
        self.session_expired = True
        self.disconnect_alert_sent = False
        await self.db.update_auth_status("DISCONNECTED")
        await self.update_bot_presence()

        # Cancel any existing delayed notification task
        if self.disconnect_alert_task and not self.disconnect_alert_task.done():
            self.disconnect_alert_task.cancel()

        # Launch 5-minute grace timer before pinging admins or posting public announcements
        self.disconnect_alert_task = asyncio.create_task(
            self._delayed_disconnect_notifier(reason),
            name="Delayed_Disconnect_Notifier",
        )

        # Trigger Multi-Tier Auto-Reconnect Engine immediately in background
        if self.auto_reconnect_enabled and not self.is_reconnecting:
            asyncio.create_task(self._run_two_stage_reconnect())

    async def _delayed_disconnect_notifier(self, reason: str):
        """
        Waits 5 minutes (300 seconds) before dispatching any Discord pings.
        If the bot recovers autonomously (Tier 1/2) within 5 minutes, this task is cancelled silently.
        """
        try:
            logger.info("⏳ Session disconnect detected. Entering Safe-Mode with 5-minute silent grace period...")
            await asyncio.sleep(self.disconnect_grace_period_seconds)

            # Check if still disconnected after 5 minutes
            if not self.is_connected and self.session_expired and not self.disconnect_alert_sent:
                self.disconnect_alert_sent = True
                logger.warning(f"🚨 Bot remained disconnected for {self.disconnect_grace_period_seconds}s. Dispatching admin alerts for: {reason}")

                target_guild_ids = await self._get_target_guild_ids()
                for g_id in target_guild_ids:
                    # 1. Private alert to #🚨-admin-disconnects
                    disc_ch = await self._resolve_feed_channel(g_id, "admin_disconnects")
                    admin_cmd_ch = await self._resolve_feed_channel(g_id, "admin_commands")
                    cmd_mention = f"<#{admin_cmd_ch.id}>" if admin_cmd_ch else "`#🔒-admin-commands`"
                    if disc_ch:
                        embed = create_system_alert_embed(
                            title="🚨 Master Session Disconnected (5-Min Inactive)",
                            description=(
                                f"**Reason:** `{reason}`\n\n"
                                f"> ⏱️ **Downtime:** Bot was unable to auto-reconnect within **5 minutes**.\n"
                                f"> 🔇 **Safe-Mode:** Student drop alerts are paused.\n"
                                f"> 🔑 **Fix:** Run `!setcurl <curl>` in {cmd_mention} or click your 1-Click Bookmarklet."
                            ),
                            level="error",
                        )
                        try:
                            await disc_ch.send(embed=embed)
                        except Exception:
                            pass

                    # 2. Public announcement to #📢-announcements (@everyone ping)
                    ann_ch = await self._resolve_feed_channel(g_id, "announcements")
                    if ann_ch:
                        embed = create_disconnect_announcement()
                        try:
                            await ann_ch.send(content="@everyone", embed=embed)
                        except Exception:
                            pass
        except asyncio.CancelledError:
            logger.info("🟢 5-Minute disconnect alert cancelled (bot reconnected autonomously within grace period).")

    async def broadcast_bot_status(self, is_online: bool, admin_name: str, reason: str | None = None):
        """Broadcasts Bot ONLINE or OFFLINE announcement with @everyone mention to #📢-announcements."""
        target_guild_ids = await self._get_target_guild_ids()
        embed = create_bot_status_announcement(is_online=is_online, admin_name=admin_name, reason=reason)

        for g_id in target_guild_ids:
            ann_ch = await self._resolve_feed_channel(g_id, "announcements")
            if ann_ch:
                try:
                    await ann_ch.send(content="@everyone", embed=embed)
                except Exception as e:
                    logger.warning(f"Could not post status announcement to #{getattr(ann_ch, 'name', ann_ch.id)}: {e}")

        await self.update_bot_presence()

    # ==========================================
    # 4-TIER AUTO-RECONNECT & SESSION RECOVERY
    # ==========================================

    async def reconnect_with_new_auth(
        self,
        new_cookies: dict[str, str],
        new_headers: dict[str, str] | None = None,
        source_label: str = "Admin !setcurl",
    ) -> bool:
        """Applies newly provided authentication credentials and resets watchdog state."""
        self.api.update_auth(new_cookies, new_headers)
        auth = await self.db.get_master_auth()
        campus_no = auth.get("campus_no") or 7 if auth else 7
        academic_session = auth.get("academic_session") or 155 if auth else 155

        is_valid = False
        try:
            is_valid = await self.api.send_heartbeat(campus_no=campus_no)
        except Exception:
            is_valid = False

        if is_valid:
            # Launch or update 24/7 background persistent headless browser keeper
            asyncio.create_task(
                self.session_refresher.inject_and_start_keeper(new_cookies, new_headers)
            )
            await self._on_reconnect_success(source_label)
            return True
        else:
            logger.warning(f"Reconnection attempt via {source_label} failed verification.")
            return False

    async def _run_two_stage_reconnect(self):
        """Attempts fast retry, Tier 2 Headless Playwright recovery, and 10m periodic probe."""
        if self.is_reconnecting:
            return
        self.is_reconnecting = True
        logger.info("Starting Multi-Tier Auto-Reconnect Engine...")

        # Tier 1 Retry: 10s Fast Probe
        await asyncio.sleep(RECONNECT_STAGE_1_DELAY)
        try:
            if await self.api.probe_portal() and await self.api.send_heartbeat():
                await self._on_reconnect_success("Stage 1 (10s Fast Retry)")
                self.is_reconnecting = False
                return
        except Exception:
            pass

        # Tier 2: Check live cookies from active 24/7 Headless Keeper
        try:
            live_cookies = await self.session_refresher.extract_live_cookies()
            if live_cookies:
                auth = await self.db.get_master_auth()
                headers = auth.get("headers") if auth else None
                reconnected = await self.reconnect_with_new_auth(
                    new_cookies=live_cookies,
                    new_headers=headers,
                    source_label="Tier 2 Live Headless Keeper Extraction",
                )
                if reconnected:
                    logger.info("🟢 [Tier 2] Session recovered via Live Headless Keeper Extraction!")
                    self.is_reconnecting = False
                    return
        except Exception as e:
            logger.debug(f"Live keeper extraction check skipped: {e}")

        # Tier 2 Fallback: Launch Headless Chromium one-shot refresh
        try:
            logger.info("🤖 [Tier 2] Launching Headless Chromium to automatically refresh session...")
            fresh_cookies = await self.session_refresher.refresh_session(timeout_seconds=20.0)
            if fresh_cookies:
                auth = await self.db.get_master_auth()
                headers = auth.get("headers") if auth else None
                await self.db.save_master_auth(
                    cookies=fresh_cookies,
                    headers=headers,
                    status="CONNECTED",
                )
                reconnected = await self.reconnect_with_new_auth(
                    new_cookies=fresh_cookies,
                    new_headers=headers,
                    source_label="Tier 2 Playwright Headless Refresher",
                )
                if reconnected:
                    logger.info("🟢 [Tier 2] Session refreshed autonomously via Headless Chromium!")
                    self.is_reconnecting = False
                    return
        except Exception as p_err:
            logger.debug(f"Tier 2 Playwright recovery skipped: {p_err}")

        # Stage 3: 10m Periodic Probe
        while not self.is_connected and not self.bot.is_closed():
            await asyncio.sleep(RECONNECT_STAGE_2_INTERVAL)
            try:
                if await self.api.probe_portal() and await self.api.send_heartbeat():
                    await self._on_reconnect_success("Stage 2 (10-Min Periodic Retry)")
                    self.is_reconnecting = False
                    return
            except Exception:
                pass

        self.is_reconnecting = False

    async def _on_reconnect_success(self, stage_label: str):
        """Called when session is restored. Updates presence and state instantly."""
        self.is_connected = True
        self.session_expired = False
        self.consecutive_errors = 0
        self.session_connected_time = time.time()
        self.has_sent_6h_warning = False

        # Cancel any pending 5-minute disconnect alert
        if self.disconnect_alert_task and not self.disconnect_alert_task.done():
            self.disconnect_alert_task.cancel()
            self.disconnect_alert_task = None
        self.disconnect_alert_sent = False

        await self.db.update_auth_status("CONNECTED")
        logger.info(f"🟢 Reconnection SUCCESS via {stage_label}!")
        await self.update_bot_presence()

    # ==========================================
    # HEALTH DIAGNOSTICS
    # ==========================================

    def get_poll_status_data(self) -> dict:
        """Returns comprehensive real-time engine telemetry and per-course polling status."""
        now_utc = datetime.now(timezone.utc)
        uptime_sec = int((now_utc - self.start_time).total_seconds()) if self.start_time else 0

        # Format uptime string
        if uptime_sec < 60:
            uptime_str = f"{uptime_sec}s"
        elif uptime_sec < 3600:
            uptime_str = f"{uptime_sec // 60}m {uptime_sec % 60}s"
        elif uptime_sec < 86400:
            uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"
        else:
            uptime_str = f"{uptime_sec // 86400}d {(uptime_sec % 86400) // 3600}h"

        latency_ms = round(self.bot.latency * 1000, 1) if (self.bot and hasattr(self.bot, "latency")) else 0.0

        return {
            "uptime_str": uptime_str,
            "uptime_seconds": uptime_sec,
            "is_connected": self.is_connected and not self.session_expired,
            "bot_active": self.bot_active,
            "ge_lc_active": self.ge_lc_active,
            "poll_interval": self.poll_interval,
            "heartbeat_interval": self.heartbeat_interval,
            "gateway_latency_ms": latency_ms,
            "heartbeat_count": self.heartbeat_count,
            "last_heartbeat_time": self.last_heartbeat_time,
            "last_poll_time": self.last_poll_time,
            "total_poll_cycles": self.total_poll_cycles,
            "total_alerts_sent": self.total_alerts_sent,
            "course_polling": self.course_last_polled.copy(),
            "course_sections": self.course_last_sections.copy(),
            "course_status": self.course_last_status.copy(),
            "course_latency": self.course_last_latency.copy(),
        }

    def get_health_data(self) -> dict:
        """Returns runtime diagnostic metrics for health checks."""
        auth_cookies = self.api.cookies
        poll_data = self.get_poll_status_data()
        poll_data.update({
            "session_expired": self.session_expired,
            "consecutive_errors": self.consecutive_errors,
            "monitored_courses_count": len({k[0] for k in self.section_slot_cache.keys()}),
            "active_watchers_count": 0,
            "tokens_present": {
                "RequestVerificationToken": "RequestVerificationToken" in auth_cookies or "__RequestVerificationToken" in auth_cookies,
                "Secure-SID": "Secure-SID" in auth_cookies or "__Secure-SID" in auth_cookies,
                "ApplicationGatewayAffinity": "ApplicationGatewayAffinity" in auth_cookies,
            },
        })
        return poll_data

    async def get_active_poll_courses(self) -> list[dict]:
        """Returns the exact list of courses actively included in the 15-second polling loop (GE/LC + watched majors)."""
        all_monitored = await self.db.get_monitored_courses(active_only=True)
        try:
            watchlisted_codes = set(await self.db.get_all_watchlisted_course_codes())
        except Exception:
            watchlisted_codes = set()

        unique_map = {}
        for c in all_monitored:
            code = c["course_code"].strip().upper()
            if code not in unique_map:
                unique_map[code] = c

        active_courses = []
        for code, c in unique_map.items():
            is_ge = classify_course(code).is_ge_lc
            is_watched = code in watchlisted_codes
            is_manual = (
                str(c.get("added_by", "")).startswith("Admin")
                or str(c.get("added_by", "")).startswith("User")
                or str(c.get("added_by", "")).startswith("Watch by")
                or str(c.get("added_by", "")).startswith("AutoWatch")
            )
            if (self.ge_lc_active and is_ge) or is_watched or is_manual:
                active_courses.append(c)

        # Strict 2-Tier Sorting: Watched college courses first (🔔), then GE/LC courses (🎯)
        def sort_key(c):
            cd = c["course_code"].strip().upper()
            if cd in watchlisted_codes:
                return (0, cd)
            elif classify_course(cd).is_ge_lc:
                return (1, cd)
            else:
                return (2, cd)

        active_courses.sort(key=sort_key)
        return active_courses

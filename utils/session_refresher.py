"""
ArcherSniper - Playwright Headless 24/7 Persistent Session Keeper (Tier 2 Auto-Recovery)
Silently runs a persistent headless Chromium context in the background on the Cloud VM (data/browser_profile).
Injects master session cookies, keeps the ArchersHub tab open 24/7, executes the website's keep-alive scripts,
and automatically extracts freshly rolled session cookies so the student can close their browser tabs.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

from config import BROWSER_PROFILE_DIR, DLSU_BASE_URL, DLSU_PORTAL_URL

logger = logging.getLogger("ArcherSniper.SessionKeeper")


class PlaywrightSessionRefresher:
    def __init__(
        self,
        target_url: str = DLSU_PORTAL_URL,
        profile_dir: Path | str = BROWSER_PROFILE_DIR,
        on_cookie_update: Callable[[dict[str, str]], Coroutine] | None = None,
    ):
        self.target_url = target_url
        self.profile_dir = Path(profile_dir)
        self.on_cookie_update = on_cookie_update
        self.is_running = False
        self.last_refreshed: datetime | None = None
        self.last_status: str = "IDLE"
        self.last_error: str | None = None
        self.live_page_title: str = "N/A"
        self.live_url: str = "N/A"
        self.extracted_cookie_count: int = 0

        self._playwright: Any = None
        self._browser_context: Any = None
        self._page: Any = None
        self._keepalive_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def get_status(self) -> dict[str, Any]:
        """Returns live telemetry dictionary of the headless browser keeper."""
        return {
            "is_running": self.is_running,
            "status": self.last_status,
            "target_url": self.target_url,
            "live_url": self.live_url,
            "page_title": self.live_page_title,
            "last_refreshed": self.last_refreshed.isoformat() if self.last_refreshed else None,
            "extracted_cookies": self.extracted_cookie_count,
            "last_error": self.last_error,
            "profile_dir": str(self.profile_dir),
        }

    async def inject_and_start_keeper(
        self,
        cookies: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> bool:
        """
        Injects session cookies into the Cloud VM's persistent Chromium profile,
        opens ArchersHub in the background, and starts the 24/7 keep-alive daemon.
        """
        if not cookies:
            logger.warning("🤖 [SessionKeeper] No cookies provided to inject.")
            return False

        async with self._lock:
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                msg = "Playwright is not installed. Run: pip install playwright && playwright install --with-deps chromium"
                logger.error(f"🤖 [SessionKeeper] {msg}")
                self.last_status = "ERROR_NO_PLAYWRIGHT"
                self.last_error = msg
                return False

            logger.info(f"🤖 [SessionKeeper] Starting 24/7 Persistent Headless Chromium at {self.target_url}...")
            self.last_status = "STARTING"
            self.last_error = None

            try:
                # Ensure profile directory exists on disk
                self.profile_dir.mkdir(parents=True, exist_ok=True)

                if self._playwright is None:
                    self._playwright = await async_playwright().start()

                # Launch persistent browser context (stores cookies & local storage on disk)
                if self._browser_context is None:
                    self._browser_context = await self._playwright.chromium.launch_persistent_context(
                        user_data_dir=str(self.profile_dir),
                        headless=True,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 800},
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-background-timer-throttling",
                            "--disable-backgrounding-occluded-windows",
                            "--disable-renderer-backgrounding",
                        ],
                    )

                # Format and inject cookies into browser context using URL target for proper domain matching
                playwright_cookies = []
                for k, v in cookies.items():
                    if not k or not v:
                        continue
                    playwright_cookies.append({
                        "name": str(k).strip(),
                        "value": str(v).strip(),
                        "url": "https://archershub.dlsu.edu.ph",
                        "path": "/",
                    })

                if playwright_cookies:
                    await self._browser_context.add_cookies(playwright_cookies)
                    logger.info(f"🤖 [SessionKeeper] Injected {len(playwright_cookies)} cookies into persistent browser context.")

                # Open or reuse page
                if not self._browser_context.pages:
                    self._page = await self._browser_context.new_page()
                else:
                    self._page = self._browser_context.pages[0]

                # Navigate to CourseFinder
                response = await self._page.goto(
                    self.target_url,
                    timeout=30000,
                    wait_until="domcontentloaded",
                )
                await asyncio.sleep(2.0)

                self.live_url = self._page.url
                try:
                    self.live_page_title = await self._page.title()
                except Exception:
                    self.live_page_title = "CourseFinder"

                logger.info(f"🤖 [SessionKeeper] Navigated to {self.live_url} ('{self.live_page_title}') | Status: {response.status if response else 200}")

                if "login" in self.live_url.lower() or "signin" in self.live_url.lower():
                    self.last_status = "NEEDS_REAUTH"
                    self.last_error = f"Redirected to login: {self.live_url}"
                    logger.warning(f"🤖 [SessionKeeper] Injected cookies were invalid or expired: {self.live_url}")
                    return False

                # Extract live cookies after initial load
                await self._harvest_and_sync_cookies()

                self.is_running = True
                self.last_status = "RUNNING_24_7"
                self.last_refreshed = datetime.now(timezone.utc)

                # Start background 5-minute keep-alive loop
                if self._keepalive_task is None or self._keepalive_task.done():
                    self._keepalive_task = asyncio.create_task(self._background_keepalive_loop())

                return True

            except Exception as e:
                logger.error(f"🤖 [SessionKeeper] Initialization error: {e}")
                self.last_status = "ERROR"
                self.last_error = str(e)
                return False

    async def _harvest_and_sync_cookies(self) -> dict[str, str]:
        """Harvests all live cookies from the headless Chromium context and syncs them."""
        if not self._browser_context:
            return {}

        try:
            # Guard against harvesting cookies while on a login page
            if self._page:
                url_lower = str(self._page.url).lower()
                if "login" in url_lower or "signin" in url_lower:
                    logger.warning(f"🤖 [SessionKeeper] Headless page is at login URL ({self._page.url}). Suppressing cookie harvest.")
                    self.last_status = "SESSION_EXPIRED_LOGIN_PAGE"
                    return {}

            raw_cookies = await self._browser_context.cookies()
            cookies_dict = {
                c["name"]: c["value"]
                for c in raw_cookies
                if c.get("name") and c.get("value")
            }
            self.extracted_cookie_count = len(cookies_dict)
            self.last_refreshed = datetime.now(timezone.utc)

            if cookies_dict and self.on_cookie_update:
                try:
                    await self.on_cookie_update(cookies_dict)
                except Exception as cb_err:
                    logger.debug(f"🤖 [SessionKeeper] on_cookie_update callback warning: {cb_err}")

            return cookies_dict
        except Exception as e:
            logger.debug(f"🤖 [SessionKeeper] Failed to extract cookies: {e}")
            return {}

    async def extract_live_cookies(self) -> dict[str, str] | None:
        """Explicitly reads current live cookies from the running browser context."""
        if not self._browser_context:
            return None
        return await self._harvest_and_sync_cookies()

    async def _background_keepalive_loop(self):
        """
        Lightweight background daemon that performs a full page reload every 5 minutes.
        Ensures ASP.NET IIS sliding expiration is continuously extended 24/7.
        """
        logger.info("🤖 [SessionKeeper] Background 5-minute keep-alive pulse daemon started.")
        while self.is_running:
            try:
                for _ in range(300):
                    if not self.is_running:
                        return
                    await asyncio.sleep(1.0)

                if not self.is_running or self._page is None:
                    break

                logger.info("🤖 [SessionKeeper] 5-minute keep-alive pulse: reloading CourseFinder page...")
                try:
                    response = await self._page.goto(self.target_url, wait_until="domcontentloaded", timeout=25000)
                    await asyncio.sleep(2.0)
                    self.live_url = self._page.url
                    try:
                        self.live_page_title = await self._page.title()
                    except Exception:
                        pass

                    if "login" in self.live_url.lower() or "signin" in self.live_url.lower():
                        self.last_status = "NEEDS_REAUTH"
                        logger.warning(f"🤖 [SessionKeeper] Keep-alive reload landed on login URL: {self.live_url}")
                    else:
                        self.last_status = "RUNNING_24_7"
                        await self._harvest_and_sync_cookies()

                except Exception as pulse_err:
                    logger.debug(f"🤖 [SessionKeeper] Keep-alive pulse error: {pulse_err}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"🤖 [SessionKeeper] Keep-alive pulse exception: {e}")
                await asyncio.sleep(30.0)

    async def refresh_session(self, timeout_seconds: float = 25.0) -> dict[str, str] | None:
        """
        One-shot refresh helper: navigates to CourseFinder and captures fresh session cookies.
        Maintains backward compatibility with test suites.
        """
        if self.is_running and self._browser_context:
            return await self._harvest_and_sync_cookies()

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright package is not installed.")
            return None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                try:
                    await page.goto(self.target_url, timeout=int(timeout_seconds * 1000), wait_until="domcontentloaded")
                    await asyncio.sleep(2.0)
                    raw_cookies = await context.cookies()
                    cookies_dict = {c["name"]: c["value"] for c in raw_cookies if c.get("name") and c.get("value")}
                    await browser.close()
                    return cookies_dict or None
                except Exception as e:
                    await browser.close()
                    logger.warning(f"One-shot refresh failed: {e}")
                    return None
        except Exception as e:
            logger.error(f"Playwright execution error: {e}")
            return None

    async def close(self):
        """Gracefully terminates the background browser context and daemon."""
        self.is_running = False
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            self._keepalive_task = None

        if self._browser_context:
            try:
                await self._browser_context.close()
            except Exception:
                pass
            self._browser_context = None
            self._page = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self.last_status = "STOPPED"
        logger.info("🤖 [SessionKeeper] Headless Chromium browser context closed.")


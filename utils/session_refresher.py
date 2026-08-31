"""
ArcherSniper - Playwright Headless Session Refresher (Tier 2 Auto-Recovery)
Silently launches headless Chromium to refresh and extract fresh ASP.NET session cookies from Archer's Hub.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("ArcherSniper.SessionRefresher")


class PlaywrightSessionRefresher:
    def __init__(self, target_url: str = "https://archershub.dlsu.edu.ph/CourseFinder/"):
        self.target_url = target_url
        self.is_running = False

    async def refresh_session(self, timeout_seconds: float = 25.0) -> dict[str, str] | None:
        """
        Launches headless Chromium, navigates to DLSU CourseFinder, and captures fresh session cookies.
        Returns a dictionary of cookie name -> value, or None if refresh fails / requires human interaction.
        """
        if self.is_running:
            logger.warning("Session refresher already running in another task.")
            return None

        self.is_running = True
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright package is not installed. Install with: pip install playwright && playwright install chromium")
            self.is_running = False
            return None

        logger.info(f"🤖 [Tier 2 Auto-Refresher] Starting headless Chromium to refresh session at {self.target_url}...")
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
                    response = await page.goto(self.target_url, timeout=int(timeout_seconds * 1000), wait_until="domcontentloaded")
                    logger.info(f"🤖 [Tier 2 Auto-Refresher] Page loaded with HTTP status {response.status if response else 'Unknown'}")

                    await asyncio.sleep(2.0)

                    raw_cookies = await context.cookies()
                    cookies_dict = {c["name"]: c["value"] for c in raw_cookies if c.get("name") and c.get("value")}

                    logger.info(f"🤖 [Tier 2 Auto-Refresher] Captured {len(cookies_dict)} cookies from browser session: {list(cookies_dict.keys())}")
                    await browser.close()

                    if cookies_dict:
                        return cookies_dict
                    else:
                        logger.warning("🤖 [Tier 2 Auto-Refresher] No cookies retrieved from CourseFinder page.")
                        return None

                except Exception as page_err:
                    logger.warning(f"🤖 [Tier 2 Auto-Refresher] Navigation or extraction failed: {page_err}")
                    await browser.close()
                    return None

        except Exception as e:
            logger.error(f"🤖 [Tier 2 Auto-Refresher] Playwright execution error: {e}")
            return None
        finally:
            self.is_running = False

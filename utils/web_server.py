"""
ArcherSniper - Lightweight Health Check & Bookmarklet Webhook Web Server
Provides HTTP endpoints:
- GET / and GET /health: Health checks for Render/Railway hosting
- POST /api/update_cookies: 1-Click Browser Bookmarklet Webhook (Tier 3)
- POST /api/update_curl: Webhook for raw cURL payload ingestion
"""

import json
import logging
from aiohttp import web
from utils.curl_parser import parse_curl, parse_cookie_string

logger = logging.getLogger("ArcherSniper.WebServer")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
}


class HealthWebServer:
    def __init__(self, bot, port: int = 8080):
        self.bot = bot
        self.port = port
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        
        # Tier 3 1-Click Bookmarklet Webhook endpoints
        self.app.router.add_options("/api/update_cookies", self.handle_options)
        self.app.router.add_post("/api/update_cookies", self.handle_update_cookies)
        self.app.router.add_options("/api/update_curl", self.handle_options)
        self.app.router.add_post("/api/update_curl", self.handle_update_curl)

    async def handle_options(self, request: web.Request) -> web.Response:
        """Handles CORS preflight requests from browser bookmarklets."""
        return web.Response(status=200, headers=CORS_HEADERS)

    async def handle_root(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "online",
            "bot": "ArcherSniper",
            "guilds": len(self.bot.guilds) if self.bot.is_ready() else 0,
            "ready": self.bot.is_ready(),
        }, headers=CORS_HEADERS)

    async def handle_health(self, request: web.Request) -> web.Response:
        engine = getattr(self.bot, "engine", None)
        health_data = engine.get_health_data() if engine else {}
        return web.json_response({
            "status": "healthy" if health_data.get("is_connected", False) else "degraded",
            "is_connected": health_data.get("is_connected", False),
            "monitored_courses": health_data.get("monitored_courses_count", 0),
            "active_watchers": health_data.get("active_watchers_count", 0),
            "total_cycles": health_data.get("total_poll_cycles", 0),
        }, headers=CORS_HEADERS)

    async def handle_update_cookies(self, request: web.Request) -> web.Response:
        """
        Receives document.cookie from 1-click browser bookmarklet,
        updates master_auth, and triggers instant engine reconnection.
        """
        try:
            body_text = await request.text()
            cookie_raw = ""
            if body_text.strip().startswith("{"):
                try:
                    payload = json.loads(body_text)
                    cookie_raw = payload.get("cookies", "") or payload.get("cookie", "")
                except Exception:
                    cookie_raw = body_text
            else:
                cookie_raw = body_text

            if not cookie_raw:
                return web.json_response({"status": "error", "message": "No cookies provided"}, status=400, headers=CORS_HEADERS)

            parsed_cookies = parse_cookie_string(cookie_raw)
            if not parsed_cookies:
                return web.json_response({"status": "error", "message": "Could not parse valid cookies"}, status=400, headers=CORS_HEADERS)

            db = getattr(self.bot, "db", None)
            engine = getattr(self.bot, "engine", None)

            if db:
                await db.save_master_auth(
                    cookies=parsed_cookies,
                    status="CONNECTED",
                )

            if engine:
                await engine.reconnect_with_new_auth(
                    new_cookies=parsed_cookies,
                    source_label="1-Click Bookmarklet Webhook",
                )

            logger.info(f"⚡ [Tier 3 Webhook] Ingested {len(parsed_cookies)} cookies via browser bookmarklet.")
            return web.json_response({
                "status": "ok",
                "message": f"Successfully updated {len(parsed_cookies)} session cookies! ArcherSniper is CONNECTED 🏹",
            }, headers=CORS_HEADERS)

        except Exception as e:
            logger.error(f"Error handling update_cookies webhook: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500, headers=CORS_HEADERS)

    async def handle_update_curl(self, request: web.Request) -> web.Response:
        """
        Receives raw cURL command, updates master_auth, and triggers engine reconnection.
        """
        try:
            body_text = await request.text()
            raw_curl = ""
            if body_text.strip().startswith("{"):
                try:
                    payload = json.loads(body_text)
                    raw_curl = payload.get("curl", "")
                except Exception:
                    raw_curl = body_text
            else:
                raw_curl = body_text

            parsed = parse_curl(raw_curl)
            if not parsed.is_valid:
                return web.json_response({"status": "error", "message": f"Invalid cURL: {parsed.error_message}"}, status=400, headers=CORS_HEADERS)

            db = getattr(self.bot, "db", None)
            engine = getattr(self.bot, "engine", None)

            if db:
                await db.save_master_auth(
                    cookies=parsed.cookies,
                    headers=parsed.headers,
                    raw_curl=raw_curl,
                    campus_no=parsed.campus_no,
                    academic_session=parsed.academic_session,
                    status="CONNECTED",
                )

            if engine:
                await engine.reconnect_with_new_auth(
                    new_cookies=parsed.cookies,
                    new_headers=parsed.headers,
                    source_label="HTTP Webhook cURL",
                )

            logger.info("⚡ [Webhook] Ingested raw cURL and reconnected engine.")
            return web.json_response({
                "status": "ok",
                "message": "cURL ingested successfully! ArcherSniper is CONNECTED 🏹",
            }, headers=CORS_HEADERS)

        except Exception as e:
            logger.error(f"Error handling update_curl webhook: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500, headers=CORS_HEADERS)

    async def start(self):
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, "0.0.0.0", self.port)
            await self.site.start()
            logger.info(f"Health & Webhook web server listening on http://0.0.0.0:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start health web server on port {self.port}: {e}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health web server stopped.")

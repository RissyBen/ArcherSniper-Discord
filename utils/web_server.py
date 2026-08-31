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
        self.app.router.add_get("/sync", self.handle_mobile_sync_ui)
        
        # Tier 3 1-Click Bookmarklet Webhook endpoints
        self.app.router.add_options("/api/update_cookies", self.handle_options)
        self.app.router.add_post("/api/update_cookies", self.handle_update_cookies)
        self.app.router.add_options("/api/update_curl", self.handle_options)
        self.app.router.add_post("/api/update_curl", self.handle_update_curl)

    async def handle_mobile_sync_ui(self, request: web.Request) -> web.Response:
        """Serves a sleek, mobile-optimized control page to update cookies or cURL from any phone."""
        engine = getattr(self.bot, "engine", None)
        is_conn = engine.is_connected if engine else False
        status_badge = "🟢 ONLINE & CONNECTED" if is_conn else "🔴 SESSION EXPIRED / DISCONNECTED"
        status_color = "#22c55e" if is_conn else "#ef4444"
        monitored_cnt = len(engine.monitored_cache) if engine and hasattr(engine, "monitored_cache") else 42
        cycles_cnt = engine.total_poll_cycles if engine else 0

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏹 ArcherSniper — Mobile Session Sync</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #0b0f19;
            color: #f1f5f9;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 16px;
        }}
        .card {{
            background: #151d30;
            border: 1px solid #1e293b;
            border-radius: 16px;
            max-width: 480px;
            width: 100%;
            padding: 24px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }}
        .header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
        }}
        .logo {{ font-size: 32px; }}
        .title {{ font-size: 20px; font-weight: 700; color: #38bdf8; }}
        .subtitle {{ font-size: 13px; color: #94a3b8; }}
        .badge {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
            background: rgba(34, 197, 94, 0.15);
            color: {status_color};
            border: 1px solid {status_color};
            margin-bottom: 16px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 20px;
        }}
        .stat-box {{
            background: #0f172a;
            border: 1px solid #334155;
            padding: 12px;
            border-radius: 10px;
            text-align: center;
        }}
        .stat-val {{ font-size: 18px; font-weight: bold; color: #38bdf8; }}
        .stat-lbl {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; margin-top: 4px; }}
        label {{ font-size: 13px; font-weight: 600; color: #cbd5e1; display: block; margin-bottom: 8px; }}
        textarea {{
            width: 100%;
            height: 120px;
            background: #090d16;
            border: 1px solid #334155;
            border-radius: 10px;
            color: #e2e8f0;
            padding: 12px;
            font-family: monospace;
            font-size: 12px;
            resize: vertical;
            outline: none;
        }}
        textarea:focus {{ border-color: #38bdf8; box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2); }}
        .btn {{
            width: 100%;
            background: #006837;
            color: #fff;
            border: none;
            padding: 14px;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            margin-top: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: all 0.2s;
        }}
        .btn:hover {{ background: #008744; }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .links {{
            margin-top: 20px;
            text-align: center;
            font-size: 13px;
        }}
        .links a {{ color: #38bdf8; text-decoration: none; font-weight: 600; }}
        .links a:hover {{ text-decoration: underline; }}
        #alert-msg {{
            margin-top: 14px;
            padding: 12px;
            border-radius: 8px;
            font-size: 13px;
            display: none;
        }}
        .alert-ok {{ background: rgba(34, 197, 94, 0.2); border: 1px solid #22c55e; color: #86efac; }}
        .alert-err {{ background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <div class="logo">🏹</div>
            <div>
                <div class="title">ArcherSniper Mobile Sync</div>
                <div class="subtitle">DLSU 24/7 Course Watchdog Control</div>
            </div>
        </div>

        <div class="badge">{status_badge}</div>

        <div class="stats">
            <div class="stat-box">
                <div class="stat-val">{monitored_cnt}</div>
                <div class="stat-lbl">Active Courses</div>
            </div>
            <div class="stat-box">
                <div class="stat-val">{cycles_cnt}</div>
                <div class="stat-lbl">Scrape Cycles</div>
            </div>
        </div>

        <label for="payload">📋 Paste cURL or Archer's Hub Cookies:</label>
        <textarea id="payload" placeholder="Paste your browser cURL (bash / cmd / PowerShell) or raw cookie string here..."></textarea>

        <button class="btn" id="sync-btn" onclick="submitAuth()">
            <span>⚡</span> Update Bot Session
        </button>

        <div id="alert-msg"></div>

        <div class="links">
            <a href="https://archershub.dlsu.edu.ph/CourseFinder/" target="_blank">🌐 Open Archer's Hub CourseFinder ➔</a>
        </div>
    </div>

    <script>
        async function submitAuth() {{
            const val = document.getElementById('payload').value.trim();
            const btn = document.getElementById('sync-btn');
            const alertBox = document.getElementById('alert-msg');

            if (!val) {{
                alertBox.className = 'alert-err';
                alertBox.textContent = '❌ Please paste your cURL or cookie string first.';
                alertBox.style.display = 'block';
                return;
            }}

            btn.disabled = true;
            btn.innerHTML = '<span>⏳</span> Syncing to Cloud Bot...';
            alertBox.style.display = 'none';

            try {{
                const isCurl = val.toLowerCase().includes('curl') || val.includes('archershub.dlsu.edu.ph');
                const endpoint = isCurl ? '/api/update_curl' : '/api/update_cookies';
                const body = isCurl ? JSON.stringify({{ curl: val }}) : JSON.stringify({{ cookies: val }});

                const res = await fetch(endpoint, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: body
                }});
                const data = await res.json();

                if (res.ok && data.status === 'ok') {{
                    alertBox.className = 'alert-ok';
                    alertBox.textContent = '✅ ' + (data.message || 'Session updated! ArcherSniper is CONNECTED 🏹');
                    document.getElementById('payload').value = '';
                    setTimeout(() => location.reload(), 2000);
                }} else {{
                    alertBox.className = 'alert-err';
                    alertBox.textContent = '❌ ' + (data.message || 'Failed to update session.');
                }}
            }} catch (err) {{
                alertBox.className = 'alert-err';
                alertBox.textContent = '❌ Connection error: ' + err.message;
            }} finally {{
                btn.disabled = false;
                btn.innerHTML = '<span>⚡</span> Update Bot Session';
                alertBox.style.display = 'block';
            }}
        }}
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html", headers=CORS_HEADERS)

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

"""
ArcherSniper - DLSU CourseFinder API Client
Handles direct asynchronous HTTP communication with archershub.dlsu.edu.ph,
session token management, keep-alive heartbeats, dynamic cookie roll-forward, and catalog sync.
"""

import asyncio
import json
import logging
import re
from typing import Callable, Coroutine, Any
import aiohttp

from config import (
    DLSU_BASE_URL,
    DLSU_CF_DATA_URL,
    DLSU_HEARTBEAT_URL,
    DLSU_COURSE_LIST_URL,
    DLSU_PORTAL_URL,
    DEFAULT_CAMPUS_NO,
    DEFAULT_ACADEMIC_SESSION,
)

logger = logging.getLogger("ArcherSniper.DLSU_API")


class DLSUApiClient:
    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        on_cookie_update: Callable[[dict[str, str]], Coroutine] | None = None,
    ):
        self.cookies: dict[str, str] = cookies or {}
        self.custom_headers: dict[str, str] = headers or {}
        self.on_cookie_update = on_cookie_update
        self.session: aiohttp.ClientSession | None = None
        self.timeout = aiohttp.ClientTimeout(total=15, connect=8)

    def _get_base_headers(self) -> dict[str, str]:
        """Returns standard DLSU CourseFinder Ajax headers with explicit cookies and tokens."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": DLSU_BASE_URL,
            "Referer": f"{DLSU_BASE_URL}/",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        # Merge custom headers (e.g. from raw cURL)
        if self.custom_headers:
            for k, v in self.custom_headers.items():
                if k.lower() not in ("cookie", "content-length", "host"):
                    headers[k] = v

        # Explicitly build Cookie header to guarantee delivery
        if self.cookies:
            cookie_parts = [f"{k}={v}" for k, v in self.cookies.items() if v]
            if cookie_parts:
                headers["Cookie"] = "; ".join(cookie_parts)

            # Set verification token header if present
            tok = (
                self.cookies.get("RequestVerificationToken")
                or self.cookies.get("__RequestVerificationToken")
            )
            if tok:
                headers["RequestVerificationToken"] = tok
                headers["__RequestVerificationToken"] = tok

        return headers

    async def get_session(self) -> aiohttp.ClientSession:
        """Returns or creates the active aiohttp session with current cookies."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
            )
        return self.session

    async def close(self):
        """Closes the underlying aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def update_auth(self, cookies: dict[str, str], headers: dict[str, str] | None = None):
        """Updates internal cookies and headers, resetting the active session."""
        if cookies:
            self.cookies.update(cookies)
        if headers:
            self.custom_headers.update(headers)

    async def _handle_response_cookies(self, response: aiohttp.ClientResponse):
        """Captures Set-Cookie headers and persists updated session cookies."""
        updated = False
        for cookie_name, morsel in response.cookies.items():
            val = morsel.value
            if val and self.cookies.get(cookie_name) != val:
                self.cookies[cookie_name] = val
                updated = True

        if updated and self.on_cookie_update:
            try:
                await self.on_cookie_update(self.cookies)
            except Exception as e:
                logger.error(f"Error in on_cookie_update callback: {e}")

    # ==========================================
    # CORE SCRAPER & API METHODS
    # ==========================================

    async def fetch_section_data(
        self,
        course_id: str,
        campus_no: int = DEFAULT_CAMPUS_NO,
        academic_session: int = DEFAULT_ACADEMIC_SESSION,
    ) -> list[dict]:
        """
        Fetches live section capacity and enrollment for a specific Course Creation ID.
        Endpoint: POST /CourseFinder/GetCFData/
        """
        cid_str = str(course_id).strip()
        if not cid_str.isdigit():
            logger.debug(f"Skipping GetCFData query for non-numeric course_id: '{cid_str}'")
            return []

        session = await self.get_session()
        payload = {
            "Campusno": str(campus_no),
            "AcademicSession": str(academic_session),
            "Courseid": cid_str,
        }

        headers = self._get_base_headers()

        async with session.post(DLSU_CF_DATA_URL, data=payload, headers=headers) as resp:
            await self._handle_response_cookies(resp)

            if resp.status == 401 or resp.status == 403:
                raise PermissionError(f"HTTP {resp.status} Unauthorized: Master session cookie is expired or invalid.")

            if resp.status != 200:
                text = await resp.text()
                raise ValueError(f"HTTP {resp.status} received from GetCFData: {text[:200]}")

            content_type = resp.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                text = await resp.text()
                if "<!DOCTYPE" in text or "<html" in text.lower():
                    raise PermissionError(f"Session expired or redirect returned instead of JSON: {text[:150]}")
                try:
                    data = json.loads(text)
                except Exception:
                    raise ValueError(f"Unexpected non-JSON response from GetCFData: {text[:200]}")
            else:
                data = await resp.json()

            sections: list[dict] = []
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    sec_name = str(item.get("SECTION_NAME", "")).strip()
                    cap_raw = str(item.get("CAPACITY", "0")).strip()
                    enl_raw = str(item.get("ENLISTED", "0")).strip()
                    teacher = str(item.get("MAIN_TEACHER", "")).strip()
                    schedule = str(item.get("SCHEDULE", "")).strip()

                    try:
                        capacity = int(cap_raw) if cap_raw.isdigit() else 0
                    except ValueError:
                        capacity = 0

                    try:
                        enlisted = int(enl_raw) if enl_raw.isdigit() else 0
                    except ValueError:
                        enlisted = 0

                    open_slots = max(0, capacity - enlisted)

                    sections.append({
                        "course_id": str(course_id).strip(),
                        "section_name": sec_name,
                        "capacity": capacity,
                        "enlisted": enlisted,
                        "open_slots": open_slots,
                        "teacher": teacher or "TBA",
                        "schedule": schedule or "TBA",
                    })

            return sections

    async def send_heartbeat(self, campus_no: int = DEFAULT_CAMPUS_NO) -> bool:
        """
        Sends keep-alive probe to maintain ASP.NET session and Azure Gateway Affinity.
        Endpoint: POST /CourseFinder/GetAllDropDownList/
        """
        session = await self.get_session()
        payload = {"Campusno": str(campus_no)}
        headers = self._get_base_headers()

        try:
            async with session.post(DLSU_HEARTBEAT_URL, data=payload, headers=headers) as resp:
                await self._handle_response_cookies(resp)
                if resp.status == 200:
                    logger.debug("DLSU Keep-Alive heartbeat successful.")
                    return True
                logger.warning(f"Heartbeat responded with HTTP {resp.status}")
                return False
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
            return False

    async def fetch_course_catalog(
        self,
        campus_no: int = DEFAULT_CAMPUS_NO,
        academic_session: int = DEFAULT_ACADEMIC_SESSION,
    ) -> list[dict]:
        """
        Fetches complete course list / catalog from CourseFinder.
        Supports /CourseFinder/GetCourseList/ with fallback to /CourseFinder/GetAllDropDownList/.
        """
        session = await self.get_session()
        payload = {
            "Campusno": str(campus_no),
            "AcademicSession": str(academic_session),
        }
        headers = self._get_base_headers()

        def parse_items(raw_data: Any) -> list[dict]:
            items = []
            if isinstance(raw_data, dict):
                # Search for nested list in common wrapper keys
                for k in ("CourseDrp", "coursedrp", "CourseList", "courselist", "data", "courses", "result", "Table", "d", "items"):
                    if k in raw_data and isinstance(raw_data[k], list):
                        raw_data = raw_data[k]
                        break

            if isinstance(raw_data, list):
                for item in raw_data:
                    if not isinstance(item, dict):
                        continue
                    lower_map = {k.lower().replace("_", ""): str(v).strip() for k, v in item.items() if v is not None}

                    # Extract ID (numeric course ID / Value / COURSE_CREATION_ID)
                    cid = (
                        lower_map.get("coursecreationid")
                        or lower_map.get("courseid")
                        or lower_map.get("id")
                        or lower_map.get("value")
                        or lower_map.get("val")
                        or ""
                    )

                    # Extract Code (e.g. STSWENG)
                    code = (
                        lower_map.get("coursecode")
                        or lower_map.get("course")
                        or lower_map.get("code")
                        or lower_map.get("subjectcode")
                        or ""
                    )

                    # Extract Title (e.g. SOFTWARE ENGINEERING)
                    title = (
                        lower_map.get("coursetitle")
                        or lower_map.get("title")
                        or lower_map.get("description")
                        or ""
                    )

                    # Check DLSU COURSE_NAME format (e.g. "STSWENG - ADVANCED SOFTWARE ENGINEERING")
                    raw_name = lower_map.get("coursename") or lower_map.get("text") or lower_map.get("textvalue") or ""
                    if raw_name:
                        if " - " in raw_name:
                            parts = raw_name.split(" - ", 1)
                            code = code or parts[0].strip().upper()
                            title = title or parts[1].strip()
                        elif " — " in raw_name:
                            parts = raw_name.split(" — ", 1)
                            code = code or parts[0].strip().upper()
                            title = title or parts[1].strip()
                        else:
                            if not code:
                                code = raw_name.strip().upper()
                            if not title:
                                title = raw_name.strip()

                    if cid and (code or title):
                        items.append({
                            "course_id": str(cid).strip(),
                            "course_code": (code or cid).strip().upper(),
                            "course_name": (title or code or cid).strip(),
                            "academic_session": academic_session,
                        })
            return items

        # Attempt 1: GetCourseList
        catalog: list[dict] = []
        try:
            async with session.post(DLSU_COURSE_LIST_URL, data=payload, headers=headers) as resp:
                await self._handle_response_cookies(resp)
                if resp.status == 200:
                    text = await resp.text()
                    try:
                        data = json.loads(text)
                        catalog = parse_items(data)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"GetCourseList request error: {e}")

        # Attempt 2: Fallback to GetAllDropDownList if catalog is still empty
        if not catalog:
            try:
                async with session.post(DLSU_HEARTBEAT_URL, data=payload, headers=headers) as resp:
                    await self._handle_response_cookies(resp)
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                            catalog = parse_items(data)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"GetAllDropDownList fallback error: {e}")

        return catalog

    async def probe_portal(self) -> bool:
        """
        Probes main CourseFinder portal page to refresh cookies/tokens and verify gateway connectivity.
        """
        session = await self.get_session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            async with session.get(DLSU_PORTAL_URL, headers=headers, allow_redirects=True) as resp:
                await self._handle_response_cookies(resp)
                if resp.status == 200:
                    text = await resp.text()
                    match = re.search(r'name=["\']__RequestVerificationToken["\']\s+type=["\']hidden["\']\s+value=["\']([^"\']+)["\']', text)
                    if match and "__RequestVerificationToken" not in self.cookies:
                        self.cookies["__RequestVerificationToken"] = match.group(1)
                        if self.on_cookie_update:
                            await self.on_cookie_update(self.cookies)
                    return True
                return False
        except Exception as e:
            logger.error(f"Probe portal failed: {e}")
            return False

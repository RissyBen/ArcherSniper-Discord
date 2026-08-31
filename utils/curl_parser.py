"""
ArcherSniper - cURL & Cookie Parser
Parses raw browser cURL strings, cookie headers, and form payloads copied from Chrome/Edge/Firefox DevTools.
Supports bash, Windows cmd (^ escaping), PowerShell, and raw cookie headers.
"""

import re
from dataclasses import dataclass, field


@dataclass
class ParsedAuthData:
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    form_data: dict[str, str] = field(default_factory=dict)
    campus_no: int | None = None
    academic_session: int | None = None
    course_id: str | None = None
    url: str | None = None
    raw_input: str = ""

    @property
    def is_valid(self) -> bool:
        """Checks if minimum essential cookies exist."""
        return len(self.cookies) > 0

    @property
    def key_tokens_present(self) -> dict[str, bool]:
        """Check presence of common DLSU CourseFinder tokens."""
        has_token = (
            "RequestVerificationToken" in self.cookies
            or "__RequestVerificationToken" in self.cookies
        )
        has_sid = (
            "Secure-SID" in self.cookies
            or "__Secure-SID" in self.cookies
        )
        has_affinity = "ApplicationGatewayAffinity" in self.cookies

        return {
            "RequestVerificationToken": has_token,
            "__RequestVerificationToken": has_token,
            "Secure-SID": has_sid,
            "__Secure-SID": has_sid,
            "ApplicationGatewayAffinity": has_affinity,
        }


def parse_cookie_string(cookie_str: str) -> dict[str, str]:
    """
    Parses a 'Cookie: key=val; key2=val2' or 'key=val; key2=val2' string into a dictionary.
    """
    cookies: dict[str, str] = {}
    if not cookie_str:
        return cookies

    cleaned = re.sub(r"^(cookie|Cookie):\s*", "", cookie_str.strip())
    # Remove caret escapes from Windows cmd
    cleaned = re.sub(r"\^+([\"'&$\^])", r"\1", cleaned)

    parts = cleaned.split(";")
    for part in parts:
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, val = part.partition("=")
        key = key.strip().strip("\"'")
        val = val.strip().strip("\"'")
        if key:
            cookies[key] = val

    _normalize_token_aliases(cookies)
    return cookies


def _normalize_token_aliases(cookies: dict[str, str]):
    """Ensure both prefixed and non-prefixed versions of ASP.NET tokens are present."""
    if "RequestVerificationToken" in cookies and "__RequestVerificationToken" not in cookies:
        cookies["__RequestVerificationToken"] = cookies["RequestVerificationToken"]
    if "__RequestVerificationToken" in cookies and "RequestVerificationToken" not in cookies:
        cookies["RequestVerificationToken"] = cookies["__RequestVerificationToken"]

    if "Secure-SID" in cookies and "__Secure-SID" not in cookies:
        cookies["__Secure-SID"] = cookies["Secure-SID"]
    if "__Secure-SID" in cookies and "Secure-SID" not in cookies:
        cookies["Secure-SID"] = cookies["__Secure-SID"]


def clean_raw_curl(raw_text: str) -> str:
    """Sanitizes line continuations and Windows cmd caret escapes."""
    # Line continuations
    text = re.sub(r"\^[\r\n]+", " ", raw_text)
    text = re.sub(r"\\(?:[\r\n]+)", " ", text)
    # Windows cmd caret escapes: ^", ^^", ^&, ^$, etc.
    text = re.sub(r"\^+([\"'&$\^])", r"\1", text)
    # Remove encoded URL carets if present (e.g. /GetCFData/%5E)
    text = text.replace("/%5E", "/")
    return text.strip()


def parse_curl(raw_text: str) -> ParsedAuthData:
    """
    Robustly parses raw cURL command from Chrome/Firefox/Edge DevTools or direct cookie strings.
    Handles Windows cmd, PowerShell, and bash formatted cURLs.
    """
    raw_text = raw_text.strip()
    result = ParsedAuthData(raw_input=raw_text)

    if not raw_text:
        return result

    # Check if raw input is just a plain cookie string without curl wrapper
    if not (raw_text.startswith("curl") or "curl " in raw_text or "http://" in raw_text or "https://" in raw_text):
        result.cookies = parse_cookie_string(raw_text)
        return result

    cleaned = clean_raw_curl(raw_text)

    # 1. URL extraction
    url_match = re.search(r'(?:--url\s+["\']?|https?://)(https?://[^\s"\']+)', cleaned)
    if url_match:
        result.url = url_match.group(1)
    else:
        direct_url = re.search(r'https?://[^\s"\']+', cleaned)
        if direct_url:
            result.url = direct_url.group(0)

    # 2. Extract cookies from -b or --cookie
    cookies: dict[str, str] = {}
    b_match = re.search(r'(?:-b|--cookie)\s+["\']?([^"\'\n]+(?:\s+[^"\'\n]+)*?)["\']?(?:\s+-[A-Za-z]|\s+--|$)', cleaned)
    if not b_match:
        b_match = re.search(r'(?:-b|--cookie)\s+["\']([^"\']+)["\']', cleaned)
    if b_match:
        cookie_raw = b_match.group(1).strip("\"' ")
        cookies.update(parse_cookie_string(cookie_raw))

    # 3. Extract headers and Cookie header from -H / --header
    headers: dict[str, str] = {}
    h_matches = re.findall(r'(?:-H|--header)\s+["\']([^"\']+)["\']', cleaned)
    for h in h_matches:
        if ":" in h:
            k, _, v = h.partition(":")
            k_clean = k.strip()
            v_clean = v.strip()
            headers[k_clean] = v_clean
            if k_clean.lower() == "cookie":
                cookies.update(parse_cookie_string(v_clean))

    # 4. Extract form data from --data-raw / --data / -d
    form_data: dict[str, str] = {}
    data_match = re.search(r'(?:--data-raw|--data|-d)\s+["\']?([^"\'\n]+)["\']?', cleaned)
    if data_match:
        raw_data = data_match.group(1).strip("\"' ")
        for part in raw_data.split("&"):
            if "=" in part:
                k, _, v = part.partition("=")
                k = k.strip().strip("\"'")
                v = v.strip().strip("\"'")
                form_data[k] = v
                if k.lower() == "campusno" and v.isdigit():
                    result.campus_no = int(v)
                elif k.lower() == "academicsession" and v.isdigit():
                    result.academic_session = int(v)
                elif k.lower() == "courseid":
                    result.course_id = v

    _normalize_token_aliases(cookies)
    result.cookies = cookies
    result.headers = headers
    result.form_data = form_data
    return result

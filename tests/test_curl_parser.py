"""
Unit Tests for cURL & Cookie Parser
"""

from utils.curl_parser import parse_curl, parse_cookie_string


def test_parse_cookie_string():
    raw = "__RequestVerificationToken=token123; __Secure-SID=sid456; ApplicationGatewayAffinity=affinity789"
    cookies = parse_cookie_string(raw)
    assert cookies["__RequestVerificationToken"] == "token123"
    assert cookies["__Secure-SID"] == "sid456"
    assert cookies["ApplicationGatewayAffinity"] == "affinity789"


def test_parse_cookie_string_with_prefix():
    raw = "Cookie: __RequestVerificationToken=token123; session=abc"
    cookies = parse_cookie_string(raw)
    assert cookies["__RequestVerificationToken"] == "token123"
    assert cookies["session"] == "abc"


def test_parse_full_browser_curl():
    curl_cmd = (
        "curl 'https://archershub.dlsu.edu.ph/CourseFinder/GetCFData/' "
        "-H 'User-Agent: Mozilla/5.0' "
        "-H 'Cookie: __RequestVerificationToken=abc; __Secure-SID=def; ApplicationGatewayAffinity=ghi' "
        "--data-raw 'Campusno=7&AcademicSession=155&Courseid=54321'"
    )
    parsed = parse_curl(curl_cmd)
    assert parsed.is_valid is True
    assert parsed.cookies.get("__RequestVerificationToken") == "abc"
    assert parsed.cookies.get("__Secure-SID") == "def"
    assert parsed.cookies.get("ApplicationGatewayAffinity") == "ghi"
    assert parsed.campus_no == 7
    assert parsed.academic_session == 155
    assert parsed.course_id == "54321"
    assert parsed.key_tokens_present["__RequestVerificationToken"] is True
    assert parsed.key_tokens_present["__Secure-SID"] is True
    assert parsed.key_tokens_present["ApplicationGatewayAffinity"] is True


def test_parse_windows_curl_with_carats():
    curl_cmd = (
        "curl.exe ^\n"
        "  -H \"Cookie: __RequestVerificationToken=tok1; __Secure-SID=sid1\" ^\n"
        "  --data-raw \"Campusno=7&AcademicSession=155&Courseid=123\" ^\n"
        "  https://archershub.dlsu.edu.ph/CourseFinder/GetCFData/"
    )
    parsed = parse_curl(curl_cmd)
    assert parsed.is_valid is True
    assert parsed.cookies.get("__RequestVerificationToken") == "tok1"
    assert parsed.cookies.get("__Secure-SID") == "sid1"
    assert parsed.campus_no == 7
    assert parsed.academic_session == 155
    assert parsed.course_id == "123"


def test_parse_empty_input():
    parsed = parse_curl("")
    assert parsed.is_valid is False
    assert len(parsed.cookies) == 0

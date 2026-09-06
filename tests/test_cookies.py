import pytest

from bid_radar.cookies import cookie_header_from_curl_file, CookieFileMissing, CookieNotFound, redact


def test_full_curl_command(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("curl 'https://www.bidnetdirect.com/x' \\n  -H 'accept: text/html' \\n  -H 'cookie: JSESSIONID=abc; other=def' \\n  -H 'user-agent: UA'\n", encoding="utf-8")
    assert cookie_header_from_curl_file(p) == "JSESSIONID=abc; other=def"


def test_dash_b_form(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("curl 'https://x' -b 'a=1; b=2'", encoding="utf-8")
    assert cookie_header_from_curl_file(p) == "a=1; b=2"


def test_bare_cookie_line(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("Cookie: a=1; b=2\n", encoding="utf-8")
    assert cookie_header_from_curl_file(p) == "a=1; b=2"


def test_missing_and_malformed(tmp_path):
    with pytest.raises(CookieFileMissing):
        cookie_header_from_curl_file(tmp_path / "nope.txt")
    p = tmp_path / "bad.txt"
    p.write_text("nothing useful here", encoding="utf-8")
    with pytest.raises(CookieNotFound):
        cookie_header_from_curl_file(p)


def test_redact_hides_cookie_values():
    assert redact("cookie: JSESSIONID=abc; x=y") == "cookie: [redacted]"
    assert redact("Set-Cookie: a=b") == "Set-Cookie: [redacted]"
    assert redact("plain text") == "plain text"


def test_redact_hides_api_keys_in_urls_and_errors():
    err = "429 Client Error for url: https://api.sam.gov/x?api_key=SAM-abc-123&postedFrom=09%2F04%2F2026&title=housing"
    out = redact(err)
    assert "SAM-abc-123" not in out
    assert "api_key=[redacted]&postedFrom=09%2F04%2F2026" in out
    assert redact("SAM_API_KEY=SAM-abc-123 was rejected") == "SAM_API_KEY=[redacted] was rejected"

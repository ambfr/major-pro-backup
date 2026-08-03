"""
Request Context Utils
Derives Language, Region, Device Type, and Time of Day from the incoming
HTTP request — no client SDK or extra API keys required.
"""

from datetime import datetime, timedelta
from fastapi import Request


# ── Device Type ────────────────────────────────────────────────

def parse_device_type(user_agent: str) -> str:
    """Lightweight UA sniffing — good enough without adding a dependency."""
    if not user_agent:
        return "unknown"
    ua = user_agent.lower()
    if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        return "tablet"
    if "mobile" in ua or "iphone" in ua or "android" in ua:
        return "mobile"
    if any(k in ua for k in ("windows", "macintosh", "linux", "x11")):
        return "desktop"
    return "unknown"


# ── Language ───────────────────────────────────────────────────

def parse_language(accept_language: str) -> str:
    """
    Parses the standard `Accept-Language` header, e.g.
    "en-US,en;q=0.9,hi;q=0.8" → "en"
    """
    if not accept_language:
        return "en"
    first = accept_language.split(",")[0].strip()
    lang = first.split("-")[0].split(";")[0].strip().lower()
    return lang or "en"


# ── Region ─────────────────────────────────────────────────────

def parse_region(request: Request) -> str:
    """
    Best-effort region detection without a paid GeoIP service:
    1. Reverse-proxy / CDN headers (Cloudflare, common LBs) if present.
    2. Locale region subtag from Accept-Language (e.g. "en-IN" → "IN").
    3. Fallback: "" (unknown) — frontend can also let the user set this
       manually via browser Geolocation API and send it as `X-Region`.
    """
    header_region = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-region")
        or request.headers.get("x-appengine-country")
    )
    if header_region and header_region != "XX":
        return header_region.upper()

    accept_language = request.headers.get("accept-language", "")
    first = accept_language.split(",")[0].strip()
    if "-" in first:
        region = first.split("-")[1].split(";")[0].strip()
        if len(region) == 2:
            return region.upper()

    return ""


# ── Time of Day ────────────────────────────────────────────────

def get_time_of_day(timezone_offset_min: int = 0) -> str:
    """
    Buckets the current local time (server UTC time + client's tz offset)
    into morning / afternoon / evening / night.

    timezone_offset_min: minutes to ADD to UTC to get local time
    (i.e. JS convention where you send -new Date().getTimezoneOffset()).
    """
    local_time = datetime.utcnow() + timedelta(minutes=timezone_offset_min)
    hour = local_time.hour

    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"  # 21:00–05:00


# ── Combined extractor ─────────────────────────────────────────

def extract_context(request: Request, timezone_offset_min: int = 0) -> dict:
    """Single call to get all four signals from one request."""
    return {
        "device_type": parse_device_type(request.headers.get("user-agent", "")),
        "language": parse_language(request.headers.get("accept-language", "")),
        "region": parse_region(request),
        "time_of_day": get_time_of_day(timezone_offset_min),
    }


async def capture_and_update_user_context(
    request: Request,
    current_user,
    db,
    timezone_offset_min: int = None,
):
    """
    Auto-detects context from the request and silently updates the user's
    row. Called once per feed/profile fetch — cheap, fire-and-forget style
    (errors here should never break the actual endpoint).
    """
    try:
        tz_offset = timezone_offset_min if timezone_offset_min is not None else (
            current_user.timezone_offset_min or 0
        )
        ctx = extract_context(request, tz_offset)

        current_user.device_type = ctx["device_type"]
        # Only auto-set language/region if user hasn't manually chosen one yet
        if not current_user.language or current_user.language == "en":
            current_user.language = ctx["language"]
        if not current_user.region:
            current_user.region = ctx["region"]
        if timezone_offset_min is not None:
            current_user.timezone_offset_min = timezone_offset_min

        current_user.last_time_of_day = ctx["time_of_day"]
        current_user.last_active_at = datetime.utcnow()

        await db.commit()
        return ctx
    except Exception:
        # Never let context capture break the feed/profile response
        return extract_context(request, current_user.timezone_offset_min or 0)
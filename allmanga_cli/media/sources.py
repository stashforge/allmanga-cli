"""Pure provider source-name, URL, and priority helpers."""

import re


CIPHER = {
    "79":"A","7a":"B","7b":"C","7c":"D","7d":"E","7e":"F","7f":"G","70":"H",
    "71":"I","72":"J","73":"K","74":"L","75":"M","76":"N","77":"O","68":"P",
    "69":"Q","6a":"R","6b":"S","6c":"T","6d":"U","6e":"V","6f":"W","60":"X",
    "61":"Y","62":"Z","59":"a","5a":"b","5b":"c","5c":"d","5d":"e","5e":"f",
    "5f":"g","50":"h","51":"i","52":"j","53":"k","54":"l","55":"m","56":"n",
    "57":"o","48":"p","49":"q","4a":"r","4b":"s","4c":"t","4d":"u","4e":"v",
    "4f":"w","40":"x","41":"y","42":"z","08":"0","09":"1","0a":"2","0b":"3",
    "0c":"4","0d":"5","0e":"6","0f":"7","00":"8","01":"9","15":"-","16":".",
    "67":"_","46":"~","02":":","17":"/","07":"?","1b":"#","63":"[","65":"]",
    "78":"@","19":"!","1c":"$","1e":"&","10":"(","11":")","12":"*","13":"+",
    "14":",","03":";","05":"=","1d":"%"
}


def _resolution_height(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def decrypt_url(hex_string):
    decoded = []
    for index in range(0, len(hex_string), 2):
        pair = hex_string[index:index + 2]
        decoded.append(CIPHER.get(pair, pair))
    return "".join(decoded).replace("/clock", "/clock.json")


def expand_wixmp(url):
    match = re.search(r"/,([^/]*),/mp4", url)
    if not match:
        return {"original": url}
    base = re.sub(
        r"\.urlset.*$",
        "",
        url.replace("repackager.wixmp.com/", ""),
    )
    resolutions = [
        resolution
        for resolution in match.group(1).split(",")
        if resolution
    ]
    resolutions.sort(key=_resolution_height, reverse=True)
    return {
        resolution: base.replace(match.group(0), f"/{resolution}/mp4")
        for resolution in resolutions
    }


def source_priority(source):
    if "priority" in source:
        return source["priority"]

    return 8


HOST_SOFT_TTL_TABLE = {
    "megaplay": 1800,      # 30m
    "faststream": 1800,    # 30m
    "anidbapp": 1800,      # 30m
    "animedao": 1200,      # 20m
    "gogo": 1800,          # 30m
    "allanime": 1200,      # 20m
    "mp4upload": 600,      # 10m
    "doodstream": 600,     # 10m
    "dood": 600,           # 10m
    "streamtape": 600,     # 10m
    "okru": 300,           # 5m
    "ok.ru": 300,          # 5m
    "default": 1800,       # 30m comfortable default
}

HOST_TTL_TABLE = HOST_SOFT_TTL_TABLE


def extract_hard_token_expiry(stream_url: str) -> float | None:
    """Extract explicit unix expiration timestamp from URL query params if present."""
    if not stream_url or ("?" not in stream_url and "&" not in stream_url):
        return None
    import urllib.parse
    try:
        parsed = urllib.parse.urlparse(stream_url)
        params = urllib.parse.parse_qs(parsed.query)
        for k in ("expires", "exp", "token_expiry", "validuntil"):
            if k in params and params[k]:
                val = int(params[k][0])
                if val > 1_600_000_000:
                    return float(val)
    except Exception:
        pass
    return None


def get_stream_soft_ttl(source_name: str = "", stream_url: str = "") -> int:
    """Determine the soft TTL in seconds for a given host."""
    combined = f"{source_name} {stream_url}".lower()
    for host_key, ttl in HOST_SOFT_TTL_TABLE.items():
        if host_key != "default" and host_key in combined:
            return ttl
    return HOST_SOFT_TTL_TABLE["default"]


def get_stream_ttl_seconds(source_name: str = "", stream_url: str = "") -> int:
    hard = extract_hard_token_expiry(stream_url)
    if hard is not None:
        import time
        rem = hard - time.time()
        return max(300, int(rem))
    return get_stream_soft_ttl(source_name, stream_url)


def calculate_stream_expiry(stream: dict, resolved_at: float | None = None) -> float:
    """Calculate the absolute timestamp when this stream expires."""
    import time
    base_time = resolved_at if resolved_at is not None else time.time()
    sname = str(stream.get("source_name") or stream.get("sourceName") or "")
    surl = str(stream.get("link") or stream.get("streamUrl") or stream.get("sourceUrl") or "")
    hard = extract_hard_token_expiry(surl)
    if hard is not None:
        return hard
    ttl = get_stream_soft_ttl(sname, surl)
    return base_time + ttl


def ping_stream_liveness(stream: dict, timeout: float = 1.5) -> bool:
    """
    Fast heuristic probe to verify if a stream URL is reachable.
    - 2xx: alive
    - 3xx: alive if redirect resolves
    - 4xx: dead
    - 5xx / timeout: transient (treated as alive / not destroyed)
    """
    if not isinstance(stream, dict):
        return False
    url = stream.get("link") or stream.get("streamUrl") or stream.get("sourceUrl")
    if not url:
        return False
    if url.startswith("file://") or url.startswith("/"):
        return True

    headers = dict(stream.get("headers") or stream.get("http_headers") or {})
    if "User-Agent" not in headers and "user-agent" not in headers:
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    referer = stream.get("referer") or headers.get("Referer") or headers.get("referer")
    if referer and "Referer" not in headers:
        headers["Referer"] = referer

    try:
        import requests
        r = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code in (200, 206):
            return True
        if r.status_code in (301, 302, 307, 308):
            return True
        if r.status_code == 405:
            r_get = requests.get(url, headers={**headers, "Range": "bytes=0-100"}, timeout=timeout, stream=True)
            if r_get.status_code in (200, 206, 301, 302, 307, 308):
                return True
            if 400 <= r_get.status_code < 500:
                return False
            return True
        if 400 <= r.status_code < 500:
            return False
        # 5xx or server hiccups: treat as transient
        return True
    except Exception:
        # Timeout or network glitch: transient, don't kill immediately
        return True


def check_stream_health_and_refresh(stream: dict, now: float | None = None) -> bool:
    """
    Evaluate stream health using the 3-tier precedence:
    1. Explicit CDN Token Expiry (expires_at):
       - If now >= expires_at: hard expired -> Return False (prune).
    2. Soft TTL Window (validated_at):
       - If now - validated_at < soft_ttl (30m): within fresh window -> Return True (keep).
    3. Stale Revalidation (now - validated_at >= soft_ttl):
       - Heuristic probe using exact stream headers.
       - If alive: update validated_at = now (+30m renewal, expires_at unchanged) -> Return True.
       - If confirmed dead (4xx): -> Return False (prune).
       - If transient (5xx / timeout): -> Return True (preserve stale mirror).
    """
    if not isinstance(stream, dict):
        return False
    import time
    current_time = now if now is not None else time.time()
    url = str(stream.get("link") or stream.get("streamUrl") or stream.get("sourceUrl") or "")
    if not url:
        return False
    if url.startswith("file://") or url.startswith("/"):
        return True

    # Stash structured timestamps
    if "created_at" not in stream:
        stream["created_at"] = stream.get("resolved_at") or current_time
    if "validated_at" not in stream:
        stream["validated_at"] = stream.get("resolved_at") or current_time

    # 1. Hard Token Expiry Check (Strict CDN Precedence)
    hard_expiry = stream.get("expires_at")
    if hard_expiry is None:
        hard_expiry = extract_hard_token_expiry(url)
        if hard_expiry is not None:
            stream["expires_at"] = hard_expiry

    if hard_expiry is not None and current_time >= float(hard_expiry):
        return False

    # 2. Soft TTL Window Check
    validated_at = float(stream.get("validated_at") or current_time)
    sname = str(stream.get("source_name") or stream.get("sourceName") or "")
    soft_ttl = get_stream_soft_ttl(sname, url)

    if (current_time - validated_at) < soft_ttl:
        return True

    # 3. Stale Revalidation Probe
    if ping_stream_liveness(stream, timeout=1.5):
        stream["validated_at"] = current_time
        return True

    return False


def is_stream_valid_fast(stream: dict, now: float | None = None) -> bool:
    """Instant in-memory validation check (strictly zero network I/O)."""
    if not isinstance(stream, dict):
        return False
    import time
    current_time = now if now is not None else time.time()
    url = str(stream.get("link") or stream.get("streamUrl") or stream.get("sourceUrl") or "")
    if not url:
        return False
    if url.startswith("file://") or url.startswith("/"):
        return True

    # Check explicit CDN hard expiry
    hard_expiry = stream.get("expires_at")
    if hard_expiry is None:
        hard_expiry = extract_hard_token_expiry(url)
        if hard_expiry is not None:
            stream["expires_at"] = hard_expiry

    if hard_expiry is not None and current_time >= float(hard_expiry):
        return False

    return True


def is_stream_valid(stream: dict, now: float | None = None) -> bool:
    return is_stream_valid_fast(stream, now)

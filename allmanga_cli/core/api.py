"""Bounded API decoding, cache scoping, and search error messages."""

import hashlib
import json
import socket
import urllib.error

from .terminal import sanitize_terminal_text


MAX_API_JSON_BYTES = 8 * 1024 * 1024


class SearchFailure(RuntimeError):
    pass


def read_limited_response(response, max_bytes=MAX_API_JSON_BYTES):
    try:
        max_bytes = max(1, int(max_bytes))
    except (TypeError, ValueError):
        raise ValueError("Invalid response size limit")
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ValueError("API response is too large")
        except ValueError as exc:
            if str(exc) == "API response is too large":
                raise
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("API response is too large")
    return data


def read_json_response(response, max_bytes=MAX_API_JSON_BYTES):
    return json.loads(read_limited_response(response, max_bytes))


def search_failure_message(source, exc):
    source = sanitize_terminal_text(source or "Search")
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403):
            return f"{source} authentication or access was rejected."
        if exc.code == 429:
            return f"{source} rate limit reached. Try again later."
        if 500 <= exc.code <= 599:
            return f"{source} service is temporarily unavailable."
        return f"{source} request failed (HTTP {exc.code})."
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return f"{source} request timed out."
    if isinstance(exc, urllib.error.URLError):
        return f"Could not connect to {source}."
    if isinstance(exc, (json.JSONDecodeError, KeyError, TypeError)):
        return f"{source} returned an invalid response."
    return f"{source} search failed."


def anilist_account_cache_key(token):
    token = str(token or "").strip()
    if not token:
        return "anonymous"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"token:{digest}"

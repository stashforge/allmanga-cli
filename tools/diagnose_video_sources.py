#!/usr/bin/env python3
import datetime
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
from allmanga_cli import app_core as _app_core
CLI = _app_core.__dict__
REPORT = ROOT / "video_source_diagnostics.md"

TESTS = [
    {
        "label": "Slime Season 4 EP 8",
        "show_id": "srGrP23qJnjsHrRYD",
        "episode": "8",
        "translation_type": "sub",
    },
    {
        "label": "ERASED EP 1",
        "show_id": "2DT65AtWa7RehsaHF",
        "episode": "1",
        "translation_type": "sub",
    },
]
TARGETS = {"Ok", "Uni", "Mp4", "Fm-Hls", "Ss-Hls", "Ak", "Yt-mp4", "Default"}
MAX_PREVIEW = 600


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def clean(value):
    return str(value or "").replace("\x00", "")


def request_headers(referer=""):
    headers = {"User-Agent": CLI["UA"], "Range": "bytes=0-0"}
    if referer:
        headers["Referer"] = referer
    return headers


def header_dict(headers):
    return {str(key): str(value) for key, value in headers.items()}


def probe(url, referer="", follow=True, timeout=10):
    result = {
        "url": url,
        "referer": referer,
        "request_headers": request_headers(referer),
        "follow_redirects": follow,
    }
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        result["error"] = "Not an HTTP(S) URL"
        return result
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CLI["SSL_CTX"]),
        *([] if follow else [NoRedirect()]),
    )
    req = urllib.request.Request(url, headers=request_headers(referer), method="GET")
    try:
        with opener.open(req, timeout=timeout) as response:
            body = response.read(MAX_PREVIEW)
            result.update({
                "status": response.status,
                "final_url": response.geturl(),
                "response_headers": header_dict(response.headers),
                "body_preview": body.decode("utf-8", errors="replace"),
                "looks_hls": (
                    ".m3u8" in response.geturl().lower()
                    or "mpegurl" in response.headers.get("Content-Type", "").lower()
                    or body.lstrip().startswith(b"#EXTM3U")
                ),
            })
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_PREVIEW)
        result.update({
            "status": exc.code,
            "final_url": exc.geturl(),
            "response_headers": header_dict(exc.headers),
            "body_preview": body.decode("utf-8", errors="replace"),
            "error": f"HTTPError: {exc}",
            "looks_hls": (
                ".m3u8" in clean(exc.geturl()).lower()
                or "mpegurl" in exc.headers.get("Content-Type", "").lower()
                or body.lstrip().startswith(b"#EXTM3U")
            ),
        })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def ytdlp_probe(url):
    command = ["yt-dlp", "-j", "--no-warnings", url]
    result = {"command": command}
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=25,
            check=False,
        )
        result["returncode"] = completed.returncode
        result["stderr"] = completed.stderr.decode("utf-8", errors="replace")[-4000:]
        result["stdout_bytes"] = len(completed.stdout)
        if completed.stdout:
            try:
                info = json.loads(completed.stdout)
                result["extractor"] = info.get("extractor")
                result["webpage_url"] = info.get("webpage_url")
                result["resolved_url"] = info.get("url")
                result["http_headers"] = info.get("http_headers")
                result["formats"] = [
                    {
                        "format_id": fmt.get("format_id"),
                        "url": fmt.get("url"),
                        "height": fmt.get("height"),
                        "ext": fmt.get("ext"),
                        "protocol": fmt.get("protocol"),
                        "http_headers": fmt.get("http_headers"),
                    }
                    for fmt in (info.get("formats") or [])
                ]
            except Exception as exc:
                result["json_error"] = f"{type(exc).__name__}: {exc}"
                result["stdout_preview"] = completed.stdout[:MAX_PREVIEW].decode(
                    "utf-8", errors="replace"
                )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def raw_episode_request(test):
    q_hash = "d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"
    variables = {
        "showId": test["show_id"],
        "translationType": test["translation_type"],
        "episodeString": test["episode"],
    }
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": q_hash}}
    url = (
        f"{CLI['API_BASE']}?variables={urllib.parse.quote(json.dumps(variables))}"
        f"&extensions={urllib.parse.quote(json.dumps(extensions))}"
    )
    headers = {
        **CLI["BASE_HDRS"],
        "Origin": "https://youtu-chan.com",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(
        req, context=CLI["SSL_CTX_SECURE"], timeout=15
    ) as response:
        raw_bytes = response.read()
        payload = json.loads(raw_bytes)
        response_meta = {
            "status": response.status,
            "final_url": response.geturl(),
            "headers": header_dict(response.headers),
            "body": payload,
        }
    encrypted = payload.get("data", {}).get("tobeparsed")
    decoded_text = CLI["decrypt_tobeparsed"](encrypted) if encrypted else None
    decoded = json.loads(decoded_text) if decoded_text else None
    return {
        "request_url": url,
        "request_headers": headers,
        "variables": variables,
        "extensions": extensions,
        "response": response_meta,
        "encrypted_tobeparsed": encrypted,
        "decoded_text": decoded_text,
        "decoded": decoded,
    }


def clock_diagnostic(source_url):
    decoded_path = CLI["decrypt_url"](source_url[2:])
    clock_url = f"https://{CLI['CLOCK_BASE']}{decoded_path}"
    req = urllib.request.Request(clock_url, headers=CLI["BASE_HDRS"], method="GET")
    result = {"decoded_path": decoded_path, "clock_url": clock_url}
    try:
        with urllib.request.urlopen(
            req, context=CLI["SSL_CTX_SECURE"], timeout=15
        ) as response:
            body = response.read()
            result.update({
                "status": response.status,
                "final_url": response.geturl(),
                "response_headers": header_dict(response.headers),
                "body": json.loads(body),
            })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def expiry_fields(url):
    parsed = urllib.parse.urlsplit(str(url or ""))
    values = urllib.parse.parse_qs(parsed.query)
    interesting = {}
    for key, value in values.items():
        if re.search(r"exp|expire|token|sig|auth|hash|policy|key", key, re.I):
            interesting[key] = value
    return interesting


def source_diagnostic(source):
    name = source.get("sourceName")
    url = source.get("sourceUrl")
    result = {
        "source_name": name,
        "raw_source_url": url,
        "raw_expiry_or_token_fields": expiry_fields(url),
    }
    if str(url).startswith("--"):
        clock = clock_diagnostic(url)
        result["decode_route"] = "Per-source substitution cipher -> Clock JSON"
        result["clock"] = clock
        links = (clock.get("body") or {}).get("links", [])
        result["clock_link_probes"] = []
        for item in links:
            link = item.get("link")
            probes = []
            for referer in (
                "",
                CLI["REFERER"],
                "https://gogoanime.tel/",
                "https://anitaku.pe/",
                "https://yugenanime.tv/",
            ):
                probes.append(probe(link, referer=referer, follow=True))
            result["clock_link_probes"].append({
                "item": item,
                "expiry_or_token_fields": expiry_fields(link),
                "probes": probes,
            })
    else:
        result["decode_route"] = "No per-source decryption; URL is passed directly"
        result["http_no_redirect"] = probe(url, follow=False)
        result["http_follow_redirect"] = probe(url, follow=True)
        result["yt_dlp"] = ytdlp_probe(url)
    return result


def json_block(value):
    return "```json\n" + json.dumps(value, indent=2, ensure_ascii=False) + "\n```\n"


def build_report():
    collected = []
    for test in TESTS:
        request = raw_episode_request(test)
        sources = (
            (request.get("decoded") or {})
            .get("episode", {})
            .get("sourceUrls", [])
        )
        diagnostics = [
            source_diagnostic(source)
            for source in sources
            if source.get("sourceName") in TARGETS
        ]
        collected.append({
            "test": test,
            "request": request,
            "sources": sources,
            "diagnostics": diagnostics,
        })

    lines = [
        "# AllAnime Video Source Diagnostics",
        "",
        f"Generated: {datetime.datetime.now().astimezone().isoformat()}",
        "",
        "> Sensitive: this file contains exact temporary/signed source URLs and tokens.",
        "",
        "## Executive Notes",
        "",
        "- The persisted GraphQL response contains one encrypted `tobeparsed` blob.",
        "- AES-256-CTR decrypts that blob once, producing the complete episode object and all `sourceUrls`.",
        "- Individual source URLs are not all AES-decrypted. Only values beginning with `--` use the separate substitution cipher and Clock endpoint.",
        "- Direct CDN sources are probed by the CLI with User-Agent, Range, and sometimes Referer.",
        "- Generic embed sources are handed to yt-dlp without CLI-supplied Referer/Origin headers.",
        "- mpv accepts both HLS and MP4; extracted external streams are loaded by URL with yt-dlp-provided HTTP headers when available.",
        "",
        "## Decryption Implementation",
        "",
        "### Outer `tobeparsed` envelope",
        "",
        "- Algorithm: AES-256-CTR through OpenSSL.",
        "- Key input: SHA-256 hex digest of ASCII `Xot36i3lK3:v1`.",
        f"- Derived key hex: `{__import__('hashlib').sha256(b'Xot36i3lK3:v1').hexdigest()}`",
        "- IV: bytes 1..12 of the base64-decoded envelope, hex-encoded, followed by `00000002`.",
        "- Ciphertext: decoded bytes 13 through 16 bytes before the end.",
        "- This decrypts the whole episode payload, therefore all server entries are inside the same decrypted object.",
        "",
        "### Per-source `--...` decoding",
        "",
        "- Algorithm: two-hex-character substitution using the CLI `CIPHER` table.",
        "- Applied only when a decoded `sourceUrl` begins with `--`.",
        "- The decoded `/clock` path is changed to `/clock.json` and fetched from `https://allanime.day`.",
        "",
        "## Current Header Behavior",
        "",
        json_block({
            "GraphQL/API": {
                **CLI["BASE_HDRS"],
                "Origin override for episode request": "https://youtu-chan.com",
            },
            "Yt-mp4/direct probe": {
                "User-Agent": CLI["UA"],
                "Range": "bytes=0-0",
                "Referer": CLI["REFERER"] + " unless wixstatic",
            },
            "Clock link probes": {
                "User-Agent": CLI["UA"],
                "Range": "bytes=0-0",
                "Referer attempts": [
                    "",
                    CLI["REFERER"],
                    "https://gogoanime.tel/",
                    "https://anitaku.pe/",
                    "https://yugenanime.tv/",
                ],
            },
            "Generic Ok/Uni/Mp4/Fm-Hls/Ss-Hls/Ak embed extraction": {
                "CLI command": ["yt-dlp", "-j", "--no-warnings", "<sourceUrl>"],
                "Explicit CLI Referer": None,
                "Explicit CLI Origin": None,
                "Explicit CLI User-Agent": None,
                "Note": "yt-dlp chooses its own request headers; extracted http_headers are later passed to mpv.",
            },
        }),
    ]

    for item in collected:
        test = item["test"]
        request = item["request"]
        lines += [
            f"## Test Episode: {test['label']}",
            "",
            "### Exact persisted GraphQL request",
            "",
            json_block({
                "URL": request["request_url"],
                "headers": request["request_headers"],
                "variables": request["variables"],
                "extensions": request["extensions"],
            }),
            "### Exact raw GraphQL response",
            "",
            json_block(request["response"]),
            "### Encrypted `tobeparsed`",
            "",
            "```text\n" + clean(request["encrypted_tobeparsed"]) + "\n```\n",
            "### Decrypted episode JSON / raw sourceUrls",
            "",
            json_block(request["decoded"]),
        ]
        for diagnostic in item["diagnostics"]:
            lines += [
                f"### Server: {diagnostic['source_name']}",
                "",
                json_block(diagnostic),
            ]

    ok_cases = []
    for item in collected:
        for diagnostic in item["diagnostics"]:
            if diagnostic["source_name"] == "Ok":
                ok_cases.append({
                    "episode": item["test"]["label"],
                    "raw_url": diagnostic["raw_source_url"],
                    "expiry_or_token_fields": diagnostic["raw_expiry_or_token_fields"],
                    "http_no_redirect": diagnostic.get("http_no_redirect"),
                    "http_follow_redirect": diagnostic.get("http_follow_redirect"),
                    "yt_dlp": diagnostic.get("yt_dlp"),
                })
    lines += [
        "## Ok Working vs Failing Comparison",
        "",
        json_block(ok_cases),
        "## HLS Handling Conclusion",
        "",
        "- URL, response Content-Type, response preview, and yt-dlp protocol fields above identify whether Fm-Hls/Ss-Hls resolve to HLS.",
        "- The CLI labels Clock links containing `.m3u8` as `hls`.",
        "- Generic embeds depend on yt-dlp to expose a playable URL and protocol.",
        "- Desktop mpv supports `.m3u8` natively. Android direct-safe mode is false for HLS/external streams, so header-dependent streams use the local proxy when headers are present.",
        "",
        "## No Changes Made",
        "",
        "This was a read-only diagnostic run. `allmanga-cli`, config, history, preferences, and caches were not modified by this script.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return collected


if __name__ == "__main__":
    data = build_report()
    print(REPORT)
    for item in data:
        names = [source.get("sourceName") for source in item["sources"]]
        print(f"{item['test']['label']}: {names}")

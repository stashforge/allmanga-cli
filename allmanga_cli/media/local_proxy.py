"""Private localhost proxy and generated-content server lifecycle."""

import http.server
import re
import threading
import urllib.parse
import urllib.request
import uuid

from ..services.http import SSL_CTX_SECURE
from .proxy_rules import (
    new_proxy_secret_path,
    proxy_filtered_headers,
    proxy_method_allowed,
    proxy_path_authorized,
    proxy_range_header,
    proxy_response_headers,
)
from .urls import validate_http_url


try:
    from curl_cffi import requests as cffi_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    cffi_requests = None
    CURL_CFFI_AVAILABLE = False


_active_lock = threading.Lock()
_active_server = None
_debug_warn = lambda context, error: None

# Fallback UA used only when the caller hasn't supplied one. Some CDNs
# validate the User-Agent shape (not just presence) against parameters
# baked into signed URLs, so a bare "Mozilla/5.0" can get rejected where a
# realistic browser UA passes.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def configure_debug_reporter(reporter):
    global _debug_warn
    _debug_warn = reporter


class _ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


def _is_playlist(url, content_type):
    return ".m3u8" in url.lower() or "mpegurl" in str(content_type or "").lower()


def _ass_to_vtt(text: str, mpegts_pts: int = 133508) -> str:
    lines = text.splitlines()
    vtt_cues = ["WEBVTT"]
    if mpegts_pts is not None:
        vtt_cues.append(f"X-TIMESTAMP-MAP=MPEGTS:{mpegts_pts},LOCAL:00:00:00.000")
    vtt_cues.append("")

    def parse_time(t_str: str) -> str:
        parts = t_str.strip().split(":")
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s_parts = parts[2].split(".")
            s = int(s_parts[0])
            cs = s_parts[1] if len(s_parts) > 1 else "00"
            if len(cs) == 1:
                ms = int(cs) * 100
            elif len(cs) == 2:
                ms = int(cs) * 10
            else:
                ms = int(cs[:3])
            return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
        return t_str

    in_events = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if stripped.startswith("[Events]"):
            in_events = True
            continue
        if stripped.startswith("[") and in_events:
            in_events = False
            continue
        if in_events and stripped.startswith("Dialogue:"):
            parts = stripped[len("Dialogue:"):].split(",", 9)
            if len(parts) >= 10:
                start_raw = parts[1]
                end_raw = parts[2]
                raw_cue = parts[9]
                is_top = any(tag in raw_cue for tag in (r"{\an8}", r"{\an7}", r"{\an9}"))
                cue_text = re.sub(r"\{[^\}]*\}", "", raw_cue)
                cue_text = cue_text.replace(r"\N", "\n").replace(r"\n", "\n").strip()
                if not cue_text:
                    continue
                start_vtt = parse_time(start_raw)
                end_vtt = parse_time(end_raw)
                line_setting = "line:10%,start" if is_top else "line:92%,end"
                vtt_cues.append(f"{start_vtt} --> {end_vtt} {line_setting}")
                vtt_cues.append(cue_text)
                vtt_cues.append("")

    return "\n".join(vtt_cues)


def _add_vtt_padding(vtt_text: str) -> str:
    """Ensure timing cues without positioning get line:92%,end for clean Android margins."""
    def _repl(match):
        timing = match.group(0).strip()
        if "line:" not in timing:
            return f"{timing} line:92%,end"
        return timing

    return re.sub(
        r"(\d{1,2}:\d{2}:\d{2}[\.,]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[\.,]\d{3}[^\r\n]*)",
        _repl,
        vtt_text,
    )


def _ensure_vtt(data_bytes: bytes) -> bytes:
    if not data_bytes:
        return b"WEBVTT\n\n"
    if data_bytes.startswith(b"\x1f\x8b"):
        try:
            import gzip
            data_bytes = gzip.decompress(data_bytes)
        except Exception:
            pass
    text = data_bytes.decode("utf-8", errors="replace").strip()
    if "[Events]" in text or "[Script Info]" in text:
        return _ass_to_vtt(text).encode("utf-8")
    if text.startswith("WEBVTT"):
        return _add_vtt_padding(text).encode("utf-8")
    # If it's an SRT subtitle or text cues, convert commas to dots and prepend WEBWTT
    text = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text)
    text = _add_vtt_padding(text)
    return f"WEBVTT\n\n{text}\n".encode("utf-8")


def _prepare_subtitle_entries(subtitles):
    """Normalize, deduplicate, and prepare subtitle entries.
    If a language has both .m3u8 and .srt/.vtt, prefer .m3u8.
    """
    lang_codes = {
        "en": "en", "eng": "en", "english": "en",
        "es": "es", "spa": "es", "spanish": "es", "español": "es", "espanol": "es",
        "pt": "pt", "por": "pt", "portuguese": "pt", "português": "pt", "portugues": "pt",
        "fr": "fr", "fre": "fr", "fra": "fr", "french": "fr", "français": "fr", "francais": "fr",
        "de": "de", "ger": "de", "deu": "de", "german": "de", "deutsch": "de",
        "it": "it", "ita": "it", "italian": "it", "italiano": "it",
        "ru": "ru", "rus": "ru", "russian": "ru",
        "ar": "ar", "ara": "ar", "arabic": "ar",
        "tr": "tr", "tur": "tr", "turkish": "tr", "türkçe": "tr", "turkce": "tr",
        "pl": "pl", "pol": "pl", "polish": "pl", "polski": "pl",
        "id": "id", "ind": "id", "indonesian": "id", "indonesia": "id", "bahasa": "id",
        "vi": "vi", "vie": "vi", "vietnamese": "vi",
        "th": "th", "tha": "th", "thai": "th",
        "zh": "zh", "chi": "zh", "zho": "zh", "chinese": "zh",
        "ja": "ja", "jpn": "ja", "japanese": "ja",
        "ko": "ko", "kor": "ko", "korean": "ko",
    }
    deduped = {}
    for s in (subtitles or []):
        url = s.get("url") or s.get("file") if isinstance(s, dict) else s[3] if isinstance(s, (list, tuple)) and len(s) > 3 else None
        if not url:
            continue
        label = s.get("label", "Sub") if isinstance(s, dict) else s[0] if isinstance(s, (list, tuple)) else "Sub"
        def_flag = s.get("default", False) if isinstance(s, dict) else s[2] if isinstance(s, (list, tuple)) and len(s) > 2 else False
        clean_label = str(label).split("(")[0].strip() or "English"
        norm_key = re.sub(r"[^a-zA-Z0-9]", "", clean_label.lower())
        is_m3u8 = ".m3u8" in url.lower()
        if norm_key not in deduped or (is_m3u8 and not deduped[norm_key]["is_m3u8"]):
            clean_lower = clean_label.lower()
            lang_code = "en" if ("eng" in clean_lower or "en" in clean_lower) else "und"
            for k, code in lang_codes.items():
                if k in clean_lower:
                    lang_code = code
                    break
            deduped[norm_key] = {
                "url": url,
                "label": clean_label,
                "lang": lang_code,
                "default": def_flag,
                "is_m3u8": is_m3u8,
            }

    if deduped and not any(d["default"] for d in deduped.values()):
        eng_key = next((k for k, v in deduped.items() if v["lang"] == "en"), None)
        if eng_key:
            deduped[eng_key]["default"] = True
        else:
            first_key = next(iter(deduped))
            deduped[first_key]["default"] = True

    return list(deduped.values())


def _guess_ext(url):
    path = urllib.parse.urlsplit(url).path
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if ext in ("m3u8", "vtt", "mp4", "m4s", "aac", "mp3", "ts"):
            return ext
    return "m3u8" if ".m3u8" in url.lower() else "vtt" if ".vtt" in url.lower() else "ts"


def _build_proxy_server(initial_entries, timeout):
    """Spin up one local proxy server backing an arbitrary set of routes.

    initial_entries: {path: entry_dict}, where entry_dict is either
      {"kind": "fetch", "url": ..., "ref": ..., "hdrs": {...}}
      {"kind": "synthetic", "text": "...m3u8 content..."}

    Returns (port, registry, register_fn, server). register_fn lets the
    handler add newly-discovered child routes (segments, sub-playlists,
    keys) on the fly while rewriting a playlist it just fetched.
    """
    registry = dict(initial_entries)
    registry_lock = threading.Lock()
    port_holder = {}

    def register(url, ref, hdrs, content_type=None):
        ext = _guess_ext(url)
        path = new_proxy_secret_path(ext)
        entry_content_type = content_type
        if not entry_content_type:
            if ext == "m3u8":
                entry_content_type = "application/vnd.apple.mpegurl"
            elif ext == "vtt":
                entry_content_type = "text/vtt; charset=utf-8"
            elif ext == "ts":
                entry_content_type = "video/MP2T"
            elif ext in ("m4s", "mp4"):
                entry_content_type = "video/mp4"
            elif ext in ("aac", "m4a", "mp3"):
                entry_content_type = "audio/mp4"
        with registry_lock:
            registry[path] = {
                "kind": "fetch",
                "url": url,
                "ref": ref,
                "hdrs": dict(hdrs),
                "content_type": entry_content_type,
            }
        return path

    def local_url_for(path):
        return f"http://127.0.0.1:{port_holder['port']}{path}"

    def rewrite_playlist(text, base_url, ref, hdrs):
        base = base_url.rsplit("/", 1)[0] + "/"
        out = []
        for line in text.splitlines():
            line = line.strip()

            if line.startswith("#EXT-X-STREAM-INF:"):
                # Clean deprecated tags like PROGRAM-ID
                line = re.sub(r"PROGRAM-ID=\d+,?", "", line)
                line = re.sub(r",+", ",", line).replace(":,", ":").rstrip(",")
                out.append(line)
                continue

            if line.startswith("#") and 'URI="' in line:
                start = line.index('URI="') + 5
                end = line.index('"', start)
                target = line[start:end]
                real = urllib.parse.urljoin(base, target)
                path = register(real, ref, hdrs)
                line = line[:start] + local_url_for(path) + line[end:]
                out.append(line)
                continue

            if line.startswith("#") or not line:
                out.append(line)
                continue

            real = urllib.parse.urljoin(base, line)
            path = register(real, ref, hdrs)
            out.append(local_url_for(path))

        return "\n".join(out)


    class ProxyHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _reject_method(self):
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _proxy(self, method):
            if not proxy_method_allowed(method):
                self._reject_method()
                return

            path = urllib.parse.urlsplit(self.path).path
            with registry_lock:
                entry = registry.get(path)
            if entry is None:
                try:
                    self.send_error(404)
                except Exception:
                    pass
                return

            if entry["kind"] == "synthetic":
                data = entry["text"].encode("utf-8")
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", entry.get("content_type", "application/vnd.apple.mpegurl"))
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Access-Control-Allow-Headers", "*")
                    self.send_header("Cache-Control", "no-store, no-cache")
                    self.end_headers()
                    if method == "GET":
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            url, ref, hdrs = entry["url"], entry["ref"], entry["hdrs"]
            range_header = proxy_range_header(self.headers.get("Range", ""))
            is_m3u8_fetch = _is_playlist(url, entry.get("content_type", ""))

            # Try upstream fetch via urllib first (primary, standard, transparent)
            try:
                request = urllib.request.Request(url, method=method)
                request.add_header("User-Agent", hdrs.get("User-Agent", _DEFAULT_UA))
                if ref:
                    request.add_header("Referer", ref)
                for key, value in hdrs.items():
                    if key.casefold() == "user-agent":
                        continue
                    request.add_header(key, value)
                if range_header and not is_m3u8_fetch:
                    request.add_header("Range", range_header)

                with urllib.request.urlopen(
                        request,
                        context=SSL_CTX_SECURE,
                        timeout=max(1, float(timeout))) as response:
                    validate_http_url(response.geturl())
                    content_type = entry.get("content_type") or response.headers.get("Content-Type", "")

                    if method == "GET" and _is_playlist(url, content_type):
                        body = response.read()
                        text = body.decode("utf-8", errors="replace")
                        rewritten = rewrite_playlist(text, url, ref, hdrs)
                        data = rewritten.encode("utf-8")
                        try:
                            self.send_response(200)
                            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                            self.send_header("Content-Length", str(len(data)))
                            self.send_header("Access-Control-Allow-Origin", "*")
                            self.send_header("Access-Control-Allow-Headers", "*")
                            self.send_header("Cache-Control", "no-store, no-cache")
                            self.end_headers()
                            self.wfile.write(data)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return

                    is_vtt = (
                        "vtt" in str(entry.get("content_type") or "").lower()
                        or "vtt" in str(content_type or "").lower()
                        or url.lower().endswith(".vtt")
                        or url.lower().endswith(".srt")
                    )
                    if method == "GET" and is_vtt:
                        raw_data = response.read()
                        vtt_data = _ensure_vtt(raw_data)
                        try:
                            self.send_response(200)
                            self.send_header("Content-Type", "text/vtt; charset=utf-8")
                            self.send_header("Content-Length", str(len(vtt_data)))
                            self.send_header("Access-Control-Allow-Origin", "*")
                            self.send_header("Access-Control-Allow-Headers", "*")
                            self.send_header("Cache-Control", "no-store, no-cache")
                            self.end_headers()
                            self.wfile.write(vtt_data)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return

                    try:
                        self.send_response(response.status)
                        content_type_sent = False
                        has_accept_ranges = False
                        for key, value in proxy_response_headers(response.headers):
                            k_low = key.lower()
                            if k_low == "accept-ranges":
                                has_accept_ranges = True
                            if k_low == "content-type":
                                if entry.get("content_type"):
                                    value = entry["content_type"]
                                elif not value.startswith("video/") and not value.startswith("audio/"):
                                    value = "video/MP2T"
                                content_type_sent = True
                            self.send_header(key, value)
                        if not content_type_sent and entry.get("content_type"):
                            self.send_header("Content-Type", entry["content_type"])
                        if not has_accept_ranges and response.status == 200:
                            self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.send_header("Access-Control-Allow-Headers", "*")
                        self.end_headers()
                        if method == "GET":
                            while chunk := response.read(65536):
                                try:
                                    self.wfile.write(chunk)
                                except (BrokenPipeError, ConnectionResetError):
                                    break
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
            except (BrokenPipeError, ConnectionResetError):
                return
            except urllib.error.HTTPError as http_err:
                # Upstream returned 403; fallback to curl_cffi if available (Cloudflare bypass)
                if http_err.code == 403 and CURL_CFFI_AVAILABLE and cffi_requests is not None:
                    try:
                        cffi_hdrs = dict(hdrs) if hdrs else {}
                        if "User-Agent" not in cffi_hdrs and "user-agent" not in cffi_hdrs:
                            cffi_hdrs["User-Agent"] = _DEFAULT_UA
                        if ref and "Referer" not in cffi_hdrs and "referer" not in cffi_hdrs:
                            cffi_hdrs["Referer"] = ref
                        if range_header and not is_m3u8_fetch:
                            cffi_hdrs["Range"] = range_header

                        imp = "firefox147" if "Firefox" in cffi_hdrs.get("User-Agent", "") else "chrome"
                        resp = cffi_requests.request(
                            method,
                            url,
                            headers=cffi_hdrs,
                            timeout=max(1, float(timeout)),
                            impersonate=imp,
                            verify=False,
                            stream=True,
                        )
                        content_type = entry.get("content_type") or resp.headers.get("Content-Type") or resp.headers.get("content-type", "")

                        if method == "GET" and _is_playlist(url, content_type):
                            raw_chunks = []
                            for chunk in resp.iter_content(65536):
                                raw_chunks.append(chunk)
                            body = b"".join(raw_chunks)
                            text = body.decode("utf-8", errors="replace")
                            rewritten = rewrite_playlist(text, url, ref, hdrs)
                            data = rewritten.encode("utf-8")
                            try:
                                self.send_response(200)
                                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                                self.send_header("Content-Length", str(len(data)))
                                self.send_header("Access-Control-Allow-Origin", "*")
                                self.send_header("Access-Control-Allow-Headers", "*")
                                self.send_header("Cache-Control", "no-store, no-cache")
                                self.end_headers()
                                self.wfile.write(data)
                            except (BrokenPipeError, ConnectionResetError):
                                pass
                            return

                        is_vtt = (
                            "vtt" in str(entry.get("content_type") or "").lower()
                            or "vtt" in str(content_type or "").lower()
                            or url.lower().endswith(".vtt")
                            or url.lower().endswith(".srt")
                        )
                        if method == "GET" and is_vtt:
                            raw_chunks = []
                            for chunk in resp.iter_content(65536):
                                raw_chunks.append(chunk)
                            vtt_data = _ensure_vtt(b"".join(raw_chunks))
                            try:
                                self.send_response(200)
                                self.send_header("Content-Type", "text/vtt; charset=utf-8")
                                self.send_header("Content-Length", str(len(vtt_data)))
                                self.send_header("Access-Control-Allow-Origin", "*")
                                self.send_header("Access-Control-Allow-Headers", "*")
                                self.send_header("Cache-Control", "no-store, no-cache")
                                self.end_headers()
                                self.wfile.write(vtt_data)
                            except (BrokenPipeError, ConnectionResetError):
                                pass
                            return

                        try:
                            self.send_response(resp.status_code)
                            content_type_sent = False
                            has_accept_ranges = False
                            for key, value in resp.headers.items():
                                k_low = key.lower()
                                if k_low in ("connection", "keep-alive", "transfer-encoding", "trailer", "upgrade", "content-encoding"):
                                    continue
                                if k_low == "accept-ranges":
                                    has_accept_ranges = True
                                if k_low == "content-type":
                                    if entry.get("content_type"):
                                        value = entry["content_type"]
                                    elif not value.startswith("video/") and not value.startswith("audio/"):
                                        value = "video/MP2T"
                                    content_type_sent = True
                                self.send_header(key, value)
                            if not content_type_sent and entry.get("content_type"):
                                self.send_header("Content-Type", entry["content_type"])
                            if not has_accept_ranges and resp.status_code == 200:
                                self.send_header("Accept-Ranges", "bytes")
                            self.send_header("Access-Control-Allow-Origin", "*")
                            self.send_header("Access-Control-Allow-Headers", "*")
                            self.end_headers()
                            if method == "GET":
                                for chunk in resp.iter_content(65536):
                                    try:
                                        self.wfile.write(chunk)
                                    except (BrokenPipeError, ConnectionResetError):
                                        break
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    except Exception as cffi_exc:
                        _debug_warn("curl_cffi local proxy fallback failed", cffi_exc)
                _debug_warn("Local proxy upstream request failed", http_err)
                try:
                    self.send_error(502, "Upstream stream unavailable")
                except Exception:
                    pass
            except Exception as exc:
                _debug_warn("Local proxy upstream request failed", exc)
                try:
                    self.send_error(502, "Upstream stream unavailable")
                except Exception:
                    pass

        def do_GET(self):
            self._proxy("GET")

        def do_HEAD(self):
            self._proxy("HEAD")

        do_POST = _reject_method
        do_PUT = _reject_method
        do_DELETE = _reject_method
        do_OPTIONS = _reject_method
        do_PATCH = _reject_method

    server = _ThreadedHTTPServer(("127.0.0.1", 0), ProxyHandler)
    port = server.server_address[1]
    port_holder["port"] = port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return port, registry, register, server


def start_local_proxy(
        target_url, referer, headers=None, timeout=15,
        stream_type="mp4", title="stream", subtitles=None):
    validate_http_url(target_url)
    is_hls = str(stream_type).lower() == "hls"
    extension = "m3u8" if is_hls else "mp4"
    base_secret = new_proxy_secret_path(extension, title=title)
    forwarded_headers = proxy_filtered_headers(headers)

    # If HLS and subtitles are provided, generate synthetic master M3U8 with #EXT-X-MEDIA:TYPE=SUBTITLES
    if is_hls and subtitles:
        master_secret = base_secret
        video_secret = new_proxy_secret_path("m3u8")

        initial = {
            master_secret: {"kind": "synthetic", "text": ""},
            video_secret: {
                "kind": "fetch",
                "url": target_url,
                "ref": referer,
                "hdrs": dict(forwarded_headers),
            },
        }

        sub_list = _prepare_subtitle_entries(subtitles)
        sub_entries = []
        for s in sub_list:
            if s["is_m3u8"]:
                sub_entries.append({
                    "name": s["label"],
                    "lang": s["lang"],
                    "default": "YES" if s["default"] else "NO",
                    "is_m3u8": True,
                    "url": s["url"],
                })
            else:
                vtt_secret = new_proxy_secret_path("vtt", title=s["label"])
                m3u8_secret = new_proxy_secret_path("m3u8", title=s["label"])
                initial[vtt_secret] = {
                    "kind": "fetch",
                    "url": s["url"],
                    "ref": referer,
                    "hdrs": dict(forwarded_headers),
                    "content_type": "text/vtt; charset=utf-8",
                }
                initial[m3u8_secret] = {
                    "kind": "synthetic",
                    "text": "",
                }
                sub_entries.append({
                    "name": s["label"],
                    "lang": s["lang"],
                    "default": "YES" if s["default"] else "NO",
                    "is_m3u8": False,
                    "m3u8_secret": m3u8_secret,
                    "vtt_secret": vtt_secret,
                })

        port, registry, _register, server = _build_proxy_server(initial, timeout)

        # Build Master M3U8 content
        master_lines = ["#EXTM3U", "#EXT-X-VERSION:3", ""]
        for sub in sub_entries:
            if sub["is_m3u8"]:
                sub_path = _register(sub["url"], referer, forwarded_headers)
                sub_m3u8_url = f"http://127.0.0.1:{port}{sub_path}"
            else:
                sub_m3u8_url = f"http://127.0.0.1:{port}{sub['m3u8_secret']}"
                sub_vtt_url = f"http://127.0.0.1:{port}{sub['vtt_secret']}"
                registry[sub["m3u8_secret"]]["text"] = (
                    f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:1500\n"
                    f"#EXT-X-MEDIA-SEQUENCE:1\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:1500.0,\n"
                    f"{sub_vtt_url}\n#EXT-X-ENDLIST\n"
                )

            master_lines.append(
                f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="{sub["name"]}",'
                f'LANGUAGE="{sub["lang"]}",DEFAULT={sub["default"]},AUTOSELECT={sub["default"]},FORCED=NO,URI="{sub_m3u8_url}"'
            )

        master_lines.append("")

        # Inspect target_url to see if it's already a master or a single stream
        video_local_url = f"http://127.0.0.1:{port}{video_secret}"
        try:
            req = urllib.request.Request(target_url)
            req.add_header("User-Agent", forwarded_headers.get("User-Agent", _DEFAULT_UA))
            if referer:
                req.add_header("Referer", referer)
            with urllib.request.urlopen(req, context=SSL_CTX_SECURE, timeout=max(1, float(timeout))) as resp:
                body = resp.read().decode("utf-8", errors="replace")

            if "#EXT-X-STREAM-INF" in body:
                base_target = target_url.rsplit("/", 1)[0] + "/"
                pending_inf = None
                for line in body.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                        if 'URI="' in stripped:
                            u_start = stripped.index('URI="') + 5
                            u_end = stripped.index('"', u_start)
                            raw_a_uri = stripped[u_start:u_end]
                            abs_a_uri = urllib.parse.urljoin(base_target, raw_a_uri)
                            a_path = _register(abs_a_uri, referer, forwarded_headers)
                            stripped = stripped[:u_start] + f"http://127.0.0.1:{port}{a_path}" + stripped[u_end:]
                        master_lines.append(stripped)
                        continue
                    if stripped.startswith("#EXT-X-STREAM-INF:"):
                        if 'SUBTITLES="' in stripped:
                            pending_inf = re.sub(r'SUBTITLES="[^"]*"', 'SUBTITLES="subs"', stripped)
                        else:
                            pending_inf = f'{stripped},SUBTITLES="subs"'
                        master_lines.append(pending_inf)
                        continue
                    if stripped.startswith("#"):
                        if not stripped.startswith("#EXTM3U") and not stripped.startswith("#EXT-X-VERSION"):
                            master_lines.append(stripped)
                        continue
                    if pending_inf is not None:
                        var_abs = urllib.parse.urljoin(base_target, stripped)
                        var_path = _register(var_abs, referer, forwarded_headers)
                        master_lines.append(f"http://127.0.0.1:{port}{var_path}")
                        pending_inf = None
            else:
                master_lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH=2889119,RESOLUTION=1920x1080,SUBTITLES="subs"')
                master_lines.append(video_local_url)
        except Exception:
            master_lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH=2889119,RESOLUTION=1920x1080,SUBTITLES="subs"')
            master_lines.append(video_local_url)

        master_lines.append("")
        registry[master_secret]["text"] = "\n".join(master_lines)
        return f"http://127.0.0.1:{port}{master_secret}", server

    initial = {
        base_secret: {
            "kind": "fetch",
            "url": target_url,
            "ref": referer,
            "hdrs": dict(forwarded_headers),
        }
    }
    port, _registry, _register, server = _build_proxy_server(initial, timeout)
    return f"http://127.0.0.1:{port}{base_secret}", server



def start_local_dual_proxy(
        video_url, audio_url, referer, headers=None, timeout=15,
        width=1280, height=720, bandwidth=2_400_000, title="stream",
        subtitles=None, audio_tracks=None):
    """Like start_local_proxy, but for sources that split video and audio
    into two separate HLS manifests (Dailymotion does this) with no
    combined master. Builds the master ourselves; both sub-manifests go
    through the SAME rewriting/header machinery as everything else, so
    Dailymotion's video track gets the same header treatment its audio
    track does, instead of being served as a static unproxied file.
    """
    validate_http_url(video_url)
    if audio_url:
        validate_http_url(audio_url)
    forwarded_headers = proxy_filtered_headers(headers)

    master_secret = new_proxy_secret_path("m3u8", title=title)
    video_secret = new_proxy_secret_path("m3u8")

    tracks_to_use = list(audio_tracks) if audio_tracks else []
    if not tracks_to_use and audio_url:
        tracks_to_use = [{"url": audio_url, "label": "Audio", "default": True}]

    has_default = any(t.get("default") for t in tracks_to_use)
    if not has_default and tracks_to_use:
        tracks_to_use[0]["default"] = True

    initial = {
        master_secret: {"kind": "synthetic", "text": ""},  # filled in below
        video_secret: {
            "kind": "fetch", "url": video_url, "ref": referer,
            "hdrs": dict(forwarded_headers),
        },
    }

    audio_secrets = []
    audio_lines = []
    for idx, track in enumerate(tracks_to_use):
        t_url = track.get("url")
        if not t_url:
            continue
        try:
            validate_http_url(t_url)
        except ValueError:
            continue
        a_secret = new_proxy_secret_path("m3u8")
        audio_secrets.append((a_secret, idx))
        initial[a_secret] = {
            "kind": "fetch", "url": t_url, "ref": referer,
            "hdrs": dict(forwarded_headers),
        }
        t_name = track.get("label") or track.get("name") or f"Audio {idx+1}"
        t_lang = track.get("language") or ""
        lang_attr = f',LANGUAGE="{t_lang}"' if t_lang else ""
        is_def = "YES" if track.get("default") else "NO"
        audio_lines.append(
            f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="{t_name}",'
            f'DEFAULT={is_def},AUTOSELECT={is_def}{lang_attr},URI="__AUDIO_URL_{idx}__"'
        )

    sub_list = _prepare_subtitle_entries(subtitles)
    sub_entries = []
    for s in sub_list:
        if s["is_m3u8"]:
            sub_entries.append({
                "name": s["label"],
                "lang": s["lang"],
                "default": "YES" if s["default"] else "NO",
                "is_m3u8": True,
                "url": s["url"],
            })
        else:
            vtt_secret = new_proxy_secret_path("vtt", title=s["label"])
            m3u8_secret = new_proxy_secret_path("m3u8", title=s["label"])
            initial[vtt_secret] = {
                "kind": "fetch",
                "url": s["url"],
                "ref": referer,
                "hdrs": dict(forwarded_headers),
                "content_type": "text/vtt; charset=utf-8",
            }
            initial[m3u8_secret] = {
                "kind": "synthetic",
                "text": "",
            }
            sub_entries.append({
                "name": s["label"],
                "lang": s["lang"],
                "default": "YES" if s["default"] else "NO",
                "is_m3u8": False,
                "m3u8_secret": m3u8_secret,
                "vtt_secret": vtt_secret,
            })

    port, registry, _register, server = _build_proxy_server(initial, timeout)

    master_lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:6",
    ]
    master_lines.extend(audio_lines)

    for sub in sub_entries:
        if sub["is_m3u8"]:
            sub_path = _register(sub["url"], referer, forwarded_headers)
            sub_m3u8_url = f"http://127.0.0.1:{port}{sub_path}"
        else:
            sub_m3u8_url = f"http://127.0.0.1:{port}{sub['m3u8_secret']}"
            sub_vtt_url = f"http://127.0.0.1:{port}{sub['vtt_secret']}"
            registry[sub["m3u8_secret"]]["text"] = (
                f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:1500\n"
                f"#EXT-X-MEDIA-SEQUENCE:1\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:1500.0,\n"
                f"{sub_vtt_url}\n#EXT-X-ENDLIST\n"
            )

        master_lines.append(
            f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="{sub["name"]}",'
            f'LANGUAGE="{sub["lang"]}",DEFAULT={sub["default"]},AUTOSELECT={sub["default"]},FORCED=NO,URI="{sub_m3u8_url}"'
        )

    audio_attr = ',AUDIO="audio"' if audio_lines else ""
    subs_attr = ',SUBTITLES="subs"' if sub_entries else ""
    codecs_attr = ',CODECS="mp4a.40.2,avc1.640028"'
    master_lines.append(
        f'#EXT-X-STREAM-INF:BANDWIDTH={int(bandwidth)},'
        f'RESOLUTION={int(width)}x{int(height)}{codecs_attr}{audio_attr}{subs_attr}'
    )
    master_lines.append("__VIDEO_URL__\n")
    master_text = "\n".join(master_lines)

    # Now that we know our own port, fill in the synthetic master with
    # local URLs pointing back at this same server.
    text = master_text.replace("__VIDEO_URL__", f"http://127.0.0.1:{port}{video_secret}")
    for a_secret, idx in audio_secrets:
        text = text.replace(f"__AUDIO_URL_{idx}__", f"http://127.0.0.1:{port}{a_secret}")
    registry[master_secret]["text"] = text

    return f"http://127.0.0.1:{port}{master_secret}", server


def start_local_content_server(content, filename, content_type):
    payload = (
        content.encode("utf-8")
        if isinstance(content, str)
        else bytes(content)
    )
    safe_name = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        str(filename or "content"),
    )
    content_type = str(content_type or "application/octet-stream")
    if not re.fullmatch(
            r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+",
            content_type):
        content_type = "application/octet-stream"
    secret_path = f"/{uuid.uuid4().hex}/{safe_name}"

    class ContentHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _serve(self, include_body):
            if not proxy_path_authorized(self.path, secret_path):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if include_body:
                self.wfile.write(payload)

        def do_GET(self):
            self._serve(True)

        def do_HEAD(self):
            self._serve(False)

        def _reject_method(self):
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_POST = _reject_method
        do_PUT = _reject_method
        do_DELETE = _reject_method
        do_OPTIONS = _reject_method
        do_PATCH = _reject_method

    server = _ThreadedHTTPServer(("127.0.0.1", 0), ContentHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}{secret_path}", server


def stop_local_proxy(server):
    if not server:
        return
    try:
        server.shutdown()
    except Exception as exc:
        _debug_warn("Local proxy shutdown failed", exc)
    try:
        server.server_close()
    except Exception as exc:
        _debug_warn("Local proxy close failed", exc)


def replace_active_local_proxy(server=None):
    global _active_server
    with _active_lock:
        previous = _active_server
        _active_server = server
    if previous is not None and previous is not server:
        stop_local_proxy(previous)
    return server


def cleanup_active_local_proxy():
    global _active_server
    with _active_lock:
        server = _active_server
        _active_server = None
    stop_local_proxy(server)

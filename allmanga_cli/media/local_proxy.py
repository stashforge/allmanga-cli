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


def _guess_ext(url):
    path = urllib.parse.urlsplit(url).path
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if re.fullmatch(r"[a-z0-9]{1,8}", ext):
            return ext
    return ""


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

    def register(url, ref, hdrs):
        ext = _guess_ext(url) or ("m3u8" if ".m3u8" in url.lower() else "ts")
        path = new_proxy_secret_path(ext)
        with registry_lock:
            registry[path] = {
                "kind": "fetch", "url": url, "ref": ref, "hdrs": dict(hdrs),
            }
        return path

    def local_url_for(path):
        return f"http://127.0.0.1:{port_holder['port']}{path}"

    def rewrite_playlist(text, base_url, ref, hdrs):
        base = base_url.rsplit("/", 1)[0] + "/"
        out = []
        for line in text.splitlines():
            line = line.strip()

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
                self.send_error(404)
                return

            if entry["kind"] == "synthetic":
                data = entry["text"].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if method == "GET":
                    self.wfile.write(data)
                return

            url, ref, hdrs = entry["url"], entry["ref"], entry["hdrs"]
            request = urllib.request.Request(url, method=method)
            request.add_header("User-Agent", hdrs.get("User-Agent", _DEFAULT_UA))
            if ref:
                request.add_header("Referer", ref)
            for key, value in hdrs.items():
                if key.casefold() == "user-agent":
                    continue
                request.add_header(key, value)
            range_header = proxy_range_header(self.headers.get("Range", ""))
            if range_header:
                request.add_header("Range", range_header)

            try:
                with urllib.request.urlopen(
                        request,
                        context=SSL_CTX_SECURE,
                        timeout=max(1, float(timeout))) as response:
                    validate_http_url(response.geturl())
                    content_type = response.headers.get("Content-Type", "")

                    if method == "GET" and _is_playlist(url, content_type):
                        body = response.read()
                        text = body.decode("utf-8", errors="replace")
                        rewritten = rewrite_playlist(text, url, ref, hdrs)
                        data = rewritten.encode("utf-8")
                        self.send_response(200)
                        self.send_header(
                            "Content-Type", "application/vnd.apple.mpegurl"
                        )
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        self.wfile.write(data)
                        return

                    self.send_response(response.status)
                    for key, value in proxy_response_headers(response.headers):
                        self.send_header(key, value)
                    self.end_headers()
                    if method == "GET":
                        while chunk := response.read(65536):
                            try:
                                self.wfile.write(chunk)
                            except Exception:
                                break
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


def start_local_proxy(target_url, referer, headers=None, timeout=15, stream_type="mp4"):
    validate_http_url(target_url)
    is_hls = str(stream_type).lower() == "hls"
    extension = "m3u8" if is_hls else "mp4"
    base_secret = new_proxy_secret_path(extension)
    forwarded_headers = proxy_filtered_headers(headers)

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
        width=1280, height=720, bandwidth=2_400_000):
    """Like start_local_proxy, but for sources that split video and audio
    into two separate HLS manifests (Dailymotion does this) with no
    combined master. Builds the master ourselves; both sub-manifests go
    through the SAME rewriting/header machinery as everything else, so
    Dailymotion's video track gets the same header treatment its audio
    track does, instead of being served as a static unproxied file.
    """
    validate_http_url(video_url)
    validate_http_url(audio_url)
    forwarded_headers = proxy_filtered_headers(headers)

    master_secret = new_proxy_secret_path("m3u8")
    video_secret = new_proxy_secret_path("m3u8")
    audio_secret = new_proxy_secret_path("m3u8")

    master_text = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Audio",'
        f'DEFAULT=YES,AUTOSELECT=YES,URI="{{audio_url}}"\n'
        f'#EXT-X-STREAM-INF:BANDWIDTH={int(bandwidth)},'
        f'RESOLUTION={int(width)}x{int(height)},AUDIO="audio"\n'
        "{video_url}\n"
    )

    initial = {
        master_secret: {"kind": "synthetic", "text": ""},  # filled in below
        video_secret: {
            "kind": "fetch", "url": video_url, "ref": referer,
            "hdrs": dict(forwarded_headers),
        },
        audio_secret: {
            "kind": "fetch", "url": audio_url, "ref": referer,
            "hdrs": dict(forwarded_headers),
        },
    }
    port, registry, _register, server = _build_proxy_server(initial, timeout)

    # Now that we know our own port, fill in the synthetic master with
    # local URLs pointing back at this same server.
    registry[master_secret]["text"] = master_text.format(
        audio_url=f"http://127.0.0.1:{port}{audio_secret}",
        video_url=f"http://127.0.0.1:{port}{video_secret}",
    )

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

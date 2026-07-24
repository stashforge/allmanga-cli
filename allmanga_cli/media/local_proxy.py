"""Private localhost proxy and generated-content server lifecycle."""

import base64
import http.server
import json
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


def configure_debug_reporter(reporter):
    global _debug_warn
    _debug_warn = reporter


def encode_segment(url: str, headers: dict) -> str:
    payload = json.dumps({"u": url, "h": headers}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_segment(token: str) -> dict:
    pad = "=" * (-len(token) % 4)
    payload = base64.urlsafe_b64decode(token + pad)
    return json.loads(payload)


def guess_ext(url: str) -> str:
    path = url.split("?", 1)[0]
    if "." in path.rsplit("/", 1)[-1]:
        return "." + path.rsplit(".", 1)[-1]
    return ""


def is_playlist(url: str, ctype: str) -> bool:
    return ".m3u8" in url.lower() or "mpegurl" in str(ctype).lower()


def rewrite_playlist(text: str, base_url: str, headers: dict, host: str, secret_base: str) -> str:
    base = base_url.rsplit("/", 1)[0] + "/"
    out = []
    for line in text.splitlines():
        line = line.strip()

        if line.startswith("#") and 'URI="' in line:
            start = line.index('URI="') + 5
            end = line.index('"', start)
            target = line[start:end]
            real = urllib.parse.urljoin(base, target)
            token = encode_segment(real, headers)
            ext = guess_ext(real) or ".bin"
            proxied = f"{host}{secret_base}/seg/{token}/x{ext}"
            line = line[:start] + proxied + line[end:]
            out.append(line)
            continue

        if line.startswith("#") or not line:
            out.append(line)
            continue

        real = urllib.parse.urljoin(base, line)
        token = encode_segment(real, headers)
        ext = guess_ext(real) or (".m3u8" if ".m3u8" in real.lower() else ".ts")
        out.append(f"{host}{secret_base}/seg/{token}/x{ext}")

    return "\n".join(out)


class _ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


def start_local_proxy(target_url, referer, headers=None, timeout=15, stream_type="mp4"):
    validate_http_url(target_url)
    extension = "m3u8" if str(stream_type).lower() == "hls" else "mp4"
    secret_path = new_proxy_secret_path(extension)
    secret_base = "/" + secret_path.split("/")[1]
    forwarded_headers = proxy_filtered_headers(headers)

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

            req_path = urllib.parse.urlsplit(self.path).path
            if not req_path.startswith(secret_base):
                self.send_error(404)
                return

            if req_path == secret_path:
                fetch_url = target_url
                fetch_headers = dict(forwarded_headers)
                if referer:
                    fetch_headers["Referer"] = referer
            elif req_path.startswith(f"{secret_base}/seg/"):
                parts = req_path.split("/")
                if len(parts) < 4:
                    self.send_error(404)
                    return
                token = parts[3]
                try:
                    data = decode_segment(token)
                    fetch_url = data["u"]
                    fetch_headers = proxy_filtered_headers(data["h"])
                except Exception:
                    self.send_error(400, "Bad segment token")
                    return
            else:
                self.send_error(404)
                return

            request = urllib.request.Request(fetch_url, method=method)
            request.add_header("User-Agent", "Mozilla/5.0")
            for key, value in fetch_headers.items():
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
                    
                    ctype = response.headers.get("Content-Type", "") or "application/octet-stream"
                    if method == "GET" and is_playlist(fetch_url, ctype):
                        text = response.read().decode('utf-8', errors='ignore')
                        host = f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"
                        rewritten = rewrite_playlist(text, fetch_url, fetch_headers, host, secret_base)
                        payload = rewritten.encode("utf-8")
                        
                        self.send_response(response.status)
                        for key, value in proxy_response_headers(response.headers):
                            if key.casefold() in ("content-length", "content-type"):
                                continue
                            self.send_header(key, value)
                        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        
                        self.wfile.write(payload)
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
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}{secret_path}", server


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

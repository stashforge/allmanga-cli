"""Private localhost proxy and generated-content server lifecycle."""

import http.server
import re
import threading
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


class _ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


def start_local_proxy(target_url, referer, headers=None, timeout=15):
    validate_http_url(target_url)
    secret_path = new_proxy_secret_path()
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
            if not proxy_path_authorized(self.path, secret_path):
                self.send_error(404)
                return

            request = urllib.request.Request(target_url, method=method)
            request.add_header("User-Agent", "Mozilla/5.0")
            if referer:
                request.add_header("Referer", referer)
            for key, value in forwarded_headers.items():
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

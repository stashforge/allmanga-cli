"""Asynchronous cover cache and poster rendering coordination."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import time

from .covers import (
    chafa_cover_command,
    enforce_cache_limits,
    fetch_cover_bytes,
)


class PosterManager:
    def __init__(
            self,
            *,
            enabled,
            cache_dir,
            hovered_show_id,
            request_redraw,
            loading_frame):
        self.enabled = enabled
        self.cache_dir = cache_dir
        self.hovered_show_id = hovered_show_id
        self.request_redraw = request_redraw
        self.loading_frame = loading_frame
        self.poster_lock = threading.Lock()
        self.download_lock = threading.Lock()
        self.active_downloads = set()

    def _mark_download(self, url_hash):
        with self.download_lock:
            if url_hash in self.active_downloads:
                return False
            self.active_downloads.add(url_hash)
            return True

    def _unmark_download(self, url_hash):
        with self.download_lock:
            self.active_downloads.discard(url_hash)

    def clear_downloads(self):
        with self.download_lock:
            self.active_downloads.clear()

    def set_status(self, show, status):
        with self.poster_lock:
            if show.get("_poster_status") != status:
                show["_poster_status"] = status
                show["_poster_status_time"] = time.time()

    def footer_line(self, show, default_text, width):
        reset = "\033[0m"
        hint = "\033[38;5;244m"

        def trim(value):
            return value[:width - 1] + "\u2026" if len(value) > width else value

        def split_replaced_footer(value):
            if "\u2502" in default_text:
                _, right = default_text.split("\u2502", 1)
                return value, f"  \u2502{right}"
            return value, ""

        def status_line(value, color, loading=False):
            left, right = split_replaced_footer(value)
            if loading:
                left = f"{self.loading_frame()} {left}"
            if len(left + right) > width:
                keep_right = max(0, width - len(left) - 1)
                right = right[:keep_right] + (
                    "\u2026" if keep_right else ""
                )
            return f"{color}{left}{reset}{hint}{right}{reset}"

        default_line = f"{hint}{trim(default_text)}{reset}"
        if not self.enabled() or not show:
            return default_line
        with self.poster_lock:
            status = show.get("_poster_status")
            status_time = float(show.get("_poster_status_time", 0) or 0)
        if status == "loading":
            return status_line("Loading cover", "\033[36m", loading=True)
        if status_time and time.time() - status_time > 3:
            return default_line
        if status == "failed":
            return status_line("Cover failed", "\033[38;5;203m")
        if status == "missing":
            return status_line("Cover unavailable", "\033[38;5;214m")
        if status == "no_chafa":
            return status_line("Cover needs chafa", "\033[38;5;214m")
        return default_line

    def needs_tick(self, show):
        if not self.enabled() or not show:
            return False
        with self.poster_lock:
            return show.get("_poster_status") == "loading"

    def get(self, show):
        if not self.enabled():
            return None
        if not show.get("thumbnail"):
            self.set_status(show, "missing")
            return ""
        if not shutil.which("chafa"):
            self.set_status(show, "no_chafa")
            return ""

        with self.poster_lock:
            if not show.get("_poster_failed"):
                raw = show.get("_poster_raw")
                if raw is not None:
                    show["_poster_status"] = "ready"
                    show["_poster_status_time"] = time.time()
                    return raw
            failed = show.get("_poster_failed")
        if failed:
            self.set_status(show, "failed")
            return ""

        url = show["thumbnail"]
        cache_dir = self.cache_dir()
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        cached_path = os.path.join(cache_dir, f"{url_hash}.jpg")
        if os.path.exists(cached_path):
            os.utime(cached_path, None)
            try:
                process = subprocess.run(
                    chafa_cover_command(cached_path),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if process.returncode == 0 and process.stdout.strip():
                    raw = process.stdout.rstrip("\n")
                    with self.poster_lock:
                        show["_poster_raw"] = raw
                        show["_poster_status"] = "ready"
                        show["_poster_status_time"] = time.time()
                    return raw
            except Exception:
                pass
            with self.poster_lock:
                show["_poster_failed"] = True
            self.set_status(show, "failed")
            return ""

        self.set_status(show, "loading")
        if self._mark_download(url_hash):
            threading.Thread(
                target=self._download,
                args=(show, url, url_hash, cache_dir, cached_path),
                daemon=True,
            ).start()
        return ""

    def _download(self, show, url, url_hash, cache_dir, cached_path):
        time.sleep(0.3)
        if self.hovered_show_id() != show.get("_id"):
            self._unmark_download(url_hash)
            return

        temporary_path = None
        try:
            os.makedirs(cache_dir, exist_ok=True)
            image_data = fetch_cover_bytes(url)
            descriptor, temporary_path = tempfile.mkstemp(
                suffix=".jpg",
                prefix="allmanga_tmp_",
            )
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(image_data)

            if shutil.which("magick"):
                converted = subprocess.run(
                    [
                        "magick",
                        temporary_path,
                        "-resize",
                        "400x600",
                        cached_path,
                    ],
                    capture_output=True,
                    timeout=10,
                )
                if converted.returncode != 0:
                    raise RuntimeError("ImageMagick could not decode cover")
            elif shutil.which("ffmpeg"):
                converted = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        temporary_path,
                        "-vf",
                        "scale=400:-1",
                        cached_path,
                    ],
                    capture_output=True,
                    timeout=10,
                )
                if converted.returncode != 0:
                    raise RuntimeError("ffmpeg could not decode cover")
            else:
                shutil.copy2(temporary_path, cached_path)

            enforce_cache_limits(cache_dir)
            process = subprocess.run(
                chafa_cover_command(cached_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if process.returncode == 0 and process.stdout.strip():
                with self.poster_lock:
                    show["_poster_raw"] = process.stdout.rstrip("\n")
                    show["_poster_status"] = "ready"
                    show["_poster_status_time"] = time.time()
            else:
                with self.poster_lock:
                    show["_poster_failed"] = True
                self.set_status(show, "failed")
            self.request_redraw()
        except Exception:
            with self.poster_lock:
                show["_poster_failed"] = True
            self.set_status(show, "failed")
            self.request_redraw()
        finally:
            if temporary_path:
                try:
                    os.remove(temporary_path)
                except Exception:
                    pass
            self._unmark_download(url_hash)

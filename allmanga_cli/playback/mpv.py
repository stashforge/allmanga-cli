"""Persistent mpv process and IPC playback controller."""

import json
import os
import select
import socket
import subprocess
import sys
import termios
import threading
import time
import tty

from .mpv_runtime import (
    TRANSITION_OSD_MS,
    cleanup_mpv_runtime,
    create_mpv_runtime,
)
from .rules import (
    episode_transition_osd,
    playback_is_actively_advancing,
    prefetch_matches_request,
)


class MpvIpc:
    def __init__(self, redraw_callback=None):
        self.redraw_callback = redraw_callback
        self.runtime_dir = None
        self.socket_path = None
        self.conf_path = None
        self.process = None
        self.client = None
        self.running = False
        self.props = {
            "playback-time": 0,
            "duration": 0,
            "pause": False,
            "paused-for-cache": False,
            "percent-pos": 0,
        }
        self.prefetched_ep = None
        self.prefetched_stream = None
        self.prefetched_res = None
        self.is_fetching = False

    def start(self):
        if self.process and self.process.poll() is None: return
        cleanup_mpv_runtime(self.runtime_dir)
        self.runtime_dir, self.socket_path, self.conf_path = create_mpv_runtime()
        try:
            self.process = subprocess.Popen([
                "mpv", "--idle=yes", "--keep-open=no", f"--input-ipc-server={self.socket_path}",
                f"--input-conf={self.conf_path}", "--force-window=yes"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            for _ in range(20):
                if os.path.exists(self.socket_path): break
                time.sleep(0.1)

            self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.client.connect(self.socket_path)
            self.client.setblocking(False)
            self.running = True
        except Exception:
            self.quit()
            raise

        self.send_cmd("observe_property", 1, "playback-time")
        self.send_cmd("observe_property", 2, "duration")
        self.send_cmd("observe_property", 3, "pause")
        self.send_cmd("observe_property", 4, "percent-pos")
        self.send_cmd("observe_property", 5, "paused-for-cache")

    def send_cmd(self, *args):
        if not self.running: return
        try:
            msg = json.dumps({"command": list(args)}) + "\n"
            self.client.sendall(msg.encode("utf-8"))
        except Exception:
            self.running = False

    def load(
            self, url, title, headers, referer, start_time=0, osd_msg="",
            audio_url="", subtitle_url=""):
        self.start()
        self.props["playback-time"] = 0
        self.props["duration"] = 0
        self.props["pause"] = False
        self.props["paused-for-cache"] = False
        self.props["percent-pos"] = 0
        self.send_cmd("set_property", "force-media-title", title)
        hf = [f"{k}: {v}" for k, v in headers.items()] if headers else []
        if referer and "wixstatic" not in url:
            hf.append(f"Referer: {referer}")
        if hf:
            self.send_cmd("set_property", "http-header-fields", ",".join(hf))

        # Override user's save-position-on-quit config to prevent cache hijacking
        self.send_cmd("set_property", "resume-playback", False)
        self.resume_time = start_time

        self.send_cmd("loadfile", url)
        if audio_url:
            self.send_cmd("audio-add", audio_url, "select")
        if subtitle_url:
            self.send_cmd("sub-add", subtitle_url, "select")

        msg = f"Now playing\n{title}\n\nShift+Right: Next  •  Shift+Left: Previous  •  Q: Quit"
        if osd_msg:
            msg += f"\n\n{osd_msg}"
        self.initial_osd_msg = msg

    def quit(self):
        self.send_cmd("quit")
        if self.client:
            try: self.client.close()
            except Exception: pass
            self.client = None
        if self.process:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            self.process = None
        self.running = False
        cleanup_mpv_runtime(self.runtime_dir)
        self.runtime_dir = None
        self.socket_path = None
        self.conf_path = None

    def wait_for_playback(self, ui_info, current_ep, total_eps, fetch_callback, is_binge=False):
        tty_fd = sys.stdin.fileno()
        if os.isatty(tty_fd):
            old_attrs = termios.tcgetattr(tty_fd)
            tty.setcbreak(tty_fd)
        else:
            old_attrs = None

        result = "EOF"
        buf = ""
        want_skip_to = None
        want_skip_ep = None
        notify_prefetched = None
        countdown_active = False
        initial_osd_shown = False
        played_seconds = 0.0
        last_playback_tick = time.monotonic()

        def do_fetch(ep_target, action):
            nonlocal notify_prefetched
            try:
                res = fetch_callback(ep_target)
                if self.prefetched_ep == ep_target and res:
                    self.prefetched_stream = res[0]
                    self.prefetched_res = res
            except Exception: pass
            self.is_fetching = False
            notify_prefetched = action

        def trigger_fetch(ep_target, action="NEXT"):
            if self.is_fetching: return
            if self.prefetched_ep == ep_target and self.prefetched_stream: return
            if not fetch_callback: return
            self.prefetched_ep = ep_target
            self.prefetched_stream = None
            self.prefetched_res = None
            self.is_fetching = True
            threading.Thread(
                target=do_fetch,
                args=(ep_target, action),
                daemon=True,
            ).start()

        current_ord = int(ui_info.get("episode_index", 0)) + 1
        next_ord = current_ord + 1
        prev_ord = current_ord - 1
        next_label = ui_info.get("next_episode") or next_ord

        def fmt_time(sec):
            if not sec: return "00:00"
            m, s = divmod(int(sec), 60)
            if m >= 60:
                h, m = divmod(m, 60)
                return f"{h:02d}:{m:02d}:{s:02d}"
            return f"{m:02d}:{s:02d}"

        def redraw():
            if self.redraw_callback:
                self.redraw_callback(self.props)

        try:
            done = False
            pending_action = None
            while self.running and not done:
                now = time.monotonic()
                elapsed = max(0.0, now - last_playback_tick)
                last_playback_tick = now
                if playback_is_actively_advancing(
                    self.props, initial_osd_shown
                ):
                    played_seconds += min(elapsed, 1.0)
                r, _, _ = select.select([self.client, sys.stdin], [], [], 0.2)

                if notify_prefetched:
                    completed_action = notify_prefetched
                    notify_prefetched = False
                    if want_skip_to == completed_action:
                        if (
                            prefetch_matches_request(
                                self.prefetched_ep, want_skip_ep
                            )
                            and self.prefetched_stream
                        ):
                            self.send_cmd(
                                "show-text",
                                episode_transition_osd(
                                    completed_action, "starting"
                                ),
                                TRANSITION_OSD_MS,
                            )
                        elif prefetch_matches_request(
                            self.prefetched_ep, want_skip_ep
                        ):
                            self.send_cmd(
                                "show-text",
                                episode_transition_osd(
                                    completed_action, "failed"
                                ),
                                5000,
                            )
                            want_skip_to = None
                            want_skip_ep = None
                    elif want_skip_to:
                        pass
                    elif self.prefetched_stream:
                        self.send_cmd(
                            "show-text",
                            episode_transition_osd(completed_action, "ready"),
                            3000,
                        )
                    else:
                        self.send_cmd(
                            "show-text",
                            episode_transition_osd(completed_action, "failed"),
                            5000,
                        )

                # Check if we have a delayed skip that is now ready
                if want_skip_to and not self.is_fetching:
                    if not prefetch_matches_request(
                        self.prefetched_ep, want_skip_ep
                    ):
                        self.send_cmd(
                            "show-text",
                            episode_transition_osd(want_skip_to, "loading"),
                            TRANSITION_OSD_MS,
                        )
                        trigger_fetch(want_skip_ep, want_skip_to)
                    elif self.prefetched_stream:
                        self.send_cmd(
                            "show-text",
                            episode_transition_osd(want_skip_to, "starting"),
                            TRANSITION_OSD_MS,
                        )
                        self.expect_ghost_eof = True
                        result = want_skip_to
                        want_skip_to = None
                        want_skip_ep = None
                        done = True
                        break
                    else:
                        failed_action = want_skip_to
                        want_skip_to = None
                        want_skip_ep = None
                        self.send_cmd(
                            "show-text",
                            episode_transition_osd(failed_action, "failed"),
                            5000,
                        )

                if sys.stdin in r:
                    key = sys.stdin.read(1)
                    if key == "\x03":
                        raise KeyboardInterrupt
                    if key.lower() == 'q':
                        pending_action = "QUIT"
                        self.send_cmd("stop")
                if self.client in r:
                    try:
                        data = self.client.recv(4096)
                        if not data:
                            self.running = False; break
                        buf += data.decode("utf-8")
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            if not line: continue
                            try:
                                msg = json.loads(line)
                                ev = msg.get("event")
                                if ev == "end-file":
                                    if getattr(self, "expect_ghost_eof", False):
                                        self.expect_ghost_eof = False
                                        continue

                                    reason = msg.get("reason")
                                    if pending_action:
                                        result = pending_action
                                        if pending_action == "QUIT":
                                            self.running = False
                                    elif reason in ("quit", "error"):
                                        result = "QUIT"
                                        self.running = False
                                    elif reason == "stop":
                                        result = "QUIT"
                                    elif reason == "eof":
                                        result = "EOF"
                                    done = True; break
                                elif ev == "property-change":
                                    name = msg.get("name")
                                    val = msg.get("data")
                                    if name in self.props:
                                        if val is not None:
                                            self.props[name] = val
                                        redraw()

                                        if name == "playback-time" and val is not None and not initial_osd_shown:
                                            initial_osd_shown = True
                                            if getattr(self, "resume_time", 0) > 0:
                                                self.send_cmd("seek", self.resume_time, "absolute")
                                            if getattr(self, "initial_osd_msg", None):
                                                self.send_cmd("show-text", self.initial_osd_msg, 5000)

                                        if name == "playback-time" and current_ord < total_eps and is_binge:
                                            pt = self.props.get("playback-time")
                                            dur = self.props.get("duration")
                                            if pt and dur and dur > 0:
                                                rem_sec = dur - pt
                                                ratio = pt / dur
                                                if rem_sec <= 150 and ratio >= 0.75 and not self.is_fetching and not self.prefetched_stream:
                                                    self.send_cmd("show-text", "Preparing next episode...", 3000)
                                                    trigger_fetch(next_ord, "NEXT")

                                                if self.prefetched_stream:
                                                    ntitle = f"{ui_info.get('title', 'Anime')} - Episode {next_label}"
                                                    if rem_sec <= 30 and rem_sec > 5:
                                                        self.send_cmd("show-text", f"Next up\n{ntitle}\nStarts in 0:{int(rem_sec):02d}", 60000)
                                                        countdown_active = True
                                                    elif rem_sec <= 5:
                                                        self.send_cmd("show-text", "Starting next episode...", 60000)
                                                        countdown_active = True
                                                    elif countdown_active:
                                                        self.send_cmd("show-text", "")
                                                        countdown_active = False

                                                if rem_sec <= 2 and self.prefetched_stream:
                                                    self.expect_ghost_eof = True
                                                    result = "NEXT"
                                                    done = True
                                                    break

                                elif ev == "client-message":
                                    args = msg.get("args", [])
                                    if args:
                                        if args[0] == "next_ep":
                                            if current_ord >= total_eps:
                                                self.send_cmd("show-text", "This is the last episode", 3000)
                                            else:
                                                want_skip_to = "NEXT"
                                                want_skip_ep = next_ord
                                                if self.prefetched_ep != next_ord or not self.prefetched_stream:
                                                    self.send_cmd(
                                                        "show-text",
                                                        episode_transition_osd(
                                                            "NEXT", "loading"
                                                        ),
                                                        TRANSITION_OSD_MS,
                                                    )
                                                    trigger_fetch(next_ord, "NEXT")
                                                else:
                                                    self.send_cmd(
                                                        "show-text",
                                                        episode_transition_osd(
                                                            "NEXT", "starting"
                                                        ),
                                                        TRANSITION_OSD_MS,
                                                    )
                                        elif args[0] == "prev_ep":
                                            if current_ord <= 1:
                                                self.send_cmd("show-text", "This is the first episode", 3000)
                                            else:
                                                want_skip_to = "PREV"
                                                want_skip_ep = prev_ord
                                                if self.prefetched_ep != prev_ord or not self.prefetched_stream:
                                                    self.send_cmd(
                                                        "show-text",
                                                        episode_transition_osd(
                                                            "PREV", "loading"
                                                        ),
                                                        TRANSITION_OSD_MS,
                                                    )
                                                    trigger_fetch(prev_ord, "PREV")
                                                else:
                                                    self.send_cmd(
                                                        "show-text",
                                                        episode_transition_osd(
                                                            "PREV", "starting"
                                                        ),
                                                        TRANSITION_OSD_MS,
                                                    )
                            except Exception: pass
                    except BlockingIOError: pass
                redraw()
        finally:
            if old_attrs: termios.tcsetattr(tty_fd, termios.TCSADRAIN, old_attrs)
            print()

        return result, played_seconds

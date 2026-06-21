"""Top-aligned provider verification page."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty

from ..core.terminal import (
    absolute_terminal_frame,
    fit_terminal_line,
    truncate_display,
)
from .picker_render import clear_terminal_images, get_key


_TITLE = "\033[1;97m"
_DIM = "\033[38;5;248m"
_HINT = "\033[38;5;244m"
_WARN = "\033[38;5;220m"
_ERROR = "\033[38;5;203m"
_PTR = "\033[38;2;243;139;168m"
_SEL = "\033[38;2;137;180;250m"
_NORMAL = "\033[38;5;252m"
_RESET = "\033[0m"


def _set_app_alt_screen(active):
    module = sys.modules.get("allmanga_cli.app_core")
    if module is not None:
        try:
            module._alt_screen_active = bool(active)
        except Exception:
            pass


def verification_page(
    title,
    episode,
    ttype,
    episode_url,
    site_url,
    legacy_url=None,
    status_message="",
):
    """Show a top-aligned verification page and return the selected action."""
    actions = [
        ("open_episode", "Open verification page"),
        ("retry", "Retry source request"),
        ("open_site", "Open site"),
        ("back", "Back"),
    ]
    status = status_message
    selected = 0

    def draw(fd):
        try:
            size = os.get_terminal_size(fd)
            rows, cols = size.lines, size.columns
        except OSError:
            rows, cols = 24, 80

        def t(text):
            return truncate_display(str(text), max(1, cols - 1))

        episode_label = f"Episode {episode} · {str(ttype or '').capitalize()}"
        out = [
            clear_terminal_images(),
            f"\033[2K{_WARN}{t('⚠ Verification required')}{_RESET}",
            f"\033[2K{_ERROR}{t('● Playback paused')}{_RESET}",
            "\033[2K",
            f"\033[2K{_DIM}{t('AllAnime blocked the episode source request.')}{_RESET}",
            f"\033[2K{_DIM}{t('Open the verification page, complete the browser check,')}{_RESET}",
            f"\033[2K{_DIM}{t('then return here and retry.')}{_RESET}",
            "\033[2K",
            f"\033[2K{_TITLE}{t('Episode')}{_RESET}",
            f"\033[2K{_DIM}{t(title)}{_RESET}",
            f"\033[2K{_DIM}{t(episode_label)}{_RESET}",
            "\033[2K",
            f"\033[2K{_TITLE}{t('Verification page')}{_RESET}",
            f"\033[2K{_WARN}{t(episode_url or 'Unavailable')}{_RESET}",
        ]
        out.extend([
            "\033[2K",
            f"\033[2K{_TITLE}{t('Alternate URLs')}{_RESET}",
            f"\033[2K{_DIM}{t('Homepage')}{_RESET}",
            f"\033[2K{_WARN}{t(site_url or 'Unavailable')}{_RESET}",
        ])
        if legacy_url:
            out.extend([
                f"\033[2K{_DIM}{t('Legacy')}{_RESET}",
                f"\033[2K{_WARN}{t(legacy_url)}{_RESET}",
            ])
        out.append(
            f"\033[2K{_DIM}{t('Note: open one of these, play any episode once, then come back.')}{_RESET}"
        )
        out.extend(["\033[2K", f"\033[2K{_TITLE}{t('Actions')}{_RESET}"])

        for idx, (_, label) in enumerate(actions):
            ptr = f"{_PTR}❯{_RESET}" if idx == selected else " "
            style = _SEL if idx == selected else _NORMAL
            reset = _RESET
            out.append(f"\033[2K{fit_terminal_line(f'{ptr} {style}{label}{reset}', cols)}")

        if status:
            out.extend(["\033[2K", f"\033[2K{_WARN}{t(status)}{_RESET}"])

        out.extend(["\033[2K", f"\033[2K{_HINT}{t('Enter select · O open page · R retry · Esc back')}{_RESET}"])
        while len(out) < rows:
            out.append("\033[2K")
        return absolute_terminal_frame(out[:rows], rows, cols)

    tty_fd = -1
    tty_file = None
    old_attrs = None
    try:
        tty_fd = os.open("/dev/tty", os.O_RDWR)
        tty_file = os.fdopen(tty_fd, "rb+", buffering=0)
        tty_fd = tty_file.fileno()
        old_attrs = termios.tcgetattr(tty_fd)
        sys.stdout.write("\033[?1049h\033[2J\033[?25l")
        sys.stdout.flush()
        _set_app_alt_screen(True)
        tty.setraw(tty_fd)
        termios.tcflush(tty_fd, termios.TCIFLUSH)

        while True:
            tty_file.write((draw(tty_fd) + "\033[1;1H\033[?25l").encode())
            tty_file.flush()
            ready = select.select([tty_fd], [], [], 0.25)[0]
            if not ready:
                continue
            key = get_key(tty_fd)
            termios.tcflush(tty_fd, termios.TCIFLUSH)
            if key == "CTRL_C":
                raise KeyboardInterrupt
            if key in ("ESC", "LEFT"):
                return "back"
            if key in ("UP", "SHIFT_TAB"):
                selected = (selected - 1) % len(actions)
            elif key in ("DOWN", "TAB"):
                selected = (selected + 1) % len(actions)
            elif key in ("ENTER", "RIGHT"):
                return actions[selected][0]
            elif key in ("o", "O"):
                return "open_episode"
            elif key in ("r", "R"):
                return "retry"
    finally:
        if old_attrs is not None and tty_fd >= 0:
            try:
                termios.tcsetattr(tty_fd, termios.TCSADRAIN, old_attrs)
            except Exception:
                pass
        try:
            sys.stdout.write("\033[?1049l\033[?25h")
            sys.stdout.flush()
            _set_app_alt_screen(False)
        except Exception:
            pass
        if tty_file:
            try:
                tty_file.close()
            except Exception:
                pass

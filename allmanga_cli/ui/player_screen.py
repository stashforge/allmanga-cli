"""
Player-screen renderer for allmanga-cli.

Renders the in-app overlay shown while an episode is loading or playing
through ``mpv``.  Extracted from ``app.py`` so that playback UI logic lives
next to the other ``ui/`` modules.

The module owns the ``_player_ui_state`` dict and the
:class:`PlayerScreen` façade class.  ``app.py`` creates a single
``PlayerScreen`` instance at startup and passes it to playback handlers.
"""

from __future__ import annotations

import os
import sys
import hashlib
import re
from typing import TYPE_CHECKING

from ..domain.titles import extract_title_parts as _extract_title_parts
from ..domain.titles import get_show_display_title
from ..domain.titles import wrap_title as _wrap_title
from ..domain.metadata import positive_int as _positive_int
from ..core.terminal import fit_terminal_line as _fit_terminal_line
from .poster import PosterManager
from .covers import (
    POSTER_HEIGHT,
    POSTER_WIDTH,
    poster_symbol_lines as _poster_symbol_lines,
    poster_uses_native_protocol as _poster_uses_native_protocol,
)
from . import terminal_images

if TYPE_CHECKING:
    from ..context import UiState, CliFlags


# ---------------------------------------------------------------------------
# Shared mutable state (kept as a plain dict to allow _setitem_ callbacks)
# ---------------------------------------------------------------------------

_player_ui_state: dict = {
    "active": False,
    "show": None,
    "current_ep": 0,
    "current_ep_label": "",
    "total_eps": 0,
    "status_lines": [],
    "stream_info": {},
    "mpv_props": None,
}
"""Module-level state dict for the currently active player overlay.

``app.py`` passes a lambda that calls :func:`update_stream_info` so that
``desktop_playback.play_desktop`` can update stream metadata without a
circular import.
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fmt_time(sec: float | None) -> str:
    """Format *sec* seconds as ``MM:SS`` or ``HH:MM:SS``."""
    if not sec:
        return "00:00"
    m, s = divmod(int(sec), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _thin_progress_bar(position: float, duration: float, width: int) -> str:
    """Return a low-height colored progress bar."""
    bar_width = max(10, min(40, width))
    ratio = 0
    if duration > 0:
        ratio = max(0, min(1, position / duration))
    filled = int(ratio * bar_width)
    return (
        f"\033[38;5;115m{'\u2501' * filled}\033[0m"
        f"\033[38;5;240m{'\u2500' * (bar_width - filled)}\033[0m"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_stream_info(info: dict) -> None:
    """Store stream metadata (mirror name, quality, preferred flag) for display."""
    _player_ui_state["stream_info"] = info


def activate(show: dict, current_ep: object, total_eps: int) -> None:
    """Mark the player screen as active and set the episode context.

    Call this before launching the player process.
    """
    _player_ui_state.update({
        "active": True,
        "show": show,
        "current_ep": current_ep,
        "current_ep_label": "",
        "total_eps": total_eps,
        "status_lines": [],
        "stream_info": {},
        "mpv_props": None,
        "_cleared_terminal_image": False,
        "_last_poster_key": None,
    })


def deactivate(close_alt: bool = False) -> None:
    """Tear down the player overlay.

    Parameters
    ----------
    close_alt:
        If ``True``, also restore the normal terminal screen (leave
        alt-screen mode).  Pass ``True`` when fully leaving the player,
        ``False`` when transitioning to the action menu.
    """
    if close_alt:
        # Exit alt screen
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()
    _player_ui_state["active"] = False


def add_status_line(message: str, color: str = "\033[94m") -> bool:
    """Append a status line to the loading overlay and trigger a redraw.

    Returns ``True`` if the player screen is currently active (and the
    message was appended), ``False`` otherwise.
    """
    s = _player_ui_state
    if not s["active"]:
        return False
    s["status_lines"].append(f"{color}{message}\033[0m")
    if len(s["status_lines"]) > 8:
        s["status_lines"].pop(0)
    render()
    return True


def get_player_poster(show: dict | None, ui: "UiState | None" = None) -> str:
    """Return the poster string for *show*, updating the hover state if *ui* is given."""
    if not show:
        return ""
    if ui is not None:
        ui.hovered_show_id = show.get("_id") or show.get("id")
    return ""  # Poster fetching is handled by PosterManager in app.py


def _playback_episode_summary(show: dict | None, player_state: dict, ttype: str = "sub") -> str:
    if not isinstance(show, dict):
        return ""
    available = None
    try:
        available = int((show.get("availableEpisodes") or {}).get(ttype))
    except (TypeError, ValueError):
        available = None
    if available is None:
        next_ep = _positive_int(show.get("_next_airing_ep"))
        if next_ep:
            available = max(0, next_ep - 1)
    if available is None:
        available = _positive_int(player_state.get("total_eps"))

    total = _positive_int(show.get("episodeCount"))
    if available is not None:
        return f"Episodes {available}/{total if total else '?'}"
    if total:
        return f"Total {total}"
    return ""


def render(
    poster_manager: "PosterManager | None" = None,
    ui: "UiState | None" = None,
    enter_alt_screen_fn=None,
) -> None:
    """Render (or refresh) the player overlay on the terminal.

    Parameters
    ----------
    poster_manager:
        The app's :class:`~allmanga_cli.ui.poster.PosterManager` instance.
        If supplied, the poster is fetched and rendered.
    ui:
        Current :class:`~allmanga_cli.context.UiState`; used to update
        ``hovered_show_id`` for the poster manager.
    enter_alt_screen_fn:
        Callable that switches to the alternate terminal screen.  If
        ``None``, the switch is skipped (caller is responsible).
    """
    s = _player_ui_state
    if not s["active"]:
        return

    if enter_alt_screen_fn is not None:
        enter_alt_screen_fn()

    try:
        w, h = os.get_terminal_size(sys.stdin.fileno())
    except Exception:
        w, h = 80, 24

    show = s["show"]
    title = get_show_display_title(show) if show else "Unknown"
    clean, sn, stype = _extract_title_parts(title)

    info_bits = []
    if sn:
        info_bits.append(f"Season {sn}")
    summary = _playback_episode_summary(show, s)
    if summary:
        info_bits.append(summary)
    ep_str = " \u2022 ".join(info_bits)

    si = s.get("stream_info", {})
    mirror = si.get("mirror")
    stream_str = ""
    if mirror:
        pref_star = " \u2022 \033[33mPreferred \u2605" if si.get("is_pref") else ""
        stream_str = f"{mirror}{pref_star}\033[0m"

    props = s.get("mpv_props")
    is_playing = props is not None

    content = []

    try:
        from ..app._app_helpers import is_incognito_fn  # lazy import to avoid circular
        if is_incognito_fn and is_incognito_fn():
            content.append("\033[1;33mINCOGNITO\033[0m")
            content.append("")
    except Exception:
        pass

    if is_playing:
        state_str = "\u258c\u258c Paused" if props.get("pause") else "\u25b6 Playing"
        pt_sec = props.get("playback-time", 0) or 0
        dur_sec = props.get("duration", 0) or 0
        rem_sec = dur_sec - pt_sec if dur_sec > 0 else 0

        bar = _thin_progress_bar(pt_sec, dur_sec, w - 4)
        time_line = f"{_fmt_time(pt_sec)} / {_fmt_time(dur_sec)}"
        if dur_sec > 0:
            time_line += f"  \u2022  -{_fmt_time(rem_sec)}"

        content.append("")
        for tl in _wrap_title(clean, w - 4, 2).splitlines():
            content.append(f"\033[1;97m{tl}\033[0m")
        content.append("")
        content.append(f"\033[38;5;248m{ep_str}\033[0m")
        content.append("")
        content.append("\033[38;5;246mCurrently playing\033[0m")
        label = s.get("current_ep_label") or str(s["current_ep"])
        content.append(f"\033[38;5;250mEpisode {label}\033[0m")
        if stream_str:
            content.append(f"\033[38;5;248m{stream_str}\033[0m")
        content.append("")
        content.append(f"\033[1;36m{state_str}\033[0m")
        content.append(bar)
        content.append(f"\033[38;5;250m{time_line}\033[0m")
        detail_lines = []
        genres = show.get("genres") if isinstance(show, dict) else None
        if not genres and isinstance(show, dict):
            genres = show.get("_provider_genres")
        if isinstance(genres, list):
            genre_text = ", ".join(str(item) for item in genres[:5] if item)
        else:
            genre_text = str(genres or "").strip()
        if genre_text:
            detail_lines.append("\033[38;5;246mGenres\033[0m")
            detail_lines.append("\033[38;5;245m" + genre_text.replace(", ", " \u00b7 ") + "\033[0m")
        description = str(show.get("description") or "").strip() if isinstance(show, dict) else ""
        if description:
            description = re.sub(r"<[^>]+>", " ", description)
            description = re.sub(r"\s+", " ", description).strip()
            if detail_lines:
                detail_lines.append("")
            detail_lines.append("\033[38;5;246mDescription\033[0m")
            detail_lines.extend(
                f"\033[38;5;245m{line}\033[0m"
                for line in _wrap_title(description, w - 4, 99).splitlines()
            )
        if detail_lines:
            content.append("")
            content.extend(detail_lines)
        content.append("")
        content.append("\033[38;5;244mQ Quit   Shift+Left Previous   Shift+Right Next\033[0m")
    else:
        content.append("")
        for tl in _wrap_title(clean, w - 4, 2).splitlines():
            content.append(f"\033[1;97m{tl}\033[0m")
        content.append("")
        content.append(f"\033[38;5;248m{ep_str}\033[0m")
        content.append("")
        content.append("\033[38;5;246mStatus\033[0m")
        content.append("\033[1;36mLoading stream...\033[0m")
        content.append("")
        for sl in s["status_lines"]:
            content.append(sl)

    # --- Poster ---
    poster_raw = ""
    if poster_manager is not None and show:
        if ui is not None:
            ui.hovered_show_id = show.get("_id") or show.get("id")
            ui.hovered_show_obj = show
        poster_raw = poster_manager.get(show) or ""

    native_poster = poster_raw if _poster_uses_native_protocol(poster_raw) else ""
    poster_key = (
        hashlib.sha256(poster_raw.encode("utf-8", errors="ignore")).hexdigest()
        if poster_raw
        else None
    )
    poster_changed = poster_key != s.get("_last_poster_key")
    s["_last_poster_key"] = poster_key
    if native_poster and poster_changed:
        terminal_images.mark_active()
    poster_lines = _poster_symbol_lines(poster_raw, POSTER_HEIGHT, w)
    out = []

    if poster_raw:
        for row in range(POSTER_HEIGHT):
            if poster_changed:
                line = poster_lines[row] if row < len(poster_lines) else ""
                out.append(f"\033[2K{line}")
            else:
                out.append("")

    for line in content:
        out.append(f"\033[2K{_fit_terminal_line(line, w)}")

    if out:
        clear_images = ""
        if not s.get("_cleared_terminal_image"):
            clear_images = terminal_images.clear_if_active()
            s["_cleared_terminal_image"] = True
        overlay = f"\033[1;1H{native_poster}" if native_poster and poster_changed else ""
        sys.stdout.write(
            clear_images + "\033[H" + "\r\n".join(out) + "\033[J"
            + overlay + "\033[1;1H\033[?25l"
        )
        sys.stdout.flush()


def update_mpv_props(props: dict | None) -> None:
    """Store the latest mpv property snapshot and trigger a redraw.

    Called from the ``MpvIpc`` redraw callback.
    """
    _player_ui_state["mpv_props"] = props
    render()

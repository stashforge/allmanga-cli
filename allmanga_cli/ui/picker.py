"""
Bottom-anchored TUI picker for allmanga-cli.

Extracted from ``app.py`` so that the picker lives with the other ``ui/``
modules.  The only structural change is that the four ``globals()`` reads
have been replaced by explicit ``flags: CliFlags`` and ``ui: UiState``
parameters:

* ``globals()["SHOW_IMAGE"]``            → ``flags.show_image``
* ``globals()["_hovered_show_id"]``      → ``ui.hovered_show_id``
* ``globals()["_active_picker_query"]``  → ``ui.active_picker_query``
* ``globals()["_needs_redraw"]``         → module-level ``_needs_redraw``
  (still a plain bool, but owned here rather than in ``app.py``)

All other logic is **preserved exactly** from the original.
"""

from __future__ import annotations

import hashlib
import os
import select
import signal
import sys
import termios
import time
import tty
from typing import TYPE_CHECKING, Callable, Optional

from ..core.terminal import (
    absolute_terminal_frame as _absolute_terminal_frame,
    bottom_align_panel_lines as _bottom_align_panel_lines,
    display_width as _display_width,
    fit_terminal_line as _fit_terminal_line,
    picker_vertical_layout as _picker_vertical_layout,
    strip_ansi as _strip_ansi,
    truncate_display as _truncate_display,
)
from .covers import (
    POSTER_HEIGHT,
    POSTER_WIDTH,
    poster_symbol_lines as _poster_symbol_lines,
    poster_uses_native_protocol as _poster_uses_native_protocol,
)
from .fallback import fallback_pick as fallback_tui_pick
from .picker_render import (
    get_key as _get_key,
    loading_frame as _loading_frame,
    loading_line as _loading_line,
    match as _match,
    render_item as _render_item,
)
from . import terminal_images

if TYPE_CHECKING:
    from ..context import CliFlags, UiState

# ---------------------------------------------------------------------------
# Colours (Catppuccin-inspired, matching original fzf theme)
# ---------------------------------------------------------------------------
_C_NORMAL  = "\033[38;5;252m"           # #cccccc  normal item text
_C_SEL     = "\033[1;97m"               # bright-white bold  selected item
_C_PTR     = "\033[38;2;243;139;168m"   # #f38ba8  pink pointer ❯
_C_PROMPT  = "\033[38;2;203;166;247m"   # #cba6f7  mauve prompt
_C_MATCH   = "\033[38;2;137;180;250m"   # #89b4fa  blue match highlight
_C_QUERY   = "\033[38;2;137;220;235m"   # #89dceb  teal query text
_C_HINT    = "\033[38;5;244m"           # #888888  dim hints / footer
_C_COUNT   = "\033[38;5;244m"           # same dim for count
_C_SCROLLI = "\033[38;2;243;139;168m"   # pink scroll indicators
_RST       = "\033[0m"

# ---------------------------------------------------------------------------
# Module-level redraw flag (was globals()["_needs_redraw"] in app.py)
# ---------------------------------------------------------------------------
_needs_redraw: bool = True


def _handle_sigwinch(signum, frame) -> None:
    global _needs_redraw
    _needs_redraw = True


try:
    signal.signal(signal.SIGWINCH, _handle_sigwinch)
except Exception:
    pass


# ---------------------------------------------------------------------------
# Public picker
# ---------------------------------------------------------------------------

def tui_pick(
    flags: "CliFlags",
    ui: "UiState",
    prompt,
    options,
    header: str = "",
    hints=None,
    live_fn=None,
    header_fn=None,
    top_header_fn=None,
    tab_fn=None,
    reverse_fn=None,
    delete_fn=None,
    right_fn=None,
    info_fn=None,
    return_query_on_enter: bool = False,
    query_history=None,
    hide_separator: bool = False,
    initial_query: str = "",
    is_search: bool = False,
    help_dict=None,
    auto_select_single_when_done: bool = False,
    keep_cursor_hidden_on_select: bool = False,
    count_total=None,
    disabled_indices=None,
    reverse_items=True,
    tick_fn=None,
):
    """Bottom-anchored alt-screen picker with flipped (bottom-up) item list.

    Parameters
    ----------
    flags:
        Read-only CLI flags (used to check ``show_image``).
    ui:
        Mutable UI state; the picker writes ``active_picker_query`` and
        reads ``hovered_show_id`` for poster rendering.
    prompt:
        Title string or zero-argument callable that returns a string.
    options:
        List of string option labels.

    Returns
    -------
    int | str
        * ``≥0``  — index of the selected option.
        * ``-2``  — Esc pressed.
        * ``-3``  — Left arrow pressed.
        * ``-4``  — No options (live search finished with empty results).
        * ``str`` — when *return_query_on_enter* is True.
    """
    global _needs_redraw

    def current_prompt() -> str:
        return str(prompt() if callable(prompt) else prompt)

    def fallback_pick():
        return fallback_tui_pick(
            current_prompt(),
            options,
            return_query_on_enter=return_query_on_enter,
            initial_query=initial_query,
        )

    tty_fd = -1
    tty_file = None
    try:
        tty_fd = os.open("/dev/tty", os.O_RDWR)
        tty_file = os.fdopen(tty_fd, "rb+", buffering=0)
        tty_fd = tty_file.fileno()
    except OSError:
        if tty_file:
            try:
                tty_file.close()
            except Exception:
                pass
            tty_file = None
        if tty_fd >= 0:
            os.close(tty_fd)
        return fallback_pick()

    try:
        old_attrs = termios.tcgetattr(tty_fd)
    except Exception:
        try:
            tty_file.close()
        except Exception:
            pass
        return fallback_pick()

    # Enter alt screen (caller's enter_alt_screen may have already done this;
    # the double write is harmless because it is idempotent)
    sys.stdout.write("\033[?1049h\033[2J\033[?25l")
    sys.stdout.flush()
    try:
        from . import display as _display
        _display.set_alt_screen_active(True)
    except Exception:
        pass

    query      = initial_query
    cursor_pos = len(query)
    sel        = 0
    scroll     = 0
    history_idx = -1
    cur_header  = header_fn(0) if header_fn else header
    show_help   = False
    last_poster_tick = 0
    last_poster_key  = None
    last_clock_minute = int(time.time() // 60)
    pending_delete_index = None
    disabled_indices = set(disabled_indices or ())
    try:
        last_terminal_size = os.get_terminal_size(tty_fd)
    except OSError:
        last_terminal_size = None

    def filt_list():
        if not query:
            return list(range(len(options)))
        return [
            i for i, o in enumerate(options)
            if _match(query, _strip_ansi(o)) is not None
        ]

    def first_selectable(filt):
        for pos, option_index in enumerate(filt):
            if option_index not in disabled_indices:
                return pos
        return 0

    def move_selection(filt, current, delta):
        if not filt:
            return 0
        selectable = [
            pos for pos, option_index in enumerate(filt)
            if option_index not in disabled_indices
        ]
        if not selectable:
            return 0
        if current not in selectable:
            return selectable[0]
        current_pos = selectable.index(current)
        return selectable[(current_pos + delta) % len(selectable)]

    def render(filt):
        nonlocal scroll, last_poster_key

        try:
            sz = os.get_terminal_size(tty_fd)
            rows, cols = sz.lines, sz.columns
        except OSError:
            rows, cols = 24, 80

        if show_help and help_dict:
            last_poster_key = None
            out = []
            out.append(terminal_images.clear_now())
            out.append("\033[2K")
            out.append(f"\033[2K  {_C_HINT}=== Keyboard Shortcuts ==={_RST}")
            out.append("\033[2K")
            for k, v in help_dict.items():
                out.append(f"\033[2K  {_C_PTR}{k:<15}{_RST} {v}")
            out.append("\033[2K")
            out.append(f"\033[2K  {_C_HINT}Press Esc or ? to close{_RST}")
            padding = rows - len(out)
            for _ in range(padding):
                out.append("\033[2K")
            buf = _absolute_terminal_frame(out, rows, cols)
            tty_file.write(buf.encode())
            tty_file.flush()
            return

        actual_top_header = None
        if top_header_fn is not None and filt:
            sel_idx = filt[sel] if sel < len(filt) else -1
            actual_top_header = top_header_fn(sel_idx)

        actual_header = cur_header
        if header_fn is not None:
            sel_idx = filt[sel] if (filt and sel < len(filt)) else -1
            # ← was: globals()["_active_picker_query"] = query
            ui.active_picker_query = query
            actual_header = header_fn(sel_idx)
        header_lines = actual_header.splitlines() if actual_header else []
        if pending_delete_index is not None:
            confirm_line = "\033[38;5;220mDelete this history entry? y/N\033[0m"
            if header_lines:
                header_lines[-1] = confirm_line
            else:
                header_lines = [confirm_line]
        header_n = max(4, len(header_lines)) if header_fn is not None else len(header_lines)

        # ← was: show_img = globals().get("SHOW_IMAGE", False)
        show_img = flags.show_image

        is_tmx = (
            os.environ.get("PREFIX", "").startswith("/data/data/com.termux")
            or os.path.exists("/data/data/com.termux")
        )
        top_header_n = (9 if is_tmx else 8) if (show_img and top_header_fn is not None) else 0
        top_margin   = 1 if top_header_n > 0 else 0

        GAP   = 0
        fixed = top_margin + 1 + header_n + top_header_n + GAP

        if rows - fixed < 10 and top_header_n > 0:
            top_header_n = 0
            top_margin   = 0
            GAP          = 0
            fixed        = 1 + header_n

        max_vis, _, _ = _picker_vertical_layout(
            rows, header_n, top_header_n, top_margin, GAP, len(filt)
        )

        if filt:
            if sel < scroll:
                scroll = sel
            elif sel >= scroll + max_vis:
                scroll = sel - max_vis + 1

        out = []

        visible     = filt[scroll:scroll + max_vis] if filt else []
        items_shown = len(visible)
        item_max_w  = max(20, cols - 3)

        _, _, padding = _picker_vertical_layout(
            rows, header_n, top_header_n, top_margin, GAP, items_shown
        )
        for _ in range(padding):
            out.append("\033[2K")

        poster_key   = None
        native_poster = ""
        poster_row   = None

        if top_header_n > 0:
            poster_raw   = actual_top_header or ""
            poster_lines = _poster_symbol_lines(poster_raw, top_header_n, cols)
            poster_row   = len(out) + 1
            poster_key   = (
                # ← was: globals().get("_hovered_show_id")
                ui.hovered_show_id,
                hashlib.sha256(poster_raw.encode("utf-8", errors="ignore")).hexdigest(),
                poster_row,
                top_header_n,
                cols,
            )
            native_poster = poster_raw if _poster_uses_native_protocol(poster_raw) else ""
            for row in range(top_header_n):
                line = poster_lines[row] if row < len(poster_lines) else ""
                out.append(f"\033[2K{line}")

        for _ in range(top_margin):
            out.append("\033[2K")
        for _ in range(GAP):
            out.append("\033[2K")

        item_positions = (
            range(items_shown - 1, -1, -1)
            if reverse_items else range(items_shown)
        )
        for vi in item_positions:
            oi     = visible[vi]
            is_sel = (scroll + vi == sel)
            disabled = oi in disabled_indices
            if disabled:
                label = _truncate_display(str(options[oi] or ""), cols)
                out.append(f"\033[2K{_fit_terminal_line(label, cols)}")
                continue
            ptr    = f"{_C_PTR}\u276f{_RST}" if is_sel and not disabled else " "
            label  = _render_item(options[oi], query, is_sel, max_w=item_max_w)
            hint   = ""
            if is_sel and hints:
                kp = _strip_ansi(options[oi])
                for k, v in hints.items():
                    if _strip_ansi(k) == kp:
                        hint_text = str(v)
                        if hint_text.strip().lower() != kp.strip().lower():
                            hint_w = max(
                                0,
                                cols - _display_width(ptr) - 2
                                - _display_width(label) - 2,
                            )
                        else:
                            hint_w = 0
                        if hint_w > 0:
                            hint = f"  {_C_HINT}{_truncate_display(hint_text, hint_w)}{_RST}"
                        break
            out.append(f"\033[2K{_fit_terminal_line(f'{ptr} {label}{hint}', cols)}")

        if is_search:
            q_left  = query[:cursor_pos]
            q_char  = query[cursor_pos] if cursor_pos < len(query) else " "
            q_right = query[cursor_pos + 1:]
            styled_query = f"{q_left}\033[7m{q_char}\033[27m{q_right}"
            pstr = f"{_C_PROMPT}{current_prompt()} \u276f{_RST} {_C_QUERY}{styled_query}{_RST}"
        else:
            pstr = f"{_C_PROMPT}{current_prompt()} \u276f{_RST} {_C_QUERY}{query}{_RST}"

        if hide_separator or len(options) == 0:
            out.append(f"\033[2K{_fit_terminal_line(pstr, cols)}")
        else:
            total_count = count_total() if callable(count_total) else count_total
            total_count = len(options) if total_count is None else total_count
            filtered_count = (
                sum(1 for option_index in filt if option_index not in disabled_indices)
                if disabled_indices else len(filt)
            )
            cstr = f"{_C_COUNT}{filtered_count}/{total_count}{_RST}"
            hidden_below = scroll
            hidden_above = max(0, len(filt) - scroll - max_vis)
            si = ""
            if hidden_above > 0: si += f"\u25b2{hidden_above} "
            if hidden_below > 0: si += f"\u25bc{hidden_below} "
            if si: si = f" {_C_SCROLLI}{si}{_RST}"
            left_str = f"{pstr}  {cstr}{si}"
            used     = _display_width(left_str)
            sep_w    = max(1, cols - used - 2)
            sep      = f" {_C_HINT}{'\u2500' * sep_w}{_RST}"
            out.append(f"\033[2K{_fit_terminal_line(f'{pstr}  {cstr}{si}{sep}', cols)}")

        for line in _bottom_align_panel_lines(header_lines, header_n):
            if not line:
                out.append("\033[2K")
            else:
                out.append(f"\033[2K{_fit_terminal_line(line, cols)}")

        poster_changed = poster_key != last_poster_key
        clear_prefix = (
            terminal_images.clear_now() + "\033[2J"
            if poster_changed and (poster_key is not None or last_poster_key is not None)
            else ""
        )
        last_poster_key = poster_key
        overlay = ""
        if poster_changed and native_poster and poster_row is not None:
            terminal_images.mark_active()
            overlay = f"\033[{poster_row};1H{native_poster}"
        frame = _absolute_terminal_frame(out, rows, cols)
        buf = (
            f"{clear_prefix}\033[?25l"
            + frame
            + overlay
            + "\033[1;1H\033[?25l"
        )
        tty_file.write(buf.encode())
        tty_file.flush()

    # -----------------------------------------------------------------------
    # Main event loop
    # -----------------------------------------------------------------------
    try:
        tty_file.write((terminal_images.clear_if_active() + "\033[2J\033[?25l").encode())
        tty_file.flush()
        tty.setraw(tty_fd)
        termios.tcflush(tty_fd, termios.TCIFLUSH)

        filt   = filt_list()
        sel    = first_selectable(filt)
        result = -2

        if (
            live_fn is None
            and len(options) == 0
            and not return_query_on_enter
            and tab_fn is None
        ):
            result = -4
            return result

        _needs_redraw = True
        live_done = live_fn is None

        while True:
            clock_minute = int(time.time() // 60)
            if clock_minute != last_clock_minute:
                last_clock_minute = clock_minute
                _needs_redraw = True

            try:
                terminal_size = os.get_terminal_size(tty_fd)
            except OSError:
                terminal_size = None
            if terminal_size != last_terminal_size:
                last_terminal_size = terminal_size
                _needs_redraw = True

            if live_fn is not None:
                new_opts, new_hdr, _done = live_fn(query)
                live_done = bool(_done)
                if new_opts != options:
                    options.clear()
                    options.extend(new_opts)
                    filt = filt_list()
                    _needs_redraw = True
                if cur_header != new_hdr:
                    cur_header = new_hdr
                    _needs_redraw = True

                if _done and auto_select_single_when_done and len(options) == 1:
                    result = 0
                    break

                if _done and len(options) == 0:
                    result = -4
                    break

            sel = max(0, min(sel, len(filt) - 1)) if filt else 0
            if filt and filt[sel] in disabled_indices:
                sel = first_selectable(filt)

            now = time.time()
            if tick_fn is not None and tick_fn() and now - last_poster_tick >= 0.1:
                last_poster_tick = now
                _needs_redraw = True
            elif flags.show_image and top_header_fn is not None and filt:
                sel_idx = filt[sel] if sel < len(filt) else -1
                if 0 <= sel_idx < len(options):
                    show_obj = ui.hovered_show_obj
                    if _poster_needs_tick(show_obj) and now - last_poster_tick >= 0.1:
                        last_poster_tick = now
                        _needs_redraw = True

            if _needs_redraw:
                render(filt)
                _needs_redraw = False

            try:
                ready = select.select([tty_fd], [], [], 0.05)[0]
            except InterruptedError:
                continue

            if not ready:
                continue

            key = _get_key(tty_fd)
            termios.tcflush(tty_fd, termios.TCIFLUSH)
            _needs_redraw = True

            if pending_delete_index is not None:
                if key in ("y", "Y"):
                    if delete_fn:
                        res = delete_fn(pending_delete_index)
                        if res:
                            options, cur_header = res[0], res[1]
                            filt = filt_list()
                            sel = max(0, min(sel, len(filt) - 1)) if filt else 0
                    pending_delete_index = None
                    continue
                pending_delete_index = None
                if key in ("n", "N", "ESC", "CTRL_C"):
                    if key == "CTRL_C":
                        raise KeyboardInterrupt
                    continue

            if key == "UP":
                if filt:
                    sel = move_selection(
                        filt, sel, -1 if not reverse_items else 1
                    )
                elif query_history:
                    history_idx = min(history_idx + 1, len(query_history) - 1)
                    if history_idx >= 0:
                        query = query_history[history_idx]
                        cursor_pos = len(query)
                        filt = filt_list()
            elif key == "DOWN":
                if filt:
                    sel = move_selection(
                        filt, sel, 1 if not reverse_items else -1
                    )
                elif query_history:
                    history_idx = max(history_idx - 1, -1)
                    if history_idx >= 0:
                        query = query_history[history_idx]
                    else:
                        query = ""
                    cursor_pos = len(query)
                    filt = filt_list()
            elif key == "HOME":
                sel = first_selectable(filt); scroll = 0
            elif key == "END":
                sel = first_selectable(list(reversed(filt)))
                if filt:
                    sel = len(filt) - 1 - sel
            elif key in ("ENTER", "RIGHT"):
                if is_search and key == "RIGHT":
                    if cursor_pos < len(query): cursor_pos += 1
                    _needs_redraw = True
                    continue
                if live_fn is not None and not live_done and not filt:
                    continue
                if return_query_on_enter:
                    result = query
                    break
                if not filt:
                    continue
                if filt[sel] in disabled_indices:
                    continue
                result = filt[sel]
                break
            elif key == "?" and help_dict:
                show_help = not show_help
            elif key == "ESC":
                if show_help:
                    show_help = False
                else:
                    result = -2; break
            elif key == "CTRL_C":
                raise KeyboardInterrupt
            elif key == "LEFT":
                if is_search:
                    if cursor_pos > 0: cursor_pos -= 1
                    _needs_redraw = True
                else:
                    result = -3; break
            elif key == "BACKSPACE":
                if is_search:
                    if cursor_pos > 0:
                        query = query[:cursor_pos - 1] + query[cursor_pos:]
                        cursor_pos -= 1
                        filt = filt_list(); sel = first_selectable(filt); scroll = 0
                else:
                    query = query[:-1]; filt = filt_list(); sel = first_selectable(filt); scroll = 0
                    cursor_pos = len(query)
            elif key == "CTRL_U":
                query = ""; filt = filt_list(); sel = first_selectable(filt); scroll = 0
                cursor_pos = 0
            elif key in ("TAB", "CTRL_N"):
                if tab_fn:
                    selected = filt[sel] if filt and sel < len(filt) else None
                    try:
                        res = tab_fn(selected, direction=1)
                    except TypeError:
                        res = tab_fn(selected)
                    if res:
                        options, cur_header = res[0], res[1]
                        if len(res) > 2:
                            disabled_indices.clear()
                            disabled_indices.update(res[2] or ())
                        filt = filt_list()
                        sel  = first_selectable(filt)
            elif key in ("SHIFT_TAB", "CTRL_P"):
                if tab_fn:
                    selected = filt[sel] if filt and sel < len(filt) else None
                    try:
                        res = tab_fn(selected, direction=-1)
                    except TypeError:
                        res = tab_fn(selected)
                    if res:
                        options, cur_header = res[0], res[1]
                        if len(res) > 2:
                            disabled_indices.clear()
                            disabled_indices.update(res[2] or ())
                        filt = filt_list()
                        sel  = first_selectable(filt)
            elif key == "CTRL_R":
                if reverse_fn:
                    selected = filt[sel] if filt and sel < len(filt) else None
                    res = reverse_fn(selected)
                    if res:
                        options, cur_header = res[0], res[1]
                        if len(res) > 2:
                            disabled_indices.clear()
                            disabled_indices.update(res[2] or ())
                        filt = filt_list()
                        sel  = first_selectable(filt)
            elif key in ("DELETE", "CTRL_D"):
                if delete_fn and filt:
                    pending_delete_index = filt[sel]
            elif key == "CTRL_O":
                if info_fn is not None and filt and sel < len(filt) and filt[sel] not in disabled_indices:
                    info_fn(filt[sel])
                    last_poster_key = None
                    _needs_redraw = True
            elif key != "UNKNOWN":
                if len(key) == 1 and key.isprintable():
                    if is_search:
                        query = query[:cursor_pos] + key + query[cursor_pos:]
                        cursor_pos += 1
                    else:
                        query += key
                        cursor_pos = len(query)
                    filt = filt_list(); sel = first_selectable(filt); scroll = 0

    finally:
        termios.tcsetattr(tty_fd, termios.TCSADRAIN, old_attrs)
        # Cursor restoration is handled by the global atexit / finally block in
        # app.py to prevent cursor flickering during rapid screen transitions.
        tty_file.flush()
        try:
            tty_file.close()
        except Exception:
            pass

    return result


def _poster_needs_tick(show_obj) -> bool:
    """Return True if the poster for *show_obj* may need a frame tick.

    This is a thin re-export of the PosterManager helper so that ``tui_pick``
    does not need to import PosterManager directly.  It is wired up by
    ``app.py`` after the PosterManager instance is created.
    """
    # Default: never tick (overridden by app.py via _set_poster_tick_fn)
    return False


_poster_tick_fn: Optional[Callable] = None


def _set_poster_tick_fn(fn: Callable) -> None:
    """Register the PosterManager.needs_tick function for use inside tui_pick."""
    global _poster_needs_tick, _poster_tick_fn
    _poster_tick_fn = fn

    def _poster_needs_tick(show_obj) -> bool:  # type: ignore[misc]
        return bool(_poster_tick_fn and _poster_tick_fn(show_obj))

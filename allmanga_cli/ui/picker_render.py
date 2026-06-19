"""Stateless picker key decoding and item rendering."""

import os
import select

from ..core.terminal import sanitize_terminal_text, truncate_display
from .spinner import loading_line, spinner_frame


NORMAL = "\033[38;5;252m"
SELECTED = "\033[1;97m"
MATCH = "\033[38;2;137;180;250m"
RESET = "\033[0m"


def loading_frame(style=None):
    return spinner_frame(style)


def get_key(descriptor):
    char = os.read(descriptor, 1)
    if char == b"\x1b":
        if select.select([descriptor], [], [], 0.2)[0]:
            second = os.read(descriptor, 1)
            if second in (b"[", b"O"):
                third = os.read(descriptor, 1)
                if third == b"A":
                    return "UP"
                if third == b"B":
                    return "DOWN"
                if third == b"C":
                    return "RIGHT"
                if third == b"D":
                    return "LEFT"
                if second == b"[" and third == b"Z":
                    return "SHIFT_TAB"
                if third == b"H":
                    return "HOME"
                if third == b"F":
                    return "END"
                rest = third
                while not (b"\x40" <= rest[-1:] <= b"\x7e"):
                    rest += os.read(descriptor, 1)
                if rest == b"3~":
                    return "DELETE"
                return "UNKNOWN"
            return "ESC"
        return "ESC"
    if char in (b"\r", b"\n"):
        return "ENTER"
    if char in (b"\x7f", b"\x08"):
        return "BACKSPACE"
    if char == b"\x03":
        return "CTRL_C"
    if char == b"\x04":
        return "CTRL_D"
    if char == b"\x0e":
        return "CTRL_N"
    if char == b"\x10":
        return "CTRL_P"
    if char == b"\x12":
        return "CTRL_R"
    if char == b"\x15":
        return "CTRL_U"
    if char == b"\t":
        return "TAB"
    return char.decode("utf-8", errors="ignore")


def match(query, text):
    if not query:
        return 0, 0
    start = text.lower().find(query.lower())
    if start == -1:
        return None
    return start, start + len(query)


def clear_terminal_images():
    return "\033_Ga=d\x1b\\"


def render_item(raw, query, selected, max_w=0):
    plain = sanitize_terminal_text(raw)
    if max_w > 0:
        plain = truncate_display(plain, max_w)
    dimmed = "\033[38;5;244m" in raw or "\033[2m" in raw
    if selected:
        base = SELECTED
    elif dimmed:
        base = "\033[38;5;244m"
    else:
        base = NORMAL

    if not query:
        return f"{base}{plain}{RESET}"
    found = match(query, plain)
    if found is None:
        return f"{base}{plain}{RESET}"
    start, end = found
    if start == end:
        return f"{base}{plain}{RESET}"
    highlight = MATCH if not selected else "\033[1;97m\033[4m"
    return (
        f"{base}{plain[:start]}{RESET}"
        f"{highlight}{plain[start:end]}{RESET}"
        f"{base}{plain[end:]}{RESET}"
    )

"""Terminal-safe text and display-width helpers."""

import re
import unicodedata


_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_TERMINAL_STRING_RE = re.compile(
    r"\x1b(?:\].*?(?:\x07|\x1b\\)|[P^_].*?\x1b\\)",
    re.DOTALL,
)


def sanitize_terminal_text(value):
    text = str(value or "")
    text = _TERMINAL_STRING_RE.sub("", text)
    text = _ANSI_RE.sub("", text)
    text = "".join(
        " " if ord(ch) < 32 or 127 <= ord(ch) <= 159 else ch
        for ch in text
    )
    return re.sub(r"\s+", " ", text).strip()


def strip_ansi(value):
    return sanitize_terminal_text(value)


def char_width(char):
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("F", "W") else 1


def display_width(value):
    return sum(char_width(char) for char in strip_ansi(str(value or "")))


def truncate_display(value, max_width):
    value = str(value or "")
    if max_width <= 0 or display_width(value) <= max_width:
        return value

    output = []
    used = 0
    index = 0
    while index < len(value):
        match = _ANSI_RE.match(value, index)
        if match:
            output.append(match.group(0))
            index = match.end()
            continue

        char = value[index]
        width = char_width(char)
        if used + width + 1 > max_width:
            break
        output.append(char)
        used += width
        index += 1
    return "".join(output) + "…"


def split_display_prefix(value, max_width):
    value = str(value or "")
    if max_width <= 0:
        return "", value

    output = []
    used = 0
    for index, char in enumerate(value):
        width = char_width(char)
        if used + width > max_width:
            return "".join(output), value[index:]
        output.append(char)
        used += width
    return "".join(output), ""

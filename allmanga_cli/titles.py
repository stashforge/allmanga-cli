"""Title selection, alternate-title choice, and display wrapping."""

import re

from .terminal import (
    display_width,
    sanitize_terminal_text,
    split_display_prefix,
    truncate_display,
)


def wrap_title(text, columns, max_lines=2):
    """Wrap text within a fixed number of terminal display rows."""
    if display_width(text) <= columns:
        return text
    lines = []
    remaining = text
    for index in range(max_lines):
        if not remaining:
            break
        if index == max_lines - 1:
            lines.append(truncate_display(remaining, columns))
        else:
            line, remaining = split_display_prefix(remaining, columns)
            lines.append(line)
    return "\n".join(lines)


def extract_title_parts(title):
    """Return clean title, season number, and trailing show type."""
    if not title:
        return "", "", ""
    title = str(title)
    show_type = ""
    match = re.search(r"\s*\(([A-Z][A-Za-z ]+)\)\s*$", title)
    if match:
        show_type = match.group(1)
        title = title[:match.start()].strip()

    season = ""
    match = re.search(
        r"(?i)\s*(?::?\s*|-\s*)season\s*(\d+)(?:[:\-]?\s*.*)?$",
        title,
    )
    if match:
        season = match.group(1)
        title = title[:match.start()].strip()
    else:
        match = re.search(
            r"(?i)\s*(?::?\s*|-\s*)(\d+)(?:st|nd|rd|th)\s+season\s*$",
            title,
        )
        if match:
            season = match.group(1)
            title = title[:match.start()].strip()
    return title, season, show_type


def get_display_titles(show, main_title):
    romaji = show.get("name")
    if romaji:
        romaji = romaji.strip()
    english = show.get("englishName")
    if english:
        english = english.strip()

    alternate = ""
    if english and romaji and english.lower() != romaji.lower():
        alternate = (
            romaji if main_title.lower() == english.lower() else english
        )

    if not alternate and show.get("altNames"):
        excluded = main_title.lower()
        candidates = [
            name.strip()
            for name in show["altNames"]
            if name and name.strip().lower() != excluded
        ]
        non_latin = re.compile(r"[^\x00-\x7F]")
        romaji_pattern = re.compile(
            r"\b(no|wo|wa|ga|ni|de|to|na|shi|tsu|chi|shita|datta|"
            r"naru|suru|kara)\b",
            re.IGNORECASE,
        )
        pinyin_pattern = re.compile(
            r"\b(dou|po|cang|qiong|nian|fan|zhi|lan|yuan|qi|sha|xiao|"
            r"zhan|chen|tang|yao|xuan|jing|feng|lei|ming|hong|ling|"
            r"wang|liu|zhang|yang|wei|jun|xue|long|shen|wu|zhou|dao|"
            r"tian|bei|nan|dong|xi)\b",
            re.IGNORECASE,
        )
        english_titles = []
        romaji_titles = []
        pinyin_titles = []
        native_titles = []
        for name in candidates:
            if non_latin.search(name):
                native_titles.append(name)
            elif romaji_pattern.search(name):
                romaji_titles.append(name)
            elif pinyin_pattern.search(name):
                pinyin_titles.append(name)
            else:
                english_titles.append(name)
        if english_titles:
            alternate = english_titles[0]
        elif romaji_titles:
            alternate = romaji_titles[0]
        elif pinyin_titles:
            alternate = pinyin_titles[0]
        elif native_titles:
            alternate = native_titles[0]

    if not alternate:
        native = show.get("nativeName")
        if native and native.strip().lower() != main_title.lower():
            alternate = native.strip()
    return sanitize_terminal_text(alternate)


def get_show_display_title(show, fallback="Unknown", sync_enabled=None):
    if not show:
        return sanitize_terminal_text(fallback)
    if show.get("_anilist_context"):
        sync_enabled = True
    if sync_enabled is None:
        sync_enabled = bool(show.get("_sync_enabled"))
    if sync_enabled:
        title = show.get("_display_name") or show.get("name") or fallback
    else:
        title = show.get("_allanime_name") or show.get("name") or fallback
    return sanitize_terminal_text(title)

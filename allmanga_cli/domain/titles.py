"""Title selection, alternate-title choice, and display wrapping."""

import re

from ..core.terminal import (
    display_width,
    sanitize_terminal_text,
    split_display_prefix,
    truncate_display,
)


def wrap_title(text, columns, max_lines=2):
    """Wrap text within a fixed number of terminal display rows, word-aware."""
    if display_width(text) <= columns:
        return text

    lines = []
    for paragraph in str(text).splitlines():
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
            
        current_line = []
        current_width = 0
        
        for word in words:
            word_width = display_width(word)
            space_width = 1 if current_line else 0
            
            if current_width + space_width + word_width > columns:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = []
                    current_width = 0
                
                while display_width(word) > columns:
                    w_line, word = split_display_prefix(word, columns)
                    lines.append(w_line)
                
                if word:
                    current_line.append(word)
                    current_width = display_width(word)
            else:
                current_line.append(word)
                current_width += space_width + word_width
                
        if current_line:
            lines.append(" ".join(current_line))

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last_line = lines[-1]
        if display_width(last_line) < columns:
            lines[-1] = last_line + "…"
        else:
            w_line, _ = split_display_prefix(last_line, columns - 1)
            lines[-1] = w_line + "…"

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
    romaji = show.get("_display_name") or show.get("name")
    if romaji:
        romaji = romaji.strip()
    english = show.get("_display_english_name") or show.get("englishName")
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
        ROMAJI_TOKENS = {
            "wo", "ga", "ni", "shi", "tsu", "chi", "shita", "datta",
            "naru", "suru", "kara", "desu", "masu", "dewa", "yori", "wa",
        }
        PINYIN_TOKENS = {
            "dou", "po", "cang", "qiong", "nian", "fan", "zhi", "lan",
            "yuan", "qi", "sha", "xiao", "zhan", "chen", "tang", "yao",
            "xuan", "jing", "feng", "lei", "ming", "hong", "ling", "wang",
            "liu", "zhang", "yang", "wei", "jun", "xue", "long", "shen",
            "wu", "zhou", "dao", "tian", "bei", "nan", "dong", "xi",
        }
        ENGLISH_STOPWORDS = {
            "the", "a", "an", "of", "and", "in", "on", "with", "for", "to",
            "is", "are", "was", "were", "my", "your", "his", "her", "their",
            "this", "that", "at", "from", "as", "it", "he", "she", "we",
        }

        non_latin = re.compile(r"[^\x00-\x7F]")
        word_re = re.compile(r"[a-zA-Z']+")

        def classify(name: str) -> str:
            if non_latin.search(name):
                return "native"

            words = [w.lower() for w in word_re.findall(name)]
            if not words:
                return "english"

            stop_hits   = sum(w in ENGLISH_STOPWORDS for w in words)
            romaji_hits = sum(w in ROMAJI_TOKENS for w in words)
            pinyin_hits = sum(w in PINYIN_TOKENS for w in words)

            if stop_hits >= 2 and stop_hits >= max(romaji_hits, pinyin_hits):
                return "english"

            if romaji_hits >= 2 and romaji_hits / len(words) >= 0.25:
                return "romaji"
            if pinyin_hits >= 2 and pinyin_hits / len(words) >= 0.25:
                return "pinyin"

            return "english"

        buckets = {"english": [], "romaji": [], "pinyin": [], "native": []}
        for name in candidates:
            buckets[classify(name)].append(name)

        for bucket in buckets.values():
            bucket.sort(key=len, reverse=True)

        for key in ("english", "romaji", "pinyin", "native"):
            if buckets[key]:
                alternate = buckets[key][0]
                break

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

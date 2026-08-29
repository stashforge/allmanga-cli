"""Episode catalog normalization and index helpers."""

import decimal
import re


def normalize_episode_ids(values):
    episode_ids = []
    seen = set()
    for value in values or []:
        episode_id = str(value).strip()
        if not episode_id or episode_id in seen:
            continue
        episode_ids.append(episode_id)
        seen.add(episode_id)
    return episode_ids


def is_contiguous_legacy_catalog(episode_ids):
    return episode_ids == [
        str(index) for index in range(1, len(episode_ids) + 1)
    ]


def episode_index_for_id(episode_ids, episode_id, labels=None):
    episode_string = str(episode_id)
    if episode_string in episode_ids:
        return episode_ids.index(episode_string)

    try:
        numeric = decimal.Decimal(episode_string)
    except decimal.InvalidOperation:
        return None

    matches = []
    for index, candidate in enumerate(episode_ids):
        if labels and candidate in labels:
            try:
                if decimal.Decimal(str(labels[candidate])) == numeric:
                    matches.append(index)
                    continue
            except decimal.InvalidOperation:
                pass

        try:
            if decimal.Decimal(str(candidate)) == numeric:
                matches.append(index)
        except decimal.InvalidOperation:
            continue

    if len(matches) == 1:
        return matches[0]

    return None


def episode_id_at(episode_ids, index):
    if not episode_ids or index is None:
        return None
    bounded_index = max(0, min(int(index), len(episode_ids) - 1))
    return episode_ids[bounded_index]


def clean_episode_identifier(raw: str) -> str:
    """Extract a clean episode number, special type, or short label from an identifier, URL, path, or slug."""
    s = str(raw or "").strip()
    if not s:
        return ""

    # 1. Clean number or standard short label like "Episode 1", "EP 1", "1"
    m_std = re.match(r"^(?:(?:ep|episode|part)\s*)?([0-9]+(?:\.[0-9]+)?)$", s, re.I)
    if m_std:
        return m_std.group(1).lstrip("0") or "0"

    m_spec_std = re.match(r"^(?:(ova|movie|special)\s*)([0-9]+(?:\.[0-9]+)?)?$", s, re.I)
    if m_spec_std:
        kind = m_spec_std.group(1).upper()
        num = m_spec_std.group(2)
        return f"{kind} {num}".strip() if num else kind

    # 2. Query parameter like ?ep=5, ?episode=5, ?num=5, ?id=5
    m_query = re.search(r"[?&](?:ep|episode|num|ep_num|episode_num|id)=([0-9]+(?:\.[0-9]+)?)(?:&|$)", s, re.I)
    if m_query:
        return m_query.group(1).lstrip("0") or "0"

    # Strip query parameters, html/php/asp extensions, and trailing slashes
    path = s.split("?")[0].rstrip("/")
    if path.endswith((".html", ".htm", ".php", ".asp", ".aspx")):
        path = path.rsplit(".", 1)[0]

    # Extract slug from path
    slug = path.split("/")[-1] if "/" in path else path

    # 3. Explicit episode patterns like episode-5, ep-5, ep_5, ep.5, ep05
    m = re.search(r"(?:^|[-_.])(?:episode|ep)[-_. ]?([0-9]+(?:\.[0-9]+)?)(?:[-_. ]|$)", slug, re.I)
    if m:
        return m.group(1).lstrip("0") or "0"

    # 4. Special types (OVA / Movie / Special)
    m_spec = re.search(r"(?:^|[-_.])(ova|movie|special)[-_. ]?([0-9]+(?:\.[0-9]+)?)?", slug, re.I)
    if m_spec:
        kind = m_spec.group(1).upper()
        num = m_spec.group(2)
        return f"{kind} {num}".strip() if num else kind

    # 5. Trailing numbers like -05, -5-sub, _05_dub, etc.
    m_num = re.search(r"[-_.]([0-9]+(?:\.[0-9]+)?)(?:[-_.](?:sub|dub|raw|eng|v\d+|end))?$", slug, re.I)
    if m_num:
        return m_num.group(1).lstrip("0") or "0"

    return slug


def episode_label(episode_id, labels=None):
    label = ""
    if labels:
        label = str(labels.get(str(episode_id)) or "").strip()
    if not label:
        label = clean_episode_identifier(str(episode_id or ""))
    label = label or str(episode_id or "")
    lowered = label.casefold()
    if lowered.startswith(("episode ", "ep ", "part ", "ova", "movie", "special")):
        return label
    return f"Episode {label}"


def episode_progress_number(episode_id, fallback=0):
    if not episode_id:
        return fallback
    clean = clean_episode_identifier(str(episode_id))
    try:
        value = decimal.Decimal(clean)
        return max(0, int(value))
    except (decimal.InvalidOperation, ValueError):
        pass
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(episode_id))
    if m:
        try:
            return max(0, int(decimal.Decimal(m.group(1))))
        except (decimal.InvalidOperation, ValueError):
            pass
    if fallback:
        try:
            return max(0, int(fallback))
        except (TypeError, ValueError):
            pass
    return fallback

def highest_episode_number(episode_ids):
    if not episode_ids:
        return 0
    max_val = None
    has_numeric = False
    for eid in episode_ids:
        try:
            val = decimal.Decimal(str(eid))
            if max_val is None or val > max_val:
                max_val = val
            has_numeric = True
        except decimal.InvalidOperation:
            continue
    if not has_numeric:
        return len(episode_ids)
    if max_val % 1 == 0:
        return int(max_val)
    return str(max_val)

def detect_next_episode_gap(current_ep, next_ep):
    if current_ep is None or next_ep is None:
        return False, ""
    try:
        curr = decimal.Decimal(str(current_ep))
        nxt = decimal.Decimal(str(next_ep))
    except decimal.InvalidOperation:
        return False, ""

    if curr % 1 != 0 or nxt % 1 != 0:
        return False, ""

    curr_int = int(curr)
    nxt_int = int(nxt)

    if nxt_int <= curr_int + 1:
        return False, ""

    start_missing = curr_int + 1
    end_missing = nxt_int - 1

    if start_missing == end_missing:
        return True, f"missing {start_missing}"
    return True, f"missing {start_missing}-{end_missing}"

def parse_episode_label(label):
    import decimal
    import math
    try:
        val = decimal.Decimal(str(label))
        if not val.is_finite():
            raise decimal.InvalidOperation
        is_int = (val % 1 == 0)
        return {
            "original": str(label),
            "numeric": val,
            "is_integer_like": is_int,
            "floor": int(math.floor(val)),
            "ceil": int(math.ceil(val))
        }
    except (decimal.InvalidOperation, TypeError, ValueError):
        return {
            "original": str(label),
            "numeric": None,
            "is_integer_like": False,
            "floor": None,
            "ceil": None
        }

def anilist_progress_target_for_episode(label, fallback=0):
    from decimal import Decimal, InvalidOperation, ROUND_FLOOR
    try:
        value = Decimal(str(label))
    except (InvalidOperation, TypeError, ValueError):
        return fallback

    if not value.is_finite():
        return fallback

    return int(value.to_integral_value(rounding=ROUND_FLOOR))

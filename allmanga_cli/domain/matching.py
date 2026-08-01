"""Pure title normalization and provider-match scoring."""

import difflib
import re
import unicodedata

_title_cache = {}


def _cached_match_titles(item):
    key = id(item)
    cached = _title_cache.get(key)
    if cached is None:
        cached = match_titles(item)
        _title_cache[key] = cached
    return cached


def reset_title_cache():
    """Call this once per batch (e.g. start of enrich_provider_results) to
    prevent unbounded growth in long-running processes."""
    _title_cache.clear()


def _positive_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def normalized_match_title(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", text)
    text = text.replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def match_titles(item):
    values = [
        item.get("name"),
        item.get("englishName"),
        item.get("nativeName"),
        *(item.get("altNames") or []),
    ]
    titles = []
    seen = set()
    for value in values:
        title = normalized_match_title(value)
        if title and title not in seen:
            titles.append(title)
            seen.add(title)
        if len(titles) >= 12:
            break
    return titles


def explicit_season_number(titles):
    numbers = set()
    patterns = (
        r"\bseason\s+(\d+)\b",
        r"\b(\d+)\s+season\b",
        r"\bs(\d+)\b",
    )
    for title in titles:
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                numbers.add(int(match.group(1)))
    return next(iter(numbers)) if len(numbers) == 1 else None


def title_match_score(left_titles, right_titles):
    best = 0
    exact = False
    for left in left_titles:
        for right in right_titles:
            left_compact = left.replace(" ", "")
            right_compact = right.replace(" ", "")
            if left == right or left_compact == right_compact:
                best = max(best, 30)
                exact = True
                continue

            shorter = min(len(left_compact), len(right_compact))
            longer = max(len(left_compact), len(right_compact))
            if shorter >= 6 and (
                left_compact in right_compact
                or right_compact in left_compact
            ):
                coverage = shorter / max(1, longer)
                if coverage >= 0.72:
                    best = max(best, 18 + int(coverage * 6))

            ratios = (
                difflib.SequenceMatcher(None, left, right).ratio(),
                difflib.SequenceMatcher(
                    None, left_compact, right_compact
                ).ratio(),
                difflib.SequenceMatcher(
                    None,
                    " ".join(sorted(left.split())),
                    " ".join(sorted(right.split())),
                ).ratio(),
            )
            ratio = max(ratios)
            if ratio >= 0.84:
                best = max(best, int(ratio * 27))
    return best, exact


def match_score_details(anilist, allmanga):
    anilist_titles = _cached_match_titles(anilist)
    allmanga_titles = _cached_match_titles(allmanga)
    title_score, exact_title = title_match_score(
        anilist_titles, allmanga_titles
    )
    details = {
        "score": title_score,
        "title_score": title_score,
        "exact_title": exact_title,
        "contradiction": "",
    }

    anilist_year = _positive_int((anilist.get("season") or {}).get("year"))
    allmanga_year = _positive_int((allmanga.get("season") or {}).get("year"))
    if anilist_year and allmanga_year:
        year_gap = abs(anilist_year - allmanga_year)
        if year_gap > 1:
            details["contradiction"] = "year"
            return details
        details["score"] += 18 if year_gap == 0 else 8

    anilist_season = explicit_season_number(anilist_titles)
    allmanga_season = explicit_season_number(allmanga_titles)
    if (
        anilist_season
        and allmanga_season
        and anilist_season != allmanga_season
    ):
        details["contradiction"] = "season"
        return details

    anilist_type = str(anilist.get("type") or "").upper().replace(" ", "_")
    allmanga_type = str(allmanga.get("type") or "").upper().replace(" ", "_")
    compatible_types = {
        frozenset(("TV", "TV_SHORT")),
        frozenset(("SPECIAL", "TV_SPECIAL")),
    }
    if anilist_type and allmanga_type:
        if (
            anilist_type == allmanga_type
            or frozenset((anilist_type, allmanga_type)) in compatible_types
        ):
            details["score"] += 8
        else:
            details["contradiction"] = "type"
            return details

    anilist_episodes = _positive_int(anilist.get("episodeCount"))
    allmanga_episodes = _positive_int(allmanga.get("episodeCount"))
    if anilist_episodes and allmanga_episodes:
        if anilist_episodes == allmanga_episodes:
            details["score"] += 10
        elif (
            max(anilist_episodes, allmanga_episodes)
            <= 2 * min(anilist_episodes, allmanga_episodes)
            and abs(anilist_episodes - allmanga_episodes) <= 3
        ):
            details["score"] += 2
        else:
            details["contradiction"] = "episodes"
            return details

    anilist_quarter = str(
        (anilist.get("season") or {}).get("quarter") or ""
    ).casefold()
    allmanga_quarter = str(
        (allmanga.get("season") or {}).get("quarter") or ""
    ).casefold()
    if anilist_quarter and allmanga_quarter == anilist_quarter:
        details["score"] += 4
    return details


def score_match(anilist, allmanga):
    return match_score_details(anilist, allmanga)["score"]


def choose_confident_match(reference, candidates):
    ranked = []
    for candidate in candidates or []:
        details = match_score_details(reference, candidate)
        if details["contradiction"] or details["title_score"] < 15:
            continue
        ranked.append((details["score"], details["exact_title"], candidate))
    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score, exact_title, best = ranked[0]
    minimum = 30 if exact_title else 42
    if best_score < minimum:
        return None
    if len(ranked) > 1 and best_score - ranked[1][0] < 8:
        return None
    return best


def best_allanime_match(anilist_show, allmanga_shows):
    """Return only an unambiguous, title-supported AllAnime match."""
    return choose_confident_match(anilist_show, allmanga_shows)


def is_same_show(show1, show2):
    """Robustly determine if two show dicts represent the same title."""
    if not show1 or not show2:
        return False
        
    id1 = str(show1.get("_id") or "")
    id2 = str(show2.get("_id") or "")
    if id1 and id1 == id2:
        return True
        
    al1 = str(show1.get("aniListId") or show1.get("_anilist_id") or "")
    al2 = str(show2.get("aniListId") or show2.get("_anilist_id") or "")
    if al1 and al1 == al2:
        return True
        
    mal1 = str(show1.get("malId") or show1.get("myanimelist_id") or "")
    mal2 = str(show2.get("malId") or show2.get("myanimelist_id") or "")
    if mal1 and mal1 == mal2:
        return True
        
    # Fallback to exact title match
    t1, t2 = _cached_match_titles(show1), _cached_match_titles(show2)
    score, exact = title_match_score(t1, t2)
    return bool(exact)

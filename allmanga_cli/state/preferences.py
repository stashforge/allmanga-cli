"""Pure mutations for playback preferences."""

import time


def preferred_mirror(preferences, show_id):
    return preferences.get(str(show_id), {})


def toggle_preferred_mirror(preferences, show_id, source_name, resolution):
    key = str(show_id)
    current = preferences.get(key, {})
    if (
        current.get("source_name") == source_name
        and current.get("resolution") == resolution
    ):
        current.pop("source_name", None)
        current.pop("resolution", None)
        if current:
            preferences[key] = current
        else:
            preferences.pop(key, None)
    else:
        current["source_name"] = source_name
        current["resolution"] = resolution
        preferences[key] = current
    return preferences


def episode_order(preferences, show_id, default):
    return preferences.get(str(show_id), {}).get("episode_order", default)


def toggle_episode_order(preferences, show_id, default):
    key = str(show_id)
    current = preferences.get(key, {})
    order = (
        "desc"
        if current.get("episode_order", default) == "asc"
        else "asc"
    )
    current["episode_order"] = order
    preferences[key] = current
    return order


def title_sync_preference(preferences, show):
    if not show:
        return None
    show_id = show.get("_id")
    anilist_id = show.get("_anilist_id")
    if show_id and "sync_enabled" in preferences.get(str(show_id), {}):
        return bool(preferences[str(show_id)]["sync_enabled"])
    key = f"al:{anilist_id}"
    if anilist_id and "sync_enabled" in preferences.get(key, {}):
        return bool(preferences[key]["sync_enabled"])
    return None


def set_title_sync(preferences, show, enabled):
    keys = []
    if show.get("_id"):
        keys.append(str(show["_id"]))
    if show.get("_anilist_id"):
        keys.append(f"al:{show['_anilist_id']}")
    for key in keys:
        current = preferences.get(key, {})
        current["sync_enabled"] = bool(enabled)
        preferences[key] = current
    return preferences


def resume_time(preferences, show_id, episode):
    return (
        preferences.get(str(show_id), {})
        .get("resumes", {})
        .get(str(episode), 0)
    )


def save_resume_time(preferences, show_id, episode, position):
    key = str(show_id)
    current = preferences.get(key, {})
    resumes = current.get("resumes", {})
    if position <= 0:
        resumes.pop(str(episode), None)
    else:
        resumes[str(episode)] = int(position)
    current["resumes"] = resumes
    preferences[key] = current
    return preferences


def pending_completion(preferences, show_id):
    pending = (
        preferences.get(str(show_id), {})
        .get("pending_completion", {})
    )
    return pending if isinstance(pending, dict) else {}


def save_pending_completion(
        preferences,
        show_id,
        episode,
        progress,
        next_episode,
        position,
        duration,
        *,
        timestamp=None):
    key = str(show_id)
    current = preferences.get(key, {})
    current["pending_completion"] = {
        "episode": str(episode),
        "progress": int(progress),
        "next_episode": str(next_episode),
        "position": int(position or 0),
        "duration": int(duration or 0),
        "timestamp": int(time.time() if timestamp is None else timestamp),
    }
    preferences[key] = current
    return preferences


def clear_pending_completion(preferences, show_id):
    key = str(show_id)
    current = preferences.get(key, {})
    if "pending_completion" in current:
        current.pop("pending_completion", None)
        preferences[key] = current
    return preferences


def anilist_match(preferences, anilist_id):
    return preferences.get(f"al:{anilist_id}", {}).get("al_match", {})


def save_anilist_match(preferences, anilist_id, source_show):
    key = f"al:{anilist_id}"
    current = preferences.get(key, {})
    current["al_match"] = {
        "_id": source_show.get("_id"),
        "name": source_show.get("name", ""),
        "englishName": source_show.get("englishName", ""),
        "thumbnail": source_show.get("thumbnail"),
    }
    preferences[key] = current
    return preferences


def source_anilist_match(preferences, show_id):
    return preferences.get(str(show_id), {}).get("anilist_match", {})


def save_source_anilist_match(preferences, source_show, anilist_show):
    show_id = str((source_show or {}).get("_id") or "")
    anilist_id = str((anilist_show or {}).get("_id") or "")
    if not show_id or not anilist_id:
        return preferences
    current = preferences.get(show_id, {})
    current["anilist_match"] = {
        "_id": anilist_id,
        "name": anilist_show.get("name", ""),
        "englishName": anilist_show.get("englishName", ""),
    }
    preferences[show_id] = current
    return save_anilist_match(preferences, anilist_id, source_show)


def clear_anilist_match(preferences, anilist_id):
    key = f"al:{anilist_id}"
    if key in preferences:
        preferences[key].pop("al_match", None)
        if not preferences[key]:
            del preferences[key]
    return preferences

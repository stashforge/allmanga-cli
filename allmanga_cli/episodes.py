"""Episode catalog normalization and index helpers."""


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


def episode_index_for_id(episode_ids, episode_id):
    episode_string = str(episode_id)
    if episode_string in episode_ids:
        return episode_ids.index(episode_string)

    try:
        numeric = float(episode_string)
    except (TypeError, ValueError):
        return None

    matches = []
    for index, candidate in enumerate(episode_ids):
        try:
            if float(str(candidate)) == numeric:
                matches.append(index)
        except (TypeError, ValueError):
            continue
    return matches[0] if len(matches) == 1 else None


def episode_id_at(episode_ids, index):
    if not episode_ids or index is None:
        return None
    bounded_index = max(0, min(int(index), len(episode_ids) - 1))
    return episode_ids[bounded_index]


def episode_label(episode_id):
    return f"Episode {episode_id}"


def episode_progress_number(episode_id, fallback=0):
    if fallback:
        try:
            return max(0, int(fallback))
        except (TypeError, ValueError):
            pass
    try:
        value = float(str(episode_id))
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback

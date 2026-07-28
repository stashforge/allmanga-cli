import decimal
from allmanga_cli.domain.episodes import episode_index_for_id

episode_ids = ["1", "2", "3", "4", "5", "6"]
s = {"_local_episode_label": "1", "_local_progress": 1}

current_ep_label = s.get("_local_episode_label") or "0"
_current_idx = episode_index_for_id(episode_ids, current_ep_label) if episode_ids else None
print(f"current_ep_label: {current_ep_label}")
print(f"_current_idx: {_current_idx}")

if _current_idx is not None and _current_idx + 1 < len(episode_ids):
    detail_next_ep = episode_ids[_current_idx + 1]
else:
    detail_next_ep = None
print(f"detail_next_ep: {detail_next_ep}")

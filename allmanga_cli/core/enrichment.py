import logging
from allmanga_cli.core.anilist import fetch_anilist_by_ids
from allmanga_cli.core.storage import get_source_anilist_matches, save_source_anilist_matches
from allmanga_cli.domain.matching import choose_confident_match, reset_title_cache

def _merge_anilist_into_provider(provider_show, anilist_show):
    """
    Merges AniList metadata into a provider show in a strictly additive manner.
    It will not overwrite fields that the provider already populated, 
    unless they are empty or 'Unknown'.
    """
    # Essential tracking fields
    provider_show["_allanime_name"] = provider_show.get("name")
    provider_show["_display_name"] = anilist_show.get("name") or provider_show.get("name")
    provider_show["_display_english_name"] = anilist_show.get("englishName") or provider_show.get("englishName")
    provider_show["_anilist_list"] = anilist_show.get("_anilist_list")
    provider_show["_anilist_progress"] = anilist_show.get("_anilist_progress")
    provider_show["_anilist_score"] = anilist_show.get("_anilist_score")

    match_source = provider_show.get("_match_source") or "fuzzy"
    provider_show["anilistMatch"] = {
        "id": anilist_show.get("_id"),
        "idMal": anilist_show.get("malId"),
        "source": match_source,
    }
    if anilist_show.get("_id"):
        provider_show["aniListId"] = str(anilist_show.get("_id"))
    if anilist_show.get("malId"):
        provider_show["malId"] = int(anilist_show["malId"])

    if anilist_show.get("_next_airing_ep"):
        provider_show["_next_airing_ep"] = anilist_show["_next_airing_ep"]
        provider_show["_next_airing_time"] = anilist_show["_next_airing_time"]
        provider_show["_next_airing_at"] = anilist_show.get("_next_airing_at")

    # Additive metadata merging
    for field in ("thumbnail", "score", "genres", "episodeCount", "airedStart", 
                  "airedEnd", "season", "status", "type", "format", "description"):
        provider_val = provider_show.get(field)
        al_val = anilist_show.get(field)
        if (not provider_val or provider_val == "Unknown" or provider_val == []) and al_val:
            provider_show[field] = al_val

    # Advanced Alt-Title logic (swapping english/romaji based on provider's primary name)
    main_name = provider_show.get("_display_name")
    
    al_romaji = anilist_show.get("romajiName")
    al_english = anilist_show.get("englishName")
    
    alt_names = []
    if main_name == al_romaji and al_english:
        alt_names = [al_english]
    elif main_name == al_english and al_romaji:
        alt_names = [al_romaji]
    
    if not alt_names:
        alt_names = list(anilist_show.get("altNames") or [])
        
    provider_val = provider_show.get("altNames")
    if (not provider_val or provider_val == []) and alt_names:
        provider_show["altNames"] = alt_names

    return provider_show

def enrich_provider_results(results, token, fuzzy_anilist_results=None):
    """
    Takes a list of provider results and batch-fetches corresponding AniList data 
    if the provider scraped 'aniListId' or 'malId'. Applies fuzzy fallback matching 
    if 'fuzzy_anilist_results' is provided.
    
    Returns the enriched results.
    """
    if not results:
        return results

    reset_title_cache()  # fresh cache per batch, avoids unbounded growth

    al_ids = [s.get("aniListId") for s in results if s.get("aniListId")]
    mal_ids = [s.get("malId") for s in results if s.get("malId")]
    
    exact_matches = []
    if al_ids or mal_ids:
        # Pass token if available so private entries can be fetched if user is logged in
        try:
            exact_matches = fetch_anilist_by_ids(token or "", anilist_ids=al_ids, mal_ids=mal_ids)
        except Exception as e:
            logging.getLogger(__name__).debug(f"Failed batch AniList fetch: {e}")

    by_anilist_id = {str(m["_id"]): m for m in exact_matches if m.get("_id")}
    by_mal_id = {str(m["malId"]): m for m in exact_matches if m.get("malId")}

    pending = {}
    unmatched_ids = set()

    for s in results:
        matched = None
        if s.get("aniListId"):
            matched = by_anilist_id.get(str(s["aniListId"]))
        elif s.get("malId"):
            matched = by_mal_id.get(str(s["malId"]))

        if matched:
            pending[id(s)] = matched
            s["_match_source"] = "id"
        else:
            unmatched_ids.add(id(s))

    stored_lookup = {}
    if unmatched_ids and fuzzy_anilist_results:
        ids = [s.get("_id") for s in results if id(s) in unmatched_ids and s.get("_id")]
        stored_lookup = get_source_anilist_matches(ids)

    to_save = []
    for s in results:
        matched = pending.get(id(s))

        if not matched and id(s) in unmatched_ids and fuzzy_anilist_results:
            stored = stored_lookup.get(s.get("_id")) or {}
            stored_id = str(stored.get("_id") or "")
            if stored_id:
                matched = next(
                    (c for c in fuzzy_anilist_results if str(c.get("_id") or "") == stored_id),
                    None,
                )
            if matched:
                s["_match_source"] = "stored"
            else:
                matched = choose_confident_match(s, fuzzy_anilist_results)
                if matched:
                    s["_match_source"] = "fuzzy"

        if matched:
            to_save.append((s, matched))
            _merge_anilist_into_provider(s, matched)

    save_source_anilist_matches(to_save)
    return results


def enrich_show_if_missing(show: dict) -> None:
    if not show:
        return
    if show.get("_title_enriched") or show.get("aniListId") or show.get("_anilist_score"):
        show["_title_enriched"] = True
        return

    from ..providers.shared.models import title_provider_id, title_provider_key
    from ..providers import get_provider
    from ..services.http import request_json as _req
    from ..core.reporting import debug_warn
    from ..core.storage import load_config

    show_id = title_provider_id(show)
    if not show_id:
        show["_title_enriched"] = True
        return

    provider = get_provider(title_provider_key(show), _req)
    if provider.id not in ("anidbapp", "animexin", "lucifer", "animekhor", "animegg", "anizone"):
        show["_title_enriched"] = True
        return

    get_title_fn = getattr(provider, "get_title", None)
    if not get_title_fn:
        show["_title_enriched"] = True
        return

    try:
        title_data = get_title_fn(show_id)
        show["_title_enriched"] = True
        if title_data:
            # Merge any newly scraped data (description, episodes, etc.) into the active show object
            for k, v in title_data.items():
                if k in ("status", "episodeCount", "_next_airing_ep", "_next_airing_at", "_next_airing_time", "aniListId", "malId", "format") and v:
                    show[k] = v
                elif v and not show.get(k):
                    show[k] = v
                elif k == "availableEpisodes" and isinstance(v, dict):
                    show.setdefault(k, {})
                    for ep_k, ep_v in v.items():
                        if ep_v > show[k].get(ep_k, 0):
                            show[k][ep_k] = ep_v

            if title_data.get("aniListId") or title_data.get("malId"):
                token = load_config().get("anilist_token")
                al_ids = [title_data["aniListId"]] if title_data.get("aniListId") else None
                mal_ids = [title_data["malId"]] if title_data.get("malId") else None
                al_data = fetch_anilist_by_ids(token, anilist_ids=al_ids, mal_ids=mal_ids)
                if al_data:
                    _merge_anilist_into_provider(show, al_data[0])
    except Exception as e:
        show["_title_enriched"] = True
        debug_warn("Late enrichment failed", e)


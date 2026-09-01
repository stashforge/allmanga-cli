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

def enrich_provider_results_fast(results, fuzzy_anilist_results=None):
    """
    Fast in-memory matching pass. Matches provider results against the AniList search results
    already in RAM without making any extra network calls.
    Returns (results, unmatched_shows_with_ids).
    """
    if not results:
        return results, []

    reset_title_cache()

    al_shows = fuzzy_anilist_results or []
    by_anilist_id = {str(m["_id"]): m for m in al_shows if m.get("_id")}
    by_mal_id = {str(m["malId"]): m for m in al_shows if m.get("malId")}

    pending = {}
    unmatched_ids = set()
    unmatched_shows_with_ids = []

    for s in results:
        matched = None
        if s.get("aniListId") and str(s["aniListId"]) in by_anilist_id:
            matched = by_anilist_id[str(s["aniListId"])]
            s["_match_source"] = "id"
        elif s.get("malId") and str(s["malId"]) in by_mal_id:
            matched = by_mal_id[str(s["malId"])]
            s["_match_source"] = "id"

        if matched:
            pending[id(s)] = matched
        else:
            unmatched_ids.add(id(s))
            if s.get("aniListId") or s.get("malId"):
                unmatched_shows_with_ids.append(s)

    stored_lookup = {}
    if unmatched_ids and al_shows:
        ids = [s.get("_id") for s in results if id(s) in unmatched_ids and s.get("_id")]
        stored_lookup = get_source_anilist_matches(ids)

    to_save = []
    for s in results:
        matched = pending.get(id(s))

        if not matched and id(s) in unmatched_ids and al_shows:
            stored = stored_lookup.get(s.get("_id")) or {}
            stored_id = str(stored.get("_id") or "")
            if stored_id:
                matched = next(
                    (c for c in al_shows if str(c.get("_id") or "") == stored_id),
                    None,
                )
            if matched:
                s["_match_source"] = "stored"
            else:
                matched = choose_confident_match(s, al_shows)
                if matched:
                    s["_match_source"] = "fuzzy"

        if matched:
            to_save.append((s, matched))
            _merge_anilist_into_provider(s, matched)
            # Remove from unmatched if fuzzy matched
            if s in unmatched_shows_with_ids:
                unmatched_shows_with_ids.remove(s)

    if to_save:
        save_source_anilist_matches(to_save)

    return results, unmatched_shows_with_ids


def enrich_provider_results_background(unmatched_shows, token="", on_updated_callback=None):
    """
    Background worker that quietly backfills AniList metadata for shows whose IDs
    were not present in the initial query results.
    """
    if not unmatched_shows:
        return

    al_ids = [s.get("aniListId") for s in unmatched_shows if s.get("aniListId")]
    mal_ids = [s.get("malId") for s in unmatched_shows if s.get("malId")]

    if not al_ids and not mal_ids:
        return

    try:
        exact_matches = fetch_anilist_by_ids(token or "", anilist_ids=al_ids, mal_ids=mal_ids)
        if not exact_matches:
            return

        by_al = {str(m["_id"]): m for m in exact_matches if m.get("_id")}
        by_mal = {str(m["malId"]): m for m in exact_matches if m.get("malId")}

        to_save = []
        updated = False
        for s in unmatched_shows:
            matched = None
            if s.get("aniListId") and str(s["aniListId"]) in by_al:
                matched = by_al[str(s["aniListId"])]
            elif s.get("malId") and str(s["malId"]) in by_mal:
                matched = by_mal[str(s["malId"])]

            if matched:
                s["_match_source"] = "id"
                to_save.append((s, matched))
                _merge_anilist_into_provider(s, matched)
                updated = True

        if to_save:
            save_source_anilist_matches(to_save)

        if updated and on_updated_callback:
            on_updated_callback()
    except Exception as e:
        logging.getLogger(__name__).debug(f"Background AniList enrich error: {e}")


def enrich_provider_results(results, token, fuzzy_anilist_results=None):
    """
    Legacy sync wrapper. Performs fast in-memory enrichment first, and fetches any missing
    IDs synchronously if requested.
    """
    enriched, unmatched = enrich_provider_results_fast(results, fuzzy_anilist_results)
    if unmatched:
        enrich_provider_results_background(unmatched, token=token)
    return enriched


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


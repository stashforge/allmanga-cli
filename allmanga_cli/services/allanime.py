"""AllAnime GraphQL queries and episode payload retrieval."""

import json
import urllib.parse

from ..core.api import SearchFailure
from ..domain.episodes import normalize_episode_ids
from ..media.decryption import decrypt_tobeparsed
from .http import API_BASE, CLOCK_BASE


SEARCH_QUERY = (
    "query($search:SearchInput $limit:Int $page:Int "
    "$translationType:VaildTranslationTypeEnumType "
    "$countryOrigin:VaildCountryOriginEnumType){"
    "shows(search:$search limit:$limit page:$page "
    "translationType:$translationType countryOrigin:$countryOrigin)"
    "{edges{_id name englishName nativeName altNames thumbnail type "
    "season score genres availableEpisodes status episodeCount airedStart}}}"
)


def search_anime(request_json, query, ttype="sub"):
    response = request_json(
        API_BASE,
        json.dumps({
            "query": SEARCH_QUERY,
            "variables": {
                "search": {
                    "allowAdult": False,
                    "allowUnknown": False,
                    "query": query,
                },
                "limit": 40,
                "page": 1,
                "translationType": ttype,
                "countryOrigin": "ALL",
            },
        }).encode(),
    )
    if response.get("errors"):
        raise SearchFailure("AllAnime rejected the search request.")
    return response.get("data", {}).get("shows", {}).get("edges", [])


def get_show(request_json, show_id):
    query = (
        "query($showId:String!){show(_id:$showId)"
        "{_id name englishName nativeName altNames thumbnail type season "
        "score genres availableEpisodes status episodeCount airedStart}}"
    )
    response = request_json(
        API_BASE,
        json.dumps({
            "query": query,
            "variables": {"showId": show_id},
        }).encode(),
    )
    return response.get("data", {}).get("show")


def fetch_episode_catalog(request_json, show_id, ttype="sub"):
    query = (
        "query($showId:String!){"
        "show(_id:$showId){availableEpisodesDetail}}"
    )
    try:
        response = request_json(
            API_BASE,
            json.dumps({
                "query": query,
                "variables": {"showId": show_id},
            }).encode(),
        )
        if response.get("errors"):
            return {
                "state": "unavailable",
                "ids": [],
                "error": "Provider rejected the episode catalog request.",
            }
        show_data = response.get("data", {}).get("show")
        if not isinstance(show_data, dict):
            return {
                "state": "unavailable",
                "ids": [],
                "error": "Provider returned no episode catalog.",
            }
        detail = show_data.get("availableEpisodesDetail")
        if not isinstance(detail, dict):
            return {
                "state": "unavailable",
                "ids": [],
                "error": "Provider returned an invalid episode catalog.",
            }
        episodes = list(detail.get(ttype) or [])
        episodes.reverse()
        return {
            "state": "loaded",
            "ids": normalize_episode_ids(episodes),
            "error": "",
        }
    except Exception:
        return {
            "state": "unavailable",
            "ids": [],
            "error": "Could not load the provider episode catalog.",
        }


def get_episode_data(request_json, show_id, episode, ttype="sub"):
    query_hash = (
        "d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"
    )
    variables = {
        "showId": show_id,
        "translationType": ttype,
        "episodeString": str(episode),
    }
    extensions = {
        "persistedQuery": {"version": 1, "sha256Hash": query_hash}
    }
    url = (
        f"{API_BASE}?variables={urllib.parse.quote(json.dumps(variables))}"
        f"&extensions={urllib.parse.quote(json.dumps(extensions))}"
    )
    response = request_json(
        url,
        extra_hdrs={"Origin": "https://youtu-chan.com"},
    )
    raw = response.get("data", {}).get("tobeparsed")
    if not raw:
        raw = response.get("data", {}).get("episode", {}).get("sourceUrls")
    if not raw:
        return None
    decoded = decrypt_tobeparsed(raw)
    return json.loads(decoded) if decoded else None


def get_clock_links(request_json, path):
    return request_json(f"https://{CLOCK_BASE}{path}").get("links", [])

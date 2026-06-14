"""AniList GraphQL requests and response normalization."""

import json
import urllib.request

from ..core.api import SearchFailure
from ..domain.metadata import set_next_airing_fields


API_URL = "https://graphql.anilist.co"
USER_AGENT = "Mozilla/5.0"


def _request(token=""):
    request = urllib.request.Request(API_URL, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", USER_AGENT)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def _post(urlopen, read_json, query, variables=None, token=""):
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    with urlopen(_request(token), json.dumps(payload).encode()) as response:
        return read_json(response)


def _start_date(media):
    start = media.get("startDate")
    if not start:
        return None
    return {
        "year": start.get("year"),
        "month": start.get("month"),
        "date": start.get("day"),
    }


def normalize_media(media, *, list_name=None, entry=None):
    titles = media.get("title") or {}
    quarter = media.get("season")
    show = {
        "_id": str(media["id"]),
        "name": titles.get("romaji") or titles.get("english") or "Unknown",
        "englishName": titles.get("english") or "",
        "nativeName": titles.get("native") or "",
        "altNames": media.get("synonyms", []),
        "type": media.get("format") or "TV",
        "season": {
            "year": media.get("seasonYear"),
            "quarter": quarter.capitalize() if quarter else None,
        },
        "airedStart": _start_date(media),
        "score": (
            media.get("averageScore") / 10.0
            if media.get("averageScore")
            else None
        ),
        "genres": media.get("genres", []),
        "availableEpisodes": {
            "sub": media.get("episodes", 0) or 0,
            "dub": 0,
            "raw": 0,
        },
        "status": media.get("status"),
        "episodeCount": media.get("episodes"),
        "thumbnail": (media.get("coverImage") or {}).get("large"),
    }
    if entry:
        show["_anilist_progress"] = entry.get("progress")
        if entry.get("updatedAt") is not None:
            show["_anilist_updated_at"] = entry.get("updatedAt")
    if list_name:
        show["_anilist_list"] = list_name
    list_entry = media.get("mediaListEntry")
    if list_entry:
        show["_anilist_list"] = list_entry.get("status")
        show["_anilist_progress"] = list_entry.get("progress")
    next_airing = media.get("nextAiringEpisode")
    if next_airing:
        set_next_airing_fields(show, next_airing)
    return show


def media_id(anime):
    candidate = anime.get("_anilist_id")
    if candidate:
        return candidate
    candidate = anime.get("_id")
    return candidate if str(candidate or "").isdigit() else None


def apply_media_update(anime, media):
    if not anime or not media:
        return False
    anime["_anilist_id"] = str(
        media.get("id") or media_id(anime) or ""
    )
    titles = media.get("title") or {}
    if titles.get("romaji"):
        anime["_display_name"] = titles["romaji"]
    if titles.get("english"):
        anime["_display_english_name"] = titles["english"]
    if titles.get("native"):
        anime["nativeName"] = titles["native"]
    if media.get("format"):
        anime["type"] = media["format"]
    anime["status"] = media.get("status") or anime.get("status")
    if media.get("episodes") is not None:
        anime["episodeCount"] = media["episodes"]
    if media.get("averageScore") is not None:
        anime["score"] = media["averageScore"] / 10.0

    list_entry = media.get("mediaListEntry") or {}
    if list_entry.get("progress") is not None:
        anime["_anilist_progress"] = max(0, int(list_entry["progress"]))
    if list_entry.get("status"):
        anime["_anilist_list"] = list_entry["status"]

    start = media.get("startDate") or {}
    if start.get("year"):
        anime["airedStart"] = {
            "year": start.get("year"),
            "month": start.get("month"),
            "date": start.get("day"),
        }
    end = media.get("endDate") or {}
    if end.get("year"):
        anime["airedEnd"] = {
            "year": end.get("year"),
            "month": end.get("month"),
            "date": end.get("day"),
        }
    else:
        anime.pop("airedEnd", None)

    next_airing = media.get("nextAiringEpisode")
    if next_airing:
        set_next_airing_fields(anime, next_airing)
    else:
        anime.pop("_next_airing_ep", None)
        anime.pop("_next_airing_time", None)
        anime.pop("_next_airing_at", None)
    return True


def fetch_media(urlopen, read_json, token, media_id):
    query = """
    query($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        title { romaji english native }
        format
        episodes
        status
        averageScore
        startDate { year month day }
        endDate { year month day }
        nextAiringEpisode { episode timeUntilAiring }
        mediaListEntry { progress status }
      }
    }
    """
    payload = _post(
        urlopen,
        read_json,
        query,
        {"id": int(media_id)},
        token,
    )
    return payload.get("data", {}).get("Media") or {}


def fetch_list(urlopen, read_json, token, status=None):
    viewer = _post(
        urlopen,
        read_json,
        "query{Viewer{id name}}",
        token=token,
    )
    user_id = viewer["data"]["Viewer"]["id"]
    query = """
    query($userId: Int, $status: MediaListStatus) {
      MediaListCollection(userId: $userId, type: ANIME, status: $status) {
        lists {
          name
          entries {
            progress
            updatedAt
            media {
              id
              title { romaji english native }
              synonyms
              format
              episodes
              status
              season
              seasonYear
              averageScore
              genres
              startDate { year month day }
              coverImage { large }
              nextAiringEpisode { episode timeUntilAiring }
            }
          }
        }
      }
    }
    """
    variables = {"userId": user_id}
    if status:
        variables["status"] = status
    payload = _post(urlopen, read_json, query, variables, token)
    lists = payload["data"]["MediaListCollection"]["lists"]
    return [
        normalize_media(
            entry["media"],
            list_name=media_list["name"],
            entry=entry,
        )
        for media_list in lists
        for entry in media_list["entries"]
    ]


def search(urlopen, read_json, token, query_text):
    query = """
    query($search: String) {
      Page(page: 1, perPage: 25) {
        media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
          id
          title { romaji english native }
          synonyms
          format
          episodes
          status
          season
          seasonYear
          averageScore
          genres
          startDate { year month day }
          coverImage { large }
          nextAiringEpisode { episode timeUntilAiring }
          mediaListEntry {
            status
            progress
          }
        }
      }
    }
    """
    payload = _post(
        urlopen,
        read_json,
        query,
        {"search": query_text},
        token,
    )
    if payload.get("errors"):
        raise SearchFailure("AniList rejected the search request.")
    return [
        normalize_media(media)
        for media in payload["data"]["Page"]["media"]
    ]


def search_media_id(urlopen, read_json, title):
    payload = _post(
        urlopen,
        read_json,
        "query($s:String){Media(search:$s type:ANIME){id}}",
        {"s": title},
    )
    return payload["data"]["Media"]["id"]


def update_entry(
        urlopen,
        read_json,
        token,
        media_id,
        *,
        progress=None,
        status=None,
        score=None):
    query = """
    mutation($id:Int, $p:Int, $s:MediaListStatus, $score:Int) {
      SaveMediaListEntry(mediaId:$id, progress:$p, status:$s, scoreRaw:$score) {
        id progress status score(format: POINT_100)
      }
    }
    """
    variables = {"id": media_id}
    if progress is not None:
        variables["p"] = progress
    if status is not None:
        variables["s"] = status
    if score is not None:
        variables["score"] = int(score)
    return _post(urlopen, read_json, query, variables, token)

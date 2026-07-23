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
    main_name = titles.get("romaji") or titles.get("english") or "Unknown"

    show = {
        "_id": str(media["id"]),
        "malId": media.get("idMal"),
        "name": main_name,
        "romajiName": titles.get("romaji") or "",
        "englishName": titles.get("english") or "",
        "nativeName": titles.get("native") or "",
        "altNames": list(media.get("synonyms") or []),
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
        "description": media.get("description", ""),
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
        show["_anilist_started_at"] = entry.get("startedAt") or {}
        show["_anilist_completed_at"] = entry.get("completedAt") or {}
    if list_name:
        show["_anilist_list"] = list_name
    list_entry = media.get("mediaListEntry")
    if list_entry:
        show["_anilist_list"] = list_entry.get("status")
        show["_anilist_progress"] = list_entry.get("progress")
        show["_anilist_score"] = list_entry.get("score")
        show["_anilist_entry_id"] = list_entry.get("id")
        show["_anilist_started_at"] = list_entry.get("startedAt") or {}
        show["_anilist_completed_at"] = list_entry.get("completedAt") or {}
    elif not entry and not list_name:
        show["_anilist_progress"] = 0
        show["_anilist_list"] = ""
    next_airing = media.get("nextAiringEpisode")
    if next_airing:
        set_next_airing_fields(show, next_airing)
    return show


def media_id(anime):
    candidate = anime.get("aniListId")
    if candidate:
        return candidate
    candidate = anime.get("_id")
    return candidate if str(candidate or "").isdigit() else None


def apply_media_update(anime, media):
    if not anime or not media:
        return False
    anime["aniListId"] = str(
        media.get("id") or media_id(anime) or ""
    )
    titles = media.get("title") or {}
    if titles.get("english"):
        anime["englishName"] = titles["english"]
        anime["_display_english_name"] = titles["english"]
    if titles.get("romaji"):
        anime["romajiName"] = titles["romaji"]
        anime["_display_name"] = titles["romaji"]
    if titles.get("native"):
        anime["nativeName"] = titles["native"]

    main_name = anime.get("_display_name") or titles.get("romaji") or titles.get("english") or "Unknown"
    
    if media.get("synonyms"):
        anime["altNames"] = list(media["synonyms"])

    if media.get("description"):
        anime["description"] = media["description"]
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
    if list_entry:
        anime["_anilist_entry_id"] = list_entry.get("id")
        anime["_anilist_started_at"] = list_entry.get("startedAt") or {}
        anime["_anilist_completed_at"] = list_entry.get("completedAt") or {}

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
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        idMal
        title {
          romaji
          english
          native
        }
        synonyms
        format
        type
        status
        episodes
        duration
        season
        seasonYear
        startDate {
          year
          month
          day
        }
        endDate {
          year
          month
          day
        }
        countryOfOrigin
        isAdult
        averageScore
        meanScore
        popularity
        coverImage {
          large
          medium
          color
        }
        bannerImage
        nextAiringEpisode {
          episode
          airingAt
          timeUntilAiring
        }
        mediaListEntry {
          id
          status
          score
          progress
          progressVolumes
          repeat
          priority
          private
          notes
          startedAt {
            year
            month
            day
          }
          completedAt {
            year
            month
            day
          }
          createdAt
          updatedAt
        }
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


def fetch_media_batch(urlopen, read_json, media_ids):
    results = {}
    chunk_size = 50
    for i in range(0, len(media_ids), chunk_size):
        chunk = media_ids[i : i + chunk_size]
        query = """
        query($ids: [Int]) {
          Page(page: 1, perPage: 50) {
            media(id_in: $ids, type: ANIME) {
              id
              status
              episodes
              nextAiringEpisode { episode airingAt timeUntilAiring }
            }
          }
        }
        """
        payload = _post(
            urlopen,
            read_json,
            query,
            {"ids": [int(mid) for mid in chunk if mid]},
            None,
        )
        media_list = payload.get("data", {}).get("Page", {}).get("media", [])
        for media in media_list:
            if media.get("id"):
                results[str(media["id"])] = media
    return results


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
            startedAt { year month day }
            completedAt { year month day }
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
              nextAiringEpisode { episode airingAt timeUntilAiring }
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
          description(asHtml: false)
          startDate { year month day }
          coverImage { large }
          nextAiringEpisode { episode airingAt timeUntilAiring }
          mediaListEntry {
            status
            progress
            startedAt { year month day }
            completedAt { year month day }
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


def fetch_by_ids(urlopen, read_json, token, anilist_ids=None, mal_ids=None):
    if not anilist_ids and not mal_ids:
        return []
    
    query = """
    query($idIn: [Int], $idMalIn: [Int]) {
      Page(page: 1, perPage: 50) {
        media(id_in: $idIn, idMal_in: $idMalIn, type: ANIME) {
          id
          idMal
          title { romaji english native }
          synonyms
          format
          episodes
          status
          season
          seasonYear
          averageScore
          genres
          description(asHtml: false)
          startDate { year month day }
          coverImage { large }
          nextAiringEpisode { episode airingAt timeUntilAiring }
          mediaListEntry {
            status
            progress
            startedAt { year month day }
            completedAt { year month day }
          }
        }
      }
    }
    """
    
    variables = {}
    if anilist_ids:
        variables["idIn"] = [int(i) for i in anilist_ids if str(i).isdigit()]
    if mal_ids:
        variables["idMalIn"] = [int(i) for i in mal_ids if str(i).isdigit()]
        
    if not variables:
        return []

    payload = _post(
        urlopen,
        read_json,
        query,
        variables,
        token,
    )
    if payload.get("errors"):
        return []
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
        score=None,
        started_at=None,
        completed_at=None):
    query = """
    mutation(
      $id:Int,
      $p:Int,
      $s:MediaListStatus,
      $score:Int,
      $startedAt:FuzzyDateInput,
      $completedAt:FuzzyDateInput
    ) {
      SaveMediaListEntry(
        mediaId:$id,
        progress:$p,
        status:$s,
        scoreRaw:$score,
        startedAt:$startedAt,
        completedAt:$completedAt
      ) {
        id
        progress
        status
        score(format: POINT_100)
        startedAt { year month day }
        completedAt { year month day }
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
    if started_at is not None:
        variables["startedAt"] = started_at
    if completed_at is not None:
        variables["completedAt"] = completed_at
    return _post(urlopen, read_json, query, variables, token)

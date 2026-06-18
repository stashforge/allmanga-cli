#!/usr/bin/env python3
import sys
import os
import json
import argparse
import urllib.error

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from allmanga_cli.services.http import API_BASE, request_json

SEARCH_QUERY = """
query(
    $search:SearchInput
    $limit:Int
    $page:Int
    $translationType:VaildTranslationTypeEnumType
    $countryOrigin:VaildCountryOriginEnumType
) {
    shows(
        search:$search
        limit:$limit
        page:$page
        translationType:$translationType
        countryOrigin:$countryOrigin
    ) {
        edges {
            _id
            name
            englishName
            nativeName
            altNames
            malId
            aniListId
            type
            season
            status
            episodeCount
            availableEpisodes
            genres
            airedStart
            score
            thumbnail
        }
    }
}
"""

SHOW_QUERY = """
query($showId:String!){
    show(_id:$showId){
        _id
        name
        englishName
        nativeName
        altNames
        malId
        aniListId
        type
        season
        status
        episodeCount
        availableEpisodes
        lastEpisodeTimestamp
        broadcastInterval
        determinedInterval
        lastEpisodeDate
        lastEpisodeInfo
        nextAiringEpisode
        airedStart
        score
        genres
        thumbnail
    }
}
"""

CATALOG_QUERY = """
query($showId:String!){
    show(_id:$showId){
        availableEpisodesDetail
    }
}
"""

def do_search(query_str, limit=5, page=1, ttype="sub"):
    try:
        response = request_json(
            API_BASE,
            json.dumps({
                "query": SEARCH_QUERY,
                "variables": {
                    "search": {"allowAdult": False, "allowUnknown": False, "query": query_str},
                    "limit": limit,
                    "page": page,
                    "translationType": ttype,
                    "countryOrigin": "ALL"
                }
            }).encode()
        )
        if "errors" in response:
            print("GraphQL Errors:", json.dumps(response["errors"], indent=2))
        return response.get("data", {}).get("shows", {}).get("edges", [])
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code}")
        try:
            print(e.read().decode())
        except:
            pass
    except Exception as e:
        print(f"Error: {e}")
    return []

def do_show(show_id, ttype="sub"):
    try:
        response = request_json(
            API_BASE,
            json.dumps({
                "query": SHOW_QUERY,
                "variables": {"showId": show_id}
            }).encode()
        )
        if "errors" in response:
            print("GraphQL Errors:", json.dumps(response["errors"], indent=2))
            return None
        show_data = response.get("data", {}).get("show", {})
        
        # Also fetch catalog
        cat_resp = request_json(
            API_BASE,
            json.dumps({
                "query": CATALOG_QUERY,
                "variables": {"showId": show_id}
            }).encode()
        )
        if "data" in cat_resp and "show" in cat_resp["data"]:
            show_data["availableEpisodesDetail"] = cat_resp["data"]["show"].get("availableEpisodesDetail")
            
        return show_data
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code}")
        try:
            print(e.read().decode())
        except:
            pass
    except Exception as e:
        print(f"Error: {e}")
    return None

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    search_p = subparsers.add_parser("search")
    search_p.add_argument("query")
    search_p.add_argument("--limit", type=int, default=5)
    search_p.add_argument("--page", type=int, default=1)
    search_p.add_argument("--ttype", default="sub", choices=["sub", "dub", "raw"])

    show_p = subparsers.add_parser("show")
    show_p.add_argument("show_id")
    show_p.add_argument("--ttype", default="sub", choices=["sub", "dub", "raw"])

    args = parser.parse_args()

    if args.cmd == "search":
        print(f"Searching for '{args.query}' (limit={args.limit})...")
        results = do_search(args.query, args.limit, args.page, args.ttype)
        for i, res in enumerate(results):
            print(f"\n[{i+1}] {res.get('name')}")
            for key in ["_id", "englishName", "nativeName", "malId", "aniListId", "status", "episodeCount", "availableEpisodes"]:
                print(f"  {key}: {res.get(key)}")
            print("  --- Raw JSON ---")
            print(json.dumps(res, indent=2, ensure_ascii=False))
            print("--------------------------------------------------")

    elif args.cmd == "show":
        print(f"Fetching show '{args.show_id}'...")
        show_data = do_show(args.show_id, args.ttype)
        if show_data:
            print("\n--- Show JSON ---")
            print(json.dumps(show_data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

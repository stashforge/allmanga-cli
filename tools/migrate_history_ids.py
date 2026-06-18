#!/usr/bin/env python3
import sys
import os
import json
import argparse
import shutil
import urllib.error

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from allmanga_cli.state.paths import HISTORY_PATH
from allmanga_cli.services.http import API_BASE, request_json

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
    }
}
"""

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
        }
    }
}
"""

def fetch_show_by_id(show_id):
    try:
        response = request_json(
            API_BASE,
            json.dumps({
                "query": SHOW_QUERY,
                "variables": {"showId": show_id}
            }).encode()
        )
        return response.get("data", {}).get("show")
    except Exception:
        return None

def search_show(title):
    try:
        response = request_json(
            API_BASE,
            json.dumps({
                "query": SEARCH_QUERY,
                "variables": {
                    "search": {"allowAdult": False, "allowUnknown": False, "query": title},
                    "limit": 5, "page": 1, "translationType": "sub", "countryOrigin": "ALL"
                }
            }).encode()
        )
        return response.get("data", {}).get("shows", {}).get("edges", [])
    except Exception:
        return []

def prompt_choice(options):
    if not options:
        return None
    for i, opt in enumerate(options):
        print(f"  [{i+1}] {opt.get('name')} (malId: {opt.get('malId')}, aniListId: {opt.get('aniListId')})")
    print(f"  [0] Skip")
    while True:
        try:
            choice = int(input("Select matching show (0 to skip): "))
            if choice == 0:
                return None
            if 1 <= choice <= len(options):
                return options[choice - 1]
        except ValueError:
            pass

def main():
    parser = argparse.ArgumentParser(description="Migrate history entries to include malId and aniListId")
    parser.add_argument("--write", action="store_true", help="Actually save changes to history.json")
    args = parser.parse_args()

    if not os.path.exists(HISTORY_PATH):
        print(f"History file not found at {HISTORY_PATH}")
        return

    with open(HISTORY_PATH, "r") as f:
        history = json.load(f)

    if not isinstance(history, list):
        print("Invalid history format (not a list).")
        return

    print(f"Loaded {len(history)} entries from {HISTORY_PATH}")
    
    modified_count = 0

    for idx, entry in enumerate(history):
        show = entry.get("show")
        if not show:
            continue
            
        print(f"\n--- Entry {idx+1}/{len(history)}: {show.get('name')} ---")
        
        # Already has the IDs?
        if "aniListId" in show or "malId" in show:
            print("Already has aniListId/malId. Skipping.")
            continue

        _id = show.get("_id")
        matched_data = None
        
        if _id:
            print(f"Fetching by existing _id: {_id}")
            matched_data = fetch_show_by_id(_id)
        
        if not matched_data:
            print(f"Could not fetch by _id. Searching by title...")
            title_to_search = show.get("name") or show.get("_display_name") or show.get("englishName")
            results = search_show(title_to_search)
            if results:
                matched_data = prompt_choice(results)
            else:
                print("No search results found.")

        if matched_data:
            # Apply data
            show["aniListId"] = matched_data.get("aniListId")
            show["malId"] = matched_data.get("malId")
            
            # Optionally update canonical name fields if missing
            show["_id"] = matched_data.get("_id")
            for field in ["name", "englishName", "nativeName", "altNames"]:
                if field in matched_data:
                    show[field] = matched_data[field]
                    
            print(f"-> Updated with aniListId: {show['aniListId']}, malId: {show['malId']}")
            modified_count += 1
        else:
            print("-> Skipped.")

    print(f"\nFinished. {modified_count} entries modified in memory.")
    
    if args.write:
        if modified_count > 0:
            bak_path = HISTORY_PATH + ".bak"
            print(f"Creating backup at {bak_path}")
            shutil.copy2(HISTORY_PATH, bak_path)
            
            print(f"Saving changes to {HISTORY_PATH}")
            with open(HISTORY_PATH, "w") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            print("Saved successfully.")
        else:
            print("No changes to save.")
    else:
        print("DRY RUN: Run with --write to save changes to history.json.")

if __name__ == "__main__":
    main()

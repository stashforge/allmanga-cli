#!/usr/bin/env python3
import argparse
import json
import shutil
import time
from pathlib import Path

from allmanga_cli.state.paths import HISTORY_PATH

REMOVE_SHOW_KEYS = {
    "_poster_raw",
    "_poster_status",
    "_poster_status_time",
    "_poster_failed",
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    path = Path(HISTORY_PATH)
    data = json.loads(path.read_text(encoding="utf-8"))

    removed_count = 0

    for entry in data:
        show = entry.get("show") or {}
        for key in list(REMOVE_SHOW_KEYS):
            if key in show:
                del show[key]
                removed_count += 1

    print(f"History path: {path}")
    print(f"Entries: {len(data)}")
    print(f"Removed fields: {removed_count}")

    if not args.write:
        print("DRY RUN: run with --write to save changes.")
        return

    backup = path.with_name(f"{path.name}.bak-before-poster-cleanup-{int(time.time())}")
    shutil.copy2(path, backup)

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Backup written: {backup}")
    print("History cleaned.")

if __name__ == "__main__":
    main()

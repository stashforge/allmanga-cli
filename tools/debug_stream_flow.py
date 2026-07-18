#!/usr/bin/env python3
"""Debug provider -> resolver -> playback stream flow without the TUI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from allmanga_cli.media.resolver import resolve_source
from allmanga_cli.media.sources import source_priority
from allmanga_cli.providers import get_provider
from allmanga_cli.providers.models import title_provider_id


def _compact_stream(stream: dict) -> dict:
    return {
        "source_name": stream.get("source_name"),
        "type": stream.get("type"),
        "resolution": stream.get("resolution"),
        "link": stream.get("link"),
        "audio_url": stream.get("audio_url"),
        "split_video_url": stream.get("split_video_url"),
        "split_audio_url": stream.get("split_audio_url"),
        "referer": stream.get("referer"),
        "headers": stream.get("headers"),
        "android_safe": stream.get("android_safe"),
        "_quality_rank": stream.get("_quality_rank"),
        "_bitrate": stream.get("_bitrate"),
    }


def _compact_source(source: dict) -> dict:
    return {
        "sourceName": source.get("sourceName"),
        "sourceUrl": source.get("sourceUrl"),
        "link": source.get("link") or source.get("streamUrl"),
        "type": source.get("type"),
        "referer": source.get("referer"),
        "headers": source.get("headers"),
        "extractHeaders": source.get("extractHeaders"),
        "_source_kind": source.get("_source_kind"),
    }


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _episode_id_for_label(catalog: dict, label: str) -> str:
    labels = catalog.get("labels") or {}
    for episode_id, episode_label in labels.items():
        if str(episode_label) == str(label):
            return str(episode_id)
    ids = catalog.get("ids") or catalog.get("_provider_episode_ids") or []
    if label.isdigit():
        index = int(label) - 1
        if 0 <= index < len(ids):
            return str(ids[index])
    return str(label)


def _select(items: list, index: int):
    if not items:
        raise SystemExit("No items found.")
    if index < 1 or index > len(items):
        raise SystemExit(f"Index {index} out of range 1-{len(items)}.")
    return items[index - 1]


def _run_mpv(stream: dict, *, title: str, no_headers: bool) -> int:
    command = ["mpv", "--force-media-title=" + title]
    if stream.get("audio_url"):
        command.append("--audio-file=" + str(stream["audio_url"]))
    headers = stream.get("headers") or {}
    referer = stream.get("referer") or ""
    header_fields = []
    if not no_headers:
        header_fields.extend(f"{key}: {value}" for key, value in headers.items())
        if referer:
            header_fields.append(f"Referer: {referer}")
    if header_fields:
        command.append("--http-header-fields=" + ",".join(header_fields))
    command.append(str(stream["link"]))
    print("\nMPV COMMAND")
    print(" ".join(command))
    return subprocess.call(command)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Trace provider search, episode sources, resolved streams, and mpv handoff."
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument("-P", "--provider", default="animexin")
    parser.add_argument("-e", "--episode", default="", help="Episode label/id; defaults to latest")
    parser.add_argument("--title-index", type=int, default=1)
    parser.add_argument("--source-index", type=int, default=0, help="1-based source index after sorting")
    parser.add_argument("--stream-index", type=int, default=1, help="1-based stream index")
    parser.add_argument("--source-filter", default="", help="Only resolve sources containing this text")
    parser.add_argument("--json", action="store_true", help="Print machine-readable final data")
    parser.add_argument("--play", action="store_true", help="Launch selected stream in mpv")
    parser.add_argument("--no-headers", action="store_true", help="Do not pass stream headers/referer to mpv")
    args = parser.parse_args(argv)

    provider = get_provider(args.provider)
    print(f"Provider: {provider.name} ({args.provider})")
    print(f"Search: {args.query}")
    titles = provider.search(args.query)
    print(f"\nTITLES ({len(titles)})")
    for index, title in enumerate(titles, 1):
        print(f"{index:2}. {title.get('name')}  [{title_provider_id(title)}]")
    title = _select(titles, args.title_index)
    title_id = title_provider_id(title)
    print(f"\nSELECTED TITLE: {title.get('name')}")
    print(f"TITLE ID: {title_id}")

    catalog = provider.episode_catalog(title_id, "sub")
    ids = catalog.get("ids") or catalog.get("_provider_episode_ids") or []
    labels = catalog.get("labels") or {}
    print(f"\nEPISODES: {len(ids)}")
    for episode_id in ids[-8:]:
        print(f"  {labels.get(str(episode_id), episode_id)} -> {episode_id}")
    episode_id = _episode_id_for_label(catalog, args.episode or str(labels.get(str(ids[-1]), ids[-1])))
    print(f"\nSELECTED EPISODE ID: {episode_id}")
    print(f"EPISODE LABEL: {labels.get(str(episode_id), args.episode or episode_id)}")

    episode_data = provider.episode_sources(title_id, episode_id, "sub") or {}
    sources = episode_data.get("episode", {}).get("sourceUrls", [])
    sources = sorted(sources, key=source_priority)
    if args.source_filter:
        needle = args.source_filter.casefold()
        sources = [
            source for source in sources
            if needle in str(source.get("sourceName", "")).casefold()
            or needle in str(source.get("sourceUrl", "")).casefold()
        ]
    print(f"\nSOURCES ({len(sources)})")
    for index, source in enumerate(sources, 1):
        print(f"{index:2}. prio={source_priority(source)} {source.get('sourceName')} -> {source.get('sourceUrl')}")
        source_referer = source.get("referer") or ""
        print(
            "    source playback: "
            f"referer={source_referer!r} "
            f"headers={source.get('headers') or {}} "
            f"extractHeaders={source.get('extractHeaders') or {}}"
        )

    from allmanga_cli.media.resolver import generate_source_passes
    import time

    selected_sources = [sources[args.source_index - 1]] if args.source_index else sources
    final_streams = []
    stats = {"resolved": 0, "failed": 0, "total": len(selected_sources)}
    seen_sources = set()

    for source, failed in generate_source_passes(selected_sources, max_passes=3):
        source_name = source.get('sourceName')
        is_retry = source_name in seen_sources
        seen_sources.add(source_name)

        retry_marker = " [RETRY]" if is_retry else ""
        print(f"\nRESOLVE SOURCE: {source_name}{retry_marker}")

        start_time = time.time()
        streams = resolve_source(source, silent=True)
        elapsed = time.time() - start_time

        print(f"STREAMS: {len(streams)} (took {elapsed:.2f}s)")
        if not streams:
            failed.append(source)
            if not is_retry:
                stats["failed"] += 1
        else:
            if not is_retry:
                stats["resolved"] += 1

        for index, stream in enumerate(streams, 1):
            compact = _compact_stream(stream)
            print(f"{index:2}. {compact['source_name']} [{compact['type']}] {compact['resolution']}")
            print(f"    link: {compact['link']}")
            print(f"    audio: {compact['audio_url']}")
            stream_referer = compact["referer"] or ""
            print(f"    stream playback: referer={stream_referer!r} headers={compact['headers'] or {}}")
        final_streams.extend(streams)

    print(f"\n--- STATS ---")
    print(f"Total sources: {stats['total']}")
    print(f"Resolved: {stats['resolved']}")
    print(f"Failed: {stats['failed']}")

    selected_stream = _select(final_streams, args.stream_index)
    if args.json:
        _print_json({
            "title": title,
            "episode_id": episode_id,
            "sources": [_compact_source(source) for source in selected_sources],
            "stream": _compact_stream(selected_stream),
        })

    if args.play:
        return _run_mpv(
            selected_stream,
            title=f"{title.get('name')} - Episode {labels.get(str(episode_id), episode_id)}",
            no_headers=args.no_headers,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

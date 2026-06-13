#!/usr/bin/env python3
import json
import re
import runpy
import subprocess
import time
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
CLI = runpy.run_path(str(ROOT / "allmanga-cli"))
REPORT = ROOT / "ak_rawurls_manual_test.md"
MPD_FILE = ROOT / "ak_rawurls_test.mpd"
SOURCE_REPORT = ROOT / "video_source_diagnostics.md"
SHOW_ID = "srGrP23qJnjsHrRYD"
EPISODE = "8"
TRANSLATION_TYPE = "sub"


def load_captured_ak_source():
    text = SOURCE_REPORT.read_text(encoding="utf-8")
    match = re.search(
        r'"source_name": "Ak",\s+"raw_source_url": "(--[0-9a-f]+)"',
        text,
    )
    if not match:
        raise RuntimeError("No captured Ak source found in diagnostic report")
    return match.group(1)


def fetch_clock(source_url):
    path = CLI["decrypt_url"](source_url[2:])
    url = f"https://{CLI['CLOCK_BASE']}{path}"
    request = urllib.request.Request(url, headers=CLI["BASE_HDRS"])
    with urllib.request.urlopen(
        request, context=CLI["SSL_CTX_SECURE"], timeout=20
    ) as response:
        return url, json.loads(response.read())


def select_tracks(raw_urls):
    videos = raw_urls.get("vids") or []
    audios = raw_urls.get("audios") or []
    avc = [item for item in videos if "avc" in str(item.get("codecs", "")).lower()]
    compatible = avc or videos
    video = max(
        compatible,
        key=lambda item: (int(item.get("height") or 0), int(item.get("bandwidth") or 0)),
    )
    audio = max(audios, key=lambda item: int(item.get("bandwidth") or 0))
    return video, audio


def http_probe(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": CLI["UA"],
            "Range": "bytes=0-1023",
        },
    )
    started = time.monotonic()
    with urllib.request.urlopen(
        request, context=CLI["SSL_CTX_SECURE"], timeout=20
    ) as response:
        sample = response.read(1024)
        return {
            "status": response.status,
            "final_url": response.geturl(),
            "content_type": response.headers.get("Content-Type"),
            "content_length": response.headers.get("Content-Length"),
            "content_range": response.headers.get("Content-Range"),
            "sample_bytes": len(sample),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }


def run_command(command, timeout):
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-8000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "timeout": timeout,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": (exc.stderr or "")[-8000:],
        }


def generate_mpd(raw_urls, videos, audio):
    duration = float(raw_urls.get("duration") or 0)
    duration_iso = f"PT{duration:.3f}S"
    video_representations = []
    for index, video in enumerate(videos):
        segment = video.get("segment_base") or {}
        video_representations.append(
            "\n".join(
                [
                    (
                        f'      <Representation id="v{index}" '
                        f'bandwidth="{int(video.get("bandwidth") or 0)}" '
                        f'width="{int(video.get("width") or 0)}" '
                        f'height="{int(video.get("height") or 0)}" '
                        f'codecs="{escape(str(video.get("codecs") or ""))}">'
                    ),
                    f"        <BaseURL>{escape(video['url'])}</BaseURL>",
                    (
                        f'        <SegmentBase indexRange="'
                        f'{escape(str(segment.get("index_range") or "0-0"))}">'
                    ),
                    (
                        f'          <Initialization range="'
                        f'{escape(str(segment.get("range") or "0-0"))}"/>'
                    ),
                    "        </SegmentBase>",
                    "      </Representation>",
                ]
            )
        )
    audio_segment = audio.get("segment_base") or {}
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" '
                'profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" '
                f'type="static" mediaPresentationDuration="{duration_iso}" '
                'minBufferTime="PT2S">'
            ),
            f'  <Period duration="{duration_iso}">',
            (
                '    <AdaptationSet mimeType="video/mp4" '
                'startWithSAP="1" segmentAlignment="true">'
            ),
            *video_representations,
            "    </AdaptationSet>",
            (
                '    <AdaptationSet mimeType="audio/mp4" lang="und" '
                'startWithSAP="1" segmentAlignment="true">'
            ),
            (
                f'      <Representation id="a0" '
                f'bandwidth="{int(audio.get("bandwidth") or 0)}" '
                f'codecs="{escape(str(audio.get("codecs") or ""))}">'
            ),
            f"        <BaseURL>{escape(audio['url'])}</BaseURL>",
            (
                f'        <SegmentBase indexRange="'
                f'{escape(str(audio_segment.get("index_range") or "0-0"))}">'
            ),
            (
                f'          <Initialization range="'
                f'{escape(str(audio_segment.get("range") or "0-0"))}"/>'
            ),
            "        </SegmentBase>",
            "      </Representation>",
            "    </AdaptationSet>",
            "  </Period>",
            "</MPD>",
            "",
        ]
    )


def main():
    source_url = load_captured_ak_source()
    clock_url, clock = fetch_clock(source_url)
    item = next(
        entry
        for entry in clock.get("links", [])
        if (entry.get("rawUrls") or {}).get("vids")
        and (entry.get("rawUrls") or {}).get("audios")
    )
    raw_urls = item["rawUrls"]
    video, audio = select_tracks(raw_urls)
    avc_videos = [
        entry
        for entry in raw_urls.get("vids") or []
        if "avc" in str(entry.get("codecs") or "").lower()
    ]
    MPD_FILE.write_text(
        generate_mpd(raw_urls, avc_videos or [video], audio),
        encoding="utf-8",
    )

    result = {
        "test": {
            "show_id": SHOW_ID,
            "episode": EPISODE,
            "translation_type": TRANSLATION_TYPE,
            "source_origin": str(SOURCE_REPORT),
        },
        "clock_url": clock_url,
        "selected_video": {
            key: video.get(key)
            for key in ("width", "height", "bandwidth", "mime_type", "codecs", "url")
        },
        "selected_audio": {
            key: audio.get(key)
            for key in ("bandwidth", "mime_type", "codecs", "url")
        },
        "video_http_probe": http_probe(video["url"]),
        "audio_http_probe": http_probe(audio["url"]),
        "ffprobe_video": run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_name,codec_type,width,height",
                "-of",
                "json",
                video["url"],
            ],
            30,
        ),
        "ffprobe_audio": run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_name,codec_type,sample_rate,channels",
                "-of",
                "json",
                audio["url"],
            ],
            30,
        ),
        "mpv_headless": run_command(
            [
                "mpv",
                "--no-config",
                "--vo=null",
                "--ao=null",
                "--no-terminal",
                "--msg-level=all=warn",
                "--start=0",
                "--length=5",
                f"--audio-file={audio['url']}",
                video["url"],
            ],
            45,
        ),
        "mpv_mpd_headless": run_command(
            [
                "mpv",
                "--no-config",
                "--vo=null",
                "--ao=null",
                "--no-terminal",
                "--msg-level=all=warn",
                "--length=5",
                str(MPD_FILE),
            ],
            45,
        ),
    }

    lines = [
        "# Ak rawUrls Manual Playback Test",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}",
        "",
        "> Sensitive: selected CDN URLs contain temporary authorization tokens.",
        "",
        "```json",
        json.dumps(result, indent=2),
        "```",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(REPORT),
                "video_status": result["video_http_probe"]["status"],
                "audio_status": result["audio_http_probe"]["status"],
                "ffprobe_video": result["ffprobe_video"].get("returncode"),
                "ffprobe_audio": result["ffprobe_audio"].get("returncode"),
                "mpv": result["mpv_headless"].get("returncode"),
                "mpv_mpd": result["mpv_mpd_headless"].get("returncode"),
                "mpd": str(MPD_FILE),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

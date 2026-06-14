"""Episode download execution."""

import os
import shutil
import subprocess

from .urls import validate_optional_referer, validate_stream_url


CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
RESET = "\033[0m"


def _error(message):
    print(f"{RED}[ERR]{RESET} {message}")


def download_episode(title, episode, stream, download_dir=""):
    audio_url = stream.get("audio_url", "")
    downloader = "ffmpeg" if audio_url else "yt-dlp"
    if not shutil.which(downloader):
        if audio_url:
            _error(
                "ffmpeg is required to download separate DASH video and audio."
            )
        else:
            _error(
                "yt-dlp is not installed. Install it to download episodes."
            )
        return False

    try:
        url = validate_stream_url(stream["link"])
        if audio_url:
            audio_url = validate_stream_url(audio_url)
        referer = validate_optional_referer(stream.get("referer", ""))
    except ValueError:
        _error("Download rejected an unsafe stream URL.")
        return False

    safe_title = "".join(
        char for char in title if char.isalnum() or char in " -_"
    ).strip()
    filename = f"{safe_title} - Episode {episode}.mp4"
    download_dir = os.path.expanduser(str(download_dir or "").strip())
    if download_dir:
        target_dir = os.path.join(download_dir, safe_title)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception as exc:
            _error(f"Could not create download folder: {exc}")
            return False
        filename = os.path.join(target_dir, filename)

    print(f"\n{CYAN}[Download]{RESET} {filename}")

    if audio_url:
        command = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-i",
            url,
            "-i",
            audio_url,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            filename,
        ]
    else:
        command = ["yt-dlp", url, "-o", filename]
        if referer:
            command.extend(["--add-header", f"Referer:{referer}"])

    try:
        subprocess.run(command, check=True)
        print(f"\n{GREEN}[Success]{RESET} Download complete.")
        return True
    except Exception as exc:
        print(f"\n{RED}[Error]{RESET} Download failed: {exc}")
        return False

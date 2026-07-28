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


def download_episode(title, episode, stream, download_dir="", downloader="auto", extra_args=None):
    extra_args = extra_args or []
    audio_url = stream.get("audio_url", "")
    if downloader == "auto":
        downloader = "ffmpeg" if audio_url else "yt-dlp"

    if not shutil.which(downloader):
        if downloader == "ffmpeg":
            _error("ffmpeg is not installed or not in PATH.")
        else:
            _error("yt-dlp is not installed or not in PATH.")
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
    
    # Always create an anime-specific folder, even if download_dir is empty
    if not download_dir:
        from allmanga_cli.core.storage import get_default_download_dir, load_config, save_config
        download_dir = get_default_download_dir()
        live_cfg = load_config()
        live_cfg["download_dir"] = download_dir
        save_config(live_cfg)
    else:
        download_dir = os.path.expanduser(str(download_dir).strip())

    target_dir = os.path.join(download_dir, safe_title)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as exc:
        _error(f"Could not create download folder: {exc}")
        return False
    filename = os.path.join(target_dir, filename)

    print(f"\n{CYAN}[Download]{RESET} {filename}")

    # Extract all headers
    headers = stream.get("headers", {})
    if referer and "Referer" not in headers:
        headers["Referer"] = referer

    if downloader == "ffmpeg":
        command = [
            "ffmpeg",
            "-nostdin",
            "-y"
        ]
        if headers:
            header_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
            command.extend(["-headers", header_str])
        
        command.extend(["-i", url])
        if audio_url:
            command.extend(["-i", audio_url, "-map", "0:v:0", "-map", "1:a:0"])
        
        command.extend(["-c", "copy", filename])
    else:
        command = ["yt-dlp", url, "-o", filename]
        
        # Auto-inject aria2c if available and user didn't manually override it
        if shutil.which("aria2c") and not any(arg in extra_args for arg in ("--downloader", "--external-downloader")):
            command.extend([
                "--downloader", "aria2c",
                "--downloader-args", "aria2c:-x 16 -s 16 -k 1M"
            ])
            
        for k, v in headers.items():
            command.extend(["--add-header", f"{k}:{v}"])

    if extra_args:
        command.extend(extra_args)

    try:
        subprocess.run(command, check=True)
        print(f"\n{GREEN}[Success]{RESET} Download complete.")
        return True
    except Exception as exc:
        print(f"\n{RED}[Error]{RESET} Download failed: {exc}")
        return False

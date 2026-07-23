# allmanga-cli

A robust, lightweight Python CLI tool for scraping and streaming anime directly to `mpv`. 

## Features
- **Headless Stream Scraping**: Fetches video streams from various anime providers directly in the terminal without requiring a bloated browser.
- **Advanced Fallback Priority**: Includes a smart stream-ranking system. When a provider returns multiple mirrors, `allmanga-cli` automatically ranks them, prioritizing the fastest, most reliable servers (like `ok.ru` and `pewe`) and seamlessly skipping failing/obfuscated embeds.
- **Direct MPV Integration**: Pipes raw `.m3u8` playlists and `.mp4` files straight to `mpv` for a native playback experience.
- **Built-in Background Resolver**: Uses background threads to resolve multiple streams simultaneously to prevent CLI blocking.
- **Browser Playback Fallback**: If scrapers fail or you want a provider's native auto-next functionality, a built-in action menu lets you extract the raw embed/watch URL and instantly open it in your desktop or Android browser.

## Installation

### Method 1: Using pipx (Recommended for Linux/macOS)
Modern Linux distributions and macOS environments often block system-wide `pip` installations (`error: externally-managed-environment`). Using `pipx` is the easiest way to install `allmanga-cli` as a global command-line tool securely:

1. Install `pipx` if you haven't already (e.g., `sudo pacman -S pipx` or `brew install pipx`).
2. Install the CLI directly from the cloned repository with optional dependencies:
   ```bash
   git clone https://github.com/stashforge/allmanga-cli.git
   cd allmanga-cli
   pipx install .[allanime,miruro]
   ```
*(Note: If you edit the source code later, run `pipx install . --force` to update the executable.)*

### Method 2: Standard pip Installation
If you are on Windows, inside a Docker container, or explicitly using a virtual environment (`venv`), you can use standard `pip`:

1. Clone the repository and set up a virtual environment:
   ```bash
   git clone https://github.com/stashforge/allmanga-cli.git
   cd allmanga-cli
   python -m venv venv
   source venv/bin/activate
   ```
2. Install the package with the necessary provider dependencies:
   ```bash
   pip install .[allanime,miruro]
   ```

### Optional Dependencies Explained
By default, the core installation only installs basic dependencies. To enable specific scrapers to bypass Cloudflare and decode streams, install their optional flags:
- `[miruro]`: Installs `curl_cffi` for advanced TLS impersonation required by the Miruro scraper.
- `[allanime]`: Installs `cryptography` for decrypting the Allanime clock endpoints.

## Configuration

On first run, the CLI automatically generates a default configuration file. The file is typically located at `~/.config/allmanga-cli/config.json` (or `~/.local/state/allmanga-cli/config.json` depending on your OS).

Here is the default configuration template and what each setting controls:

```json
{
    "quality": "1080p",               // Preferred video quality (e.g., "best", "1080p", "720p", "480p")
    "translation_type": "sub",        // Default audio type ("sub" or "dub")
    "binge": false,                   // (true/false) Auto-play next episode when current finishes
    "player": "mpv",                  // Default video player ("mpv", "vlc", "mpvex", "next")
    "anilist_token": "",              // Your AniList OAuth token (auto-populated if you run with --login)
    "auto_track": false,              // (true/false) Automatically track watch progress on AniList
    "cover": false,                   // (true/false) Display anime cover art in terminal (requires image support)
    "download_dir": "",               // Absolute path to save downloaded episodes
    "anilist_sort": "recent",         // Default sorting method for AniList library ("recent", "score", etc.)
    "spinner": "braille",             // Terminal loading spinner style
    "allanime_frontend_domain": "https://mkissa.to", // Domain used for the AllAnime provider
    "provider": "miruro"              // Default streaming provider (e.g., "miruro", "allanime", "anidbapp")
}
```

*Note: The CLI will automatically populate your config file with any missing fields when you run it, so your config will never fall out of sync after an update!*

## Requirements
- Python 3.10+
- `mpv` player installed on your system
- `yt-dlp` (often used by mpv to resolve certain HTTP streams)

## Architecture Notes
- `allmanga_cli/providers/`: Contains modular scraper logic for individual sources (e.g., `miruro.py`, `allanime.py`, `anidbapp.py`). Each scraper is responsible for assigning a `"priority"` to the streams it finds.
- `allmanga_cli/media/`: Contains the global resolver and background streaming logic. The global stream ranker blindly trusts the `priority` tag assigned by the provider to decouple ranking logic from the playback engine.

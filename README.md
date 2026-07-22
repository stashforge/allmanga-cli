# allmanga-cli

A robust, lightweight Python CLI tool for scraping and streaming anime directly to `mpv`. 

## Features
- **Headless Stream Scraping**: Fetches video streams from various anime providers directly in the terminal without requiring a bloated browser.
- **Advanced Fallback Priority**: Includes a smart stream-ranking system. When a provider returns multiple mirrors, `allmanga-cli` automatically ranks them, prioritizing the fastest, most reliable servers (like `ok.ru` and `pewe`) and seamlessly skipping failing/obfuscated embeds.
- **Direct MPV Integration**: Pipes raw `.m3u8` playlists and `.mp4` files straight to `mpv` for a native playback experience.
- **Built-in Background Resolver**: Uses background threads to resolve multiple streams simultaneously to prevent CLI blocking.

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/stashforge/allmanga-cli.git
   cd allmanga-cli
   ```
2. Set up a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install the CLI package:
   ```bash
   pip install .
   ```

## Requirements
- Python 3.10+
- `mpv` player installed on your system
- `yt-dlp` (often used by mpv to resolve certain HTTP streams)

## Architecture Notes
- `allmanga_cli/providers/`: Contains modular scraper logic for individual sources (e.g., `miruro.py`, `allanime.py`). Each scraper is responsible for assigning a `"priority"` to the streams it finds.
- `allmanga_cli/media/`: Contains the global resolver and background streaming logic. The global stream ranker blindly trusts the `priority` tag assigned by the provider to decouple ranking logic from the playback engine.

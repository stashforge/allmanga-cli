import os
import tempfile
import time
from unittest.mock import MagicMock

import pytest

from allmanga_cli.domain.history import (
    history_entry_category,
    refresh_history_entry_provider_catalog,
)
from allmanga_cli.core import storage
from allmanga_cli.state import paths
from allmanga_cli.domain.metadata import (
    format_next_airing,
    apply_provider_metadata_to_history_show,
)
from allmanga_cli.providers.shared.wordpress import (
    parse_series,
    WordPressAnimeProvider,
)
from allmanga_cli.core.terminal import display_width as _display_width


def test_history_caught_up_to_active_transition():
    """Show caught up in Up to date moves to Active with ◆ when new ep drops."""
    entry = {
        "show": {
            "_id": "show-1",
            "name": "Test Anime",
            "status": "RELEASING",
            "availableEpisodes": {"sub": 12},
        },
        "episode": "12",
        "translation_type": "sub",
    }

    # 1. User watched 12/12 -> Up to date, was_caught_up=True, has_new_release=False
    cat = history_entry_category(entry)
    assert cat == "Up to date"
    assert entry.get("was_caught_up") is True
    assert entry.get("has_new_release") is False

    # 2. Episode 13 drops -> availableEpisodes becomes 13
    entry["show"]["availableEpisodes"]["sub"] = 13
    cat = history_entry_category(entry)
    assert cat == "Active"
    assert entry.get("has_new_release") is True

    # 3. Check prefix formatting
    prefix = "\033[38;2;166;227;161m◆\033[0m " if entry.get("has_new_release") else "  "
    assert "◆" in prefix
    assert _display_width(prefix) == 2


def test_history_backlogged_show_does_not_get_indicator():
    """Show backlogged in Active (watched 5/12) does NOT get ◆ when ep 13 drops."""
    entry = {
        "show": {
            "_id": "show-2",
            "name": "Backlogged Anime",
            "status": "RELEASING",
            "availableEpisodes": {"sub": 12},
        },
        "episode": "5",
        "translation_type": "sub",
    }

    # Initial check -> was_caught_up is not True
    cat = history_entry_category(entry)
    assert cat == "Active"
    assert not entry.get("was_caught_up")
    assert not entry.get("has_new_release")

    # Episode 13 drops
    entry["show"]["availableEpisodes"]["sub"] = 13
    cat = history_entry_category(entry)
    assert cat == "Active"
    assert not entry.get("has_new_release")

    prefix = "\033[38;2;166;227;161m◆\033[0m " if entry.get("has_new_release") else "  "
    assert prefix == "  "
    assert _display_width(prefix) == 2


def test_history_watched_clears_indicator(monkeypatch):
    """Watching the latest episode clears has_new_release and moves back to Up to date."""
    with tempfile.TemporaryDirectory() as tmpdir:
        hist_path = os.path.join(tmpdir, "history.json")
        monkeypatch.setattr(paths, "HISTORY_PATH", hist_path)
        monkeypatch.setattr(paths, "STATE_DIR", tmpdir)
        monkeypatch.setattr(storage, "_history_cache", None)

        show = {
            "_id": "show-3",
            "name": "Catchup Anime",
            "status": "RELEASING",
            "availableEpisodes": {"sub": 12},
        }

        # Progress at 12
        entry1 = storage.write_history_progress(show, "12", "sub")
        assert entry1.get("was_caught_up") is True
        assert entry1.get("has_new_release") is False

        # New episode 13 releases
        show["availableEpisodes"]["sub"] = 13
        cat = history_entry_category(entry1)
        assert cat == "Active"
        assert entry1.get("has_new_release") is True

        # User watches episode 13
        entry2 = storage.write_history_progress(show, "13", "sub")
        assert entry2.get("was_caught_up") is True
        assert entry2.get("has_new_release") is False
        assert history_entry_category(entry2) == "Up to date"


def test_format_next_airing_clears_when_episode_is_available():
    """format_next_airing returns empty string when availableEpisodes >= _next_airing_ep."""
    now = time.time()
    anime = {
        "_next_airing_ep": 25,
        "_next_airing_at": int(now + 86400),  # 1 day in the future
        "availableEpisodes": {"sub": 25},     # Released early!
    }
    # Even though remaining > 0, ep 25 is available -> return ""
    result = format_next_airing(anime, now=now)
    assert result == ""

    # If only ep 24 is available, countdown should be displayed
    anime["availableEpisodes"]["sub"] = 24
    result = format_next_airing(anime, now=now)
    assert "Next EP 25 in" in result


def test_apply_provider_metadata_clears_stale_airing_fields():
    """apply_provider_metadata_to_history_show clears _next_airing_* when show is up to date or provider cleared it."""
    show = {
        "_id": "show-4",
        "_next_airing_ep": 25,
        "_next_airing_at": 1780000000,
        "_next_airing_time": 1780000000,
        "availableEpisodes": {"sub": 24},
    }

    provider_show = {
        "_next_airing_ep": None,
        "_next_airing_at": None,
        "_next_airing_time": None,
        "availableEpisodes": {"sub": 25},
    }

    changed = apply_provider_metadata_to_history_show(show, provider_show)
    assert changed is True
    assert show.get("_next_airing_ep") is None
    assert show.get("_next_airing_at") is None
    assert show.get("_next_airing_time") is None
    assert show.get("availableEpisodes", {}).get("sub") == 25


def test_wordpress_parse_series_includes_early_released_episode():
    """parse_series does not drop an episode > latest_released_num if it has video mirrors."""
    series_html = """
    <div class="lastend">
        <span class="epcurlast">Episode 24</span>
    </div>
    <div class="eplister">
        <ul>
            <li>
                <a href="https://example.com/ep-25/">
                    <div class="epl-num">Episode 25</div>
                    <div class="epl-title">Episode 25</div>
                </a>
            </li>
            <li>
                <a href="https://example.com/ep-24/">
                    <div class="epl-num">Episode 24</div>
                    <div class="epl-title">Episode 24</div>
                </a>
            </li>
        </ul>
    </div>
    """

    def mock_fetch(url):
        if "ep-25" in url:
            # Episode 25 has player mirrors (early release)
            return """
            <html>
                <select class="mirror">
                    <option value="https://stream.example.com/video.m3u8">Server 1</option>
                </select>
            </html>
            """
        return ""

    entries = parse_series("https://example.com", series_html, fetch_fn=mock_fetch)
    # Episode 25 must be included!
    assert len(entries) == 2
    urls = [e.url for e in entries]
    assert "https://example.com/ep-25/" in urls


def test_wordpress_parse_series_drops_unreleased_countdown():
    """parse_series drops upcoming episode if it only has a tickcounter countdown."""
    series_html = """
    <div class="lastend">
        <span class="epcurlast">Episode 24</span>
    </div>
    <div class="eplister">
        <ul>
            <li>
                <a href="https://example.com/ep-25/">
                    <div class="epl-num">Episode 25</div>
                    <div class="epl-title">Episode 25</div>
                </a>
            </li>
            <li>
                <a href="https://example.com/ep-24/">
                    <div class="epl-num">Episode 24</div>
                    <div class="epl-title">Episode 24</div>
                </a>
            </li>
        </ul>
    </div>
    """

    def mock_fetch(url):
        if "ep-25" in url:
            # Episode 25 is unreleased countdown (no mirrors, only tickcounter)
            return """
            <html>
                <a class="tickcounter" data-id="12345">Countdown</a>
            </html>
            """
        return ""

    entries = parse_series("https://example.com", series_html, fetch_fn=mock_fetch)
    assert len(entries) == 1
    assert entries[0].url == "https://example.com/ep-24/"

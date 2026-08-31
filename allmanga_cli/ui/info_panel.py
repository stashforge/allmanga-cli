"""Show information panel builders, metadata line formatters, and picker callbacks."""

from __future__ import annotations

from typing import Any, Callable

from ..domain.metadata import (
    format_available_episodes,
    format_info_metadata_line,
    format_progress,
    format_years,
    prepare_show_display_state,
)
from .panels import render_header_card



def buildEpStr(show: dict, ttype: str) -> str:
    return format_progress(show) or format_available_episodes(show, ttype)


def buildYearStr(show: dict) -> str:
    start_y = show.get("airedStart", {}).get("year") if show.get("airedStart") else None
    end_y = show.get("airedEnd", {}).get("year") if show.get("airedEnd") else None
    return format_years(start_y, end_y, show.get("status"))


def buildInfoMetadataLine(
    show: dict,
    ttype: str,
    override_ep_str: str | None = None,
    local_only: bool = False,
    hide_anilist_status: bool | None = None,
) -> str:
    return format_info_metadata_line(
        show,
        ttype,
        override_ep_str=override_ep_str,
        local_only=local_only,
        hide_anilist_status=hide_anilist_status,
    )


def build_info_panel(
    show: dict,
    ttype: str,
    w: int,
    parts: list[str],
    override_ep_str: str | None = None,
    main_title: str | None = None,
    local_only: bool = False,
    hide_anilist_status: bool | None = None,
) -> None:
    prepare_show_display_state(show, ttype, show.get("_sync_enabled") if "_sync_enabled" in show else None)
    card_lines = render_header_card(
        show,
        ttype=ttype,
        width=w,
        footer_text=None,
        override_ep_str=override_ep_str,
        main_title=main_title,
        local_only=local_only,
        hide_anilist_status=hide_anilist_status,
    )
    # The first 3 lines are Title, Alt Title, and Metadata
    parts.extend(card_lines[:3])


def make_info_fn(shows_getter: Callable[[], list[dict]], ui: Any) -> Callable[[int], str]:
    """Return an ``info_fn`` callback suitable for passing to ``tui_pick``."""
    return make_shows_info_fn(shows_getter, ui)


def make_shows_info_fn(shows_getter: Callable[[], list[dict]], ui: Any) -> Callable[[int], str]:
    from ..ui import display
    from ..ui.modals import make_shows_info_fn as _make_shows_info_fn
    from ..core.enrichment import enrich_show_if_missing
    return _make_shows_info_fn(
        shows_getter,
        ui,
        poster_manager=display._poster_manager,
        enrich_fn=enrich_show_if_missing,
    )


def make_single_show_info_fn(show: dict, ui: Any) -> Callable[[int], str]:
    from ..ui import display
    from ..ui.modals import make_single_show_info_fn as _make_single_show_info_fn
    from ..core.enrichment import enrich_show_if_missing
    return _make_single_show_info_fn(
        show,
        ui,
        poster_manager=display._poster_manager,
        enrich_fn=enrich_show_if_missing,
    )

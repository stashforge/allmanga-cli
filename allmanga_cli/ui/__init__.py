"""Terminal UI components."""

from .picker import tui_pick
from .player_screen import (
    _player_ui_state,
    activate as activate_player_screen,
    deactivate as deactivate_player_screen,
    add_status_line,
    render as render_player_screen,
    update_stream_info,
    update_mpv_props,
)
from .banners import print_app_banner, print_episode_header
from .panels import (
    render_header_card,
    render_search_header,
    render_modal_card,
    render_menu_card,
)
from .modals import (
    confirm_auto_match,
    confirm_auto_anilist_match,
    select_provider_for_match,
    manual_anilist_input_header,
    manual_match_input_header,
    search_input_header,
    search_cover_header,
    search_result_header,
    make_single_show_info_fn,
    make_shows_info_fn,
)

"""AniList root-menu presentation."""

from ..core.terminal import (
    absolute_terminal_frame,
    display_width,
    fit_terminal_line,
)
from .picker_render import render_item


LIST_STATUSES = {
    "Airing": "ANILIST_AIRING",
    "Watching": "CURRENT",
    "Plan to Watch": "PLANNING",
    "Completed": "COMPLETED",
    "Rewatching": "REPEATING",
    "Paused": "PAUSED",
    "Dropped": "DROPPED",
    "Search": "ANILIST_SEARCH",
}


def menu_header():
    hint = "\033[38;5;244m"
    detail = "\033[38;5;248m"
    reset = "\033[0m"
    return "\n".join([
        "",
        f"{detail}Choose an AniList list.{reset}",
        f"{hint}Titles are matched to AllAnime before playback.{reset}",
        f"{hint}Enter/Right=select  Left=search  Esc=quit{reset}",
    ])


def menu_navigation(result):
    if result == -2:
        return "QUIT"
    if result == -3:
        return "SEARCH"
    return None


def loading_frame(status, rows, columns):
    pointer_color = "\033[38;2;243;139;168m"
    prompt_color = "\033[38;2;203;166;247m"
    hint = "\033[38;5;244m"
    reset = "\033[0m"
    options = list(LIST_STATUSES)
    selected = next(
        (
            index
            for index, label in enumerate(options)
            if LIST_STATUSES[label] == status
        ),
        -1,
    )
    header_lines = menu_header().splitlines()
    item_count = len(options)
    padding = max(0, rows - item_count - 1 - len(header_lines))
    output = [""] * padding
    item_width = max(20, columns - 3)

    for index in range(item_count - 1, -1, -1):
        is_selected = index == selected
        pointer = (
            f"{pointer_color}\u276f{reset}" if is_selected else " "
        )
        label = render_item(
            options[index],
            "",
            is_selected,
            max_w=item_width,
        )
        output.append(fit_terminal_line(
            f"{pointer} {label}",
            columns,
        ))

    prompt = f"{prompt_color}AniList Lists \u276f{reset}"
    count = f"{hint}{item_count}/{item_count}{reset}"
    used = display_width(f"{prompt}  {count}")
    separator_width = max(1, columns - used - 2)
    separator = f" {hint}{'\u2500' * separator_width}{reset}"
    output.append(fit_terminal_line(
        f"{prompt}  {count}{separator}",
        columns,
    ))
    output.extend(
        fit_terminal_line(line, columns) for line in header_lines
    )
    return absolute_terminal_frame(output, rows, columns)

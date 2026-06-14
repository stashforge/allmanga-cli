"""Reusable picker help content."""


def picker_help(
        select_label="Select",
        back_label="Go back",
        quit_label="Quit",
        tab_label=None):
    help_items = {
        "\u2191 / \u2193": "Move selection",
        "Home / End": "Jump to first or last item",
        "Type": "Filter visible items",
        "Backspace": "Edit filter",
        "Ctrl+U": "Clear filter",
        "Enter / Right": select_label,
        "Left": back_label,
        "Esc": quit_label,
        "?": "Show or hide this help",
        "Ctrl+C": "Exit program",
    }
    if tab_label:
        help_items["Tab"] = tab_label
    return help_items


def search_input_help():
    return {
        "Type": "Edit search query",
        "\u2190 / \u2192": "Move cursor",
        "\u2191 / \u2193": "Browse search history",
        "Backspace": "Delete character",
        "Ctrl+U": "Clear query",
        "Enter": "Search",
        "Esc": "Cancel",
        "?": "Show or hide this help",
        "Ctrl+C": "Exit program",
    }

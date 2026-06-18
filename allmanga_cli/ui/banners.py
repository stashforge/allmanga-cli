"""
Terminal banner and episode-header printers for allmanga-cli.

Extracted from ``app.py`` to keep cosmetic / startup output separate from
orchestration logic.
"""

from __future__ import annotations

import sys

from ..domain.titles import extract_title_parts as _extract_title_parts


def print_app_banner() -> None:
    """Clear the screen and print the allmanga-cli startup banner."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    C, B, R = "\033[36m", "\033[1m", "\033[0m"
    line = f"{C}{'─' * 48}{R}"
    print(f"{line}\n{C}{B}▶ allmanga-cli — Anime Stream Player{R}\n{line}")


def print_episode_header(title: str, ep: object, total: int) -> None:
    """Print a "now playing" header above the player status area.

    Parameters
    ----------
    title:
        Full display title of the show (may include season/type tags).
    ep:
        Episode identifier (string or int).
    total:
        Total number of episodes in the catalog.
    """
    B, R, LG = "\033[1m", "\033[0m", "\033[38;5;248m"
    clean, sn, stype = _extract_title_parts(title)
    info_bits = []
    if sn:
        info_bits.append(f"season {sn}")
    if stype:
        info_bits.append(stype)
    ep_str = f"episode {ep} / {total}"
    if info_bits:
        ep_str += f"  \u2022  {' \u2022 '.join(info_bits)}"
    print(f"\n\033[2;36mnow playing\033[0m\n{B}{clean}{R}")
    print(f"{LG}{ep_str}{R}")
    print()

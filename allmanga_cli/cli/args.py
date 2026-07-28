"""Command-line parsing and help formatting for Anime Providers CLI."""

import argparse
import os
import re
import sys

from allmanga_cli.providers import available_providers, _DEFAULT_PROVIDER_ID

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

COMMAND_NAMES = {
    "search", "download", "downloads", "anilist", "history", "continue",
    "auth", "providers", "completion",
}

COMPLETION_SHELLS = ("bash", "zsh", "fish")


def _provider_help():
    providers = ", ".join(sorted(available_providers()))
    return f"Streaming provider: {providers}" if providers else "Streaming provider"

def _provider_command_names():
    return set(available_providers())

def _help_color_enabled():
    return (
        os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM", "") != "dumb"
        and hasattr(sys.stdout, "isatty")
        and sys.stdout.isatty()
    )

class MinimalHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_help_position", 22)
        super().__init__(*args, **kwargs)
        self._minimal_color = _help_color_enabled()

    def _set_color(self, color):
        super()._set_color(False)
        self._decolor = lambda value: _ANSI_RE.sub("", value)

    def start_section(self, heading):
        if self._minimal_color:
            heading = f"\033[1;34m{heading}\033[0m"
        super().start_section(heading)

    def _format_action_invocation(self, action):
        if not action.option_strings:
            return super()._format_action_invocation(action)
        return ", ".join(action.option_strings)

    def _fill_text(self, text, width, indent):
        lines = []
        for line in text.splitlines(keepends=True):
            plain = line.rstrip("\r\n")
            ending = line[len(plain):]
            if (
                self._minimal_color
                and plain in ("Lists:", "Actions:", "Examples:")
            ):
                line = f"\033[1;34m{plain}\033[0m{ending}"
            lines.append(indent + line)
        return "".join(lines)

class CommandHelpFormatter(MinimalHelpFormatter):
    def _format_action(self, action):
        text = super()._format_action(action)
        if isinstance(action, argparse._SubParsersAction):
            lines = text.splitlines(keepends=True)[1:]
            return "".join(
                line[2:] if line.startswith("    ") else line
                for line in lines
                if "==SUPPRESS==" not in line
            )
        return text

def _configure_help_parser(parser):
    if hasattr(parser, "color"):
        parser.color = False
    return parser

ANILIST_COMMAND_TARGETS = {
    "menu": "menu",
    "airing": "airing",
    "search": "search",
    "watching": "CURRENT",
    "current": "CURRENT",
    "planning": "PLANNING",
    "plan-to-watch": "PLANNING",
    "paused": "PAUSED",
    "dropped": "DROPPED",
    "completed": "COMPLETED",
    "rewatching": "REPEATING",
    "repeating": "REPEATING",
}

def _anilist_target(value):
    target = str(value or "").lower()
    if target not in ANILIST_COMMAND_TARGETS:
        raise argparse.ArgumentTypeError(
            "use airing, watching, planning, completed, paused, dropped, or rewatching"
        )
    return target

def _auth_action(value):
    action = str(value or "").lower()
    if action not in ("login", "logout", "status", "token"):
        raise argparse.ArgumentTypeError("use login, logout, status, or token")
    return action

def _set_cli_defaults(parser):
    parser.set_defaults(
        query=[],
        episode=None,
        quality=None,
        dub=False,
        binge=False,
        player=None,
        sources=False,
        download=False,
        downloads=False,
        sync=False,
        no_sync=False,
        login=False,
        logout=False,
        print_url=False,
        history=False,
        anilist=None,
        cont=False,
        cover=False,
        incognito=False,
        debug=False,
        json=False,
        completion_shell=None,
        completion_install=False,
        auth_status=False,
        auth_token=False,
        auth_token_raw=False,
        provider="allanime",
    )


def _add_provider_option(group):
    group.add_argument(
        "-P", "--provider",
        metavar="PROVIDER",
        help=_provider_help(),
    )


def _add_debug_option(parser, *, suppress_default=False):
    kwargs = {
        "action": "store_true",
        "help": "Show full tracebacks on crash",
    }
    if suppress_default:
        kwargs["default"] = argparse.SUPPRESS
    parser.add_argument("--debug", **kwargs)

def _add_search_options(parser):
    playback = parser.add_argument_group("Playback options")
    playback.add_argument("-e", "--episode", type=str, help="Episode number or range")
    playback.add_argument(
        "-q", "--quality",
        choices=["best", "1080p", "720p", "480p"],
        metavar="QUALITY",
        help="Preferred quality: best, 1080p, 720p, 480p",
    )
    playback.add_argument("--dub", action="store_true", help="Prefer dubbed episodes")
    playback.add_argument("-b", "--binge", action="store_true", help="Continue through episodes")
    playback.add_argument(
        "-p", "--player",
        choices=["mpv", "mpvex", "vlc", "next"],
        metavar="PLAYER",
        help="Player: mpv, mpvex, vlc, next",
    )
    playback.add_argument(
        "-s", "--sources", action="store_true",
        help="Choose a mirror before playback",
    )
    playback.add_argument("--print-url", action="store_true", help="Print selected stream URL")

    tracking = parser.add_argument_group("Tracking options")
    tracking.add_argument(
        "-t", "--sync", dest="sync", action="store_true",
        help="Enable AniList sync",
    )
    tracking.add_argument(
        "--no-sync", dest="no_sync", action="store_true",
        help="Disable AniList sync",
    )

    output = parser.add_argument_group("Output options")
    output.add_argument("--cover", action="store_true", help="Show cover images")
    output.add_argument("--json", action="store_true", help="Print search results as JSON")
    _add_provider_option(output)

    global_options = parser.add_argument_group("Global options")
    global_options.add_argument(
        "--incognito", action="store_true",
        help="Do not save history or update AniList",
    )
    _add_debug_option(global_options, suppress_default=True)
    global_options.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )

def _add_download_options(parser):
    download = parser.add_argument_group("Download options")
    download.add_argument("-e", "--episode", type=str, help="Episode number or range")
    download.add_argument(
        "-q", "--quality",
        choices=["best", "1080p", "720p", "480p"],
        metavar="QUALITY",
        help="Preferred quality: best, 1080p, 720p, 480p",
    )
    download.add_argument("--dub", action="store_true", help="Prefer dubbed episodes")
    download.add_argument(
        "-s", "--sources", action="store_true",
        help="Choose a mirror before downloading",
    )
    output = parser.add_argument_group("Output options")
    output.add_argument("--cover", action="store_true", help="Show cover images")
    _add_provider_option(output)
    global_options = parser.add_argument_group("Global options")
    _add_debug_option(global_options, suppress_default=True)
    global_options.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )
    parser.set_defaults(download=True)

def _add_anilist_options(parser, *, search=False):
    output = parser.add_argument_group("Output options")
    output.add_argument("--cover", action="store_true", help="Show cover images")
    output.add_argument("--json", action="store_true", help="Print results as JSON")
    global_options = parser.add_argument_group("Global options")
    global_options.add_argument(
        "--incognito", action="store_true",
        help="Do not save activity or update AniList",
    )
    _add_debug_option(global_options, suppress_default=True)
    global_options.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )

def _add_resume_options(parser):
    playback = parser.add_argument_group("Playback options")
    playback.add_argument(
        "-q", "--quality",
        choices=["best", "1080p", "720p", "480p"],
        metavar="QUALITY",
        help="Preferred quality: best, 1080p, 720p, 480p",
    )
    playback.add_argument("--dub", action="store_true", help="Prefer dubbed episodes")
    playback.add_argument("-b", "--binge", action="store_true", help="Continue through episodes")
    playback.add_argument(
        "-p", "--player",
        choices=["mpv", "mpvex", "vlc", "next"],
        metavar="PLAYER",
        help="Player: mpv, mpvex, vlc, next",
    )
    playback.add_argument(
        "-s", "--sources", action="store_true",
        help="Choose a mirror before playback",
    )
    playback.add_argument("--print-url", action="store_true", help="Print selected stream URL")

    tracking = parser.add_argument_group("Tracking options")
    tracking.add_argument(
        "-t", "--sync", dest="sync", action="store_true",
        help="Enable AniList sync",
    )
    tracking.add_argument(
        "--no-sync", dest="no_sync", action="store_true",
        help="Disable AniList sync",
    )

    output = parser.add_argument_group("Output options")
    output.add_argument("--cover", action="store_true", help="Show cover images")

    global_options = parser.add_argument_group("Global options")
    global_options.add_argument(
        "--incognito", action="store_true",
        help="Do not save history or update AniList",
    )
    _add_debug_option(global_options, suppress_default=True)
    global_options.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )

def build_command_parser():
    parser = _configure_help_parser(argparse.ArgumentParser(
        prog="allmanga-cli",
        usage="allmanga-cli <command> [options]",
        description="Watch anime from multiple providers with optional AniList integration.",
        add_help=False,
        epilog=(
            "Quick start:\n"
            "  allmanga-cli search frieren\n"
            "  allmanga-cli continue\n"
            "  allmanga-cli download frieren\n"
            "  allmanga-cli anilist watching\n\n"
            "Run 'allmanga-cli <command> --help' for command-specific help.\n\n"
            "Examples:\n"
            "  allmanga-cli search --help\n"
            "  allmanga-cli download --help\n"
            "  allmanga-cli anilist --help"
        ),
        formatter_class=CommandHelpFormatter,
    ))
    _set_cli_defaults(parser)
    commands = parser.add_subparsers(dest="command", metavar="<command>", title="Main commands")
    global_options = parser.add_argument_group("Global options")
    global_options.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )
    _add_debug_option(global_options)

    search = commands.add_parser(
        "search",
        help="Search and watch anime",
        usage="allmanga-cli search <query> [options]",
        description="Search and watch anime from Anime Providers.",
        epilog=(
            "Examples:\n"
            "  allmanga-cli search slime\n"
            "  allmanga-cli search slime -e 3\n"
            "  allmanga-cli search slime -e 3 --dub -q 1080p\n"
            '  allmanga-cli search "one piece" -e 1000 -p mpv'
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(search)
    search._positionals.title = "Arguments"
    search.add_argument("query", nargs="+", help="Anime title to search")
    _add_search_options(search)

    for provider_id, provider in sorted(available_providers().items()):
        provider_parser = commands.add_parser(
            provider_id,
            help=argparse.SUPPRESS,
            usage=f"allmanga-cli {provider_id} search <query> [options]",
            description=f"Search and watch anime from {provider.name}.",
            epilog=(
                "Examples:\n"
                f"  allmanga-cli {provider_id} search renegade\n"
                f"  allmanga-cli {provider_id} search renegade -e 3"
            ),
            add_help=False,
            formatter_class=MinimalHelpFormatter,
        )
        _configure_help_parser(provider_parser)
        provider_parser._positionals.title = "Arguments"
        provider_parser.add_argument(
            "provider_action",
            choices=["search"],
            metavar="<action>",
            help=argparse.SUPPRESS,
        )
        provider_parser.add_argument("query", nargs="+", help="Anime title to search")
        _add_search_options(provider_parser)
        provider_parser.set_defaults(provider=provider_id)

    download = commands.add_parser(
        "download",
        help="Download episodes",
        usage="allmanga-cli download <query> [options]",
        description="Download anime episodes locally.",
        epilog=(
            "Examples:\n"
            "  allmanga-cli download slime -e 3\n"
            '  allmanga-cli download "one piece" -e 1000 -q 720p'
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(download)
    download._positionals.title = "Arguments"
    download.add_argument("query", nargs="+", help="Anime title to search")
    _add_download_options(download)

    downloads = commands.add_parser(
        "downloads",
        help="Browse downloaded episodes",
        usage="allmanga-cli downloads [options]",
        description="Browse and play downloaded episodes.",
        epilog=(
            "Examples:\n"
            "  allmanga-cli downloads\n"
            "  allmanga-cli downloads -p vlc"
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(downloads)
    downloads.set_defaults(downloads=True)
    playback = downloads.add_argument_group("Playback options")
    playback.add_argument(
        "-p", "--player",
        choices=["mpv", "mpvex", "vlc", "next"],
        metavar="PLAYER",
        help="Player: mpv, mpvex, vlc, next",
    )
    global_options = downloads.add_argument_group("Global options")
    _add_debug_option(global_options, suppress_default=True)
    global_options.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )

    anilist = commands.add_parser(
        "anilist",
        help="Browse or search AniList",
        usage=(
            "allmanga-cli anilist [list]\n"
            "       allmanga-cli anilist search <query>"
        ),
        description=(
            "Browse your AniList library.\n\n"
            "Lists:\n"
            "  airing         Upcoming episodes from your lists\n"
            "  watching       Currently watching\n"
            "  planning       Planning to watch\n"
            "  completed      Completed\n"
            "  paused         Paused\n"
            "  dropped        Dropped\n"
            "  rewatching     Rewatching"
        ),
        epilog=(
            "Examples:\n"
            "  allmanga-cli anilist\n"
            "  allmanga-cli anilist watching\n"
            "  allmanga-cli anilist airing\n"
            "  allmanga-cli anilist completed\n"
            "  allmanga-cli anilist search erased"
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(anilist)
    anilist._positionals.title = "Arguments"
    anilist.add_argument(
        "target", nargs="?", default="menu", metavar="[list]",
        type=_anilist_target,
        help="List to open. Omit to show the AniList menu.",
    )
    _add_anilist_options(anilist)

    history = commands.add_parser(
        "history",
        help="Browse watch history",
        usage="allmanga-cli history [options]",
        description="Browse your local watch history and resume a title.",
        epilog=(
            "Examples:\n"
            "  allmanga-cli history\n"
            "  allmanga-cli history --cover\n"
            "  allmanga-cli history --incognito"
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(history)
    history.set_defaults(history=True)
    _add_resume_options(history)

    cont = commands.add_parser(
        "continue",
        help="Continue the last watched title",
        usage="allmanga-cli continue [options]",
        description="Continue the most recently watched title.",
        epilog=(
            "Examples:\n"
            "  allmanga-cli continue\n"
            "  allmanga-cli continue -q 720p\n"
            "  allmanga-cli continue --no-sync"
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(cont)
    cont.set_defaults(cont=True)
    _add_resume_options(cont)

    auth = commands.add_parser(
        "auth",
        help="Login or logout from AniList",
        usage="allmanga-cli auth <action>",
        description=(
            "Manage AniList authentication.\n\n"
            "Actions:\n"
            "  status         Show AniList authentication and storage status\n"
            "  login          Store an AniList token\n"
            "  logout         Remove the stored AniList token\n"
            "  token          Show the masked stored token\n"
            "  token --raw    Print the complete stored token"
        ),
        epilog=(
            "Examples:\n"
            "  allmanga-cli auth status\n"
            "  allmanga-cli auth login\n"
            "  allmanga-cli auth logout\n"
            "  allmanga-cli auth token\n"
            "  allmanga-cli auth token --raw"
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(auth)
    auth._positionals.title = "Arguments"
    auth.add_argument(
        "action", metavar="<action>", type=_auth_action,
        help="Authentication action to run",
    )
    auth_options = auth.add_argument_group("Auth options")
    auth_options.add_argument(
        "--raw", action="store_true",
        help="With auth token, print the complete stored token",
    )
    global_options = auth.add_argument_group("Global options")
    _add_debug_option(global_options, suppress_default=True)
    global_options.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )

    providers = commands.add_parser(
        "providers",
        help="List available providers",
        description="List available streaming providers.",
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(providers)
    providers.set_defaults(list_providers=True)

    completion = commands.add_parser(
        "completion",
        help="Generate shell completion",
        usage=(
            "allmanga-cli completion <shell>\n"
            "       allmanga-cli completion install <shell>"
        ),
        description=(
            "Generate shell completion for allmanga-cli.\n\n"
            "Shells:\n"
            "  bash          Bash completion script\n"
            "  zsh           Zsh completion script\n"
            "  fish          Fish completion script\n\n"
            "Actions:\n"
            "  install       Install completion to a user-local shell path"
        ),
        epilog=(
            "Examples:\n"
            "  allmanga-cli completion bash\n"
            "  allmanga-cli completion zsh\n"
            "  allmanga-cli completion fish\n"
            "  allmanga-cli completion install bash"
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    )
    _configure_help_parser(completion)
    completion._positionals.title = "Arguments"
    completion.add_argument(
        "completion_args", nargs="+", metavar="<shell|install>",
        help="Shell to print, or install <shell>",
    )
    global_options = completion.add_argument_group("Global options")
    _add_debug_option(global_options, suppress_default=True)
    global_options.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )

    return parser

def build_anilist_search_parser():
    parser = _configure_help_parser(argparse.ArgumentParser(
        prog="allmanga-cli anilist search",
        usage="allmanga-cli anilist search <query> [options]",
        description="Search anime on AniList.",
        epilog=(
            "Examples:\n"
            "  allmanga-cli anilist search erased\n"
            '  allmanga-cli anilist search "attack on titan"'
        ),
        add_help=False,
        formatter_class=MinimalHelpFormatter,
    ))
    _set_cli_defaults(parser)
    parser._positionals.title = "Arguments"
    parser.add_argument("query", nargs="+", help="Anime title to search")
    _add_anilist_options(parser, search=True)
    parser.set_defaults(command="anilist", anilist="search")
    return parser

def build_legacy_parser():
    parser = _configure_help_parser(argparse.ArgumentParser(
        description="Watch anime from Anime Providers.",
        formatter_class=MinimalHelpFormatter,
    ))
    _set_cli_defaults(parser)
    parser.add_argument("query", nargs="*")
    parser.add_argument("-e", "--episode", type=str)
    parser.add_argument("-q", "--quality", choices=["best", "1080p", "720p", "480p"])
    parser.add_argument("--dub", action="store_true")
    parser.add_argument("-b", "--binge", action="store_true")
    parser.add_argument("-p", "--player", choices=["mpv", "mpvex", "vlc", "next"])
    parser.add_argument("-s", "--sources", action="store_true", help="Fetch and select mirrors on first episode")
    parser.add_argument("-d", "--download", action="store_true", help="Download episode(s) locally instead of streaming")
    parser.add_argument("--downloads", action="store_true", help="Browse and play downloaded episodes from download_dir")
    parser.add_argument("-t", "--sync", dest="sync", action="store_true", help="Enable and remember AniList sync for this title")
    parser.add_argument("--no-sync", dest="no_sync", action="store_true", help="Disable AniList sync for this run")
    parser.add_argument("--login", action="store_true", help="Login to AniList")
    parser.add_argument("--logout", action="store_true", help="Logout of AniList")
    parser.add_argument("--print-url", action="store_true")
    parser.add_argument("-H", "--history", action="store_true", help="Browse watch history")
    parser.add_argument("-a", "--anilist", nargs="?", const="menu", default=None, help="Browse AniList (e.g., CURRENT, PLANNING)")
    parser.add_argument("-c", "--continue-last", action="store_true", dest="cont", help="Resume last watched")
    parser.add_argument("--cover", action="store_true", help="Show image cover in search results")
    parser.add_argument("--provider", default=None, help="Streaming provider to search")
    parser.add_argument("--incognito", action="store_true", help="Do not save local playback data or update AniList")
    _add_debug_option(parser)
    parser.add_argument("--json", action="store_true", help="Print search results as JSON and exit")
    return parser

def parse_cli_args(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    meaningful = [arg for arg in argv if arg != "--debug"]
    if meaningful[:2] == ["anilist", "search"]:
        debug_enabled = "--debug" in argv
        nested_argv = meaningful[2:]
        if debug_enabled:
            nested_argv.append("--debug")
        parser = build_anilist_search_parser()
        return parser.parse_args(nested_argv), parser
    use_commands = bool(
        meaningful
        and (
            meaningful[0] in COMMAND_NAMES
            or meaningful[0] in _provider_command_names()
            or meaningful[0] in ("-h", "--help")
        )
    )
    parser = build_command_parser() if use_commands else build_legacy_parser()
    args = parser.parse_args(argv)
    if not use_commands:
        return args, parser

    if args.command is None:
        parser.print_help()
        parser.exit()
    if args.command == "anilist":
        target = str(args.target or "menu").lower()
        if target == "search":
            parser.error("anilist search requires a query")
        args.anilist = ANILIST_COMMAND_TARGETS[target]
        del args.target
    elif args.command == "auth":
        args.login = args.action == "login"
        args.logout = args.action == "logout"
        args.auth_status = args.action == "status"
        args.auth_token = args.action == "token"
        args.auth_token_raw = bool(args.raw)
        if args.raw and args.action != "token":
            parser.error("auth --raw is only valid with auth token")
        del args.action
    elif args.command == "completion":
        values = list(args.completion_args)
        if values[0] == "install":
            if len(values) != 2 or values[1] not in COMPLETION_SHELLS:
                parser.error("completion install requires bash, zsh, or fish")
            args.completion_install = True
            args.completion_shell = values[1]
        else:
            if len(values) != 1 or values[0] not in COMPLETION_SHELLS:
                parser.error("completion requires bash, zsh, or fish")
            args.completion_shell = values[0]
        del args.completion_args
    elif args.command in _provider_command_names():
        if args.provider_action != "search":
            parser.error(f"{args.command} only supports search for now")
        args.command = "search"
        del args.provider_action
    return args, parser

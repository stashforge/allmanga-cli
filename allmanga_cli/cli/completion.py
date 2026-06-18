"""Static shell completion scripts for allmanga-cli."""

from pathlib import Path

COMMANDS = (
    "search", "download", "downloads", "anilist", "history", "continue",
    "auth", "completion",
)
ANILIST_LISTS = (
    "watching", "planning", "completed", "paused", "dropped", "rewatching",
    "search",
)
AUTH_ACTIONS = ("login", "logout")
SHELLS = ("bash", "zsh", "fish")

ROOT_OPTIONS = ("-h", "--help", "--debug")
SEARCH_OPTIONS = (
    "-e", "--episode", "-q", "--quality", "--dub", "-b", "--binge",
    "-p", "--player", "-s", "--sources", "--print-url", "-t", "--sync",
    "--no-sync", "--cover", "--json", "--incognito", "--debug", "-h",
    "--help",
)
DOWNLOAD_OPTIONS = (
    "-e", "--episode", "-q", "--quality", "--dub", "-s", "--sources",
    "--cover", "--debug", "-h", "--help",
)
DOWNLOADS_OPTIONS = ("-p", "--player", "--debug", "-h", "--help")
ANILIST_OPTIONS = ("--cover", "--json", "--incognito", "--debug", "-h", "--help")
RESUME_OPTIONS = (
    "-q", "--quality", "--dub", "-b", "--binge", "-p", "--player",
    "-s", "--sources", "--print-url", "-t", "--sync", "--no-sync",
    "--cover", "--incognito", "--debug", "-h", "--help",
)
AUTH_OPTIONS = ("--debug", "-h", "--help")
COMPLETION_OPTIONS = ("install", "--debug", "-h", "--help")


def _words(values):
    return " ".join(values)


def bash_completion():
    return f"""# allmanga-cli bash completion
_allmanga_cli_completion()
{{
    local cur prev cmd
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    cmd="${{COMP_WORDS[1]}}"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "{_words(COMMANDS)} {_words(ROOT_OPTIONS)}" -- "$cur") )
        return 0
    fi

    case "$cmd" in
        search)
            COMPREPLY=( $(compgen -W "{_words(SEARCH_OPTIONS)}" -- "$cur") )
            ;;
        download)
            COMPREPLY=( $(compgen -W "{_words(DOWNLOAD_OPTIONS)}" -- "$cur") )
            ;;
        downloads)
            COMPREPLY=( $(compgen -W "{_words(DOWNLOADS_OPTIONS)}" -- "$cur") )
            ;;
        anilist)
            COMPREPLY=( $(compgen -W "{_words(ANILIST_LISTS)} {_words(ANILIST_OPTIONS)}" -- "$cur") )
            ;;
        history|continue)
            COMPREPLY=( $(compgen -W "{_words(RESUME_OPTIONS)}" -- "$cur") )
            ;;
        auth)
            COMPREPLY=( $(compgen -W "{_words(AUTH_ACTIONS)} {_words(AUTH_OPTIONS)}" -- "$cur") )
            ;;
        completion)
            COMPREPLY=( $(compgen -W "{_words(SHELLS)} {_words(COMPLETION_OPTIONS)}" -- "$cur") )
            ;;
    esac
}}
complete -F _allmanga_cli_completion allmanga-cli
"""


def zsh_completion():
    return f"""#compdef allmanga-cli

local -a commands
commands=(
  'search:Search and watch anime'
  'download:Download episodes'
  'downloads:Browse downloaded episodes'
  'anilist:Browse or search AniList'
  'history:Browse watch history'
  'continue:Continue the last watched title'
  'auth:Login or logout from AniList'
  'completion:Generate shell completion'
)

case $words[2] in
  anilist)
    _arguments '*:: :(({_words(ANILIST_LISTS)} {_words(ANILIST_OPTIONS)}))'
    ;;
  auth)
    _arguments '*:: :(({_words(AUTH_ACTIONS)} {_words(AUTH_OPTIONS)}))'
    ;;
  completion)
    _arguments '*:: :(({_words(SHELLS)} {_words(COMPLETION_OPTIONS)}))'
    ;;
  search)
    _arguments '*:: :(({_words(SEARCH_OPTIONS)}))'
    ;;
  download)
    _arguments '*:: :(({_words(DOWNLOAD_OPTIONS)}))'
    ;;
  downloads)
    _arguments '*:: :(({_words(DOWNLOADS_OPTIONS)}))'
    ;;
  history|continue)
    _arguments '*:: :(({_words(RESUME_OPTIONS)}))'
    ;;
  *)
    _describe 'command' commands
    ;;
esac
"""


def fish_completion():
    lines = ["# allmanga-cli fish completion"]
    for command in COMMANDS:
        lines.append(
            f"complete -c allmanga-cli -n '__fish_use_subcommand' -a {command}"
        )
    for option in ROOT_OPTIONS:
        lines.append(f"complete -c allmanga-cli -n '__fish_use_subcommand' -a {option}")
    for item in ANILIST_LISTS:
        lines.append(
            "complete -c allmanga-cli -n "
            "'__fish_seen_subcommand_from anilist' -a "
            f"{item}"
        )
    for item in AUTH_ACTIONS:
        lines.append(
            "complete -c allmanga-cli -n "
            "'__fish_seen_subcommand_from auth' -a "
            f"{item}"
        )
    for item in SHELLS:
        lines.append(
            "complete -c allmanga-cli -n "
            "'__fish_seen_subcommand_from completion' -a "
            f"{item}"
        )

    command_options = {
        "search": SEARCH_OPTIONS,
        "download": DOWNLOAD_OPTIONS,
        "downloads": DOWNLOADS_OPTIONS,
        "anilist": ANILIST_OPTIONS,
        "history": RESUME_OPTIONS,
        "continue": RESUME_OPTIONS,
        "auth": AUTH_OPTIONS,
        "completion": COMPLETION_OPTIONS,
    }
    for command, options in command_options.items():
        for option in options:
            lines.append(
                "complete -c allmanga-cli -n "
                f"'__fish_seen_subcommand_from {command}' -a {option}"
            )
    return "\n".join(lines) + "\n"


def generate_completion(shell):
    shell = str(shell or "").lower()
    if shell == "bash":
        return bash_completion()
    if shell == "zsh":
        return zsh_completion()
    if shell == "fish":
        return fish_completion()
    raise ValueError(f"Unsupported shell: {shell}")


def completion_install_path(shell, home=None):
    shell = str(shell or "").lower()
    root = Path(home).expanduser() if home is not None else Path.home()
    if shell == "bash":
        return root / ".local/share/bash-completion/completions/allmanga-cli"
    if shell == "zsh":
        return root / ".zfunc/_allmanga-cli"
    if shell == "fish":
        return root / ".config/fish/completions/allmanga-cli.fish"
    raise ValueError(f"Unsupported shell: {shell}")


def install_completion(shell, home=None):
    path = completion_install_path(shell, home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_completion(shell), encoding="utf-8")
    return path

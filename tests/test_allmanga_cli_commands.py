import os
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from tests.app_namespace import load_app_namespace

namespace = load_app_namespace()
parse_cli_args = namespace["parse_cli_args"]
build_command_parser = namespace["build_command_parser"]
build_anilist_search_parser = namespace["build_anilist_search_parser"]


class CommandRouterTests(unittest.TestCase):
    def test_search_command_maps_to_existing_runtime_fields(self):
        args, _ = parse_cli_args(
            ["search", "slime", "-e", "3", "-q", "1080p", "--sync"]
        )

        self.assertEqual(args.query, ["slime"])
        self.assertEqual(args.episode, "3")
        self.assertEqual(args.quality, "1080p")
        self.assertTrue(args.sync)
        self.assertFalse(args.download)

    def test_track_aliases_are_not_supported(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                parse_cli_args(["search", "slime", "--track"])
            with self.assertRaises(SystemExit):
                parse_cli_args(["search", "slime", "--no-track"])
            with self.assertRaises(SystemExit):
                parse_cli_args(["slime", "--track"])
            with self.assertRaises(SystemExit):
                parse_cli_args(["slime", "--no-track"])

    def test_download_and_library_commands_are_distinct(self):
        download, _ = parse_cli_args(["download", "slime", "-e", "2-4"])
        library, _ = parse_cli_args(["downloads", "--player", "vlc"])

        self.assertTrue(download.download)
        self.assertFalse(download.downloads)
        self.assertEqual(download.query, ["slime"])
        self.assertTrue(library.downloads)
        self.assertFalse(library.download)
        self.assertEqual(library.player, "vlc")

    def test_anilist_friendly_names_map_to_api_statuses(self):
        watching, _ = parse_cli_args(["anilist", "watching"])
        airing, _ = parse_cli_args(["anilist", "airing"])
        rewatching, _ = parse_cli_args(["anilist", "rewatching"])
        search, _ = parse_cli_args(["anilist", "search", "erased"])

        self.assertEqual(watching.anilist, "CURRENT")
        self.assertEqual(airing.anilist, "airing")
        self.assertEqual(rewatching.anilist, "REPEATING")
        self.assertEqual(search.anilist, "search")
        self.assertEqual(search.query, ["erased"])

    def test_existing_mode_commands_map_without_state_machine_changes(self):
        history, _ = parse_cli_args(["history"])
        cont, _ = parse_cli_args(["continue"])
        login, _ = parse_cli_args(["auth", "login"])
        status, _ = parse_cli_args(["auth", "status"])
        token, _ = parse_cli_args(["auth", "token"])
        raw_token, _ = parse_cli_args(["auth", "token", "--raw"])
        completion, _ = parse_cli_args(["completion", "bash"])
        completion_install, _ = parse_cli_args(["completion", "install", "bash"])

        self.assertTrue(history.history)
        self.assertTrue(cont.cont)
        self.assertTrue(login.login)
        self.assertFalse(login.logout)
        self.assertTrue(status.auth_status)
        self.assertTrue(token.auth_token)
        self.assertFalse(token.auth_token_raw)
        self.assertTrue(raw_token.auth_token_raw)
        self.assertEqual(completion.completion_shell, "bash")
        self.assertFalse(completion.completion_install)
        self.assertEqual(completion_install.completion_shell, "bash")
        self.assertTrue(completion_install.completion_install)

    def test_legacy_invocations_remain_supported(self):
        bare, _ = parse_cli_args(["slime", "-e", "3"])
        anilist, _ = parse_cli_args(["-a", "CURRENT"])
        history, _ = parse_cli_args(["-H"])
        login, _ = parse_cli_args(["--login"])

        self.assertEqual(bare.query, ["slime"])
        self.assertEqual(bare.episode, "3")
        self.assertEqual(anilist.anilist, "CURRENT")
        self.assertTrue(history.history)
        self.assertTrue(login.login)

    def test_root_and_command_help_are_separate(self):
        parser = build_command_parser()
        root_help = parser.format_help()
        subparsers = next(
            action for action in parser._actions
            if action.__class__.__name__ == "_SubParsersAction"
        )
        search_help = subparsers.choices["search"].format_help()
        download_help = subparsers.choices["download"].format_help()
        downloads_help = subparsers.choices["downloads"].format_help()
        anilist_help = subparsers.choices["anilist"].format_help()
        history_help = subparsers.choices["history"].format_help()
        continue_help = subparsers.choices["continue"].format_help()
        auth_help = subparsers.choices["auth"].format_help()
        completion_help = subparsers.choices["completion"].format_help()
        anilist_search_help = build_anilist_search_parser().format_help()

        self.assertIn("allmanga-cli <command> [options]", root_help)
        self.assertIn("Global options:", root_help)
        self.assertIn("search", root_help)
        self.assertIn("anilist", root_help)
        self.assertIn("completion", root_help)
        self.assertLess(root_help.index("Commands:"), root_help.index("Global options:"))
        self.assertNotIn("\n  <command>\n", root_help)
        self.assertIn("--episode", search_help)
        self.assertNotIn("--episode EPISODE", search_help)
        self.assertNotIn("--quality QUALITY", search_help)
        self.assertNotIn("--player PLAYER", search_help)
        self.assertIn("Playback options:", search_help)
        self.assertIn("Tracking options:", search_help)
        self.assertNotIn("Browse downloaded episodes", search_help)
        self.assertNotIn("--sync", download_help)
        self.assertNotIn("--incognito", download_help)
        self.assertIn("[list]", anilist_help)
        self.assertIn("allmanga-cli anilist airing", anilist_help)
        self.assertIn("Lists:", anilist_help)
        self.assertLess(anilist_help.index("Lists:"), anilist_help.index("Arguments:"))
        self.assertIn("Omit to show the AniList menu.", anilist_help)
        self.assertNotIn("--episode", anilist_help)
        self.assertNotIn("--quality", anilist_help)
        self.assertNotIn("current,dropped", anilist_help)
        self.assertNotIn("  menu", anilist_help)
        self.assertNotIn("  repeating", anilist_help)
        self.assertIn("Search anime on AniList.", anilist_search_help)
        self.assertNotIn("--episode", anilist_search_help)
        for help_text in (
            search_help, download_help, downloads_help, anilist_help,
            anilist_search_help, history_help, continue_help, auth_help,
            completion_help,
        ):
            self.assertIn("Global options:", help_text)
            self.assertIn("Examples:", help_text)
            self.assertNotIn("\noptions:\n", help_text)
        self.assertIn("Playback options:", downloads_help)
        self.assertIn("Browse and play downloaded episodes.", downloads_help)
        self.assertIn("Browse your local watch history", history_help)
        self.assertIn("Tracking options:", history_help)
        self.assertIn("Continue the most recently watched title.", continue_help)
        self.assertIn("Actions:", auth_help)
        self.assertLess(auth_help.index("Actions:"), auth_help.index("Arguments:"))
        self.assertNotIn("{login,logout}", auth_help)
        self.assertIn("Shells:", completion_help)
        self.assertIn("Actions:", completion_help)

    def test_help_colors_only_headers_and_option_flags_on_tty(self):
        with (
            patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=False),
            patch.object(sys.stdout, "isatty", return_value=True),
        ):
            os.environ.pop("NO_COLOR", None)
            parser = build_command_parser()
            subparsers = next(
                action for action in parser._actions
                if action.__class__.__name__ == "_SubParsersAction"
            )
            help_text = subparsers.choices["anilist"].format_help()

        self.assertIn("\033[1;34mLists:\033[0m", help_text)
        self.assertIn("\033[1;34mArguments\033[0m:", help_text)
        self.assertIn("\033[32m--cover\033[0m", help_text)
        self.assertNotIn("\033[32m[list]\033[0m", help_text)
        examples = help_text.split("\033[1;34mExamples:\033[0m", 1)[-1]
        self.assertNotIn("\033[", examples)

    def test_help_is_plain_when_color_is_disabled(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            help_text = build_command_parser().format_help()

        self.assertNotIn("\033[", help_text)

    def test_global_debug_works_before_or_after_command(self):
        before, _ = parse_cli_args(["--debug", "search", "slime"])
        after, _ = parse_cli_args(["search", "slime", "--debug"])

        self.assertTrue(before.debug)
        self.assertTrue(after.debug)


if __name__ == "__main__":
    unittest.main()

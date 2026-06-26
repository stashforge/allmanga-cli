import unittest
from tempfile import TemporaryDirectory

from allmanga_cli.cli.completion import (
    completion_install_path,
    generate_completion,
    install_completion,
)


class ShellCompletionTests(unittest.TestCase):
    def test_bash_completion_includes_commands_and_sync_options(self):
        script = generate_completion("bash")

        self.assertIn("complete -F _allmanga_cli_completion allmanga-cli", script)
        self.assertIn(
            "search download downloads anilist history continue auth completion",
            script,
        )
        self.assertIn("animexin", script)
        self.assertIn("luciferdonghua", script)
        self.assertIn("--sync", script)
        self.assertIn("--no-sync", script)
        self.assertIn("-P", script)
        self.assertIn("--provider", script)
        self.assertNotIn("--track", script)

    def test_bash_completion_includes_nested_values(self):
        script = generate_completion("bash")

        self.assertIn('compgen -W "best 1080p 720p 480p"', script)
        self.assertIn('compgen -W "mpv mpvex vlc next"', script)
        self.assertIn("luciferdonghua", script)
        self.assertIn("allanime|animexin|luciferdonghua)", script)
        self.assertIn('compgen -W "search"', script)
        self.assertIn('if [[ "$cmd" == "completion" ]]', script)
        self.assertIn('if [[ "$cmd" == "auth" ]]', script)
        self.assertIn('compgen -W "--raw --debug -h --help"', script)

    def test_zsh_and_fish_completion_include_anilist_lists(self):
        for shell in ("zsh", "fish"):
            with self.subTest(shell=shell):
                script = generate_completion(shell)

                self.assertIn("watching", script)
                self.assertIn("rewatching", script)
                self.assertIn("airing", script)
                self.assertIn("completion", script)

    def test_completion_install_paths_are_user_local(self):
        with TemporaryDirectory() as tmp:
            path = install_completion("bash", home=tmp)

            self.assertEqual(
                path,
                completion_install_path("bash", home=tmp),
            )
            self.assertEqual(
                str(path),
                f"{tmp}/.local/share/bash-completion/completions/allmanga-cli",
            )
            self.assertIn("_allmanga_cli_completion", path.read_text())


if __name__ == "__main__":
    unittest.main()

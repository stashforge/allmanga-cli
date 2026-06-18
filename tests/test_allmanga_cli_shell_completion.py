import unittest

from allmanga_cli.cli.completion import generate_completion


class ShellCompletionTests(unittest.TestCase):
    def test_bash_completion_includes_commands_and_sync_options(self):
        script = generate_completion("bash")

        self.assertIn("complete -F _allmanga_cli_completion allmanga-cli", script)
        self.assertIn(
            "search download downloads anilist history continue auth completion",
            script,
        )
        self.assertIn("--sync", script)
        self.assertIn("--no-sync", script)
        self.assertNotIn("--track", script)

    def test_zsh_and_fish_completion_include_anilist_lists(self):
        for shell in ("zsh", "fish"):
            with self.subTest(shell=shell):
                script = generate_completion(shell)

                self.assertIn("watching", script)
                self.assertIn("rewatching", script)
                self.assertIn("completion", script)


if __name__ == "__main__":
    unittest.main()

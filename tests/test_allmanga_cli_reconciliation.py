import unittest

from allmanga_cli.domain.reconciliation import (
    decide_progress_reconciliation,
    reconcile_status,
)


class ReconciliationDecisionTests(unittest.TestCase):
    def decide(self, **overrides):
        values = {
            "local": 3,
            "remote": 3,
            "last_synced": 3,
            "status": "CURRENT",
            "anilist_source": False,
            "sync_enabled": True,
        }
        values.update(overrides)
        return decide_progress_reconciliation(**values)

    def test_equal_progress_stays_anilist_authoritative(self):
        self.assertEqual(
            self.decide(),
            {"action": "equal", "authority": "AL", "progress": 3},
        )

    def test_local_only_change_is_pushed(self):
        self.assertEqual(
            self.decide(local=4),
            {"action": "push", "progress": 4},
        )

    def test_remote_only_change_is_imported(self):
        self.assertEqual(
            self.decide(remote=4),
            {"action": "import", "authority": "AL"},
        )

    def test_completed_two_sided_change_is_conflict(self):
        self.assertEqual(
            self.decide(local=5, remote=6, status="COMPLETED"),
            {
                "action": "conflict",
                "authority": "LOCAL",
                "local": 5,
                "anilist": 6,
            },
        )

    def test_no_sync_keeps_changed_local_progress(self):
        self.assertEqual(
            self.decide(
                local=4,
                remote=6,
                anilist_source=True,
                sync_enabled=False,
            ),
            {
                "action": "local",
                "authority": "LOCAL",
                "progress": 4,
            },
        )

    def test_completed_total_sets_completed_status(self):
        show = {
            "_anilist_list": "CURRENT",
            "episodeCount": 12,
        }
        self.assertEqual(
            reconcile_status(show, 12, lambda value: int(value)),
            "COMPLETED",
        )


if __name__ == "__main__":
    unittest.main()

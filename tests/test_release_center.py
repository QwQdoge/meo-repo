import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from unittest import mock

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("release_center", ROOT / "tools/release_center.py")
release_center = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_center)


class ReleaseCenterTests(unittest.TestCase):
    def test_pending_train_tracks_reviewed_sources_but_cannot_be_dispatched(self):
        records = release_center.pending_trains("beta")
        train = next(record for record in records if record["release"] == "2026.09-beta.8")
        self.assertEqual({c["package"] for c in train["components"]},
                         {"meoui-qml", "meo-account", "omnistore-bin"})
        self.assertNotIn(train["path"], release_center.manifests("beta"))
        with mock.patch.object(release_center, "run") as run:
            result = release_center.validate_selection("beta", train["path"], "omnistore-bin")
        self.assertFalse(result["ok"])
        run.assert_not_called()

    def test_pending_records_are_filtered_by_channel_and_require_pinned_commits(self):
        self.assertEqual(release_center.pending_trains("stable"), [])
        self.assertEqual(release_center.pending_trains("../pending"), [])
        payload = release_center.pending_trains("beta")[0]
        payload["components"][0]["reviewedCommit"] = "main"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "manifests" / "pending"
            target.mkdir(parents=True)
            (target / "invalid.json").write_text(json.dumps(payload))
            with mock.patch.object(release_center, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "invalid preparation component"):
                    release_center.pending_trains("beta")

    def test_manifest_lists_stay_inside_channel(self):
        for channel in ("beta", "stable"):
            entries = release_center.manifests(channel)
            self.assertTrue(entries)
            self.assertTrue(all(path.startswith(f"manifests/{channel}/") for path in entries))

    def test_components_come_from_selected_manifest(self):
        manifest = release_center.manifests("beta")[0]
        components = release_center.manifest_components(manifest, "beta")
        self.assertIn("meo-desktop", components)
        self.assertIn("meoui-qml", components)

    def test_beta_requires_explicit_candidate(self):
        manifest = release_center.manifests("beta")[0]
        result = release_center.validate_selection("beta", manifest, "", full=False)
        self.assertFalse(result["ok"])
        self.assertIn("requires one explicit candidate", result["output"])

    def test_candidate_must_exist_in_manifest(self):
        manifest = release_center.manifests("stable")[0]
        result = release_center.validate_selection("stable", manifest, "definitely-not-a-package", full=False)
        self.assertFalse(result["ok"])
        self.assertIn("not present", result["output"])

    def test_manifest_cannot_cross_channels(self):
        beta = release_center.manifests("beta")[0]
        result = release_center.validate_selection("stable", beta, "", full=False)
        self.assertFalse(result["ok"])
        self.assertIn("select a committed manifest", result["output"])

    def test_manifest_health_surfaces_version_or_epoch_drift(self):
        manifest = release_center.manifests("beta")[0]
        result = release_center.manifest_health(manifest, "beta")
        self.assertIn("components", result)
        rows = {row["name"]: row for row in result["components"]}
        self.assertIn("meo-desktop", rows)
        self.assertIn("expected", rows["meo-desktop"])
        self.assertIn("recipe", rows["meo-desktop"])
        self.assertIn("epoch", rows["meo-desktop"])
        self.assertEqual(rows["meo-desktop"]["ok"],
                         rows["meo-desktop"]["expected"] == rows["meo-desktop"]["recipe"]
                         and rows["meo-desktop"]["epoch"])

    def test_git_sync_requires_exact_remote_main_head(self):
        responses = [
            {"ok": True, "code": 0, "output": "a" * 40},
            {"ok": True, "code": 0, "output": "b" * 40},
        ]
        with mock.patch.object(release_center, "run", side_effect=responses):
            result = release_center.git_sync(fetch=False)
        self.assertFalse(result["ok"])
        self.assertIn("does not match", result["output"])

    def test_dispatch_stops_before_gh_when_main_is_not_synced(self):
        with mock.patch.object(release_center, "validate_selection",
                               return_value={"ok": True, "output": "ok"}), \
             mock.patch.object(release_center, "git_sync",
                               return_value={"ok": False, "output": "main differs"}), \
             mock.patch.object(release_center, "gh_ready") as gh_ready:
            result = release_center.dispatch("beta", "manifests/beta/example.json", "meo-desktop")
        self.assertFalse(result["ok"])
        self.assertIn("Push/sync main", result["output"])
        gh_ready.assert_not_called()


if __name__ == "__main__":
    unittest.main()

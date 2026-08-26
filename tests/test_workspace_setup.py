from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workspace_setup.py"
SPEC = importlib.util.spec_from_file_location("workspace_setup", SCRIPT)
assert SPEC and SPEC.loader
workspace_setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace_setup)


class WorkspaceSetupTest(unittest.TestCase):
    def test_cli_plan_outputs_json_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "plan",
                    "--root",
                    str(root),
                    "--storage",
                    "local",
                    "--season",
                    "2026 하반기",
                ],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], "new")
            self.assertFalse(root.exists())

    def test_new_workspace_plan_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "한글 경로" / "취업 자료"
            plan = workspace_setup.setup_plan(
                root, "local", "2026 하반기", "disabled", "disabled", False
            )
            self.assertEqual(plan["status"], "new")
            self.assertIn(".chwippohaja/workspace.json", plan["create"])

            result = workspace_setup.apply_setup(
                root, "local", "2026 하반기", "disabled", "disabled", False
            )
            self.assertEqual(result["status"], "configured")
            self.assertTrue((root / "AGENTS.md").is_file())
            self.assertTrue((root / "공통자료" / "경력_프로젝트_소재.md").is_file())
            self.assertTrue((root / "2026 하반기").is_dir())

            config = json.loads(
                (root / ".chwippohaja" / "workspace.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["workspace_root"], ".")
            self.assertEqual(config["profile_status"], "empty")
            self.assertNotIn(str(root), json.dumps(config, ensure_ascii=False))

    def test_legacy_marker_defaults_profile_status_to_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            marker = root / ".chwippohaja" / "workspace.json"
            marker.parent.mkdir(parents=True)
            marker.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "workspace_root": ".",
                        "storage_mode": "local",
                        "active_season": "2026 하반기",
                        "integrations": {
                            "google_drive": "disabled",
                            "notion": "disabled",
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = workspace_setup.read_marker(root)
            self.assertIsNotNone(config)
            self.assertEqual(config["profile_status"], "empty")

    def test_profile_status_can_be_updated_without_changing_other_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            workspace_setup.apply_setup(
                root, "google-drive", "2026 하반기", "pending", "enabled", False
            )
            original = workspace_setup.read_marker(root)

            first = workspace_setup.update_profile_status(root, "in_progress")
            second = workspace_setup.update_profile_status(root, "ready")
            updated = workspace_setup.read_marker(root)

            self.assertEqual(first["previous_profile_status"], "empty")
            self.assertEqual(first["profile_status"], "in_progress")
            self.assertEqual(second["previous_profile_status"], "in_progress")
            self.assertEqual(updated["profile_status"], "ready")
            self.assertEqual(updated["storage_mode"], original["storage_mode"])
            self.assertEqual(updated["active_season"], original["active_season"])
            self.assertEqual(updated["integrations"], original["integrations"])

    def test_profile_status_requires_configured_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            root.mkdir()
            with self.assertRaises(workspace_setup.SetupError):
                workspace_setup.update_profile_status(root, "in_progress")

    def test_cli_profile_status_reports_and_updates_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            workspace_setup.apply_setup(
                root, "local", "2026 하반기", "disabled", "disabled", False
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "profile-status",
                    "--root",
                    str(root),
                    "--set",
                    "in_progress",
                ],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["profile_status"], "in_progress")

    def test_integration_status_can_be_updated_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            workspace_setup.apply_setup(
                root, "google-drive", "2026 하반기", "pending", "pending", False
            )

            result = workspace_setup.update_integration_status(root, "notion", "enabled")
            config = workspace_setup.read_marker(root)

            self.assertEqual(result["previous_integration_status"], "pending")
            self.assertEqual(result["integration_status"], "enabled")
            self.assertEqual(config["integrations"]["notion"], "enabled")
            self.assertEqual(config["integrations"]["google_drive"], "pending")

    def test_integration_status_rejects_unknown_service(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            workspace_setup.apply_setup(
                root, "local", "2026 하반기", "disabled", "disabled", False
            )
            with self.assertRaises(workspace_setup.SetupError):
                workspace_setup.update_integration_status(root, "calendar", "enabled")

    def test_cli_integration_status_reports_and_updates_selected_service(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            workspace_setup.apply_setup(
                root, "google-drive", "2026 하반기", "pending", "pending", False
            )
            updated = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "integration-status",
                    "--root",
                    str(root),
                    "--service",
                    "notion",
                    "--set",
                    "enabled",
                ],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )
            reported = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "integration-status",
                    "--root",
                    str(root),
                ],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )

            self.assertEqual(updated.returncode, 0, updated.stderr)
            self.assertEqual(json.loads(updated.stdout)["integration_status"], "enabled")
            self.assertEqual(reported.returncode, 0, reported.stderr)
            self.assertEqual(
                json.loads(reported.stdout)["integrations"],
                {"google_drive": "pending", "notion": "enabled"},
            )

    def test_second_apply_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            workspace_setup.apply_setup(
                root, "local", "2026 하반기", "disabled", "disabled", False
            )
            original = root / "AGENTS.md"
            original.write_text("사용자 규칙\n", encoding="utf-8")

            result = workspace_setup.apply_setup(
                root, "local", "2026 하반기", "disabled", "disabled", False
            )
            self.assertEqual(result["status"], "already-configured")
            self.assertEqual(original.read_text(encoding="utf-8"), "사용자 규칙\n")

    def test_existing_workspace_requires_adopt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            common = root / "공통자료"
            common.mkdir(parents=True)
            existing = common / "경력_프로젝트_소재.md"
            existing.write_text("기존 내용\n", encoding="utf-8")

            with self.assertRaises(workspace_setup.SetupError):
                workspace_setup.setup_plan(
                    root, "local", "2026 하반기", "disabled", "disabled", False
                )

            workspace_setup.apply_setup(
                root, "local", "2026 하반기", "pending", "pending", True
            )
            self.assertEqual(existing.read_text(encoding="utf-8"), "기존 내용\n")
            self.assertTrue((root / ".chwippohaja" / "workspace.json").is_file())

    def test_invalid_season_is_rejected(self) -> None:
        for season in (
            "",
            ".",
            "..",
            "2026/하반기",
            "2026\\하반기",
            "2026:하반기",
            "CON",
            "하반기.",
        ):
            with self.subTest(season=season):
                with self.assertRaises(workspace_setup.SetupError):
                    workspace_setup.validate_season(season)

    def test_home_directory_is_rejected(self) -> None:
        with self.assertRaises(workspace_setup.SetupError):
            workspace_setup.validate_root(Path.home())

    def test_discovery_from_home_does_not_offer_home_as_workspace(self) -> None:
        result = workspace_setup.discovery(Path.home())
        self.assertNotIn(str(Path.home().resolve()), result["candidates"]["local"])

    def test_drive_content_root_uses_my_drive_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            account_root = Path(temporary) / "GoogleDrive-account"
            my_drive = account_root / "내 드라이브"
            my_drive.mkdir(parents=True)
            self.assertEqual(workspace_setup.drive_content_roots(account_root), [my_drive])

    def test_invalid_marker_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            marker = root / ".chwippohaja" / "workspace.json"
            marker.mkdir(parents=True)
            result = workspace_setup.inspect_workspace(root)
            self.assertEqual(result["status"], "invalid")

    def test_marker_with_invalid_season_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            marker = root / ".chwippohaja" / "workspace.json"
            marker.parent.mkdir(parents=True)
            marker.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "workspace_root": ".",
                        "storage_mode": "local",
                        "active_season": None,
                        "integrations": {
                            "google_drive": "disabled",
                            "notion": "disabled",
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = workspace_setup.inspect_workspace(root)
            self.assertEqual(result["status"], "invalid")

    def test_marker_with_invalid_profile_status_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            marker = root / ".chwippohaja" / "workspace.json"
            marker.parent.mkdir(parents=True)
            marker.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "workspace_root": ".",
                        "storage_mode": "local",
                        "active_season": "2026 하반기",
                        "profile_status": "complete",
                        "integrations": {
                            "google_drive": "disabled",
                            "notion": "disabled",
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = workspace_setup.inspect_workspace(root)
            self.assertEqual(result["status"], "invalid")

    def test_non_object_marker_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            marker = root / ".chwippohaja" / "workspace.json"
            marker.parent.mkdir(parents=True)
            marker.write_text("[]", encoding="utf-8")
            result = workspace_setup.inspect_workspace(root)
            self.assertEqual(result["status"], "invalid")

    def test_file_directory_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            (root / "AGENTS.md").mkdir(parents=True)
            with self.assertRaises(workspace_setup.SetupError):
                workspace_setup.setup_plan(
                    root, "local", "2026 하반기", "disabled", "disabled", True
                )

    def test_find_workspace_from_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            workspace_setup.apply_setup(
                root, "google-drive", "2026 하반기", "enabled", "enabled", False
            )
            child = root / "2026 하반기" / "회사"
            child.mkdir()
            self.assertEqual(workspace_setup.find_workspace(child), root.resolve())

    def test_discovery_infers_workspace_above_season_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            for name in ("공통자료", "작성템플릿", "증빙서류"):
                (root / name).mkdir(parents=True)
            (root / "AGENTS.md").write_text("규칙\n", encoding="utf-8")
            season = root / "2026 하반기"
            season.mkdir()
            (season / "AGENTS.md").write_text("시즌 규칙\n", encoding="utf-8")

            result = workspace_setup.discovery(season)

            self.assertEqual(result["workspace_root"], str(root.resolve()))
            self.assertEqual(result["workspace"]["status"], "adoptable")
            self.assertEqual(result["candidates"]["local"][0], str(root.resolve()))


if __name__ == "__main__":
    unittest.main()

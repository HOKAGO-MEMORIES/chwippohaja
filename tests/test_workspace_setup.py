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
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((root / "README_취업자료_운영규칙.md").exists())
            self.assertTrue((root / "공통자료" / "경력_프로젝트_소재.md").is_file())
            self.assertTrue((root / "증빙서류" / "자격증_어학").is_dir())
            self.assertTrue((root / "증빙서류" / "경력_병역").is_dir())
            self.assertFalse((root / "증빙서류" / "자격증").exists())
            self.assertFalse((root / "증빙서류" / "경력").exists())
            self.assertTrue((root / "2026 하반기").is_dir())

            config = json.loads(
                (root / ".chwippohaja" / "workspace.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["workspace_root"], ".")
            self.assertEqual(config["profile_status"], "empty")
            self.assertNotIn(str(root), json.dumps(config, ensure_ascii=False))

    def test_new_workspace_rejects_nonempty_profile_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            with self.assertRaises(workspace_setup.SetupError):
                workspace_setup.setup_plan(
                    root,
                    "local",
                    "2026 하반기",
                    "disabled",
                    "disabled",
                    False,
                    "ready",
                )

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
            templates = root / "작성템플릿"
            templates.mkdir()
            existing_template = templates / "기존_작성기준.md"
            existing_template.write_text("기존 템플릿\n", encoding="utf-8")
            evidence = root / "증빙서류"
            (evidence / "자격증_어학").mkdir(parents=True)
            (evidence / "경력_병역").mkdir()
            season = root / "2026 하반기"
            season.mkdir()
            local_rules = root / "AGENTS.md"
            local_rules.write_text("사용자 추가 규칙\n", encoding="utf-8")
            files_before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            directories_before = {
                path.relative_to(root)
                for path in root.rglob("*")
                if path.is_dir()
            }

            with self.assertRaises(workspace_setup.SetupError):
                workspace_setup.setup_plan(
                    root, "local", "2026 하반기", "disabled", "disabled", False
                )

            plan = workspace_setup.setup_plan(
                root,
                "local",
                "2026 하반기",
                "pending",
                "pending",
                True,
                "ready",
            )
            self.assertIn("AGENTS.md", plan["preserve"])
            self.assertNotIn("AGENTS.md", plan["create"])
            self.assertEqual(
                plan["create"],
                [".chwippohaja/", ".chwippohaja/workspace.json"],
            )
            self.assertEqual(plan["config"]["profile_status"], "ready")

            workspace_setup.apply_setup(
                root,
                "local",
                "2026 하반기",
                "pending",
                "pending",
                True,
                "ready",
            )
            self.assertEqual(existing.read_text(encoding="utf-8"), "기존 내용\n")
            self.assertEqual(
                existing_template.read_text(encoding="utf-8"), "기존 템플릿\n"
            )
            self.assertEqual(local_rules.read_text(encoding="utf-8"), "사용자 추가 규칙\n")
            self.assertTrue((root / ".chwippohaja" / "workspace.json").is_file())
            self.assertFalse((evidence / "자격증").exists())
            self.assertFalse((evidence / "어학").exists())
            self.assertFalse((evidence / "경력").exists())
            self.assertFalse((evidence / "병역").exists())
            self.assertFalse((templates / "자소서_작성설계.md").exists())

            config = workspace_setup.read_marker(root)
            self.assertIsNotNone(config)
            self.assertEqual(config["profile_status"], "ready")
            files_after = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file() and root / ".chwippohaja" not in path.parents
            }
            directories_after = {
                path.relative_to(root)
                for path in root.rglob("*")
                if path.is_dir() and path != root / ".chwippohaja"
            }
            self.assertEqual(files_after, files_before)
            self.assertEqual(directories_after, directories_before)

    def test_adopt_creates_missing_active_season_but_no_default_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            (root / "공통자료").mkdir(parents=True)
            (root / "작성템플릿").mkdir()
            (root / "증빙서류").mkdir()

            plan = workspace_setup.setup_plan(
                root,
                "local",
                "2026 하반기",
                "disabled",
                "disabled",
                True,
                "in_progress",
            )

            self.assertEqual(
                plan["create"],
                [
                    "2026 하반기/",
                    ".chwippohaja/",
                    ".chwippohaja/workspace.json",
                ],
            )
            workspace_setup.apply_setup(
                root,
                "local",
                "2026 하반기",
                "disabled",
                "disabled",
                True,
                "in_progress",
            )
            self.assertTrue((root / "2026 하반기").is_dir())
            self.assertFalse((root / "작성템플릿" / "자소서_작성설계.md").exists())
            self.assertEqual(
                workspace_setup.read_marker(root)["profile_status"], "in_progress"
            )

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

    def test_adopt_rejects_active_season_file_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            (root / "공통자료").mkdir(parents=True)
            (root / "2026 하반기").write_text("폴더 아님\n", encoding="utf-8")
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

    def test_discovery_infers_workspace_above_season_folder_without_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            for name in ("공통자료", "작성템플릿", "증빙서류"):
                (root / name).mkdir(parents=True)
            season = root / "2026 하반기"
            season.mkdir()

            result = workspace_setup.discovery(season)

            self.assertEqual(result["workspace_root"], str(root.resolve()))
            self.assertEqual(result["workspace"]["status"], "adoptable")
            self.assertEqual(result["candidates"]["local"][0], str(root.resolve()))


if __name__ == "__main__":
    unittest.main()

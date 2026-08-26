from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
APPLICATION_SCRIPT = SCRIPT_DIRECTORY / "application_workspace.py"
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

WORKSPACE_SPEC = importlib.util.spec_from_file_location(
    "workspace_setup", SCRIPT_DIRECTORY / "workspace_setup.py"
)
assert WORKSPACE_SPEC and WORKSPACE_SPEC.loader
workspace_setup = importlib.util.module_from_spec(WORKSPACE_SPEC)
sys.modules["workspace_setup"] = workspace_setup
WORKSPACE_SPEC.loader.exec_module(workspace_setup)

APPLICATION_SPEC = importlib.util.spec_from_file_location(
    "application_workspace", SCRIPT_DIRECTORY / "application_workspace.py"
)
assert APPLICATION_SPEC and APPLICATION_SPEC.loader
application_workspace = importlib.util.module_from_spec(APPLICATION_SPEC)
APPLICATION_SPEC.loader.exec_module(application_workspace)


class ApplicationWorkspaceTest(unittest.TestCase):
    def configured_root(self, temporary: str) -> Path:
        root = Path(temporary) / "취업"
        workspace_setup.apply_setup(
            root, "local", "2026 하반기", "disabled", "disabled", False
        )
        return root

    def test_first_application_uses_company_folder_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.configured_root(temporary)
            first = application_workspace.apply_application(root, "예시전자", "IT")
            second = application_workspace.apply_application(root, "예시전자", "IT")

            application = root / "2026 하반기" / "예시전자"
            self.assertEqual(first["status"], "configured")
            self.assertEqual(second["status"], "already-configured")
            self.assertTrue((application / "01_공고_JD").is_dir())
            self.assertTrue((application / "02_작성중").is_dir())
            self.assertTrue((application / "99_최종제출").is_dir())

    def test_second_role_uses_role_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.configured_root(temporary)
            application_workspace.apply_application(root, "예시전자", "IT")
            result = application_workspace.apply_application(root, "예시전자", "Solution SW")
            self.assertEqual(
                Path(result["application"]).name,
                "예시전자_Solution SW",
            )

    def test_same_role_new_application_requires_posting_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.configured_root(temporary)
            application_workspace.apply_application(root, "예시전자", "IT")
            with self.assertRaises(application_workspace.ApplicationError):
                application_workspace.application_plan(
                    root, "예시전자", "IT", new_application=True
                )

            result = application_workspace.apply_application(
                root,
                "예시전자",
                "IT",
                posting_key="R261762",
                new_application=True,
            )
            self.assertEqual(Path(result["application"]).name, "예시전자_IT_R261762")

    def test_existing_keyed_application_does_not_resume_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.configured_root(temporary)
            application_workspace.apply_application(
                root, "예시전자", "IT", posting_key="R100"
            )
            with self.assertRaises(application_workspace.ApplicationError):
                application_workspace.application_plan(root, "예시전자", "IT")

    def test_different_posting_key_requires_new_application_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.configured_root(temporary)
            application_workspace.apply_application(
                root, "예시전자", "IT", posting_key="R100"
            )
            with self.assertRaises(application_workspace.ApplicationError):
                application_workspace.application_plan(
                    root, "예시전자", "IT", posting_key="R200"
                )

    def test_legacy_company_folder_requires_explicit_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.configured_root(temporary)
            legacy = root / "2026 하반기" / "기존회사"
            (legacy / "01_공고_JD").mkdir(parents=True)
            with self.assertRaises(application_workspace.ApplicationError):
                application_workspace.application_plan(root, "기존회사", "개발")

            result = application_workspace.apply_application(
                root, "기존회사", "개발", adopt_existing=True
            )
            marker = legacy / "01_공고_JD" / ".application.json"
            self.assertEqual(result["status"], "configured")
            self.assertEqual(json.loads(marker.read_text(encoding="utf-8"))["role"], "개발")

    def test_next_draft_uses_highest_number_without_reusing_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.configured_root(temporary)
            result = application_workspace.apply_application(root, "예시전자", "IT")
            application = Path(result["application"])
            draft = application / "02_작성중"
            (draft / "01_초안.md").write_text("초안\n", encoding="utf-8")
            (draft / "03_수정.md").write_text("수정\n", encoding="utf-8")

            next_file = application_workspace.next_draft(
                application, "예시전자_IT_자소서_초안", "md"
            )
            self.assertEqual(next_file["number"], 4)
            self.assertEqual(next_file["filename"], "04_예시전자_IT_자소서_초안.md")

    def test_windows_reserved_component_is_rejected(self) -> None:
        with self.assertRaises(application_workspace.ApplicationError):
            application_workspace.safe_component("CON", "기업명")

    def test_cli_plan_is_read_only_and_apply_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.configured_root(temporary)
            command = [
                sys.executable,
                str(APPLICATION_SCRIPT),
                "plan",
                "--root",
                str(root),
                "--company",
                "예시전자",
                "--role",
                "IT",
                "--posting-key",
                "R100",
            ]
            planned = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            application = root / "2026 하반기" / "예시전자"

            self.assertEqual(planned.returncode, 0, planned.stderr)
            self.assertEqual(json.loads(planned.stdout)["status"], "new")
            self.assertFalse(application.exists())

            command[2] = "apply"
            applied = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            resumed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["status"], "configured")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(json.loads(resumed.stdout)["status"], "already-configured")


if __name__ == "__main__":
    unittest.main()

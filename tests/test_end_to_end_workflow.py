from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
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


class EndToEndWorkflowTest(unittest.TestCase):
    def test_local_workspace_from_onboarding_to_versioned_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"

            workspace_setup.apply_setup(
                root,
                "local",
                "2026 하반기",
                "pending",
                "disabled",
                False,
            )
            workspace_setup.update_profile_status(root, "in_progress")
            workspace_setup.update_integration_status(root, "notion", "enabled")
            application_result = application_workspace.apply_application(
                root, "예시전자", "IT", posting_key="EXAMPLE-001"
            )
            application = Path(application_result["application"])
            first = application_workspace.next_draft(
                application, "예시전자_IT_자소서_초안", "md"
            )
            Path(first["path"]).write_text("```text\n검증용 본문\n```\n", encoding="utf-8")
            second = application_workspace.next_draft(
                application, "예시전자_IT_자소서_수정", "md"
            )

            workspace_marker = json.loads(
                (root / ".chwippohaja" / "workspace.json").read_text(encoding="utf-8")
            )
            application_marker = json.loads(
                (application / "01_공고_JD" / ".application.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(workspace_marker["profile_status"], "in_progress")
            self.assertEqual(workspace_marker["integrations"]["notion"], "enabled")
            self.assertEqual(application_marker["posting_key"], "EXAMPLE-001")
            self.assertEqual(first["number"], 1)
            self.assertEqual(second["number"], 2)
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((root / "README_취업자료_운영규칙.md").exists())
            self.assertNotIn(str(root), json.dumps(workspace_marker, ensure_ascii=False))
            self.assertNotIn(str(root), json.dumps(application_marker, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()

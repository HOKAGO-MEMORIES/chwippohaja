from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "essay_hook.py"
INSTALLER = ROOT / "scripts" / "install_essay_hooks.py"
HOOK_ID = "chwippohaja-essay-hook"


def checkpoint(value: dict[str, object]) -> str:
    return (
        "<!-- chwippohaja:essay-checkpoint:start -->\n"
        "```json\n"
        f"{json.dumps(value, ensure_ascii=False)}\n"
        "```\n"
        "<!-- chwippohaja:essay-checkpoint:end -->\n"
    )


def pre_draft() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "pre_draft",
        "document_status": "ready_full",
        "questions": [
            {
                "id": "1",
                "question_type": "개선",
                "subquestions": ["무엇을 개선했는가"],
                "experience_question": True,
                "reflection_required": False,
                "material_fit": "direct",
                "material_fit_reason": "문제 판단과 개선 행동을 직접 보여준다.",
                "evidence": ["확인된 프로젝트 기록"],
                "missing_information": [],
                "follow_up_questions": [],
                "action": "write",
            }
        ],
    }


def draft_review() -> dict[str, object]:
    return {
        "schema_version": 1,
        "phase": "draft_review",
        "document_status": "valid_draft",
        "questions": [
            {
                "id": "1",
                "answer_status": "valid",
                "answer_present": True,
                "experience_question": True,
                "reflection_required": False,
                "fatal_issues": [],
                "recommended_issues": [],
                "missing_information": [],
                "follow_up_questions": [],
                "content_checks": {
                    "all_subquestions_answered": True,
                    "question_type_fit_verified": True,
                    "facts_verified": True,
                    "role_verified": True,
                    "material_fit_verified": True,
                    "judgment_action_result_connected": True,
                    "reader_effect_clear": True,
                    "reflection_requirement_met": None,
                    "experience_meaning_present": True,
                },
            }
        ],
        "style_review": {
            "validator_run": True,
            "structural_passed": True,
            "candidates_reviewed": True,
            "character_count_checked": True,
        },
        "revision": {
            "previous_version": None,
            "purpose": "첫 유효 초안 작성",
            "issue_ids": [],
            "changes": ["확인된 소재로 첫 답변 작성"],
            "resolved_issues": [],
            "remaining_issues": [],
            "remaining_fatal_issues": [],
            "character_count_impact": "첫 버전 33자",
            "all_identified_issues_reviewed": True,
        },
    }


class EssayHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".chwippohaja").mkdir()
        (self.root / ".chwippohaja" / "workspace.json").write_text(
            '{"schema_version": 1, "workspace_root": "."}\n', encoding="utf-8"
        )
        self.working = self.root / "2026 하반기" / "예시기업" / "02_작성중"
        self.working.mkdir(parents=True)
        self.plan = self.working / "01_작성설계.md"
        self.draft = self.working / "02_자소서_초안.md"
        self.plan.write_text(checkpoint(pre_draft()), encoding="utf-8")
        self.write_valid_draft()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_valid_draft(self) -> None:
        body = "[재실행에도 수렴하는 구조]\n문제를 확인하고 구조를 바꾼 뒤 결과를 검증했습니다."
        self.draft.write_text(
            f"```text\n{body}\n```\n\n{checkpoint(draft_review())}", encoding="utf-8"
        )

    def run_script(self, *args: str, input_value: dict[str, object] | None = None) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=json.dumps(input_value, ensure_ascii=False) if input_value else None,
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )

    def start(self) -> subprocess.CompletedProcess[str]:
        started = self.run_script(
            "start",
            "--workspace",
            str(self.root),
            "--plan",
            str(self.plan),
            "--draft",
            str(self.draft),
            "--limit",
            "1:20:1500",
        )
        if started.returncode == 0:
            checked = self.run_script("plan-check", "--workspace", str(self.root))
            if checked.returncode != 0:
                return checked
        return started

    def test_check_accepts_valid_essay_run(self) -> None:
        self.assertEqual(self.start().returncode, 0)
        result = self.run_script("check", "--workspace", str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["valid"])

    def test_check_accepts_partial_draft_without_answer_block_for_deferred_question(self) -> None:
        plan = pre_draft()
        plan["document_status"] = "ready_partial"
        plan["questions"].append(
            {
                "id": "2",
                "question_type": "소통",
                "subquestions": ["어떻게 의견을 조율했는가"],
                "experience_question": True,
                "reflection_required": True,
                "material_fit": "missing",
                "material_fit_reason": "확인된 조율 경험이 없다.",
                "evidence": [],
                "missing_information": ["의견 조율 경험"],
                "follow_up_questions": ["의견을 조율한 경험을 알려주세요."],
                "action": "defer",
            }
        )
        review = draft_review()
        review["document_status"] = "partial_draft"
        review["questions"].append(
            {
                "id": "2",
                "answer_status": "deferred",
                "answer_present": False,
                "experience_question": True,
                "reflection_required": True,
                "fatal_issues": [],
                "recommended_issues": [],
                "missing_information": ["의견 조율 경험"],
                "follow_up_questions": ["의견을 조율한 경험을 알려주세요."],
            }
        )
        self.plan.write_text(checkpoint(plan), encoding="utf-8")
        source = self.draft.read_text(encoding="utf-8")
        body = source.split("<!-- chwippohaja:essay-checkpoint:start -->", 1)[0]
        self.draft.write_text(body + checkpoint(review), encoding="utf-8")
        started = self.run_script(
            "start",
            "--workspace",
            str(self.root),
            "--plan",
            str(self.plan),
            "--draft",
            str(self.draft),
            "--limit",
            "1:20:1500",
            "--limit",
            "2:0:1500",
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        planned = self.run_script("plan-check", "--workspace", str(self.root))
        self.assertEqual(planned.returncode, 0, planned.stderr + planned.stdout)
        result = self.run_script("check", "--workspace", str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_full_check_rejects_draft_before_plan_checkpoint(self) -> None:
        started = self.run_script(
            "start",
            "--workspace",
            str(self.root),
            "--plan",
            str(self.plan),
            "--draft",
            str(self.draft),
            "--limit",
            "1:20:1500",
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        result = self.run_script("check", "--workspace", str(self.root))
        self.assertEqual(result.returncode, 2)
        self.assertIn("초안 작성 전에", result.stdout)

    def test_post_tool_use_advances_from_plan_to_draft_in_separate_writes(self) -> None:
        started = self.run_script(
            "start",
            "--workspace",
            str(self.root),
            "--plan",
            str(self.plan),
            "--draft",
            str(self.draft),
            "--limit",
            "1:20:1500",
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        plan_event = self.run_script(
            "hook",
            input_value={
                "event": "PostToolUse",
                "session_id": "session-a",
                "cwd": str(self.working),
                "tool_input": {"path": str(self.plan)},
            },
        )
        self.assertEqual(json.loads(plan_event.stdout), {})
        draft_event = self.run_script(
            "hook",
            input_value={
                "event": "PostToolUse",
                "session_id": "session-a",
                "cwd": str(self.working),
                "tool_input": {"path": str(self.draft)},
            },
        )
        self.assertEqual(json.loads(draft_event.stdout), {})
        state = json.loads(
            (self.root / ".chwippohaja" / "runs" / "essay-current.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["phase"], "drafting")
        self.assertEqual(state["status"], "passed")

    def test_post_tool_use_blocks_plan_and_draft_created_together(self) -> None:
        started = self.run_script(
            "start",
            "--workspace",
            str(self.root),
            "--plan",
            str(self.plan),
            "--draft",
            str(self.draft),
            "--limit",
            "1:20:1500",
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        result = self.run_script(
            "hook",
            input_value={
                "event": "PostToolUse",
                "session_id": "session-a",
                "cwd": str(self.working),
                "tool_input": {"patch": f"{self.plan}\n{self.draft}"},
            },
        )
        response = json.loads(result.stdout)
        self.assertEqual(response["decision"], "block")
        self.assertIn("한 번에", response["reason"])

    def test_stop_blocks_structurally_invalid_draft(self) -> None:
        self.assertEqual(self.start().returncode, 0)
        source = self.draft.read_text(encoding="utf-8")
        self.draft.write_text(source.replace("[재실행에도 수렴하는 구조]", "[구조를 개선했습니다]"), encoding="utf-8")
        result = self.run_script(
            "hook",
            input_value={"event": "Stop", "session_id": "session-a", "cwd": str(self.working)},
        )
        response = json.loads(result.stdout)
        self.assertEqual(response["decision"], "block")
        self.assertIn("서술형 요약", response["reason"])

    def test_waiting_for_user_allows_stop(self) -> None:
        self.assertEqual(self.start().returncode, 0)
        wait = self.run_script(
            "wait",
            "--workspace",
            str(self.root),
            "--reason",
            "문항에 맞는 협업 경험이 없음",
            "--question",
            "의견을 조율한 경험을 알려주세요.",
        )
        self.assertEqual(wait.returncode, 0, wait.stderr)
        result = self.run_script(
            "hook",
            input_value={"event": "Stop", "session_id": "session-a", "cwd": str(self.working)},
        )
        self.assertEqual(json.loads(result.stdout), {})

    def test_unrelated_post_tool_use_does_not_revalidate(self) -> None:
        self.assertEqual(self.start().returncode, 0)
        self.draft.unlink()
        result = self.run_script(
            "hook",
            input_value={
                "event": "PostToolUse",
                "session_id": "session-a",
                "cwd": str(self.working),
                "tool_input": {"path": "unrelated.md"},
            },
        )
        self.assertEqual(json.loads(result.stdout), {})

    def test_target_outside_workspace_is_rejected(self) -> None:
        result = self.run_script(
            "start",
            "--workspace",
            str(self.root),
            "--plan",
            str(self.plan),
            "--draft",
            str(self.root.parent / "outside.md"),
            "--limit",
            "1:0:1500",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("워크스페이스 내부", result.stderr)

    def test_installer_preserves_existing_hooks_and_is_idempotent(self) -> None:
        project_root = self.root / "2026 하반기"
        config = project_root / ".codex" / "hooks.json"
        config.parent.mkdir()
        config.write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [
                            {"hooks": [{"type": "command", "command": "existing-hook"}]}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for _ in range(2):
            result = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    str(self.root),
                    "--project-root",
                    str(project_root),
                ],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        loaded = json.loads(config.read_text(encoding="utf-8"))
        stop_commands = [
            hook["command"]
            for group in loaded["hooks"]["Stop"]
            for hook in group["hooks"]
        ]
        self.assertIn("existing-hook", stop_commands)
        self.assertEqual(sum(HOOK_ID in item for item in stop_commands), 1)
        self.assertIn("PostToolUse", loaded["hooks"])


if __name__ == "__main__":
    unittest.main()

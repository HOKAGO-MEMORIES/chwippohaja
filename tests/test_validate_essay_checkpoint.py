from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPT_DIRECTORY / "validate_essay_checkpoint.py"
SPEC = importlib.util.spec_from_file_location("validate_essay_checkpoint", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def wrapped(checkpoint: dict[str, object]) -> str:
    return (
        "<!-- chwippohaja:essay-checkpoint:start -->\n"
        "```json\n"
        f"{json.dumps(checkpoint, ensure_ascii=False)}\n"
        "```\n"
        "<!-- chwippohaja:essay-checkpoint:end -->\n"
    )


def pre_question(identifier: str, action: str = "write") -> dict[str, object]:
    if action == "write":
        return {
            "id": identifier,
            "question_type": "학습",
            "subquestions": ["문항의 핵심 질문"],
            "experience_question": True,
            "reflection_required": False,
            "material_fit": "direct",
            "material_fit_reason": "부족했던 지식과 실제 학습 과정을 직접 보여준다.",
            "evidence": ["확인된 프로젝트 기록"],
            "missing_information": [],
            "follow_up_questions": [],
            "action": "write",
        }
    return {
        "id": identifier,
        "question_type": "소통",
        "subquestions": ["문항의 핵심 질문"],
        "experience_question": True,
        "reflection_required": True,
        "material_fit": "missing",
        "material_fit_reason": "상대와 주고받은 정보와 행동 변화가 확인되지 않는다.",
        "evidence": [],
        "missing_information": ["해당 행동을 보여주는 경험"],
        "follow_up_questions": ["관련 경험에서 본인이 한 행동은 무엇인가요?"],
        "action": "defer",
    }


def valid_answer(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
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


def deferred_answer(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
        "answer_status": "deferred",
        "answer_present": False,
        "experience_question": True,
        "reflection_required": True,
        "fatal_issues": [],
        "recommended_issues": [],
        "missing_information": ["적합한 협업 경험"],
        "follow_up_questions": ["의견 차이를 조율한 경험이 있나요?"],
    }


STYLE_REVIEW = {
    "validator_run": True,
    "structural_passed": True,
    "candidates_reviewed": True,
    "character_count_checked": True,
}


class ValidateEssayCheckpointTest(unittest.TestCase):
    def test_accepts_full_pre_draft_checkpoint(self) -> None:
        checkpoint = {
            "schema_version": 1,
            "phase": "pre_draft",
            "document_status": "ready_full",
            "questions": [pre_question("1"), pre_question("2")],
        }
        parsed = validator.load_checkpoint(wrapped(checkpoint))
        self.assertEqual(validator.validate(parsed), [])

    def test_accepts_partial_pre_draft_checkpoint(self) -> None:
        checkpoint = {
            "schema_version": 1,
            "phase": "pre_draft",
            "document_status": "ready_partial",
            "questions": [pre_question("1"), pre_question("2", "defer")],
        }
        self.assertEqual(validator.validate(checkpoint), [])

    def test_rejects_writing_with_missing_material(self) -> None:
        question = pre_question("1")
        question["material_fit"] = "missing"
        checkpoint = {
            "schema_version": 1,
            "phase": "pre_draft",
            "document_status": "ready_full",
            "questions": [question],
        }
        errors = validator.validate(checkpoint)
        self.assertTrue(any("write할 수 없습니다" in error for error in errors))

    def test_accepts_partial_draft_with_valid_and_deferred_answers(self) -> None:
        checkpoint = {
            "schema_version": 1,
            "phase": "draft_review",
            "document_status": "partial_draft",
            "questions": [valid_answer("1"), deferred_answer("2")],
            "style_review": STYLE_REVIEW,
        }
        self.assertEqual(validator.validate(checkpoint), [])

    def test_rejects_valid_answer_with_fatal_issue(self) -> None:
        answer = valid_answer("1")
        answer["fatal_issues"] = ["문항의 필수 질문 누락"]
        checkpoint = {
            "schema_version": 1,
            "phase": "draft_review",
            "document_status": "valid_draft",
            "questions": [answer],
            "style_review": STYLE_REVIEW,
        }
        errors = validator.validate(checkpoint)
        self.assertTrue(any("valid로 판정할 수 없습니다" in error for error in errors))

    def test_final_candidate_requires_experience_meaning(self) -> None:
        answer = valid_answer("1")
        answer["content_checks"]["experience_meaning_present"] = False
        checkpoint = {
            "schema_version": 1,
            "phase": "draft_review",
            "document_status": "final_candidate",
            "questions": [answer],
            "style_review": STYLE_REVIEW,
        }
        errors = validator.validate(checkpoint)
        self.assertTrue(any("경험의 구체적인 의미" in error for error in errors))

    def test_cli_returns_nonzero_for_invalid_checkpoint(self) -> None:
        checkpoint = {
            "schema_version": 1,
            "phase": "pre_draft",
            "document_status": "ready_full",
            "questions": [pre_question("1", "defer")],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "작성설계.md"
            path.write_text(wrapped(checkpoint), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("valid=false", completed.stdout)

    def test_all_deferred_pre_draft_is_blocked(self) -> None:
        checkpoint = {
            "schema_version": 1,
            "phase": "pre_draft",
            "document_status": "blocked",
            "questions": [pre_question("1", "defer")],
        }
        errors = validator.validate(checkpoint)
        self.assertTrue(any("진행할 수 없습니다" in error for error in errors))

    def test_needs_revision_draft_cannot_pass_checkpoint(self) -> None:
        answer = valid_answer("1")
        answer["answer_status"] = "needs_revision"
        answer["fatal_issues"] = ["문항의 필수 질문 누락"]
        checkpoint = {
            "schema_version": 1,
            "phase": "draft_review",
            "document_status": "needs_revision",
            "questions": [answer],
        }
        errors = validator.validate(checkpoint)
        self.assertTrue(any("다시 검사" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

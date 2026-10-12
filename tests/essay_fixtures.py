"""Shared checkpoint fixtures for essay tests."""

from __future__ import annotations

import json


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



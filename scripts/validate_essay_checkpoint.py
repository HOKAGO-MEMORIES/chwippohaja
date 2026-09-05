#!/usr/bin/env python3
"""Validate machine-readable pre-draft and draft-review essay checkpoints."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


CHECKPOINT = re.compile(
    r"<!--\s*chwippohaja:essay-checkpoint:start\s*-->\s*"
    r"```json\s*(\{.*?\})\s*```\s*"
    r"<!--\s*chwippohaja:essay-checkpoint:end\s*-->",
    re.DOTALL,
)
PRE_DRAFT_STATUSES = {"ready_full", "ready_partial", "blocked"}
DRAFT_REVIEW_STATUSES = {
    "valid_draft",
    "partial_draft",
    "needs_revision",
    "blocked",
    "final_candidate",
}
MATERIAL_FITS = {"direct", "conditional_resolved", "unsuitable", "missing"}
ACTIONS = {"write", "defer"}
ANSWER_STATUSES = {"valid", "deferred", "needs_revision"}
REQUIRED_CONTENT_CHECKS = (
    "all_subquestions_answered",
    "question_type_fit_verified",
    "facts_verified",
    "role_verified",
    "material_fit_verified",
    "judgment_action_result_connected",
    "reader_effect_clear",
)
REQUIRED_STYLE_CHECKS = (
    "validator_run",
    "structural_passed",
    "candidates_reviewed",
    "character_count_checked",
)


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def load_checkpoint(source: str) -> dict[str, Any]:
    matches = CHECKPOINT.findall(source)
    if len(matches) != 1:
        raise ValueError(
            "essay checkpoint 블록이 정확히 1개 필요합니다: "
            "chwippohaja:essay-checkpoint:start/end"
        )
    try:
        checkpoint = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"essay checkpoint JSON이 올바르지 않습니다: {exc}") from exc
    if not isinstance(checkpoint, dict):
        raise ValueError("essay checkpoint는 JSON 객체여야 합니다.")
    return checkpoint


def validate_common(checkpoint: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if checkpoint.get("schema_version") != 1:
        errors.append("schema_version은 1이어야 합니다.")
    questions = checkpoint.get("questions")
    if not isinstance(questions, list) or not questions:
        errors.append("questions는 비어 있지 않은 배열이어야 합니다.")
        return errors
    identifiers: list[str] = []
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            errors.append(f"questions[{index}]는 객체여야 합니다.")
            continue
        identifier = question.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"questions[{index}].id가 필요합니다.")
        else:
            identifiers.append(identifier)
    if len(identifiers) != len(set(identifiers)):
        errors.append("question id가 중복되었습니다.")
    return errors


def validate_pre_draft(checkpoint: dict[str, Any]) -> list[str]:
    errors = validate_common(checkpoint)
    if checkpoint.get("phase") != "pre_draft":
        errors.append("phase는 pre_draft여야 합니다.")
    status = checkpoint.get("document_status")
    if status not in PRE_DRAFT_STATUSES:
        errors.append("pre_draft document_status가 올바르지 않습니다.")

    actions: list[str] = []
    for question in checkpoint.get("questions", []):
        if not isinstance(question, dict):
            continue
        identifier = question.get("id", "?")
        question_type = question.get("question_type")
        if not isinstance(question_type, str) or not question_type.strip():
            errors.append(f"{identifier}: question_type이 필요합니다.")
        if not nonempty_list(question.get("subquestions")):
            errors.append(f"{identifier}: subquestions에 한 개 이상의 하위 질문이 필요합니다.")
        if not isinstance(question.get("experience_question"), bool):
            errors.append(f"{identifier}: experience_question은 boolean이어야 합니다.")
        if not isinstance(question.get("reflection_required"), bool):
            errors.append(f"{identifier}: reflection_required는 boolean이어야 합니다.")
        fit = question.get("material_fit")
        if fit not in MATERIAL_FITS:
            errors.append(f"{identifier}: material_fit이 올바르지 않습니다.")
        fit_reason = question.get("material_fit_reason")
        if not isinstance(fit_reason, str) or not fit_reason.strip():
            errors.append(f"{identifier}: material_fit_reason이 필요합니다.")
        action = question.get("action")
        if action not in ACTIONS:
            errors.append(f"{identifier}: action은 write 또는 defer여야 합니다.")
            continue
        actions.append(action)
        evidence = question.get("evidence")
        missing = question.get("missing_information")
        if not string_list(missing):
            errors.append(f"{identifier}: missing_information은 문자열 배열이어야 합니다.")
            missing = []
        if action == "write":
            if fit not in {"direct", "conditional_resolved"}:
                errors.append(f"{identifier}: 부적합하거나 근거 없는 소재로 write할 수 없습니다.")
            if not nonempty_list(evidence):
                errors.append(f"{identifier}: write에는 직접 근거가 필요합니다.")
            if missing:
                errors.append(f"{identifier}: 미확정 정보가 있으면 write할 수 없습니다.")
        if action == "defer":
            if fit not in {"unsuitable", "missing"}:
                errors.append(f"{identifier}: 적합한 소재를 근거 없이 defer할 수 없습니다.")
            if not nonempty_list(missing):
                errors.append(f"{identifier}: defer에는 필요한 추가 정보가 있어야 합니다.")
            if not nonempty_list(question.get("follow_up_questions")):
                errors.append(f"{identifier}: defer에는 사용자 확인 질문이 필요합니다.")

    expected = None
    if actions and all(action == "write" for action in actions):
        expected = "ready_full"
    elif actions and all(action == "defer" for action in actions):
        expected = "blocked"
    elif actions:
        expected = "ready_partial"
    if expected and status != expected:
        errors.append(f"document_status는 질문별 action에 따라 {expected}여야 합니다.")
    if status == "blocked":
        errors.append("모든 문항이 보류되어 초안 작성 단계로 진행할 수 없습니다.")
    return errors


def validate_draft_review(checkpoint: dict[str, Any]) -> list[str]:
    errors = validate_common(checkpoint)
    if checkpoint.get("phase") != "draft_review":
        errors.append("phase는 draft_review여야 합니다.")
    status = checkpoint.get("document_status")
    if status not in DRAFT_REVIEW_STATUSES:
        errors.append("draft_review document_status가 올바르지 않습니다.")

    answer_statuses: list[str] = []
    for question in checkpoint.get("questions", []):
        if not isinstance(question, dict):
            continue
        identifier = question.get("id", "?")
        answer_status = question.get("answer_status")
        if answer_status not in ANSWER_STATUSES:
            errors.append(f"{identifier}: answer_status가 올바르지 않습니다.")
            continue
        answer_statuses.append(answer_status)
        fatal = question.get("fatal_issues")
        recommended = question.get("recommended_issues")
        if not string_list(fatal):
            errors.append(f"{identifier}: fatal_issues는 문자열 배열이어야 합니다.")
            fatal = []
        if not string_list(recommended):
            errors.append(f"{identifier}: recommended_issues는 문자열 배열이어야 합니다.")
        if not isinstance(question.get("experience_question"), bool):
            errors.append(f"{identifier}: experience_question은 boolean이어야 합니다.")
        if not isinstance(question.get("reflection_required"), bool):
            errors.append(f"{identifier}: reflection_required는 boolean이어야 합니다.")

        if answer_status == "valid":
            if fatal:
                errors.append(f"{identifier}: 치명 이슈가 있는 답변을 valid로 판정할 수 없습니다.")
            checks = question.get("content_checks")
            if not isinstance(checks, dict):
                errors.append(f"{identifier}: valid 답변에는 content_checks가 필요합니다.")
                continue
            for name in REQUIRED_CONTENT_CHECKS:
                if checks.get(name) is not True:
                    errors.append(f"{identifier}: {name} 검증을 통과해야 합니다.")
            if question.get("reflection_required") is True and checks.get(
                "reflection_requirement_met"
            ) is not True:
                errors.append(f"{identifier}: 문항이 요구한 성찰에 답해야 합니다.")
            if status == "final_candidate" and question.get("experience_question") is True:
                if checks.get("experience_meaning_present") is not True:
                    errors.append(f"{identifier}: 최종 후보에는 경험의 구체적인 의미가 필요합니다.")

        if answer_status == "deferred":
            if question.get("answer_present") is not False:
                errors.append(f"{identifier}: deferred 문항에는 답변 본문을 만들지 않습니다.")
            if not nonempty_list(question.get("missing_information")):
                errors.append(f"{identifier}: deferred 문항에는 필요한 추가 정보가 있어야 합니다.")
            if not nonempty_list(question.get("follow_up_questions")):
                errors.append(f"{identifier}: deferred 문항에는 사용자 확인 질문이 필요합니다.")

        if answer_status == "needs_revision" and not fatal:
            errors.append(f"{identifier}: needs_revision에는 수정할 치명 이슈가 있어야 합니다.")

    expected = None
    if answer_statuses and all(item == "valid" for item in answer_statuses):
        expected = {"valid_draft", "final_candidate"}
    elif "needs_revision" in answer_statuses:
        expected = {"needs_revision"}
    elif answer_statuses and all(item == "deferred" for item in answer_statuses):
        expected = {"blocked"}
    elif answer_statuses:
        expected = {"partial_draft"}
    if expected and status not in expected:
        expected_text = " 또는 ".join(sorted(expected))
        errors.append(f"document_status는 질문별 answer_status에 따라 {expected_text}여야 합니다.")

    if status == "needs_revision":
        errors.append("치명 이슈를 수정하고 다시 검사해야 합니다.")
    if status == "blocked":
        errors.append("작성된 유효 답변이 없어 번호가 붙은 초안으로 저장할 수 없습니다.")

    if status in {"valid_draft", "partial_draft", "final_candidate"}:
        style_review = checkpoint.get("style_review")
        if not isinstance(style_review, dict):
            errors.append("저장 가능한 초안에는 style_review가 필요합니다.")
        else:
            for name in REQUIRED_STYLE_CHECKS:
                if style_review.get(name) is not True:
                    errors.append(f"style_review.{name}가 true여야 합니다.")
    return errors


def validate(checkpoint: dict[str, Any]) -> list[str]:
    phase = checkpoint.get("phase")
    if phase == "pre_draft":
        return validate_pre_draft(checkpoint)
    if phase == "draft_review":
        return validate_draft_review(checkpoint)
    return ["phase는 pre_draft 또는 draft_review여야 합니다."]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument("file", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = parse_args(argv)
    try:
        checkpoint = load_checkpoint(args.file.read_text(encoding="utf-8"))
        errors = validate(checkpoint)
    except (OSError, UnicodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = {
        "file": str(args.file),
        "phase": checkpoint.get("phase"),
        "document_status": checkpoint.get("document_status"),
        "questions": len(checkpoint.get("questions", [])),
        "valid": not errors,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"phase={result['phase']} status={result['document_status']} "
            f"questions={result['questions']} valid={str(result['valid']).lower()}"
        )
        for error in errors:
            print(f"error: {error}")
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())

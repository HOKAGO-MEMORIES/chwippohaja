#!/usr/bin/env python3
"""Check one essay plan and draft pair without any shared run state.

Every invocation names its own files, so parallel work on different
applications never interferes. This replaces the former Codex hook runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from essay_rules import check_answers, load_rules, validate_rules
from validate_essay_checkpoint import load_checkpoint, validate


VALID_DOCUMENT_STATUSES = {"valid_draft", "partial_draft", "final_candidate"}


def configure_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def parse_limit(raw: str) -> dict[str, str | int | None]:
    try:
        identifier, minimum_raw, maximum_raw = raw.split(":", 2)
        minimum = int(minimum_raw) if minimum_raw else 0
        maximum = int(maximum_raw) if maximum_raw else None
    except ValueError as exc:
        raise argparse.ArgumentTypeError("글자 수 제한은 ID:MIN:MAX 형식이어야 합니다.") from exc
    if not identifier.strip() or minimum < 0 or (maximum is not None and maximum < minimum):
        raise argparse.ArgumentTypeError("글자 수 제한 범위가 올바르지 않습니다.")
    return {"id": identifier.strip(), "min": minimum, "max": maximum}


def validate_checkpoint_file(path: Path, phase: str) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, [f"파일이 없습니다: {path}"]
    try:
        checkpoint = load_checkpoint(path.read_text(encoding="utf-8"))
        errors = validate(checkpoint)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        return None, [str(exc)]
    if checkpoint.get("phase") != phase:
        errors.append(f"체크포인트 phase는 {phase}여야 합니다.")
    return checkpoint, errors


def question_ids(checkpoint: dict[str, Any]) -> list[str]:
    questions = checkpoint.get("questions", [])
    if not isinstance(questions, list):
        return []
    return [q.get("id") for q in questions if isinstance(q, dict) and isinstance(q.get("id"), str)]


def question_set_errors(checkpoint: dict[str, Any], registered: list[str]) -> list[str]:
    ids = question_ids(checkpoint)
    if len(registered) != len(set(registered)) or set(ids) != set(registered):
        return ["등록 문항 ID와 체크포인트 문항 ID가 중복 없이 정확히 일치해야 합니다."]
    return []


def check_plan(plan: Path, limits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    checkpoint, errors = validate_checkpoint_file(plan, "pre_draft")
    if checkpoint and limits:
        errors.extend(question_set_errors(checkpoint, [item["id"] for item in limits]))
    return {
        "valid": not errors,
        "errors": [f"작성 설계: {item}" for item in errors],
        "document_status": checkpoint.get("document_status") if checkpoint else None,
    }


def check_pair(plan: Path, draft: Path, limits: list[dict[str, Any]] | None = None,
               rules: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    pre_checkpoint, pre_errors = validate_checkpoint_file(plan, "pre_draft")
    errors.extend(f"작성 설계: {item}" for item in pre_errors)

    draft_checkpoint, draft_errors = validate_checkpoint_file(draft, "draft_review")
    errors.extend(f"자소서: {item}" for item in draft_errors)
    if draft_checkpoint and draft_checkpoint.get("document_status") not in VALID_DOCUMENT_STATUSES:
        errors.append("자소서: 저장 가능한 draft_review 상태가 아닙니다.")
    if (pre_checkpoint and draft_checkpoint
            and pre_checkpoint.get("schema_version") != draft_checkpoint.get("schema_version")):
        errors.append("작성 설계와 자소서의 체크포인트 schema_version이 다릅니다. 같은 버전으로 검토해야 합니다.")

    limits = resolve_limits(pre_checkpoint or draft_checkpoint or {}, limits, rules or {})
    registered = [item["id"] for item in limits]
    for checkpoint in (pre_checkpoint, draft_checkpoint):
        if checkpoint:
            errors.extend(question_set_errors(checkpoint, registered))
    if pre_checkpoint and draft_checkpoint and question_ids(pre_checkpoint) != question_ids(draft_checkpoint):
        errors.append("작성 설계와 자소서 검토의 문항 ID 및 순서가 다릅니다.")
    if pre_checkpoint and not pre_errors and draft_checkpoint and not draft_errors:
        planned = {q["id"]: q for q in pre_checkpoint["questions"]}
        for question in draft_checkpoint["questions"]:
            original = planned.get(question["id"])
            if original is None:
                continue
            expected = "valid" if original["action"] == "write" else "deferred"
            if question["answer_status"] != expected:
                errors.append(f"{question['id']}: 설계의 작성·보류 결정과 작성본 상태가 다릅니다. 설계를 먼저 갱신하세요.")
            for field in ("experience_question", "reflection_required"):
                if question.get(field) != original.get(field):
                    errors.append(f"{question['id']}: 설계와 작성본의 {field}가 다릅니다.")

    result: dict[str, Any] = {"counts": [], "style_totals": None, "style_blocks": [], "answers": {}}
    # A valid plan defines the expected body even while review flags are false.
    # Completion errors remain errors; they must not hide count/format results.
    body_questions = None
    if pre_checkpoint and not pre_errors:
        body_questions = planned_answers(pre_checkpoint)
    elif draft_checkpoint and not draft_errors:
        body_questions = draft_checkpoint["questions"]
    if draft.is_file() and body_questions is not None:
        try:
            result = check_answers(draft.read_text(encoding="utf-8"),
                                   body_questions, limits, rules or {})
            errors.extend(result["errors"])
            if draft_checkpoint and not draft_errors and pre_checkpoint and not pre_errors and pre_checkpoint.get("evidence_mapping_required"):
                errors.extend(evidence_errors(pre_checkpoint, draft_checkpoint, result["answers"]))
            if draft_checkpoint and not draft_errors:
                required = bool(pre_checkpoint and pre_checkpoint.get("reader_rubric_required") is True)
                errors.extend(memorable_line_errors(draft_checkpoint, result["answers"], required))
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"자소서: 표현 또는 글자 수 검사 실패: {exc}")
    return {
        "valid": not errors,
        "errors": errors,
        "document_status": draft_checkpoint.get("document_status") if draft_checkpoint else None,
        "counts": result["counts"],
        "style_totals": result["style_totals"],
        "style_blocks": result["style_blocks"],
    }


def planned_answers(checkpoint: dict[str, Any]) -> list[dict[str, str]]:
    return [{"id": q["id"], "answer_status": "valid" if q["action"] == "write" else "deferred"}
            for q in checkpoint["questions"]]


def resolve_limits(checkpoint: dict[str, Any], limits: list[dict[str, Any]] | None,
                   rules: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {identifier: {"id": identifier, "min": 0, "max": None}
             for identifier in question_ids(checkpoint)}
    by_id.update({item["id"]: {"id": item["id"], "min": 0, "max": None} for item in limits or []})
    validate_rules(rules, list(by_id))
    by_id.update({item["id"]: item for item in limits_from_rules(rules)})
    by_id.update({item["id"]: item for item in limits or []})
    return list(by_id.values())


def check_body(plan: Path, draft: Path, limits: list[dict[str, Any]] | None = None,
               rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inspect raw answer blocks before review records exist; never certify content."""
    checkpoint, errors = validate_checkpoint_file(plan, "pre_draft")
    result: dict[str, Any] = {"counts": [], "style_totals": None, "style_blocks": []}
    if checkpoint and not errors:
        limits = resolve_limits(checkpoint, limits, rules or {})
        errors.extend(question_set_errors(checkpoint, [item["id"] for item in limits]))
        try:
            result = check_answers(draft.read_text(encoding="utf-8"), planned_answers(checkpoint),
                                   limits, rules or {})
            errors.extend(result["errors"])
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(str(exc))
    return {"check_scope": "body_only", "content_review_verified": False,
            "valid": not errors, "errors": errors, "counts": result["counts"],
            "style_totals": result["style_totals"], "style_blocks": result["style_blocks"]}


def evidence_errors(pre_checkpoint: dict[str, Any], draft_checkpoint: dict[str, Any],
                    answers: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for question in draft_checkpoint["questions"]:
        if question["answer_status"] != "valid":
            continue
        planned = next((q for q in pre_checkpoint["questions"] if q["id"] == question["id"]), {})
        sources = {item["source"] for item in planned.get("evidence_map", [])}
        links = question.get("answer_evidence", [])
        if not isinstance(links, list) or not links:
            errors.append(f"{question['id']}: 답변 구절과 출처의 연결이 필요합니다.")
            continue
        for link in links:
            if (not isinstance(link, dict) or not isinstance(link.get("quote"), str)
                    or not link["quote"].strip() or link.get("source") not in sources
                    or link["quote"] not in answers.get(question["id"], "")):
                errors.append(f"{question['id']}: 근거 출처 또는 실제 답변 인용 구절이 일치하지 않습니다.")
    return errors


def memorable_line_errors(draft_checkpoint: dict[str, Any], answers: dict[str, str],
                          required_by_plan: bool = False) -> list[str]:
    """The recorded memorable line must be real body text.

    Final candidates must have one only when the document opts in with
    reader_rubric_required, so drafts written before the rubric still pass.
    """
    errors: list[str] = []
    final = (draft_checkpoint.get("document_status") == "final_candidate"
             and (required_by_plan or draft_checkpoint.get("reader_rubric_required") is True))
    for question in draft_checkpoint["questions"]:
        if question.get("answer_status") != "valid":
            continue
        review = question.get("reader_review")
        line = review.get("memorable_line") if isinstance(review, dict) else None
        if isinstance(line, str) and line.strip():
            if line.strip() not in answers.get(question["id"], ""):
                errors.append(f"{question['id']}: memorable_line이 실제 답변 본문에 없습니다.")
        elif final and question.get("experience_question") is True:
            errors.append(f"{question['id']}: final_candidate의 경험형 답변에는 본문에서 옮긴 memorable_line이 필요합니다.")
    return errors


def limits_from_rules(rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Read optional min/max per question from already validated rules."""
    return [{"id": identifier, "min": rule.get("min") or 0, "max": rule.get("max")}
            for identifier, rule in rules.items() if "min" in rule or "max" in rule]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path, help="pre_draft 체크포인트가 있는 작성 설계")
    parser.add_argument("--draft", type=Path, help="draft_review 체크포인트가 있는 작성본. 없으면 설계만 검사")
    parser.add_argument("--body-only", action="store_true", help="검토 기록 전 본문·형식·분량만 검사 (--draft 필요)")
    parser.add_argument("--limit", type=parse_limit, action="append", default=[],
                        help="문항ID:최소:최대. 규칙 파일의 min/max보다 우선")
    parser.add_argument("--rules", type=Path, help="문항 ID별 형식·계산·분량 규칙 JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = parse_args(argv)
    try:
        if args.body_only and args.draft is None:
            raise ValueError("--body-only에는 --draft가 필요합니다.")
        if args.draft is not None and args.plan.resolve() == args.draft.resolve():
            raise ValueError("작성 설계와 작성본은 서로 다른 파일이어야 합니다.")
        checkpoint, _ = validate_checkpoint_file(args.plan, "pre_draft")
        by_id = {identifier: {"id": identifier, "min": 0, "max": None}
                 for identifier in (question_ids(checkpoint) if checkpoint else [])}
        by_id.update({item["id"]: {"id": item["id"], "min": 0, "max": None} for item in args.limit})
        rules = load_rules(args.rules, list(by_id)) if args.rules else {}
        by_id.update({item["id"]: item for item in limits_from_rules(rules)})
        by_id.update({item["id"]: item for item in args.limit})
        limits = list(by_id.values())
        if args.body_only:
            result = check_body(args.plan, args.draft, limits, rules)
        elif args.draft is None:
            result = check_plan(args.plan, limits)
        else:
            result = check_pair(args.plan, args.draft, limits, rules)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result = {"valid": False, "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())

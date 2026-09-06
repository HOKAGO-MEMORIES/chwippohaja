#!/usr/bin/env python3
"""Manage and enforce an active chwippohaja essay drafting run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from count_essay_characters import count_blocks, extract_blocks
from validate_essay_checkpoint import load_checkpoint, validate
from validate_essay_style import analyze


MARKER = Path(".chwippohaja") / "workspace.json"
STATE = Path(".chwippohaja") / "runs" / "essay-current.json"
HOOK_ID = "chwippohaja-essay-hook"
VALID_DOCUMENT_STATUSES = {"valid_draft", "partial_draft", "final_candidate"}


def configure_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_workspace(start: Path) -> Path | None:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / MARKER).is_file():
            return candidate
    return None


def workspace_from_argument(raw: str | None) -> Path:
    if raw:
        root = Path(raw).expanduser().resolve()
        if not (root / MARKER).is_file():
            raise ValueError(f"워크스페이스 표식이 없습니다: {root / MARKER}")
        return root
    root = find_workspace(Path.cwd())
    if root is None:
        raise ValueError("현재 위치에서 .chwippohaja/workspace.json을 찾지 못했습니다.")
    return root


def relative_target(root: Path, raw: str) -> str:
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError("자소서 훅 대상은 워크스페이스 내부 파일이어야 합니다.") from exc
    if target.suffix.lower() != ".md":
        raise ValueError("자소서 훅 대상은 Markdown 파일이어야 합니다.")
    if "02_작성중" not in relative.parts:
        raise ValueError("자소서 훅 대상은 기업별 02_작성중 폴더에 있어야 합니다.")
    return relative.as_posix()


def state_path(root: Path) -> Path:
    return root / STATE


def load_state(root: Path) -> dict[str, Any] | None:
    path = state_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"자소서 훅 상태 파일을 읽을 수 없습니다: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("자소서 훅 상태 파일 형식이 올바르지 않습니다.")
    required_strings = ("plan_file", "draft_file", "status", "phase")
    if any(not isinstance(data.get(name), str) or not data[name].strip() for name in required_strings):
        raise ValueError("자소서 훅 상태 파일에 필수 경로 또는 상태가 없습니다.")
    if data["phase"] not in {"planning", "drafting"}:
        raise ValueError("자소서 훅 단계는 planning 또는 drafting이어야 합니다.")
    limits = data.get("character_limits")
    if not isinstance(limits, list) or not limits:
        raise ValueError("자소서 훅 상태 파일에 글자 수 제한이 없습니다.")
    for item in limits:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"].strip()
            or not isinstance(item.get("min"), int)
        ):
            raise ValueError("자소서 훅 글자 수 제한 형식이 올바르지 않습니다.")
        maximum = item.get("max")
        if maximum is not None and not isinstance(maximum, int):
            raise ValueError("자소서 훅 최대 글자 수는 정수 또는 null이어야 합니다.")
    return data


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_checkpoint_file(path: Path, phase: str) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, [f"파일이 없습니다: {path}"]
    try:
        checkpoint = load_checkpoint(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return None, [str(exc)]
    errors = validate(checkpoint)
    if checkpoint.get("phase") != phase:
        errors.append(f"체크포인트 phase는 {phase}여야 합니다.")
    return checkpoint, errors


def validate_plan(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    plan = root / state["plan_file"]
    checkpoint, errors = validate_checkpoint_file(plan, "pre_draft")
    return {
        "valid": not errors,
        "errors": [f"작성 설계: {item}" for item in errors],
        "document_status": checkpoint.get("document_status") if checkpoint else None,
        "plan_digest": digest(plan) if plan.is_file() else None,
    }


def validate_run(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    plan = root / state["plan_file"]
    draft = root / state["draft_file"]

    pre_checkpoint, pre_errors = validate_checkpoint_file(plan, "pre_draft")
    errors.extend(f"작성 설계: {item}" for item in pre_errors)

    draft_checkpoint, draft_errors = validate_checkpoint_file(draft, "draft_review")
    errors.extend(f"자소서: {item}" for item in draft_errors)
    if draft_checkpoint and draft_checkpoint.get("document_status") not in VALID_DOCUMENT_STATUSES:
        errors.append("자소서: 저장 가능한 draft_review 상태가 아닙니다.")

    counts: list[dict[str, int]] = []
    style: dict[str, Any] | None = None
    if draft.is_file():
        try:
            source = draft.read_text(encoding="utf-8")
            blocks = extract_blocks(source)
            if not blocks:
                errors.append("자소서: text 코드 블록이 없습니다.")
            else:
                counts = count_blocks(blocks)
                style = analyze(source, require_summary=True)
                if not style["structural_valid"]:
                    totals = style["totals"]
                    errors.append(
                        "자소서: 대괄호 요약 또는 서술식 본문 구조 검사를 통과하지 못했습니다 "
                        f"(요약 누락 {totals['missing_summaries']}, 서술형 요약 "
                        f"{totals['declarative_summaries']}, 문장부호 요약 "
                        f"{totals['punctuated_summaries']}, 개조식 행 {totals['outline_lines']})."
                    )
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"자소서: 표현 또는 글자 수 검사 실패: {exc}")

    limits = state.get("character_limits", [])
    limits_by_id = {item["id"]: item for item in limits}
    if len(limits_by_id) != len(limits):
        errors.append("자소서: 문항별 글자 수 제한 ID가 중복되었습니다.")

    valid_questions: list[dict[str, Any]] = []
    if pre_checkpoint and draft_checkpoint:
        pre_ids = [item.get("id") for item in pre_checkpoint.get("questions", [])]
        draft_ids = [item.get("id") for item in draft_checkpoint.get("questions", [])]
        if pre_ids != draft_ids:
            errors.append("작성 설계와 자소서 검토의 문항 ID 및 순서가 다릅니다.")
        missing_limits = [identifier for identifier in pre_ids if identifier not in limits_by_id]
        if missing_limits:
            errors.append(
                "자소서: 글자 수 제한이 없는 문항이 있습니다: "
                + ", ".join(str(identifier) for identifier in missing_limits)
            )
        valid_questions = [
            item
            for item in draft_checkpoint.get("questions", [])
            if isinstance(item, dict) and item.get("answer_status") == "valid"
        ]
        if len(valid_questions) != len(counts):
            errors.append(
                f"valid 답변 {len(valid_questions)}개와 실제 답변 블록 {len(counts)}개가 다릅니다."
            )

    if len(valid_questions) == len(counts):
        for count, question in zip(counts, valid_questions):
            identifier = question["id"]
            limit = limits_by_id.get(identifier)
            if not limit:
                continue
            characters = count["characters"]
            minimum = limit["min"]
            maximum = limit["max"]
            if characters < minimum:
                errors.append(f"자소서 {identifier}번: {characters}자로 최소 {minimum}자보다 짧습니다.")
            if maximum is not None and characters > maximum:
                errors.append(f"자소서 {identifier}번: {characters}자로 최대 {maximum}자를 초과했습니다.")

    return {
        "valid": not errors,
        "errors": errors,
        "counts": counts,
        "style_totals": style["totals"] if style else None,
        "plan_digest": digest(plan) if plan.is_file() else None,
        "draft_digest": digest(draft) if draft.is_file() else None,
    }


def validate_ready_run(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    result = validate_run(root, state)
    plan = root / state["plan_file"]
    current_plan_digest = digest(plan) if plan.is_file() else None
    if state.get("phase") != "drafting" or not state.get("validated_plan_digest"):
        result["errors"].insert(0, "작성 설계 체크포인트가 초안 작성 전에 통과되지 않았습니다.")
    elif state.get("validated_plan_digest") != current_plan_digest:
        result["errors"].insert(0, "통과한 작성 설계가 이후 변경됐습니다. 설계를 다시 검사해야 합니다.")
    early_digest = state.get("early_draft_digest")
    draft = root / state["draft_file"]
    if early_digest and draft.is_file() and digest(draft) == early_digest:
        result["errors"].insert(0, "작성 설계 통과 전에 만든 자소서 본문을 다시 검토하고 수정해야 합니다.")
    result["valid"] = not result["errors"]
    return result


def event_name(payload: dict[str, Any]) -> str:
    return str(payload.get("event") or payload.get("hook_event_name") or "")


def bind_session(state: dict[str, Any], payload: dict[str, Any]) -> bool:
    incoming = payload.get("session_id")
    bound = state.get("session_id")
    if bound and incoming and bound != incoming:
        return False
    if not bound and incoming:
        state["session_id"] = incoming
    return True


def serialized_tool_input(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload.get("tool_input", {}), ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload.get("tool_input", ""))


def touched_file(target: str, payload: dict[str, Any]) -> bool:
    serialized = serialized_tool_input(payload).replace("\\", "/")
    return target in serialized or Path(target).name in serialized


def block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


def hook_command() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        block(f"자소서 훅 입력을 읽지 못했습니다: {exc}")
        return 0
    if not isinstance(payload, dict):
        block("자소서 훅 입력은 JSON 객체여야 합니다.")
        return 0

    cwd = Path(str(payload.get("cwd") or Path.cwd()))
    root = find_workspace(cwd)
    if root is None:
        print("{}")
        return 0
    try:
        state = load_state(root)
    except ValueError as exc:
        block(str(exc))
        return 0
    if state is None:
        print("{}")
        return 0
    if not bind_session(state, payload):
        print("{}")
        return 0
    state["updated_at"] = now_iso()

    event = event_name(payload)
    if event == "PostToolUse":
        plan_touched = touched_file(state["plan_file"], payload)
        draft_touched = touched_file(state["draft_file"], payload)
        if not plan_touched and not draft_touched:
            write_json_atomic(state_path(root), state)
            print("{}")
            return 0
        if plan_touched:
            plan_result = validate_plan(root, state)
            state["last_plan_validation"] = plan_result
            if not plan_result["valid"]:
                state["phase"] = "planning"
                state["validated_plan_digest"] = None
                state["status"] = "active"
                if draft_touched and (root / state["draft_file"]).is_file():
                    state["early_draft_digest"] = digest(root / state["draft_file"])
                write_json_atomic(state_path(root), state)
                details = "\n".join(f"- {item}" for item in plan_result["errors"][:12])
                block("초안 전 작성 설계 검사를 통과하지 못했습니다.\n" + details)
                return 0
            state["phase"] = "drafting"
            state["validated_plan_digest"] = plan_result["plan_digest"]
            state["status"] = "active"
            if draft_touched:
                if (root / state["draft_file"]).is_file():
                    state["early_draft_digest"] = digest(root / state["draft_file"])
                write_json_atomic(state_path(root), state)
                block(
                    "작성 설계와 자소서 본문을 한 번에 만들었습니다. 초안 전 체크포인트를 "
                    "분리해 통과시켜야 하므로 현재 자소서 본문을 다시 검토하고 수정한 뒤 검사하세요."
                )
                return 0
            write_json_atomic(state_path(root), state)
            print("{}")
            return 0
    if event == "Stop" and state.get("status") == "waiting_user":
        if not str(state.get("waiting_reason") or "").strip() or not all(
            isinstance(item, str) and item.strip()
            for item in state.get("follow_up_questions", [])
        ) or not state.get("follow_up_questions"):
            block("사용자 대기 상태에는 구체적인 보류 이유와 확인 질문이 필요합니다.")
            return 0
        write_json_atomic(state_path(root), state)
        print("{}")
        return 0

    result = validate_ready_run(root, state)
    if result["valid"]:
        state["early_draft_digest"] = None
    state["last_validation"] = result
    state["status"] = "passed" if result["valid"] else "active"
    write_json_atomic(state_path(root), state)
    if result["valid"]:
        print("{}")
        return 0

    details = "\n".join(f"- {item}" for item in result["errors"][:12])
    block(
        "자소서 완료 조건을 통과하지 못했습니다. 현재 자료로 수정한 뒤 다시 검사하세요. "
        "새로운 사용자 사실이 필요하면 essay_hook.py wait로 전환하고 필요한 질문을 남기세요.\n"
        + details
    )
    return 0


def start_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = {
        "schema_version": 1,
        "hook_id": HOOK_ID,
        "status": "active",
        "phase": "planning",
        "session_id": None,
        "plan_file": relative_target(root, args.plan),
        "draft_file": relative_target(root, args.draft),
        "character_limits": args.limit,
        "waiting_reason": None,
        "follow_up_questions": [],
        "validated_plan_digest": None,
        "early_draft_digest": None,
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "last_plan_validation": None,
        "last_validation": None,
    }
    write_json_atomic(state_path(root), state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def wait_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 자소서 작업이 없습니다.")
    state["status"] = "waiting_user"
    state["waiting_reason"] = args.reason.strip()
    state["follow_up_questions"] = [item.strip() for item in args.question if item.strip()]
    state["updated_at"] = now_iso()
    state["last_validation"] = validate_run(root, state)
    write_json_atomic(state_path(root), state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def resume_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 자소서 작업이 없습니다.")
    state["status"] = "active"
    state["waiting_reason"] = None
    state["follow_up_questions"] = []
    state["updated_at"] = now_iso()
    write_json_atomic(state_path(root), state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def check_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 자소서 작업이 없습니다.")
    result = validate_ready_run(root, state)
    state["last_validation"] = result
    state["status"] = "passed" if result["valid"] else "active"
    state["updated_at"] = now_iso()
    write_json_atomic(state_path(root), state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


def finish_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 자소서 작업이 없습니다.")
    result = validate_ready_run(root, state)
    if not result["valid"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    state_path(root).unlink()
    print(json.dumps({"finished": True, "draft_file": state["draft_file"]}, ensure_ascii=False))
    return 0


def plan_check_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 자소서 작업이 없습니다.")
    result = validate_plan(root, state)
    state["last_plan_validation"] = result
    state["updated_at"] = now_iso()
    if result["valid"]:
        state["phase"] = "drafting"
        state["validated_plan_digest"] = result["plan_digest"]
        state["status"] = "active"
    else:
        state["phase"] = "planning"
        state["validated_plan_digest"] = None
    write_json_atomic(state_path(root), state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


def status_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    print(json.dumps(state or {"status": "inactive"}, ensure_ascii=False, indent=2))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="자소서 검증 실행 상태를 시작")
    start.add_argument("--workspace")
    start.add_argument("--plan", required=True, help="초안 전 체크포인트가 있는 작성 설계")
    start.add_argument("--draft", required=True, help="검증할 자소서 작성본")
    start.add_argument(
        "--limit",
        type=parse_limit,
        action="append",
        required=True,
        help="문항별 공백 포함 ID:MIN:MAX 글자 수. 최대값이 없으면 ID:MIN:",
    )
    start.set_defaults(handler=start_command)

    wait = subparsers.add_parser("wait", help="사용자 사실을 기다리는 정상 중단 상태")
    wait.add_argument("--workspace")
    wait.add_argument("--reason", required=True)
    wait.add_argument("--question", action="append", required=True)
    wait.set_defaults(handler=wait_command)

    plan_check = subparsers.add_parser("plan-check", help="초안 작성 전 설계 체크포인트 검사")
    plan_check.add_argument("--workspace")
    plan_check.set_defaults(handler=plan_check_command)

    for name, help_text, handler in (
        ("resume", "사용자 답변 뒤 검증 작업 재개", resume_command),
        ("check", "현재 자소서 실행을 즉시 검사", check_command),
        ("finish", "통과한 실행 상태를 종료", finish_command),
        ("status", "현재 자소서 실행 상태 조회", status_command),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--workspace")
        command.set_defaults(handler=handler)

    hook = subparsers.add_parser("hook", help="Codex hooks.json에서 호출")
    hook.add_argument("--hook-id", default=HOOK_ID)
    hook.set_defaults(handler=lambda _args: hook_command())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, UnicodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

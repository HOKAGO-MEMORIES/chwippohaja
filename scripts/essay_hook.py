#!/usr/bin/env python3
"""Manage and enforce an active chwippohaja essay drafting run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from essay_rules import check_answers, load_rules, validate_rules
from validate_essay_checkpoint import load_checkpoint, validate


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
    root = root.expanduser().resolve()
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
    for name in ("plan_file", "draft_file"):
        if relative_target(root, data[name]) != data[name]:
            raise ValueError("상태 파일의 대상 경로가 올바르지 않습니다.")
    validate_rules(data.get("question_rules", {}), [item["id"] for item in limits])
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
        errors = validate(checkpoint)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        return None, [str(exc)]
    if checkpoint.get("phase") != phase:
        errors.append(f"체크포인트 phase는 {phase}여야 합니다.")
    return checkpoint, errors


def validate_plan(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    plan = root / state["plan_file"]
    checkpoint, errors = validate_checkpoint_file(plan, "pre_draft")
    if checkpoint:
        errors.extend(question_set_errors(checkpoint, state))
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
    if pre_checkpoint and draft_checkpoint and pre_checkpoint.get("schema_version") != draft_checkpoint.get("schema_version"):
        errors.append("작성 설계와 자소서의 체크포인트 schema_version이 다릅니다. 같은 버전으로 검토해야 합니다.")

    for checkpoint in (pre_checkpoint, draft_checkpoint):
        if checkpoint:
            errors.extend(question_set_errors(checkpoint, state))
    if (pre_checkpoint and draft_checkpoint
            and isinstance(pre_checkpoint.get("questions"), list)
            and isinstance(draft_checkpoint.get("questions"), list)):
        pre_ids = [q.get("id") for q in pre_checkpoint.get("questions", []) if isinstance(q, dict)]
        draft_ids = [q.get("id") for q in draft_checkpoint.get("questions", []) if isinstance(q, dict)]
        if pre_ids != draft_ids:
            errors.append("작성 설계와 자소서 검토의 문항 ID 및 순서가 다릅니다.")
    result = {"counts": [], "style_totals": None, "answers": {}}
    if draft.is_file() and draft_checkpoint and not draft_errors:
        try:
            result = check_answers(draft.read_text(encoding="utf-8"),
                                   draft_checkpoint["questions"], state["character_limits"],
                                   state.get("question_rules", {}))
            errors.extend(result["errors"])
            if pre_checkpoint and not pre_errors and pre_checkpoint.get("evidence_mapping_required"):
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
                                or link["quote"] not in result["answers"].get(question["id"], "")):
                            errors.append(f"{question['id']}: 근거 출처 또는 실제 답변 인용 구절이 일치하지 않습니다.")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"자소서: 표현 또는 글자 수 검사 실패: {exc}")
    return {
        "valid": not errors, "errors": errors,
        "counts": result["counts"], "style_totals": result["style_totals"],
        "plan_digest": digest(plan) if plan.is_file() else None,
        "draft_digest": digest(draft) if draft.is_file() else None,
    }


def question_set_errors(checkpoint: dict[str, Any], state: dict[str, Any]) -> list[str]:
    questions = checkpoint.get("questions", [])
    if not isinstance(questions, list):
        return ["문항 목록은 배열이어야 합니다."]
    ids = [q.get("id") for q in questions if isinstance(q, dict) and isinstance(q.get("id"), str)]
    registered = [item["id"] for item in state["character_limits"]]
    if len(registered) != len(set(registered)) or set(ids) != set(registered):
        return ["등록 문항 ID와 체크포인트 문항 ID가 중복 없이 정확히 일치해야 합니다."]
    return []


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


def new_state(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    plan = relative_target(root, args.plan)
    draft = relative_target(root, args.draft)
    if plan == draft or Path(plan).parent != Path(draft).parent:
        raise ValueError("작성 설계와 답변은 같은 지원 건의 서로 다른 파일이어야 합니다.")
    ids = [item["id"] for item in args.limit]
    if len(ids) != len(set(ids)):
        raise ValueError("문항별 글자 수 제한 ID가 중복되었습니다.")
    return {
        "schema_version": 1,
        "hook_id": HOOK_ID,
        "run_id": uuid.uuid4().hex,
        "question_rules": load_rules(args.rules, ids),
        "status": "active",
        "phase": "planning",
        "session_id": None,
        "plan_file": plan,
        "draft_file": draft,
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


def create_state(root: Path, state: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents two concurrent starts from replacing each other.
    with path.open("x", encoding="utf-8") as output:
        json.dump(state, output, ensure_ascii=False, indent=2)
        output.write("\n")


def archive_state(root: Path, state: dict[str, Any], status: str) -> str:
    identifier = state.get("run_id") or uuid.uuid4().hex
    state["run_id"] = identifier
    snapshot = {**state, "archived_status": status, "archived_at": now_iso()}
    write_json_atomic(root / STATE.parent / "essay-history" / f"{identifier}.json", snapshot)
    return identifier


def start_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    proposed = new_state(root, args)
    previous = load_state(root)
    if previous:
        keys = ("plan_file", "draft_file", "character_limits", "question_rules")
        if all(previous.get(key, {}) == proposed[key] for key in keys):
            print(json.dumps(previous, ensure_ascii=False, indent=2))
            return 0
        raise ValueError("활성 자소서 작업이 있습니다. 같은 지원 건의 새 버전은 advance, 다른 지원 건은 suspend 후 start를 사용하세요.")
    create_state(root, proposed)
    print(json.dumps(proposed, ensure_ascii=False, indent=2))
    return 0


def advance_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    previous = load_state(root)
    if not previous:
        raise ValueError("활성 자소서 작업이 없습니다.")
    proposed = new_state(root, args)
    if Path(previous["draft_file"]).parent != Path(proposed["draft_file"]).parent:
        raise ValueError("advance는 같은 지원 건의 새 버전에만 사용합니다.")
    if previous["draft_file"] == proposed["draft_file"]:
        raise ValueError("새 버전에는 다른 답변 파일을 지정하세요.")
    proposed["session_id"] = previous.get("session_id")
    proposed["previous_run_id"] = archive_state(root, previous, "advanced")
    write_json_atomic(state_path(root), proposed)
    print(json.dumps(proposed, ensure_ascii=False, indent=2))
    return 0


def suspend_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if not state:
        raise ValueError("활성 자소서 작업이 없습니다.")
    identifier = archive_state(root, state, "suspended")
    state_path(root).unlink()
    print(json.dumps({"suspended": True, "run_id": identifier}, ensure_ascii=False))
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
    if args.run_id:
        if state:
            raise ValueError("활성 작업을 종료하거나 suspend한 뒤 보관된 작업을 재개하세요.")
        if len(args.run_id) != 32 or any(c not in "0123456789abcdef" for c in args.run_id):
            raise ValueError("run_id가 올바르지 않습니다.")
        archived = root / STATE.parent / "essay-history" / f"{args.run_id}.json"
        state = json.loads(archived.read_text(encoding="utf-8"))
        if state.get("archived_status") != "suspended":
            raise ValueError("suspend한 실행만 재개할 수 있습니다.")
        create_state(root, state)
        state = load_state(root)
    if state is None:
        raise ValueError("활성 자소서 작업이 없습니다.")
    if args.rebind:
        state["session_id"] = None
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
    state["last_validation"] = result
    archive_state(root, state, "finished")
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
    start.add_argument("--rules", type=Path, help="문항 ID별 형식과 계산 규칙 JSON")
    start.set_defaults(handler=start_command)

    advance = subparsers.add_parser("advance", help="기존 실행을 보존하고 같은 지원 건의 새 버전으로 전환")
    advance.add_argument("--workspace")
    advance.add_argument("--plan", required=True)
    advance.add_argument("--draft", required=True)
    advance.add_argument("--limit", type=parse_limit, action="append", required=True)
    advance.add_argument("--rules", type=Path)
    advance.set_defaults(handler=advance_command)
    suspend = subparsers.add_parser("suspend", help="실행 상태를 보존하고 다른 지원 건 작업을 허용")
    suspend.add_argument("--workspace")
    suspend.set_defaults(handler=suspend_command)

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
        if name == "resume":
            command.add_argument("--run-id", help="suspend가 반환한 실행 ID")
            command.add_argument("--rebind", action="store_true", help="새 Codex 작업에서 다음 훅 세션에 다시 연결")
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

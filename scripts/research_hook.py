#!/usr/bin/env python3
"""Manage and enforce a chwippohaja posting and company research run."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_research_stage import validate_research_stage
from application_state import sync_verified


MARKER = Path(".chwippohaja") / "workspace.json"
STATE = Path(".chwippohaja") / "runs" / "research-current.json"
LAST_STATE = Path(".chwippohaja") / "runs" / "research-last.json"
HOOK_ID = "chwippohaja-research-hook"
DISPOSITIONS = {"partial", "failed", "not_attempted", "waiting_user"}
SUMMARY_LABELS = {
    "total": "전체 대상",
    "complete": "완료",
    "partial": "부분 완료",
    "failed": "실패",
    "not_attempted": "미시도",
}


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


def read_workspace_marker(root: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / MARKER).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"워크스페이스 표식을 읽을 수 없습니다: {exc}") from exc
    return value if isinstance(value, dict) else {}


def relative_application(root: Path, raw: str) -> str:
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError("공고 조사 대상은 워크스페이스 내부여야 합니다.") from exc
    if not relative.parts or relative == Path("."):
        raise ValueError("워크스페이스 루트를 지원 건 폴더로 사용할 수 없습니다.")
    active_season = read_workspace_marker(root).get("active_season")
    if isinstance(active_season, str) and active_season.strip():
        if relative.parts[0] != active_season:
            raise ValueError(f"공고 조사 대상은 활성 시즌 {active_season} 아래에 있어야 합니다.")
    return relative.as_posix()


def state_path(root: Path) -> Path:
    return root / STATE


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


def load_state(root: Path) -> dict[str, Any] | None:
    path = state_path(root)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"공고 조사 훅 상태 파일을 읽을 수 없습니다: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("공고 조사 훅 상태 파일 형식이 올바르지 않습니다.")
    targets = value.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("공고 조사 훅에 대상 목록이 없습니다.")
    if value.get("expected_total") != len(targets):
        raise ValueError("공고 조사 훅의 예상 대상 수와 실제 대상 목록이 다릅니다.")
    applications: list[str] = []
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("application"), str):
            raise ValueError("공고 조사 훅 대상 형식이 올바르지 않습니다.")
        applications.append(target["application"])
    if len(applications) != len(set(applications)):
        raise ValueError("공고 조사 훅 대상이 중복되었습니다.")
    return value


def target_for(state: dict[str, Any], application: str) -> dict[str, Any]:
    for target in state["targets"]:
        if target["application"] == application:
            return target
    raise ValueError("등록되지 않은 지원 건입니다.")


def validate_targets(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    counts = {
        "total": len(state["targets"]),
        "complete": 0,
        "partial": 0,
        "failed": 0,
        "not_attempted": 0,
        "pending": 0,
    }
    for target in state["targets"]:
        application = root / target["application"]
        validation = validate_research_stage(application)
        pending_services = []
        for service in state.get("required_services", []):
            try:
                verified = sync_verified(application, service)
            except (OSError, ValueError):
                verified = False
            if not verified:
                pending_services.append(service)
        disposition = target.get("disposition")
        if disposition in {"partial", "waiting_user"}:
            outcome = "partial"
        elif disposition in {"failed", "not_attempted"}:
            outcome = disposition
        elif validation["status"] == "complete" and not pending_services:
            outcome = "complete"
        else:
            outcome = "pending"
        counts[outcome] += 1
        results.append(
            {
                "application": target["application"],
                "outcome": outcome,
                "disposition": target.get("disposition"),
                "reason": target.get("reason"),
                "attempts": target.get("attempts", []),
                "questions": target.get("questions", []),
                "validation": validation,
                "local_complete": validation["status"] == "complete",
                "pending_services": pending_services,
            }
        )
    accounted = (
        counts["complete"]
        + counts["partial"]
        + counts["failed"]
        + counts["not_attempted"]
    )
    return {
        "complete": counts["complete"] == counts["total"],
        "accounted": accounted == counts["total"] and counts["pending"] == 0,
        "counts": counts,
        "targets": results,
    }


def target_has_both_documents(root: Path, target: dict[str, Any]) -> bool:
    research = root / target["application"] / "01_공고_JD"
    return bool(list(research.glob("*공고분석*.md"))) and bool(
        list(research.glob("*기업리서치*.md"))
    )


def serialized_tool_input(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload.get("tool_input", {}), ensure_ascii=False).replace("\\", "/")
    except (TypeError, ValueError):
        return str(payload.get("tool_input", "")).replace("\\", "/")


def touched_targets(state: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    serialized = serialized_tool_input(payload)
    return [
        target
        for target in state["targets"]
        if target["application"] in serialized
    ]


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


def block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


def summary_matches(message: str, counts: dict[str, int]) -> bool:
    normalized = message.replace("*", "").replace("`", "")
    return all(
        re.search(rf"{re.escape(label)}\s*:\s*{counts[key]}(?:\D|$)", normalized)
        for key, label in SUMMARY_LABELS.items()
    )


def forbidden_complete_claim(message: str, counts: dict[str, int]) -> bool:
    if counts["complete"] == counts["total"]:
        return False
    return bool(re.search(r"전체\s*완료|모두\s*(?:완료|반영)|누락\s*없", message))


def archive_and_clear(root: Path, state: dict[str, Any], result: dict[str, Any]) -> None:
    archived = dict(state)
    archived["closed_at"] = now_iso()
    archived["final_validation"] = result
    write_json_atomic(root / LAST_STATE, archived)
    state_path(root).unlink()


def hook_command() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        block(f"공고 조사 훅 입력을 읽지 못했습니다: {exc}")
        return 0
    if not isinstance(payload, dict):
        block("공고 조사 훅 입력은 JSON 객체여야 합니다.")
        return 0
    root = find_workspace(Path(str(payload.get("cwd") or Path.cwd())))
    if root is None:
        print("{}")
        return 0
    try:
        state = load_state(root)
    except ValueError as exc:
        block(str(exc))
        return 0
    if state is None or not bind_session(state, payload):
        print("{}")
        return 0

    state["updated_at"] = now_iso()
    event = event_name(payload)
    if event == "PostToolUse":
        touched = touched_targets(state, payload)
        if not touched:
            write_json_atomic(state_path(root), state)
            print("{}")
            return 0
        result = validate_targets(root, state)
        state["ready_to_report"] = False
        state["last_validation"] = result
        write_json_atomic(state_path(root), state)
        assembled_invalid = [
            item
            for item in result["targets"]
            if any(item["application"] == target["application"] for target in touched)
            and not item["local_complete"]
            and target_has_both_documents(root, item)
        ]
        if assembled_invalid:
            details: list[str] = []
            for item in assembled_invalid:
                details.append(f"{item['application']}:")
                details.extend(f"- {error}" for error in item["validation"]["errors"][:8])
            block("공고 분석과 기업 리서치가 모두 있지만 완료 기준을 통과하지 못했습니다.\n" + "\n".join(details))
            return 0
        print("{}")
        return 0

    result = validate_targets(root, state)
    state["last_validation"] = result
    write_json_atomic(state_path(root), state)
    if event != "Stop":
        print("{}")
        return 0

    if not result["accounted"]:
        pending = [item["application"] for item in result["targets"] if item["outcome"] == "pending"]
        block(
            "공고 조사 대상 중 검증되지 않았거나 실패 사유가 기록되지 않은 대상이 있습니다. "
            "조사를 계속하거나 research_hook.py defer로 실제 상태와 시도 내용을 기록하세요.\n- "
            + "\n- ".join(pending)
        )
        return 0

    if result["complete"] and not state.get("ready_to_report"):
        block(
            "모든 대상의 로컬 검사는 통과했지만 finish 검사가 기록되지 않았습니다. "
            "research_hook.py finish를 실행한 뒤 최종 보고하세요."
        )
        return 0

    message = str(payload.get("last_assistant_message") or "")
    counts = result["counts"]
    if len(state["targets"]) > 1 or not result["complete"]:
        if not summary_matches(message, counts):
            block(
                "최종 보고에 전체 대상, 완료, 부분 완료, 실패, 미시도 집계를 정확히 적어야 합니다. "
                f"현재 검증값: 전체 대상 {counts['total']}, 완료 {counts['complete']}, "
                f"부분 완료 {counts['partial']}, 실패 {counts['failed']}, "
                f"미시도 {counts['not_attempted']}"
            )
            return 0
    if forbidden_complete_claim(message, counts):
        block("미완료 대상이 있으므로 전체 완료, 모두 반영 또는 누락 없음으로 보고할 수 없습니다.")
        return 0

    if any(item.get("disposition") == "waiting_user" for item in result["targets"]):
        print("{}")
        return 0
    archive_and_clear(root, state, result)
    print("{}")
    return 0


def start_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    if state_path(root).is_file():
        raise ValueError(
            "이미 활성 공고 조사 작업이 있습니다. 기존 작업을 확인하고 종료한 뒤 새 작업을 시작하세요."
        )
    applications = [relative_application(root, raw) for raw in args.application]
    if len(applications) != len(set(applications)):
        raise ValueError("공고 조사 대상이 중복되었습니다.")
    expected = args.expected_total if args.expected_total is not None else len(applications)
    if expected != len(applications):
        raise ValueError("--expected-total은 등록한 --application 개수와 같아야 합니다.")
    state = {
        "schema_version": 1,
        "hook_id": HOOK_ID,
        "session_id": None,
        "expected_total": expected,
        "required_services": sorted(set(args.require_service)),
        "targets": [
            {
                "application": application,
                "disposition": None,
                "reason": None,
                "attempts": [],
                "questions": [],
            }
            for application in applications
        ],
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "last_validation": None,
        "ready_to_report": False,
    }
    write_json_atomic(state_path(root), state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def defer_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 공고 조사 작업이 없습니다.")
    application = relative_application(root, args.application)
    target = target_for(state, application)
    attempts = [item.strip() for item in args.attempt if item.strip()]
    questions = [item.strip() for item in args.question if item.strip()]
    reason = args.reason.strip()
    if len(reason) < 10:
        raise ValueError("미완료 사유는 원인과 남은 범위를 알 수 있도록 10자 이상 기록해야 합니다.")
    if args.status in {"partial", "failed"} and len(set(attempts)) < 2:
        raise ValueError(
            "부분 완료 또는 실패에는 서로 다른 실제 조사 시도를 두 개 이상 기록해야 합니다."
        )
    if args.status == "waiting_user" and not questions:
        raise ValueError("사용자 대기에는 구체적인 확인 질문이 필요합니다.")
    target.update(
        {
            "disposition": args.status,
            "reason": reason,
            "attempts": attempts,
            "questions": questions,
        }
    )
    state["updated_at"] = now_iso()
    state["ready_to_report"] = False
    state["last_validation"] = validate_targets(root, state)
    write_json_atomic(state_path(root), state)
    print(json.dumps(target, ensure_ascii=False, indent=2))
    return 0


def resume_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 공고 조사 작업이 없습니다.")
    if args.rebind:
        state["session_id"] = None
    application = relative_application(root, args.application)
    target = target_for(state, application)
    target.update({"disposition": None, "reason": None, "attempts": [], "questions": []})
    state["updated_at"] = now_iso()
    state["ready_to_report"] = False
    write_json_atomic(state_path(root), state)
    print(json.dumps(target, ensure_ascii=False, indent=2))
    return 0


def check_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 공고 조사 작업이 없습니다.")
    result = validate_targets(root, state)
    state["ready_to_report"] = False
    state["last_validation"] = result
    state["updated_at"] = now_iso()
    write_json_atomic(state_path(root), state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["complete"] else 2


def finish_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    if state is None:
        raise ValueError("활성 공고 조사 작업이 없습니다.")
    result = validate_targets(root, state)
    if not result["complete"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    state["ready_to_report"] = True
    state["last_validation"] = result
    state["updated_at"] = now_iso()
    write_json_atomic(state_path(root), state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def status_command(args: argparse.Namespace) -> int:
    root = workspace_from_argument(args.workspace)
    state = load_state(root)
    print(json.dumps(state or {"status": "inactive"}, ensure_ascii=False, indent=2))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="공고 조사 대상 목록 고정")
    start.add_argument("--workspace")
    start.add_argument("--application", action="append", required=True)
    start.add_argument("--expected-total", type=int)
    start.add_argument("--require-service", action="append", default=[], choices=("google_drive", "notion"),
                       help="이번 요청의 완료에 필요한 외부 반영")
    start.set_defaults(handler=start_command)

    defer = subparsers.add_parser("defer", help="미완료 대상의 실제 상태와 시도 기록")
    defer.add_argument("--workspace")
    defer.add_argument("--application", required=True)
    defer.add_argument("--status", required=True, choices=sorted(DISPOSITIONS))
    defer.add_argument("--reason", required=True)
    defer.add_argument("--attempt", action="append", default=[])
    defer.add_argument("--question", action="append", default=[])
    defer.set_defaults(handler=defer_command)

    resume = subparsers.add_parser("resume", help="보류한 공고 조사 재개")
    resume.add_argument("--workspace")
    resume.add_argument("--application", required=True)
    resume.add_argument("--rebind", action="store_true", help="새 Codex 작업의 훅 세션에 다시 연결")
    resume.set_defaults(handler=resume_command)

    for name, help_text, handler in (
        ("check", "전체 대상 검사", check_command),
        ("finish", "모든 대상이 완료된 실행 종료", finish_command),
        ("status", "현재 공고 조사 실행 상태 조회", status_command),
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

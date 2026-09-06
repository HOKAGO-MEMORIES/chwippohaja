#!/usr/bin/env python3
"""Track selected artifacts separately from preparation, sync and submission state."""

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

STATE = Path("01_공고_JD") / ".application-state.json"
KINDS = {"posting_analysis": "01_공고_JD", "company_research": "01_공고_JD",
         "essay": "02_작성중", "application": "02_작성중"}
STAGES = {"materials": {"pending", "partial", "ready"},
          "writing": {"pending", "partial_draft", "valid_draft", "final_candidate"},
          "submission": {"not_submitted", "confirmed", "evidence_saved"}}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(application: Path) -> dict[str, Any]:
    path = application / STATE
    if not path.exists():
        return {"schema_version": 1, "current_artifacts": {}, "stages": {}, "integrations": {}, "history": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("지원 건 상태 형식이 올바르지 않습니다.")
    for key in ("current_artifacts", "stages", "integrations"):
        if not isinstance(value.get(key), dict):
            raise ValueError(f"지원 건 상태의 {key}는 객체여야 합니다.")
    if not isinstance(value.get("history"), list):
        raise ValueError("지원 건 상태의 history는 배열이어야 합니다.")
    return value


def save(application: Path, state: dict[str, Any]) -> None:
    if not (application / "01_공고_JD/.application.json").is_file():
        raise ValueError("지원 건 표식이 없습니다.")
    path = application / STATE
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".application-state-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(state, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def artifact_path(application: Path, kind: str, raw: str) -> Path:
    root = application.resolve()
    target = Path(raw)
    target = (target if target.is_absolute() else root / target).resolve()
    relative = target.relative_to(root)
    if not relative.parts or relative.parts[0] != KINDS[kind] or target.suffix.lower() != ".md" or not target.is_file():
        raise ValueError("기준 파일은 해당 지원 건의 올바른 폴더에 있는 Markdown 파일이어야 합니다.")
    return target


def select(application: Path, kind: str, raw: str, note: str) -> dict[str, Any]:
    if kind not in KINDS or not note.strip():
        raise ValueError("파일 종류와 선택 근거가 필요합니다.")
    target = artifact_path(application, kind, raw)
    state = load(application)
    record = {"path": target.relative_to(application.resolve()).as_posix(),
              "sha256": file_digest(target), "selected_at": now(), "note": note.strip()}
    previous = state["current_artifacts"].get(kind)
    if previous and previous.get("path") == record["path"] and previous.get("sha256") == record["sha256"]:
        return previous
    state["history"].append({"kind": kind, "previous": previous, "selected": record})
    state["current_artifacts"][kind] = record
    if kind in {"essay", "application"}:
        state["stages"].pop("writing", None)
    else:
        state["stages"].pop("materials", None)
    save(application, state)
    return record


def current(application: Path, kind: str, fallback: list[Path] | None = None) -> Path | None:
    record = load(application)["current_artifacts"].get(kind)
    if record is not None:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError(f"{kind}: 기준 파일 기록이 올바르지 않습니다.")
        target = artifact_path(application, kind, record["path"])
        if record.get("sha256") != file_digest(target):
            raise ValueError(f"{kind}: 선택 이후 내용이 변경됐습니다. 확인 후 기준 파일을 다시 선택하세요.")
        return target
    candidates = fallback or []
    if len(candidates) > 1:
        raise ValueError(f"{kind}: 문서가 여러 개입니다. application_state.py select로 최신 유효 문서를 지정하세요.")
    return candidates[0] if candidates else None


def snapshot(application: Path, scope: str) -> dict[str, str]:
    patterns = {"posting_analysis": "*공고분석*.md", "company_research": "*기업리서치*.md"}
    kinds = patterns if scope == "research" else KINDS
    result = {}
    for kind in kinds:
        fallback = sorted((application / "01_공고_JD").glob(patterns[kind])) if kind in patterns else []
        path = current(application, kind, fallback)
        if path:
            result[path.relative_to(application.resolve()).as_posix()] = file_digest(path)
    if not result:
        raise ValueError("검증할 현재 기준 파일이 없습니다.")
    return result


def sync(application: Path, service: str, status: str, note: str, scope: str = "research") -> dict:
    if service not in {"google_drive", "notion"} or status not in {"pending", "verified"} or not note.strip():
        raise ValueError("서비스, 반영 상태와 실제 확인 근거가 필요합니다.")
    state = load(application)
    record = {"status": status, "scope": scope, "note": note.strip(), "checked_at": now(),
              "snapshot": snapshot(application, scope) if status == "verified" else {}}
    state["integrations"].setdefault(scope, {})[service] = record
    save(application, state)
    return record


def sync_verified(application: Path, service: str, scope: str = "research") -> bool:
    record = load(application)["integrations"].get(scope, {}).get(service, {})
    if record.get("status") != "verified":
        return False
    try:
        return record.get("snapshot") == snapshot(application, scope)
    except (OSError, ValueError):
        return False


def stage(application: Path, name: str, status: str, evidence: str) -> dict:
    if name not in STAGES or status not in STAGES[name] or not evidence.strip():
        raise ValueError("단계에 맞는 상태와 확인 근거가 필요합니다.")
    state = load(application)
    record = {"status": status, "evidence": evidence.strip(), "checked_at": now()}
    if name in {"materials", "writing"}:
        record["snapshot"] = snapshot(application, "research" if name == "materials" else "application")
    state["history"].append({"stage": name, "previous": state["stages"].get(name), "recorded": record})
    state["stages"][name] = record
    save(application, state)
    return record


def status_view(application: Path) -> dict:
    state = load(application)
    state["current_checks"] = {}
    for kind in state["current_artifacts"]:
        try:
            current(application, kind)
            state["current_checks"][kind] = "unchanged"
        except (OSError, ValueError) as exc:
            state["current_checks"][kind] = str(exc)
    for scope, services in state["integrations"].items():
        for service, record in services.items():
            record["effective_status"] = "verified" if sync_verified(application, service, scope) else "pending"
    for name, record in state["stages"].items():
        if name == "submission":
            continue
        try:
            unchanged = record.get("snapshot") == snapshot(application, "research" if name == "materials" else "application")
        except (OSError, ValueError):
            unchanged = False
        record["effective_status"] = record["status"] if unchanged else "needs_review"
    return state


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if callable(getattr(stream, "reconfigure", None)):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("select", "sync", "stage", "status"):
        sub = commands.add_parser(name)
        sub.add_argument("--application", type=Path, required=True)
        if name == "select":
            sub.add_argument("--kind", choices=KINDS, required=True)
            sub.add_argument("--file", required=True)
            sub.add_argument("--note", required=True)
        elif name == "sync":
            sub.add_argument("--service", choices=("google_drive", "notion"), required=True)
            sub.add_argument("--status", choices=("pending", "verified"), required=True)
            sub.add_argument("--scope", choices=("research", "application"), default="research")
            sub.add_argument("--note", required=True)
        elif name == "stage":
            sub.add_argument("--stage", choices=STAGES, required=True)
            sub.add_argument("--status", required=True)
            sub.add_argument("--evidence", required=True)
    args = parser.parse_args(argv)
    application = args.application.expanduser().resolve()
    try:
        if args.command == "select":
            result = select(application, args.kind, args.file, args.note)
        elif args.command == "sync":
            result = sync(application, args.service, args.status, args.note, args.scope)
        elif args.command == "stage":
            result = stage(application, args.stage, args.status, args.evidence)
        else:
            result = status_view(application)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

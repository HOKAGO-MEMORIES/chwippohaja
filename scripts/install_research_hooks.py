#!/usr/bin/env python3
"""Install or update project-local Codex hooks for posting research."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any


HOOK_ID = "chwippohaja-research-hook"
MARKER = Path(".chwippohaja") / "workspace.json"
CONFIG = Path(".codex") / "hooks.json"


def command_for(script: Path) -> tuple[str, str]:
    posix = f"python3 {shlex.quote(str(script))} hook --hook-id {HOOK_ID}"
    escaped = str(script).replace('"', '\\"')
    windows = f'py -3 "{escaped}" hook --hook-id {HOOK_ID}'
    return posix, windows


def hook_spec(script: Path) -> dict[str, Any]:
    command, command_windows = command_for(script)
    return {
        "type": "command",
        "command": command,
        "commandWindows": command_windows,
        "timeout": 30,
        "statusMessage": "공고 조사 완료 조건 검사 중",
    }


def is_ours(item: Any) -> bool:
    return isinstance(item, dict) and HOOK_ID in str(item.get("command", ""))


def merge_config(existing: dict[str, Any], script: Path) -> dict[str, Any]:
    result = dict(existing)
    hooks = dict(result.get("hooks", {}))
    spec = hook_spec(script)
    additions = {
        "PostToolUse": {"matcher": "apply_patch|Edit|Write", "hooks": [spec]},
        "Stop": {"hooks": [spec]},
    }
    for event, addition in additions.items():
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            raise ValueError(f"기존 hooks.{event}는 배열이어야 합니다.")
        cleaned: list[Any] = []
        for group in groups:
            if not isinstance(group, dict):
                cleaned.append(group)
                continue
            commands = group.get("hooks", [])
            if not isinstance(commands, list):
                cleaned.append(group)
                continue
            remaining = [item for item in commands if not is_ours(item)]
            if remaining:
                copy = dict(group)
                copy["hooks"] = remaining
                cleaned.append(copy)
        cleaned.append(addition)
        hooks[event] = cleaned
    result["hooks"] = hooks
    return result


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Codex에서 연 프로젝트 경로. 생략하면 워크스페이스 루트",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def configure_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = parse_args(argv)
    root = args.workspace.expanduser().resolve()
    if not (root / MARKER).is_file():
        print(f"워크스페이스 표식이 없습니다: {root / MARKER}", file=sys.stderr)
        return 1
    project_root = (args.project_root or root).expanduser().resolve()
    try:
        project_root.relative_to(root)
    except ValueError:
        print("Codex 프로젝트 경로는 취업 워크스페이스 내부여야 합니다.", file=sys.stderr)
        return 1
    if not project_root.is_dir():
        print(f"Codex 프로젝트 경로가 없습니다: {project_root}", file=sys.stderr)
        return 1
    script = Path(__file__).resolve().with_name("research_hook.py")
    path = project_root / CONFIG
    try:
        existing: dict[str, Any] = {}
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("기존 hooks.json은 JSON 객체여야 합니다.")
            existing = loaded
        result = merge_config(existing, script)
        if args.dry_run:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            write_json_atomic(path, result)
            print(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

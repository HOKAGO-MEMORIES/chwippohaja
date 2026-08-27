#!/usr/bin/env python3
"""Discover, plan, and initialize a chwippohaja workspace safely."""

from __future__ import annotations

import argparse
import json
import os
import platform
import string
import sys
import tempfile
from pathlib import Path
from typing import Any


MARKER = Path(".chwippohaja") / "workspace.json"
ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "workspace"
INTEGRATION_STATES = ("disabled", "pending", "enabled")
INTEGRATION_SERVICES = ("google_drive", "notion")
STORAGE_MODES = ("local", "google-drive")
PROFILE_STATUSES = ("empty", "in_progress", "ready")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}

BASE_DIRECTORIES = (
    Path("공통자료"),
    Path("작성템플릿"),
    Path("증빙서류"),
    Path("증빙서류") / "학력",
    Path("증빙서류") / "자격증_어학",
    Path("증빙서류") / "교육_수상",
    Path("증빙서류") / "경력_병역",
    Path("증빙서류") / "사진_서명",
    Path("증빙서류") / "민감서류",
)

ASSET_FILES = (
    Path("공통자료") / "경력_프로젝트_소재.md",
    Path("작성템플릿") / "자소서_작성설계.md",
)

OPTIONAL_RULE_FILES = (
    Path("AGENTS.md"),
    Path("README_취업자료_운영규칙.md"),
)

RECOGNIZED_ENTRIES = (
    *OPTIONAL_RULE_FILES,
    Path("공통자료"),
    Path("작성템플릿"),
    Path("증빙서류"),
)

WORKSPACE_CORE_DIRECTORIES = (
    Path("공통자료"),
    Path("작성템플릿"),
    Path("증빙서류"),
)


class SetupError(RuntimeError):
    """Raised when setup cannot proceed safely."""


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def resolved(raw: str | Path) -> Path:
    return Path(raw).expanduser().resolve(strict=False)


def validate_root(raw: str | Path) -> Path:
    root = resolved(raw)
    home = Path.home().resolve(strict=False)
    anchor = Path(root.anchor).resolve(strict=False)
    if root == home:
        raise SetupError("사용자 홈 자체를 워크스페이스로 사용할 수 없습니다. 하위 폴더를 선택하세요.")
    if root == anchor:
        raise SetupError("파일 시스템 루트를 워크스페이스로 사용할 수 없습니다.")
    if root.exists() and not root.is_dir():
        raise SetupError(f"워크스페이스 경로가 폴더가 아닙니다: {root}")
    return root


def validate_season(value: str) -> str:
    if not isinstance(value, str):
        raise SetupError("시즌 이름은 문자열이어야 합니다.")
    season = value.strip()
    if not season or season in {".", ".."}:
        raise SetupError("시즌 이름을 입력하세요.")
    if any(character in season for character in '/\\\0<>:"|?*'):
        raise SetupError("시즌 이름에 운영체제에서 사용할 수 없는 문자가 있습니다.")
    if season.endswith((".", " ")):
        raise SetupError("시즌 이름은 마침표나 공백으로 끝날 수 없습니다.")
    if season.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        raise SetupError("Windows 예약어는 시즌 이름으로 사용할 수 없습니다.")
    return season


def read_marker(root: Path) -> dict[str, Any] | None:
    marker = root / MARKER
    if not marker.exists():
        return None
    if not marker.is_file():
        raise SetupError("워크스페이스 표식 경로가 파일이 아닙니다.")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"워크스페이스 표식을 읽을 수 없습니다: {exc}") from exc
    if not isinstance(data, dict):
        raise SetupError("지원하지 않거나 손상된 워크스페이스 표식입니다.")
    integrations = data.get("integrations", {})
    if not isinstance(integrations, dict):
        raise SetupError("지원하지 않거나 손상된 워크스페이스 표식입니다.")
    profile_status = data.get("profile_status", "empty")
    try:
        active_season = validate_season(data.get("active_season", ""))
    except SetupError as exc:
        raise SetupError("지원하지 않거나 손상된 워크스페이스 표식입니다.") from exc
    if (
        data.get("schema_version") != 1
        or data.get("workspace_root") != "."
        or data.get("storage_mode") not in STORAGE_MODES
        or data.get("active_season") != active_season
        or integrations.get("google_drive") not in INTEGRATION_STATES
        or integrations.get("notion") not in INTEGRATION_STATES
        or profile_status not in PROFILE_STATUSES
    ):
        raise SetupError("지원하지 않거나 손상된 워크스페이스 표식입니다.")
    data["profile_status"] = profile_status
    return data


def inspect_workspace(root: Path) -> dict[str, Any]:
    if root.exists() and not root.is_dir():
        return {"status": "invalid", "reason": "path-is-not-directory"}
    if (root / MARKER).exists():
        try:
            config = read_marker(root)
        except SetupError as exc:
            return {"status": "invalid", "reason": str(exc)}
        return {"status": "configured", "config": config}
    if not root.exists():
        return {"status": "empty"}
    if any((root / entry).exists() for entry in RECOGNIZED_ENTRIES):
        return {"status": "adoptable"}
    try:
        has_entries = next(root.iterdir(), None) is not None
    except OSError as exc:
        return {"status": "invalid", "reason": str(exc)}
    return {"status": "nonempty" if has_entries else "empty"}


def find_workspace(start: Path) -> Path | None:
    current = (start if start.is_dir() else start.parent).resolve(strict=False)
    for candidate in (current, *current.parents):
        if (candidate / MARKER).is_file():
            return candidate.resolve(strict=False)
    return None


def adoptable_workspace_score(root: Path) -> int:
    if not root.is_dir():
        return 0
    core_count = sum((root / entry).is_dir() for entry in WORKSPACE_CORE_DIRECTORIES)
    if core_count < 2:
        return 0
    guide_count = sum(
        (root / entry).is_file()
        for entry in OPTIONAL_RULE_FILES
    )
    return core_count * 10 + guide_count


def find_adoptable_workspace(start: Path) -> Path | None:
    current = (start if start.is_dir() else start.parent).resolve(strict=False)
    home = Path.home().resolve(strict=False)
    candidates: list[tuple[int, int, Path]] = []
    for distance, candidate in enumerate((current, *current.parents)):
        if candidate == home or candidate == Path(candidate.anchor).resolve(strict=False):
            continue
        score = adoptable_workspace_score(candidate)
        if score:
            candidates.append((score, -distance, candidate))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(path.resolve(strict=False))
        key = normalized.casefold() if os.name == "nt" else normalized
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def drive_content_roots(container: Path) -> list[Path]:
    content_roots = [container / name for name in ("My Drive", "내 드라이브")]
    found = [candidate for candidate in content_roots if candidate.is_dir()]
    return found or [container]


def google_drive_roots() -> list[Path]:
    home = Path.home()
    roots: list[Path] = []
    configured = os.environ.get("GOOGLE_DRIVE_ROOT")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_dir():
            roots.append(candidate)

    system = platform.system()
    if system == "Darwin":
        cloud_storage = home / "Library" / "CloudStorage"
        if cloud_storage.is_dir():
            for account_root in cloud_storage.glob("GoogleDrive-*"):
                if account_root.is_dir():
                    roots.extend(drive_content_roots(account_root))
        legacy = Path("/Volumes/GoogleDrive")
        if legacy.is_dir():
            roots.extend(drive_content_roots(legacy))
    elif system == "Windows":
        for candidate in (home / "Google Drive", home / "My Drive", home / "내 드라이브"):
            if candidate.is_dir():
                roots.append(candidate)
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if not drive.is_dir():
                continue
            for name in ("My Drive", "내 드라이브"):
                candidate = drive / name
                if candidate.is_dir():
                    roots.append(candidate)
    return unique_paths(roots)


def discovery(path: Path) -> dict[str, Any]:
    root = resolved(path)
    if root.exists() and not root.is_dir():
        root = root.parent
    configured = find_workspace(root) if root.exists() else None
    adoptable = find_adoptable_workspace(root) if root.exists() and configured is None else None
    found = configured or adoptable
    local_candidates: list[Path] = []
    for candidate in (found, root, Path.home() / "Documents" / "취업"):
        if candidate is None:
            continue
        try:
            local_candidates.append(validate_root(candidate))
        except SetupError:
            continue
    local_candidates = unique_paths(local_candidates)
    drive_candidates = unique_paths([drive_root / "취업" for drive_root in google_drive_roots()])
    inspected = inspect_workspace(found or root)
    return {
        "platform": platform.system() or "Unknown",
        "requested_path": str(root),
        "workspace_root": str(found) if found else None,
        "workspace": inspected,
        "candidates": {
            "local": [str(candidate) for candidate in local_candidates],
            "google_drive": [str(candidate) for candidate in drive_candidates],
        },
    }


def config_for(
    storage: str,
    season: str,
    notion: str,
    drive_plugin: str,
    profile_status: str = "empty",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workspace_root": ".",
        "storage_mode": storage,
        "active_season": season,
        "profile_status": profile_status,
        "integrations": {
            "google_drive": drive_plugin,
            "notion": notion,
        },
    }


def setup_plan(
    root: Path,
    storage: str,
    season: str,
    notion: str,
    drive_plugin: str,
    adopt: bool,
    profile_status: str | None = None,
) -> dict[str, Any]:
    root = validate_root(root)
    season = validate_season(season)
    if storage not in STORAGE_MODES:
        raise SetupError(f"지원하지 않는 저장 방식입니다: {storage}")
    if notion not in INTEGRATION_STATES or drive_plugin not in INTEGRATION_STATES:
        raise SetupError("지원하지 않는 연결 상태입니다.")
    selected_profile_status = profile_status or "empty"
    if selected_profile_status not in PROFILE_STATUSES:
        raise SetupError("지원하지 않는 정보 설정 상태입니다.")
    state = inspect_workspace(root)
    if state["status"] == "invalid":
        raise SetupError(str(state.get("reason", "워크스페이스 상태를 확인할 수 없습니다.")))
    if state["status"] == "configured":
        return {
            "root": str(root),
            "status": "already-configured",
            "create": [],
            "preserve": [],
            "config": state["config"],
        }
    if state["status"] in {"adoptable", "nonempty"} and not adopt:
        raise SetupError("기존 파일이 있습니다. 보존하면서 가져오려면 --adopt를 사용하세요.")

    adopting = state["status"] in {"adoptable", "nonempty"} and adopt
    if not adopting and selected_profile_status != "empty":
        raise SetupError(
            "새 워크스페이스의 정보 설정 상태는 empty로 시작합니다. "
            "환경 설정 후 profile-status로 갱신하세요."
        )
    directories = (
        (Path(season), MARKER.parent)
        if adopting
        else (*BASE_DIRECTORIES, Path(season), MARKER.parent)
    )
    create: list[str] = []
    preserve: list[str] = []

    if not root.exists():
        create.append(".")
    elif adopting:
        for target in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
            if target == root / MARKER.parent:
                continue
            suffix = "/" if target.is_dir() else ""
            preserve.append(target.name + suffix)
    for relative in directories:
        target = root / relative
        if target.exists() and not target.is_dir():
            raise SetupError(f"폴더 경로에 같은 이름의 파일이 있습니다: {target}")
        (preserve if target.exists() else create).append(relative.as_posix() + "/")
    if not adopting:
        for relative in ASSET_FILES:
            target = root / relative
            if target.exists() and not target.is_file():
                raise SetupError(f"파일 경로에 같은 이름의 폴더가 있습니다: {target}")
            (preserve if target.exists() else create).append(relative.as_posix())
    for relative in OPTIONAL_RULE_FILES:
        target = root / relative
        if target.exists():
            suffix = "/" if target.is_dir() else ""
            preserve.append(relative.as_posix() + suffix)
    create.append(MARKER.as_posix())
    create = list(dict.fromkeys(create))
    preserve = list(dict.fromkeys(preserve))

    return {
        "root": str(root),
        "status": "adopt" if state["status"] in {"adoptable", "nonempty"} else "new",
        "create": create,
        "preserve": preserve,
        "config": config_for(
            storage,
            season,
            notion,
            drive_plugin,
            selected_profile_status,
        ),
    }


def nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return candidate


def apply_setup(
    root: Path,
    storage: str,
    season: str,
    notion: str,
    drive_plugin: str,
    adopt: bool,
    profile_status: str | None = None,
) -> dict[str, Any]:
    plan = setup_plan(
        root,
        storage,
        season,
        notion,
        drive_plugin,
        adopt,
        profile_status,
    )
    if plan["status"] == "already-configured":
        return plan

    root = validate_root(root)
    parent = nearest_existing_parent(root)
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise SetupError(f"선택한 경로에 쓸 수 없습니다: {root}")
    adopting = plan["status"] == "adopt"
    missing_assets = (
        []
        if adopting
        else [relative for relative in ASSET_FILES if not (ASSET_ROOT / relative).is_file()]
    )
    if missing_assets:
        names = ", ".join(relative.as_posix() for relative in missing_assets)
        raise SetupError(f"온보딩 템플릿이 없습니다: {names}")

    created_files: list[Path] = []
    created_directories: list[Path] = []
    try:
        if not root.exists():
            missing_chain: list[Path] = []
            candidate = root
            while not candidate.exists():
                missing_chain.append(candidate)
                candidate = candidate.parent
            for directory in reversed(missing_chain):
                directory.mkdir()
                created_directories.append(directory)

        directories = sorted(
            (
                (Path(validate_season(season)), MARKER.parent)
                if adopting
                else (*BASE_DIRECTORIES, Path(validate_season(season)), MARKER.parent)
            ),
            key=lambda path: len(path.parts),
        )
        for relative in directories:
            target = root / relative
            if not target.exists():
                target.mkdir()
                created_directories.append(target)
            elif not target.is_dir():
                raise SetupError(f"폴더를 만들 수 없습니다. 같은 이름의 파일이 있습니다: {target}")

        if not adopting:
            for relative in ASSET_FILES:
                source = ASSET_ROOT / relative
                destination = root / relative
                if destination.exists():
                    continue
                with destination.open("xb") as output:
                    output.write(source.read_bytes())
                created_files.append(destination)

        marker = root / MARKER
        with marker.open("x", encoding="utf-8") as output:
            output.write(json.dumps(plan["config"], ensure_ascii=False, indent=2) + "\n")
        created_files.append(marker)
    except Exception:
        for path in reversed(created_files):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        for path in reversed(created_directories):
            try:
                path.rmdir()
            except OSError:
                pass
        raise

    return {**plan, "status": "configured"}


def write_marker_atomic(root: Path, config: dict[str, Any]) -> None:
    marker = root / MARKER
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=marker.parent,
            prefix=".workspace.",
            suffix=".tmp",
            delete=False,
        ) as output:
            json.dump(config, output, ensure_ascii=False, indent=2)
            output.write("\n")
            temporary_path = Path(output.name)
        os.replace(temporary_path, marker)
        temporary_path = None
    except OSError as exc:
        raise SetupError(f"워크스페이스 표식을 갱신할 수 없습니다: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def update_profile_status(root: Path, status: str) -> dict[str, Any]:
    root = validate_root(root)
    if status not in PROFILE_STATUSES:
        raise SetupError(f"지원하지 않는 정보 설정 상태입니다: {status}")

    config = read_marker(root)
    if config is None:
        raise SetupError("설정된 워크스페이스가 아닙니다. 환경 설정을 먼저 완료하세요.")

    previous = config["profile_status"]
    result_status = "unchanged" if previous == status else "updated"
    if previous != status:
        config["profile_status"] = status
        write_marker_atomic(root, config)

    return {
        "root": str(root),
        "status": result_status,
        "previous_profile_status": previous,
        "profile_status": status,
    }


def update_integration_status(root: Path, service: str, status: str) -> dict[str, Any]:
    root = validate_root(root)
    if service not in INTEGRATION_SERVICES:
        raise SetupError(f"지원하지 않는 연결 서비스입니다: {service}")
    if status not in INTEGRATION_STATES:
        raise SetupError(f"지원하지 않는 연결 상태입니다: {status}")
    config = read_marker(root)
    if config is None:
        raise SetupError("설정된 워크스페이스가 아닙니다. 환경 설정을 먼저 완료하세요.")

    previous = config["integrations"][service]
    result_status = "unchanged" if previous == status else "updated"
    if previous != status:
        config["integrations"][service] = status
        write_marker_atomic(root, config)
    return {
        "root": str(root),
        "status": result_status,
        "service": service,
        "previous_integration_status": previous,
        "integration_status": status,
    }


def add_setup_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", required=True, help="워크스페이스로 사용할 경로")
    parser.add_argument("--storage", required=True, choices=STORAGE_MODES)
    parser.add_argument("--season", required=True)
    parser.add_argument("--notion", choices=INTEGRATION_STATES, default="disabled")
    parser.add_argument("--drive-plugin", choices=INTEGRATION_STATES, default="disabled")
    parser.add_argument(
        "--profile-status",
        choices=PROFILE_STATUSES,
        help="기존 환경에서 사용자가 확인한 정보 준비 상태",
    )
    parser.add_argument("--adopt", action="store_true", help="기존 파일을 보존하며 구조를 가져오기")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="현재 환경과 경로 후보 확인")
    discover_parser.add_argument("--path", default=os.getcwd())

    plan_parser = subparsers.add_parser("plan", help="변경 없이 생성 계획 출력")
    add_setup_arguments(plan_parser)

    apply_parser = subparsers.add_parser("apply", help="승인된 생성 계획 적용")
    add_setup_arguments(apply_parser)

    profile_parser = subparsers.add_parser("profile-status", help="정보 설정 상태 확인 또는 변경")
    profile_parser.add_argument("--root", required=True, help="설정된 워크스페이스 경로")
    profile_parser.add_argument("--set", dest="profile_status", choices=PROFILE_STATUSES)

    integration_parser = subparsers.add_parser(
        "integration-status", help="연결 서비스 상태 확인 또는 변경"
    )
    integration_parser.add_argument("--root", required=True, help="설정된 워크스페이스 경로")
    integration_parser.add_argument("--service", choices=INTEGRATION_SERVICES)
    integration_parser.add_argument("--set", dest="integration_status", choices=INTEGRATION_STATES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = parse_args(argv)
    try:
        if args.command == "discover":
            result = discovery(resolved(args.path))
        elif args.command == "profile-status":
            root = resolved(args.root)
            if args.profile_status is None:
                config = read_marker(validate_root(root))
                if config is None:
                    raise SetupError("설정된 워크스페이스가 아닙니다. 환경 설정을 먼저 완료하세요.")
                result = {
                    "root": str(validate_root(root)),
                    "status": "configured",
                    "profile_status": config["profile_status"],
                }
            else:
                result = update_profile_status(root, args.profile_status)
        elif args.command == "integration-status":
            root = validate_root(resolved(args.root))
            if args.integration_status is not None:
                if args.service is None:
                    raise SetupError("연결 상태를 변경하려면 --service를 지정하세요.")
                result = update_integration_status(
                    root, args.service, args.integration_status
                )
            else:
                config = read_marker(root)
                if config is None:
                    raise SetupError("설정된 워크스페이스가 아닙니다. 환경 설정을 먼저 완료하세요.")
                integrations = config["integrations"]
                result = {
                    "root": str(root),
                    "status": "configured",
                    "integrations": (
                        {args.service: integrations[args.service]}
                        if args.service is not None
                        else integrations
                    ),
                }
        else:
            operation = setup_plan if args.command == "plan" else apply_setup
            result = operation(
                resolved(args.root),
                args.storage,
                args.season,
                args.notion,
                args.drive_plugin,
                args.adopt,
                args.profile_status,
            )
    except SetupError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

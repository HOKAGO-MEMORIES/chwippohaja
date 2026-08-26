#!/usr/bin/env python3
"""Plan and create one application workspace without overwriting existing work."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from workspace_setup import (  # noqa: E402
    WINDOWS_RESERVED_NAMES,
    SetupError,
    read_marker,
    resolved,
    validate_root,
)


APPLICATION_DIRECTORIES = (Path("01_공고_JD"), Path("02_작성중"), Path("99_최종제출"))
APPLICATION_MARKER = Path("01_공고_JD") / ".application.json"
DRAFT_NUMBER = re.compile(r"^(\d{2})_")
INVALID_COMPONENT_CHARACTERS = set('/\\\0<>:"|?*')


class ApplicationError(RuntimeError):
    """Raised when an application workspace cannot be handled safely."""


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def safe_component(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ApplicationError(f"{label}은 문자열이어야 합니다.")
    stripped = " ".join(value.strip().split())
    cleaned = "".join(
        "_" if character in INVALID_COMPONENT_CHARACTERS else character
        for character in stripped
    ).strip(". ")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned or cleaned in {".", ".."}:
        raise ApplicationError(f"{label}을 입력하세요.")
    if cleaned.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        raise ApplicationError(f"{label}에 Windows 예약어를 사용할 수 없습니다.")
    return cleaned


def application_identity(company: str, role: str, posting_key: str | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "company": company.strip(),
        "role": role.strip(),
        "posting_key": posting_key.strip() if posting_key else None,
    }


def identity_key(identity: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(identity.get("company", "")).casefold(),
        str(identity.get("role", "")).casefold(),
        str(identity.get("posting_key") or "").casefold(),
    )


def read_application_marker(application: Path) -> dict[str, Any] | None:
    marker = application / APPLICATION_MARKER
    if not marker.exists():
        return None
    if not marker.is_file():
        raise ApplicationError(f"지원 건 표식 경로가 파일이 아닙니다: {marker}")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApplicationError(f"지원 건 표식을 읽을 수 없습니다: {marker}: {exc}") from exc
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("company"), str)
        or not data.get("company", "").strip()
        or not isinstance(data.get("role"), str)
        or not data.get("role", "").strip()
        or (data.get("posting_key") is not None and not isinstance(data.get("posting_key"), str))
    ):
        raise ApplicationError(f"지원하지 않거나 손상된 지원 건 표식입니다: {marker}")
    return data


def existing_applications(season_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    if not season_root.is_dir():
        return result
    for marker in season_root.glob(f"*/{APPLICATION_MARKER.as_posix()}"):
        application = marker.parent.parent
        identity = read_application_marker(application)
        if identity is not None:
            result.append((application, identity))
    return result


def require_workspace(root: Path) -> tuple[Path, dict[str, Any], Path]:
    try:
        root = validate_root(root)
        config = read_marker(root)
    except SetupError as exc:
        raise ApplicationError(str(exc)) from exc
    if config is None:
        raise ApplicationError("설정된 워크스페이스가 아닙니다. 환경 설정을 먼저 완료하세요.")
    season_root = root / config["active_season"]
    if not season_root.is_dir():
        raise ApplicationError(f"활성 시즌 폴더가 없습니다: {season_root}")
    return root, config, season_root


def choose_application_path(
    season_root: Path,
    identity: dict[str, Any],
    new_application: bool,
    adopt_existing: bool,
) -> tuple[Path, str]:
    applications = existing_applications(season_root)
    exact = [path for path, current in applications if identity_key(current) == identity_key(identity)]
    if exact and not new_application:
        if len(exact) > 1:
            raise ApplicationError("같은 식별 정보를 가진 지원 건이 여러 개입니다. 먼저 중복을 정리하세요.")
        return exact[0], "already-configured"

    same_role = [
        path
        for path, current in applications
        if str(current["company"]).casefold() == str(identity["company"]).casefold()
        and str(current["role"]).casefold() == str(identity["role"]).casefold()
    ]
    if same_role and not new_application:
        if not identity.get("posting_key"):
            raise ApplicationError(
                "같은 기업과 직무의 기존 지원 건이 있습니다. 기존 공고 키를 확인해 전달하세요."
            )
        raise ApplicationError(
            "같은 기업과 직무에 다른 공고 키가 있습니다. 별도 지원이면 --new-application을 사용하세요."
        )
    if new_application and same_role and not identity.get("posting_key"):
        raise ApplicationError("같은 기업과 직무의 새 지원 건에는 --posting-key가 필요합니다.")

    company = safe_component(identity["company"], "기업명")
    role = safe_component(identity["role"], "직무명")
    posting_key = (
        safe_component(identity["posting_key"], "공고 키") if identity.get("posting_key") else None
    )
    if new_application and same_role:
        names = [f"{company}_{role}_{posting_key}"]
    elif new_application:
        names = [f"{company}_{role}"]
        if posting_key:
            names.append(f"{company}_{role}_{posting_key}")
    else:
        names = [company, f"{company}_{role}"]
        if posting_key:
            names.append(f"{company}_{role}_{posting_key}")

    for index, name in enumerate(names):
        candidate = season_root / name
        if not candidate.exists():
            return candidate, "new"
        if not candidate.is_dir():
            raise ApplicationError(f"지원 건 폴더 경로에 같은 이름의 파일이 있습니다: {candidate}")
        current = read_application_marker(candidate)
        if current is not None:
            if identity_key(current) == identity_key(identity) and not new_application:
                return candidate, "already-configured"
            continue
        if adopt_existing and not new_application:
            return candidate, "adopt"
        if not new_application and index == 0:
            raise ApplicationError(
                "기존 기업 폴더의 지원 건을 확인할 수 없습니다. 가져오려면 --adopt-existing, "
                "별도 지원이면 --new-application을 사용하세요."
            )

    if not posting_key:
        raise ApplicationError("지원 건을 구분할 --posting-key가 필요합니다.")
    raise ApplicationError("생성할 지원 건 폴더가 이미 사용 중입니다. 공고 키를 다시 확인하세요.")


def application_plan(
    root: Path,
    company: str,
    role: str,
    posting_key: str | None = None,
    new_application: bool = False,
    adopt_existing: bool = False,
) -> dict[str, Any]:
    root, config, season_root = require_workspace(root)
    identity = application_identity(company, role, posting_key)
    application, status = choose_application_path(
        season_root, identity, new_application, adopt_existing
    )

    if status == "already-configured":
        return {
            "root": str(root),
            "application": str(application),
            "status": status,
            "create": [],
            "preserve": [str(application.relative_to(root))],
            "identity": identity,
        }

    create: list[str] = []
    preserve: list[str] = []
    if not application.exists():
        create.append(str(application.relative_to(root)) + "/")
    else:
        preserve.append(str(application.relative_to(root)) + "/")
    for relative in APPLICATION_DIRECTORIES:
        target = application / relative
        if target.exists() and not target.is_dir():
            raise ApplicationError(f"폴더 경로에 같은 이름의 파일이 있습니다: {target}")
        collection = preserve if target.exists() else create
        collection.append(str(target.relative_to(root)) + "/")
    marker = application / APPLICATION_MARKER
    if marker.exists():
        raise ApplicationError(f"지원 건 표식이 이미 있습니다: {marker}")
    create.append(str(marker.relative_to(root)))

    return {
        "root": str(root),
        "active_season": config["active_season"],
        "application": str(application),
        "status": status,
        "create": create,
        "preserve": preserve,
        "identity": identity,
    }


def apply_application(
    root: Path,
    company: str,
    role: str,
    posting_key: str | None = None,
    new_application: bool = False,
    adopt_existing: bool = False,
) -> dict[str, Any]:
    plan = application_plan(
        root, company, role, posting_key, new_application, adopt_existing
    )
    if plan["status"] == "already-configured":
        return plan

    application = Path(plan["application"])
    created_files: list[Path] = []
    created_directories: list[Path] = []
    try:
        if not application.exists():
            application.mkdir()
            created_directories.append(application)
        for relative in APPLICATION_DIRECTORIES:
            target = application / relative
            if not target.exists():
                target.mkdir()
                created_directories.append(target)
        marker = application / APPLICATION_MARKER
        with marker.open("x", encoding="utf-8") as output:
            json.dump(plan["identity"], output, ensure_ascii=False, indent=2)
            output.write("\n")
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


def next_draft(application: Path, name: str, extension: str) -> dict[str, Any]:
    application = resolved(application)
    draft_folder = application / "02_작성중"
    if not draft_folder.is_dir():
        raise ApplicationError(f"작성 중 폴더가 없습니다: {draft_folder}")
    base_name = safe_component(name, "문서 이름")
    normalized_extension = extension.strip().lstrip(".")
    if not normalized_extension or not normalized_extension.isalnum():
        raise ApplicationError("확장자는 영문자와 숫자만 사용할 수 있습니다.")
    used = [
        int(match.group(1))
        for path in draft_folder.iterdir()
        if path.is_file() and (match := DRAFT_NUMBER.match(path.name))
    ]
    number = max(used, default=0) + 1
    if number > 99:
        raise ApplicationError("두 자리 작성 번호를 모두 사용했습니다. 작성본 번호 정책을 갱신하세요.")
    filename = f"{number:02d}_{base_name}.{normalized_extension}"
    target = draft_folder / filename
    if target.exists():
        raise ApplicationError(f"다음 작성 파일이 이미 있습니다: {target}")
    return {
        "application": str(application),
        "status": "available",
        "number": number,
        "filename": filename,
        "path": str(target),
    }


def add_application_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--posting-key")
    parser.add_argument("--new-application", action="store_true")
    parser.add_argument("--adopt-existing", action="store_true")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="변경 없이 지원 건 생성 계획 출력")
    add_application_arguments(plan_parser)
    apply_parser = subparsers.add_parser("apply", help="지원 건 생성 계획 적용")
    add_application_arguments(apply_parser)
    draft_parser = subparsers.add_parser("next-draft", help="다음 작성 파일 이름 계산")
    draft_parser.add_argument("--application", required=True)
    draft_parser.add_argument("--name", required=True)
    draft_parser.add_argument("--extension", default="md")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = parse_args(argv)
    try:
        if args.command == "next-draft":
            result = next_draft(Path(args.application), args.name, args.extension)
        else:
            operation = application_plan if args.command == "plan" else apply_application
            result = operation(
                resolved(args.root),
                args.company,
                args.role,
                args.posting_key,
                args.new_application,
                args.adopt_existing,
            )
    except ApplicationError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

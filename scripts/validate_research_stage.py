#!/usr/bin/env python3
"""Validate the minimum local artifacts for application research stage one."""

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
from application_state import current


URL_PATTERN = re.compile(r"https?://[^\s)>]+", re.IGNORECASE)
DATE_PATTERN = re.compile(r"20\d{2}(?:[-./년]\s*\d{1,2})?")
HEADING_PATTERN = re.compile(r"(?m)^#{1,6}\s+\S+")
MARKDOWN_NOISE = re.compile(r"[`#>*_\-|\[\]()]|https?://\S+", re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(
    r"\bTBD\b|준비\s*중|미등록|내용\s*없음|자료\s*없음|확인\s*불가",
    re.IGNORECASE,
)
ROLE_SEPARATOR_PATTERN = re.compile(r"[\s/·._-]+")
SOURCE_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".doc",
    ".docx",
    ".hwp",
    ".hwpx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}


def read_text(path: Path, errors: list[str]) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"파일을 읽을 수 없습니다: {path.name}: {exc}")
        return ""
    if not text.strip():
        errors.append(f"파일이 비어 있습니다: {path.name}")
    return text


def contains_any(text: str, candidates: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(candidate.casefold() in lowered for candidate in candidates)


def contains_role(text: str, role: str) -> bool:
    normalized_text = ROLE_SEPARATOR_PATTERN.sub("", text).casefold()
    normalized_role = ROLE_SEPARATOR_PATTERN.sub("", role).casefold()
    if normalized_role and normalized_role in normalized_text:
        return True
    tokens = [
        token.casefold()
        for token in ROLE_SEPARATOR_PATTERN.split(role)
        if len(token.strip()) >= 2
    ]
    return bool(tokens) and any(token in text.casefold() for token in tokens)


def validate_document(
    path: Path,
    *,
    company: str,
    keyword_groups: tuple[tuple[str, ...], ...],
    minimum_characters: int,
    minimum_headings: int,
    minimum_urls: int,
    role: str | None,
    errors: list[str],
) -> None:
    text = read_text(path, errors)
    if not text.strip():
        return
    if company.casefold() not in text.casefold():
        errors.append(f"기업명이 없습니다: {path.name}")
    urls = URL_PATTERN.findall(text)
    if len(set(urls)) < minimum_urls:
        errors.append(f"출처 URL이 {minimum_urls}개보다 적습니다: {path.name}")
    if not DATE_PATTERN.search(text):
        errors.append(f"확인일 또는 기준일이 없습니다: {path.name}")
    if role and not contains_role(text, role):
        errors.append(f"지원 직무가 없습니다: {path.name}: {role}")
    headings = HEADING_PATTERN.findall(text)
    if len(headings) < minimum_headings:
        errors.append(f"의미 있는 구역이 {minimum_headings}개보다 적습니다: {path.name}")
    substantive = MARKDOWN_NOISE.sub("", text)
    substantive = PLACEHOLDER_PATTERN.sub("", substantive)
    substantive = re.sub(r"\s+", "", substantive)
    if len(substantive) < minimum_characters:
        errors.append(
            f"실질 내용이 부족합니다: {path.name}: {len(substantive)}/{minimum_characters}자"
        )
    if len(PLACEHOLDER_PATTERN.findall(text)) >= 3:
        errors.append(f"미확인 상태 문구가 반복됩니다: {path.name}")
    for candidates in keyword_groups:
        if not contains_any(text, candidates):
            errors.append(
                f"필수 내용이 없습니다: {path.name}: {' 또는 '.join(candidates)}"
            )


def relative_names(paths: list[Path], application: Path) -> list[str]:
    return [str(path.relative_to(application)) for path in paths]


def validate_research_stage(application: Path) -> dict[str, Any]:
    application = application.expanduser().resolve()
    research_root = application / "01_공고_JD"
    errors: list[str] = []
    warnings: list[str] = []

    if not application.is_dir():
        return {
            "status": "partial",
            "errors": ["지원 건 폴더가 없습니다."],
            "warnings": [],
            "artifacts": {},
        }
    if not research_root.is_dir():
        return {
            "status": "partial",
            "errors": ["01_공고_JD 폴더가 없습니다."],
            "warnings": [],
            "artifacts": {},
        }

    marker = research_root / ".application.json"
    identity: dict[str, Any] = {}
    if not marker.is_file():
        errors.append("지원 건 표식 .application.json이 없습니다.")
    else:
        try:
            identity = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"지원 건 표식을 읽을 수 없습니다: {exc}")
        if not isinstance(identity, dict):
            errors.append("지원 건 표식은 JSON 객체여야 합니다.")
            identity = {}
        if (
            identity.get("schema_version") != 1
            or not isinstance(identity.get("company"), str)
            or not identity.get("company", "").strip()
            or not isinstance(identity.get("role"), str)
            or not identity.get("role", "").strip()
        ):
            errors.append("지원 건 표식의 기업명, 직무 또는 스키마가 올바르지 않습니다.")

    def selected(kind: str, pattern: str) -> list[Path]:
        try:
            path = current(application, kind, sorted(research_root.glob(pattern)))
            return [path] if path else []
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            return []

    analyses = selected("posting_analysis", "*공고분석*.md")
    researches = selected("company_research", "*기업리서치*.md")
    if not analyses:
        errors.append("공고 분석 문서가 없습니다.")
    if not researches:
        errors.append("기업 리서치 문서가 없습니다.")

    company = str(identity.get("company") or application.name).strip()
    role = str(identity.get("role") or "").strip()
    for path in analyses:
        validate_document(
            path,
            company=company,
            keyword_groups=(
                ("주요 업무", "담당 업무", "수행 업무"),
                ("자격요건", "지원 자격", "지원 조건", "필수 요건"),
                ("전형", "첨부", "제출"),
                ("마감", "접수 기간", "모집 기간"),
            ),
            minimum_characters=220,
            minimum_headings=4,
            minimum_urls=1,
            role=role,
            errors=errors,
        )
    for path in researches:
        validate_document(
            path,
            company=company,
            keyword_groups=(
                ("사업", "서비스", "제품"),
                ("인재상", "핵심 가치", "조직 문화", "일하는 방식"),
                ("최근", "동향", "계획", "전환", "전략"),
                ("직무", "지원자", "지원 관점"),
                ("출처", "참고 자료"),
            ),
            minimum_characters=320,
            minimum_headings=5,
            minimum_urls=2,
            role=role,
            errors=errors,
        )

    source_files = sorted(
        path
        for path in research_root.iterdir()
        if path.is_file() and path.suffix.casefold() in SOURCE_SUFFIXES
    )
    if not source_files and analyses:
        warnings.append(
            "보관된 공고 원본 파일이 없습니다. 다운로드할 수 없는 공고라면 공고 분석의 원문 URL과 확인일을 유지하세요."
        )

    return {
        "status": "complete" if not errors else "partial",
        "errors": errors,
        "warnings": warnings,
        "artifacts": {
            "application_marker": str(marker.relative_to(application)) if marker.exists() else None,
            "posting_analyses": relative_names(analyses, application),
            "company_research": relative_names(researches, application),
            "source_files": relative_names(source_files, application),
        },
    }


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--application", required=True, type=Path)
    args = parser.parse_args()
    result = validate_research_stage(args.application)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Find essay style candidates that require explicit human review."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from count_essay_characters import extract_blocks


MIDDOT = "·"
ENGLISH_TOKEN = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_.+#/-]*(?![A-Za-z0-9_])")
CONNECTIVE_COMMA = re.compile(
    r"[가-힣A-Za-z0-9_)`]+(?:하고|했고|하며|했으며|지만|했지만|는데|했는데|면서|해서),"
)
SUMMARY = re.compile(r"^\[[^\[\]\n]+\]$")
DECLARATIVE_SUMMARY_ENDING = re.compile(r"[다요][.!?]?$")
SUMMARY_TERMINAL_PUNCTUATION = re.compile(r"[.!?]$")
OUTLINE_LINE = re.compile(r"(?m)^[ \t]*(?:[-*+][ \t]+|\d+[.)][ \t]+)")


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def location(content: str, offset: int) -> tuple[int, int]:
    line = content.count("\n", 0, offset) + 1
    last_newline = content.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def context_for(content: str, offset: int, length: int, radius: int = 28) -> str:
    start = max(0, offset - radius)
    end = min(len(content), offset + length + radius)
    return content[start:end].replace("\n", " ")


def occurrences(content: str, pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for match in pattern.finditer(content):
        line, column = location(content, match.start())
        results.append(
            {
                "value": match.group(0),
                "line": line,
                "column": column,
                "context": context_for(content, match.start(), len(match.group(0))),
            }
        )
    return results


def analyze_block(content: str, index: int, require_summary: bool) -> dict[str, Any]:
    middots: list[dict[str, Any]] = []
    for offset, character in enumerate(content):
        if character != MIDDOT:
            continue
        line, column = location(content, offset)
        middots.append(
            {
                "line": line,
                "column": column,
                "context": context_for(content, offset, 1),
            }
        )

    english = occurrences(content, ENGLISH_TOKEN)
    lines = content.splitlines()
    first_line = lines[0].strip() if lines else ""
    summary_ok = bool(SUMMARY.fullmatch(first_line)) if require_summary else None
    summary_text = first_line[1:-1].strip() if summary_ok else ""
    summary_declarative = (
        bool(DECLARATIVE_SUMMARY_ENDING.search(summary_text))
        if require_summary and summary_ok
        else None
    )
    summary_punctuated = (
        bool(SUMMARY_TERMINAL_PUNCTUATION.search(summary_text))
        if require_summary and summary_ok
        else None
    )
    outline_lines = occurrences(content, OUTLINE_LINE)
    if summary_ok:
        outline_lines = [item for item in outline_lines if item["line"] > 1]
    return {
        "block": index,
        "middots": middots,
        "english_candidates": english,
        "connective_commas": occurrences(content, CONNECTIVE_COMMA),
        "outline_lines": outline_lines,
        "summary": {
            "required": require_summary,
            "present": summary_ok,
            "first_line": first_line,
            "style": (
                "declarative"
                if summary_declarative
                else "punctuated"
                if summary_punctuated
                else "nominal"
                if summary_declarative is False
                else "missing"
                if require_summary
                else "unchecked"
            ),
        },
    }


def analyze(source: str, plain: bool = False, require_summary: bool = True) -> dict[str, Any]:
    blocks = extract_blocks(source, plain)
    if not blocks:
        raise ValueError("text 코드 블록이 없습니다. 파일 전체는 --plain을 사용하세요.")
    results = [
        analyze_block(content, index, require_summary)
        for index, content in enumerate(blocks, start=1)
    ]
    return {
        "mode": "plain" if plain else "text-blocks",
        "blocks": results,
        "totals": {
            "blocks": len(results),
            "middots": sum(len(item["middots"]) for item in results),
            "english_candidates": sum(
                len(item["english_candidates"]) for item in results
            ),
            "connective_commas": sum(
                len(item["connective_commas"]) for item in results
            ),
            "missing_summaries": sum(
                1 for item in results if item["summary"]["present"] is False
            ),
            "declarative_summaries": sum(
                1 for item in results if item["summary"]["style"] == "declarative"
            ),
            "punctuated_summaries": sum(
                1 for item in results if item["summary"]["style"] == "punctuated"
            ),
            "outline_lines": sum(len(item["outline_lines"]) for item in results),
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plain", action="store_true", help="파일 전체를 하나의 본문으로 검사")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="대괄호 핵심 요약 검사를 생략",
    )
    parser.add_argument("file", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = parse_args(argv)
    try:
        source = args.file.read_text(encoding="utf-8")
        result = analyze(source, args.plain, not args.no_summary)
    except (OSError, UnicodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result["file"] = str(args.file)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    totals = result["totals"]
    print(
        "blocks={blocks} middots={middots} english_candidates={english_candidates} "
        "connective_commas={connective_commas} missing_summaries={missing_summaries} "
        "declarative_summaries={declarative_summaries} "
        "punctuated_summaries={punctuated_summaries} outline_lines={outline_lines}".format(
            **totals
        )
    )
    for block in result["blocks"]:
        for name in ("middots", "english_candidates", "connective_commas", "outline_lines"):
            for item in block[name]:
                value = item.get("value", MIDDOT)
                print(
                    f"block {block['block']} {name} line {item['line']} "
                    f"column {item['column']}: {value} | {item['context']}"
                )
        if block["summary"]["present"] is False:
            print(
                f"block {block['block']} missing_summary: "
                f"{block['summary']['first_line']}"
            )
        elif block["summary"]["style"] == "declarative":
            print(
                f"block {block['block']} declarative_summary: "
                f"{block['summary']['first_line']}"
            )
        elif block["summary"]["style"] == "punctuated":
            print(
                f"block {block['block']} punctuated_summary: "
                f"{block['summary']['first_line']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

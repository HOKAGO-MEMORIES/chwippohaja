#!/usr/bin/env python3
"""Count characters in plain text or fenced text blocks of an essay file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TEXT_BLOCK = re.compile(
    r"^[ \t]*```text[^\r\n]*\r?\n(.*?)\r?\n[ \t]*```[ \t]*\r?$",
    re.MULTILINE | re.DOTALL,
)
ANSWER_BLOCK = re.compile(
    r"^[ \t]*```text(?P<meta>[^\r\n]*)\r?\n(?P<body>.*?)\r?\n[ \t]*```[ \t]*\r?$",
    re.MULTILINE | re.DOTALL,
)


def answer_blocks(source: str) -> list[dict[str, str | None]]:
    results = []
    for match in ANSWER_BLOCK.finditer(source):
        metadata = match['meta'].strip()
        identifier = None
        if metadata:
            tag = re.fullmatch(r"question=([^\s]+)", metadata)
            if not tag:
                raise ValueError("답변 블록은 ```text 또는 ```text question=문항ID 형식이어야 합니다.")
            identifier = tag[1]
        results.append({"id": identifier, "text": match['body']})
    return results


def measure(content: str, unit: str = "characters", whitespace: str = "include",
            line_endings: str = "lf") -> int:
    if unit not in {"characters", "utf8_bytes", "utf16_units"}:
        raise ValueError("지원하지 않는 글자 수 단위입니다.")
    if whitespace not in {"include", "exclude"} or line_endings not in {"lf", "crlf", "remove"}:
        raise ValueError("공백 또는 줄바꿈 계산 기준이 올바르지 않습니다.")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = content.replace("\n", {"lf": "\n", "crlf": "\r\n", "remove": ""}[line_endings])
    if whitespace == "exclude":
        content = re.sub(r"\s", "", content)
    if unit == "utf8_bytes":
        return len(content.encode("utf-8"))
    if unit == "utf16_units":
        return len(content.encode("utf-16-le")) // 2
    return len(content)


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def extract_blocks(source: str, plain: bool = False) -> list[str]:
    return [source] if plain else TEXT_BLOCK.findall(source)


def count_blocks(blocks: list[str]) -> list[dict[str, int]]:
    return [
        {
            "block": index,
            "characters": len(content),
            "bytes": len(content.encode("utf-8")),
            "lines": content.count("\n") + 1 if content else 0,
        }
        for index, content in enumerate(blocks, start=1)
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plain", action="store_true", help="파일 전체를 하나의 본문으로 계산")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument("--unit", choices=("characters", "utf8_bytes", "utf16_units"), default="characters")
    parser.add_argument("--whitespace", choices=("include", "exclude"), default="include")
    parser.add_argument("--line-endings", choices=("lf", "crlf", "remove"), default="lf")
    parser.add_argument("file", type=Path)
    return parser.parse_args(argv)


def result_for(path: Path, plain: bool) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    blocks = extract_blocks(source, plain)
    if not blocks:
        raise ValueError("text 코드 블록이 없습니다. 파일 전체는 --plain을 사용하세요.")
    return {
        "file": str(path),
        "mode": "plain" if plain else "text-blocks",
        "results": count_blocks(blocks),
    }


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = parse_args(argv)
    try:
        result = result_for(args.file, args.plain)
        blocks = extract_blocks(args.file.read_text(encoding="utf-8"), args.plain)
        for row, content in zip(result["results"], blocks):
            row["measured"] = measure(content, args.unit, args.whitespace, args.line_endings)
        result["counting"] = {"unit": args.unit, "whitespace": args.whitespace, "line_endings": args.line_endings}
    except (OSError, UnicodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["results"]:
            print(
                f"block {item['block']}: {item['characters']} characters, "
                f"{item['lines']} lines"
                f", measured={item['measured']} {args.unit}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

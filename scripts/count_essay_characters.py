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
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

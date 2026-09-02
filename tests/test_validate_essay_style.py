from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

SCRIPT = SCRIPT_DIRECTORY / "validate_essay_style.py"
SPEC = importlib.util.spec_from_file_location("validate_essay_style", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ValidateEssayStyleTest(unittest.TestCase):
    def test_finds_style_review_candidates_in_text_blocks(self) -> None:
        source = """```text
[검증 가능한 운영 범위]
Java·Spring으로 Read Model을 설계했고, OOM이 없음을 확인했습니다.
```\n"""

        result = validator.analyze(source)

        self.assertEqual(result["totals"]["middots"], 1)
        self.assertEqual(result["totals"]["english_candidates"], 5)
        self.assertEqual(result["totals"]["connective_commas"], 1)
        self.assertEqual(result["totals"]["missing_summaries"], 0)
        self.assertEqual(result["totals"]["declarative_summaries"], 0)
        self.assertEqual(result["totals"]["punctuated_summaries"], 0)
        self.assertEqual(result["totals"]["outline_lines"], 0)
        tokens = [
            item["value"] for item in result["blocks"][0]["english_candidates"]
        ]
        self.assertEqual(tokens, ["Java", "Spring", "Read", "Model", "OOM"])

    def test_reports_missing_summary(self) -> None:
        source = "```text\n바로 본문을 시작합니다.\n```\n"
        result = validator.analyze(source)
        self.assertEqual(result["totals"]["missing_summaries"], 1)

    def test_reports_declarative_summary(self) -> None:
        source = """```text
[운영 가능한 시스템을 만들었습니다]
본문은 서술식으로 작성했습니다.
```\n"""
        result = validator.analyze(source)
        self.assertEqual(result["totals"]["missing_summaries"], 0)
        self.assertEqual(result["totals"]["declarative_summaries"], 1)
        self.assertEqual(result["blocks"][0]["summary"]["style"], "declarative")

    def test_accepts_nominal_summary(self) -> None:
        source = """```text
[실패 원인을 분리한 통합 검증]
본문은 서술식으로 작성했습니다.
```\n"""
        result = validator.analyze(source)
        self.assertEqual(result["totals"]["declarative_summaries"], 0)
        self.assertEqual(result["blocks"][0]["summary"]["style"], "nominal")

    def test_reports_punctuation_on_nominal_summary(self) -> None:
        source = """```text
[실패 원인을 분리한 통합 검증.]
본문은 서술식으로 작성했습니다.
```\n"""
        result = validator.analyze(source)
        self.assertEqual(result["totals"]["punctuated_summaries"], 1)
        self.assertEqual(result["blocks"][0]["summary"]["style"], "punctuated")

    def test_reports_outline_lines_in_answer_body(self) -> None:
        source = """```text
[실패 원인을 분리한 통합 검증]
- 서버 자원을 확인했습니다.
1. 부하 발생기를 나눴습니다.
```\n"""
        result = validator.analyze(source)
        self.assertEqual(result["totals"]["outline_lines"], 2)
        self.assertEqual(len(result["blocks"][0]["outline_lines"]), 2)

    def test_plain_mode_can_skip_summary_check(self) -> None:
        result = validator.analyze(
            "공식 고유명사 Knowledge · Challenge · Courage",
            plain=True,
            require_summary=False,
        )
        self.assertEqual(result["totals"]["middots"], 2)
        self.assertEqual(result["totals"]["missing_summaries"], 0)
        self.assertEqual(result["totals"]["declarative_summaries"], 0)
        self.assertEqual(result["totals"]["punctuated_summaries"], 0)

    def test_cli_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "자소서.md"
            path.write_text("```text\n[요약]\nAPI를 검증했습니다.\n```\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--json", str(path)],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["totals"]["english_candidates"], 1)


if __name__ == "__main__":
    unittest.main()

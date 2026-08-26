from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "count_essay_characters.py"
SPEC = importlib.util.spec_from_file_location("count_essay_characters", SCRIPT)
assert SPEC and SPEC.loader
counter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(counter)


class CountEssayCharactersTest(unittest.TestCase):
    def test_extracts_and_counts_multiple_text_blocks(self) -> None:
        first = "안녕 세상\n둘째 줄"
        second = "ABC 123"
        source = f"제목\n\n```text\n{first}\n```\n\n```text\n{second}\n```\n"

        results = counter.count_blocks(counter.extract_blocks(source))

        self.assertEqual(results[0]["characters"], len(first))
        self.assertEqual(results[0]["bytes"], len(first.encode("utf-8")))
        self.assertEqual(results[0]["lines"], 2)
        self.assertEqual(results[1]["characters"], len(second))

    def test_plain_mode_counts_entire_file(self) -> None:
        source = "첫 줄\n둘째 줄\n"
        blocks = counter.extract_blocks(source, plain=True)
        self.assertEqual(counter.count_blocks(blocks)[0]["characters"], len(source))

    def test_cli_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "자소서.md"
            path.write_text("```text\n지원서 본문\n```\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--json", str(path)],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["mode"], "text-blocks")
            self.assertEqual(result["results"][0]["characters"], len("지원서 본문"))

    def test_cli_rejects_file_without_text_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "자소서.md"
            path.write_text("일반 본문\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("--plain", completed.stderr)


if __name__ == "__main__":
    unittest.main()

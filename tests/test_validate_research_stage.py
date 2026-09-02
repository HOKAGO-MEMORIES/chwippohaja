from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_research_stage.py"
SPEC = importlib.util.spec_from_file_location("validate_research_stage", SCRIPT)
assert SPEC and SPEC.loader
validate_research_stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_research_stage)


class ValidateResearchStageTest(unittest.TestCase):
    def application(self, temporary: str) -> Path:
        application = Path(temporary) / "예시전자"
        research = application / "01_공고_JD"
        research.mkdir(parents=True)
        (research / ".application.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "company": "예시전자",
                    "role": "백엔드",
                    "posting_key": "EXAMPLE-1",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return application

    def write_valid_documents(self, application: Path) -> None:
        research = application / "01_공고_JD"
        (research / "예시전자_백엔드_공고분석.md").write_text(
            """# 예시전자 백엔드 공고 분석

- 확인일: 2026-09-02
- 출처: https://example.com/jobs/1

## 주요 업무
API 개발

## 지원 자격
Java 경험

## 전형
서류와 면접
""",
            encoding="utf-8",
        )
        (research / "예시전자_기업리서치.md").write_text(
            """# 예시전자 기업 리서치

- 기준일: 2026-09-02

## 사업과 서비스
기업용 서비스를 운영한다.

## 지원자와 직무의 연결
백엔드 직무와의 연결을 검토한다.

## 출처
- https://example.com/company
""",
            encoding="utf-8",
        )

    def test_url_only_research_is_complete_with_source_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.application(temporary)
            self.write_valid_documents(application)

            result = validate_research_stage.validate_research_stage(application)

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["errors"], [])
            self.assertEqual(len(result["warnings"]), 1)

    def test_local_source_file_removes_source_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.application(temporary)
            self.write_valid_documents(application)
            (application / "01_공고_JD" / "공고원본.pdf").write_bytes(b"%PDF-test")

            result = validate_research_stage.validate_research_stage(application)

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["warnings"], [])

    def test_missing_research_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.application(temporary)
            self.write_valid_documents(application)
            (application / "01_공고_JD" / "예시전자_기업리서치.md").unlink()

            result = validate_research_stage.validate_research_stage(application)

            self.assertEqual(result["status"], "partial")
            self.assertIn("기업 리서치 문서가 없습니다.", result["errors"])

    def test_cli_returns_nonzero_for_incomplete_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.application(temporary)
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--application", str(application)],
                check=False,
                capture_output=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 1)
            self.assertEqual(json.loads(completed.stdout)["status"], "partial")


if __name__ == "__main__":
    unittest.main()

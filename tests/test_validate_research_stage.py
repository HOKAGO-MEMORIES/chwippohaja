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
백엔드 개발자는 기업 고객이 사용하는 주문 API와 내부 운영 도구를 개발합니다. 기존 서비스의 장애 원인을 분석하고 데이터 정합성을 유지하는 배치 작업도 맡습니다.

## 지원 자격
백엔드 직무는 Java와 관계형 데이터베이스를 이용한 서버 개발 경험을 요구합니다. HTTP API 설계, 테스트 코드 작성과 협업 도구 사용 경험도 확인합니다.

## 우대사항
운영 환경에서 로그와 지표를 바탕으로 문제를 해결했거나 배포 자동화를 구성한 경험을 우대합니다. 지원자가 담당한 범위와 검증 결과를 포트폴리오에서 확인합니다.

## 전형
서류 검토 뒤 실무 면접과 최종 면접을 진행합니다. 제출 자료에는 이력서와 포트폴리오가 포함됩니다.

## 마감
모집 마감은 2026-09-30 18:00이며 공식 채용 페이지 기준으로 확인했습니다.
""",
            encoding="utf-8",
        )
        (research / "예시전자_기업리서치.md").write_text(
            """# 예시전자 기업 리서치

- 기준일: 2026-09-02

## 사업과 서비스
예시전자는 기업 고객을 위한 업무 자동화 서비스를 운영합니다. 주문과 정산 데이터를 연결하고 관리자가 처리 상태를 확인할 수 있는 웹 제품을 제공합니다.

## 핵심 가치와 일하는 방식
공식 소개에서는 고객 문제를 수치로 확인하고 작은 개선을 반복하는 방식을 핵심 가치로 설명합니다. 백엔드 직무에서도 장애 원인과 영향 범위를 투명하게 공유하는 태도를 강조합니다.

## 최근 사업 동향
2026년에는 기존 온프레미스 제품의 클라우드 전환과 데이터 처리 구조 개선을 추진하고 있습니다. 신규 기능 확대보다 안정적인 이전과 운영 자동화를 우선한다는 계획을 밝혔습니다.

## 지원자와 직무의 연결
백엔드 직무는 Java 서버와 데이터베이스 운영 경험을 직접 활용할 수 있습니다. 다만 특정 산업의 대규모 상용 트래픽 경험은 확인되지 않았으므로 강한 접점으로 과장하지 않습니다.

## 추가 확인 사항
실제 배치 주기와 팀별 배포 권한은 공개 자료에서 확인되지 않아 면접 질문 후보로 남깁니다.

## 출처
- https://example.com/company
- https://example.com/news/cloud-2026
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

    def test_rejects_shallow_documents_with_only_keywords_and_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.application(temporary)
            research = application / "01_공고_JD"
            (research / "예시전자_백엔드_공고분석.md").write_text(
                "# 예시전자 백엔드\n## 주요 업무\nTBD\n## 지원 자격\n준비 중\n"
                "## 전형과 마감\n확인 불가 2026-09-02 https://example.com/jobs/1\n",
                encoding="utf-8",
            )
            (research / "예시전자_기업리서치.md").write_text(
                "# 예시전자\n## 사업\nTBD\n## 인재상\n준비 중\n## 최근 동향\n확인 불가\n"
                "## 백엔드 직무\n자료 없음\n## 출처\nhttps://example.com/company\n",
                encoding="utf-8",
            )

            result = validate_research_stage.validate_research_stage(application)

            self.assertEqual(result["status"], "partial")
            self.assertTrue(any("실질 내용이 부족" in item for item in result["errors"]))
            self.assertTrue(any("미확인 상태 문구가 반복" in item for item in result["errors"]))

    def test_accepts_role_with_only_separator_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.application(temporary)
            marker = application / "01_공고_JD" / ".application.json"
            identity = json.loads(marker.read_text(encoding="utf-8"))
            identity["role"] = "백엔드/개발"
            marker.write_text(json.dumps(identity, ensure_ascii=False), encoding="utf-8")
            self.write_valid_documents(application)

            result = validate_research_stage.validate_research_stage(application)

            self.assertEqual(result["status"], "complete", result["errors"])


if __name__ == "__main__":
    unittest.main()

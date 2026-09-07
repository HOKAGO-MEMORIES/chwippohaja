from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research_hook.py"
INSTALLER = ROOT / "scripts" / "install_research_hooks.py"
HOOK_ID = "chwippohaja-research-hook"


class ResearchHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".chwippohaja").mkdir()
        (self.root / ".chwippohaja" / "workspace.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "workspace_root": ".",
                    "active_season": "2026 하반기",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.season = self.root / "2026 하반기"
        self.season.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_script(
        self, *args: str, input_value: dict[str, object] | None = None
    ) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=json.dumps(input_value, ensure_ascii=False) if input_value else None,
            encoding="utf-8",
            capture_output=True,
            env=environment,
            check=False,
        )

    def create_application(self, name: str, complete: bool = True) -> Path:
        application = self.season / name
        research = application / "01_공고_JD"
        research.mkdir(parents=True)
        (research / ".application.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "company": name,
                    "role": "백엔드",
                    "posting_key": f"{name}-1",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if complete:
            (research / f"{name}_백엔드_공고분석.md").write_text(
                f"""# {name} 백엔드 공고 분석

- 확인일: 2026-09-06
- 출처: https://example.com/{name}/jobs/1

## 주요 업무
백엔드 개발자는 고객이 사용하는 주문 API와 내부 운영 도구를 개발합니다. 장애 원인을 분석하고 데이터 정합성을 유지하는 배치 작업도 담당합니다.

## 지원 자격
백엔드 직무는 Java와 관계형 데이터베이스를 이용한 서버 개발 경험을 요구합니다. HTTP API 설계와 테스트 코드 작성 경험도 확인합니다.

## 우대사항
운영 환경에서 로그와 지표를 바탕으로 문제를 해결했거나 배포 자동화를 구성한 경험을 우대합니다. 담당 범위와 검증 결과를 포트폴리오에서 확인합니다.

## 전형
서류 검토 뒤 실무 면접과 최종 면접을 진행합니다. 제출 자료에는 이력서와 포트폴리오가 포함됩니다.

## 마감
모집 마감은 2026-09-30 18:00이며 공식 채용 페이지 기준으로 확인했습니다.
""",
                encoding="utf-8",
            )
            (research / f"{name}_기업리서치.md").write_text(
                f"""# {name} 기업 리서치

- 기준일: 2026-09-06

## 사업과 서비스
{name}은 기업 고객을 위한 업무 자동화 서비스를 운영합니다. 주문과 정산 데이터를 연결하고 관리자가 처리 상태를 확인할 수 있는 웹 제품을 제공합니다.

## 핵심 가치와 일하는 방식
공식 소개에서는 고객 문제를 수치로 확인하고 작은 개선을 반복하는 방식을 핵심 가치로 설명합니다. 백엔드 직무에서도 장애 원인과 영향 범위를 투명하게 공유하는 태도를 강조합니다.

## 최근 사업 동향
2026년에는 기존 제품의 클라우드 전환과 데이터 처리 구조 개선을 추진하고 있습니다. 신규 기능 확대보다 안정적인 이전과 운영 자동화를 우선한다는 계획을 밝혔습니다.

## 지원자와 직무의 연결
백엔드 직무는 Java 서버와 데이터베이스 운영 경험을 직접 활용할 수 있습니다. 특정 산업의 대규모 상용 트래픽 경험은 확인되지 않았으므로 강한 접점으로 과장하지 않습니다.

## 추가 확인 사항
실제 배치 주기와 팀별 배포 권한은 공개 자료에서 확인되지 않아 면접 질문 후보로 남깁니다.

## 출처
- https://example.com/{name}/company
- https://example.com/{name}/news/cloud-2026
""",
                encoding="utf-8",
            )
        return application

    def start(self, *applications: Path) -> subprocess.CompletedProcess[str]:
        arguments = ["start", "--workspace", str(self.root), "--expected-total", str(len(applications))]
        for application in applications:
            arguments.extend(["--application", str(application)])
        return self.run_script(*arguments)

    def stop(self, message: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            "hook",
            input_value={
                "event": "Stop",
                "session_id": "session-a",
                "cwd": str(self.season),
                "last_assistant_message": message,
            },
        )

    def test_check_accepts_all_complete_targets(self) -> None:
        first = self.create_application("예시전자")
        second = self.create_application("예시소프트")
        self.assertEqual(self.start(first, second).returncode, 0)
        result = self.run_script("check", "--workspace", str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["counts"]["complete"], 2)

    def test_finish_marks_ready_but_stop_still_requires_multi_target_summary(self) -> None:
        first = self.create_application("예시전자")
        second = self.create_application("예시소프트")
        self.assertEqual(self.start(first, second).returncode, 0)

        finished = self.run_script("finish", "--workspace", str(self.root))
        self.assertEqual(finished.returncode, 0, finished.stderr)
        state_path = self.root / ".chwippohaja" / "runs" / "research-current.json"
        self.assertTrue(state_path.is_file())
        self.assertTrue(json.loads(state_path.read_text(encoding="utf-8"))["ready_to_report"])

        blocked = self.stop("두 기업 조사를 완료했습니다.")
        self.assertEqual(json.loads(blocked.stdout)["decision"], "block")

        accepted = self.stop(
            "전체 대상: 2\n완료: 2\n부분 완료: 0\n실패: 0\n미시도: 0"
        )
        self.assertEqual(json.loads(accepted.stdout), {})
        self.assertFalse(state_path.exists())

    def test_stop_requires_finish_for_complete_run(self) -> None:
        application = self.create_application("예시전자")
        self.assertEqual(self.start(application).returncode, 0)
        blocked = self.stop("공고 조사와 기업 리서치를 완료했습니다.")
        self.assertEqual(json.loads(blocked.stdout)["decision"], "block")
        self.assertIn("finish", json.loads(blocked.stdout)["reason"])

    def test_stop_blocks_unaccounted_target(self) -> None:
        complete = self.create_application("예시전자")
        missing = self.season / "미시도기업"
        self.assertEqual(self.start(complete, missing).returncode, 0)
        result = self.stop("작업을 마쳤습니다.")
        response = json.loads(result.stdout)
        self.assertEqual(response["decision"], "block")
        self.assertIn("검증되지 않았거나", response["reason"])

    def test_accounted_failure_requires_exact_summary_and_rejects_full_completion_claim(self) -> None:
        complete = self.create_application("예시전자")
        failed = self.season / "접근실패기업"
        self.assertEqual(self.start(complete, failed).returncode, 0)
        deferred = self.run_script(
            "defer",
            "--workspace",
            str(self.root),
            "--application",
            str(failed),
            "--status",
            "failed",
            "--reason",
            "공식 채용 페이지 접근 제한",
            "--attempt",
            "공식 URL과 채용 홈을 각각 확인했으나 접근 거부",
            "--attempt",
            "기업 공식 홈페이지의 채용 목록과 공고 번호를 교차 검색했으나 원문 없음",
        )
        self.assertEqual(deferred.returncode, 0, deferred.stderr)

        missing_summary = self.stop("한 곳은 완료했고 한 곳은 실패했습니다.")
        self.assertEqual(json.loads(missing_summary.stdout)["decision"], "block")

        false_claim = self.stop(
            "전체 대상: 2\n완료: 1\n부분 완료: 0\n실패: 1\n미시도: 0\n모두 완료했습니다."
        )
        self.assertEqual(json.loads(false_claim.stdout)["decision"], "block")

        accepted = self.stop(
            "전체 대상: 2\n완료: 1\n부분 완료: 0\n실패: 1\n미시도: 0\n"
            "예시전자는 완료했고 접근실패기업은 공식 페이지 접근 제한으로 실패했습니다."
        )
        self.assertEqual(json.loads(accepted.stdout), {})
        self.assertFalse((self.root / ".chwippohaja" / "runs" / "research-current.json").exists())
        self.assertTrue((self.root / ".chwippohaja" / "runs" / "research-last.json").is_file())

    def test_waiting_user_keeps_active_state_after_valid_partial_report(self) -> None:
        complete = self.create_application("예시전자")
        waiting = self.season / "직무확인기업"
        self.assertEqual(self.start(complete, waiting).returncode, 0)
        deferred = self.run_script(
            "defer",
            "--workspace",
            str(self.root),
            "--application",
            str(waiting),
            "--status",
            "waiting_user",
            "--reason",
            "지원 직무가 두 개라 대상 확인 필요",
            "--question",
            "백엔드와 데이터 중 어느 직무를 조사할까요?",
        )
        self.assertEqual(deferred.returncode, 0, deferred.stderr)
        accepted = self.stop(
            "전체 대상: 2\n완료: 1\n부분 완료: 1\n실패: 0\n미시도: 0\n"
            "나머지 한 곳은 지원 직무 확인이 필요합니다."
        )
        self.assertEqual(json.loads(accepted.stdout), {})
        self.assertTrue((self.root / ".chwippohaja" / "runs" / "research-current.json").is_file())

    def test_defer_rejects_one_search_failure(self) -> None:
        failed = self.season / "접근실패기업"
        self.assertEqual(self.start(failed).returncode, 0)
        result = self.run_script(
            "defer",
            "--workspace",
            str(self.root),
            "--application",
            str(failed),
            "--status",
            "failed",
            "--reason",
            "공식 채용 페이지에서 공고 원문을 찾지 못했습니다.",
            "--attempt",
            "검색 결과 한 번 확인",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("두 개 이상", result.stderr)

    def test_start_does_not_replace_active_run(self) -> None:
        first = self.create_application("예시전자")
        second = self.create_application("예시소프트")
        self.assertEqual(self.start(first).returncode, 0)
        result = self.start(second)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("이미 활성", result.stderr)

        state = json.loads(
            (self.root / ".chwippohaja" / "runs" / "research-current.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["targets"][0]["application"], "2026 하반기/예시전자")

    def test_post_tool_use_blocks_assembled_shallow_documents(self) -> None:
        application = self.create_application("얕은기업", complete=False)
        research = application / "01_공고_JD"
        (research / "얕은기업_공고분석.md").write_text(
            "# 얕은기업 백엔드\n## 주요 업무\nTBD\n## 지원 자격\n준비 중\n"
            "## 전형과 마감\n확인 불가 2026-09-06 https://example.com/job\n",
            encoding="utf-8",
        )
        target = research / "얕은기업_기업리서치.md"
        target.write_text(
            "# 얕은기업\n## 사업\nTBD\n## 인재상\n준비 중\n## 최근 동향\n확인 불가\n"
            "## 백엔드 직무\n자료 없음\n## 출처\nhttps://example.com/company\n",
            encoding="utf-8",
        )
        self.assertEqual(self.start(application).returncode, 0)
        # A decoded Windows path becomes doubled backslashes in serialized JSON.
        # Exercise both formats on every OS, not only on Windows CI.
        for target_path in (target.as_posix(), target.as_posix().replace("/", "\\")):
            with self.subTest(path=target_path):
                result = self.run_script(
                    "hook",
                    input_value={
                        "event": "PostToolUse",
                        "session_id": "session-a",
                        "cwd": str(self.season),
                        "tool_input": {"path": target_path},
                    },
                )
                response = json.loads(result.stdout)
                self.assertEqual(response["decision"], "block")
                self.assertIn("완료 기준", response["reason"])

    def test_expected_total_must_match_fixed_target_list(self) -> None:
        application = self.create_application("예시전자")
        result = self.run_script(
            "start",
            "--workspace",
            str(self.root),
            "--application",
            str(application),
            "--expected-total",
            "2",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("개수와 같아야", result.stderr)

    def test_installer_preserves_essay_hook_and_is_idempotent(self) -> None:
        config = self.season / ".codex" / "hooks.json"
        config.parent.mkdir()
        config.write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 essay_hook.py hook --hook-id chwippohaja-essay-hook",
                                    }
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for _ in range(2):
            result = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    str(self.root),
                    "--project-root",
                    str(self.season),
                ],
                encoding="utf-8",
                capture_output=True,
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        loaded = json.loads(config.read_text(encoding="utf-8"))
        commands = [
            hook["command"]
            for group in loaded["hooks"]["Stop"]
            for hook in group["hooks"]
        ]
        self.assertTrue(any("chwippohaja-essay-hook" in item for item in commands))
        self.assertEqual(sum(HOOK_ID in item for item in commands), 1)


if __name__ == "__main__":
    unittest.main()

# 자소서 훅

자소서 작성 지침을 읽었다는 선언만으로 작업이 끝나지 않도록 Codex의 `PostToolUse`와 `Stop` 훅을 사용한다. 훅은 의미 판단을 대신하지 않는다. 작성자가 남긴 문항별 판정과 근거가 기계 판독 가능한지, 실제 저장본이 그 판정과 등록한 형식 및 분량 조건을 충족하는지를 종료 직전에 다시 확인한다.

## 설치 범위

훅은 전역 설정이 아니라 Codex에서 실제로 연 취업 프로젝트의 `.codex/hooks.json`에 설치한다. 따라서 다른 프로젝트에는 영향을 주지 않는다. 기존 훅 설정은 보존하고 `chwippohaja-essay-hook` 항목만 추가하거나 갱신한다.

```bash
python scripts/install_essay_hooks.py "/path/to/job-workspace"
```

Codex에서 연 프로젝트가 워크스페이스의 활성 시즌처럼 하위 폴더라면 그 경로를 함께 지정한다.

```bash
python scripts/install_essay_hooks.py "/path/to/job-workspace" \
  --project-root "/path/to/job-workspace/2026 하반기"
```

설치 후 Codex에서 해당 프로젝트를 신뢰하고 `/hooks` 화면에서 새 프로젝트 훅을 검토해 활성화한다. 훅 설정을 바꾼 뒤에는 새 Codex 작업에서 다시 시작하는 편이 안전하다.

Windows에서는 같은 스크립트를 `py -3`으로 실행할 수 있다. 생성되는 설정에는 macOS 및 Linux용 `python3` 명령과 Windows용 `py -3` 명령이 함께 들어간다.

## 실행 상태 시작

자소서 작업을 시작하면 작성 설계 파일, 앞으로 저장할 자소서 파일과 문항별 글자 수를 등록한다. 파일은 아직 없어도 되지만 둘 다 기업별 `02_작성중` 아래의 Markdown 경로여야 한다.

```bash
python scripts/essay_hook.py start \
  --workspace "/path/to/job-workspace" \
  --plan "2026 하반기/회사/02_작성중/01_자소서_작성설계.md" \
  --draft "2026 하반기/회사/02_작성중/02_자소서_초안.md" \
  --limit "1:1200:1500" \
  --limit "2:1200:1500"
```

`--limit`은 `문항ID:최소:최대` 형식이다. 기본값은 공백 포함 문자 수이며, 기업별 형식이나 계산 기준이 다르면 [문항별 규칙](essay-rules.md)에 따라 `--rules "규칙 JSON"`을 함께 전달한다. 기업이 최소 글자 수를 정하지 않았다면 최소값을 `0`으로 둔다. 모든 문항을 등록하되 부분 초안에서 `deferred`인 문항은 실제 `text` 답변 블록 수에 포함하지 않는다.

실행 상태는 `.chwippohaja/runs/essay-current.json`에 저장한다. 세션 ID는 첫 훅 호출 때 자동으로 결합되며 다른 Codex 작업의 훅 호출에는 반응하지 않는다. 활성 실행이 있으면 다른 대상의 `start`는 거절한다. 같은 경로와 조건의 재호출은 기존 상태를 보존한다. 새 버전과 작업 전환은 아래 명시적인 명령을 사용한다.

작성 설계의 `pre_draft` 체크포인트를 먼저 만든 뒤 별도 쓰기에서 훅이 통과 결과를 확인하게 한다. 훅 호출이 없는 도구로 작성했다면 다음 명령을 직접 실행한다.

```bash
python scripts/essay_hook.py plan-check --workspace "/path/to/job-workspace"
```

설계와 답변 본문을 한 번의 파일 쓰기로 함께 만들면 차단된다. 작성 설계를 먼저 검사한 기록이 있고 그 파일이 이후 바뀌지 않았을 때만 자소서 본문을 유효하게 검사한다.

## 검사 동작

`PostToolUse`는 작성 설계나 자소서 대상 파일을 편집한 경우에만 검사한다. 다른 지원 파일을 편집한 경우에는 통과한다. 실패한 쓰기를 되돌리지는 않지만 오류를 모델에 돌려주어 같은 작업에서 수정과 재검사를 계속하게 한다.

`Stop`은 활성 자소서 작업이 있으면 항상 다음을 검사한다.

- 작성 설계의 `pre_draft` 체크포인트
- 답변 본문보다 먼저 작성 설계가 통과했다는 기록과 설계 파일 해시
- 자소서의 `draft_review` 체크포인트
- 등록한 전체 문항 ID와 두 체크포인트의 문항 ID가 중복 없이 정확히 일치함
- 두 체크포인트의 schema_version 일치, 문항 순서 일치와 태그가 있는 답변 블록의 ID 대응
- 버전 2의 작성 설명·정보 선택·독해 검토 기록, 미해결 독해 이슈와 수정 이력 연결
- `valid` 문항 수와 실제 `text` 답변 블록 수 일치
- 등록한 문항별 소제목과 본문 형식
- 등록한 계산 기준에 따른 문항별 최소 및 최대 분량
- 저장 가능한 `valid_draft`, `partial_draft` 또는 `final_candidate` 상태

다음 명령으로 훅을 기다리지 않고 같은 검사를 실행할 수 있다.

```bash
python scripts/essay_hook.py check --workspace "/path/to/job-workspace"
```

검사가 실패하면 그 결과를 완료 산출물로 보고하지 않는다. 현재 자료로 고칠 수 있으면 같은 버전의 임시 내용을 수정하고 다시 검사한다. 새 버전 파일은 유효한 초안이나 사용자가 채택한 수정본을 보존할 때 만든다.

## 사용자 입력 대기

문항에 맞는 경험이나 확인된 사실이 없어 사용자의 답변이 필요하면 종료를 무한히 막지 않는다. 보류 이유와 실제 확인 질문을 상태에 기록한 뒤 정상 대기한다.

```bash
python scripts/essay_hook.py wait \
  --workspace "/path/to/job-workspace" \
  --reason "문항에서 요구한 의견 조율 경험이 확인되지 않음" \
  --question "의견 차이가 있었고 본인이 조율한 경험을 알려주세요."
```

사용자가 답하면 다음 명령으로 재개한다.

```bash
python scripts/essay_hook.py resume --workspace "/path/to/job-workspace"
```

`waiting_user`는 완료 상태가 아니다. 최종 보고에는 작성 완료 수, 보류 문항과 필요한 입력을 구분하고, 유효한 답변이 있으면 `부분초안`으로만 보존한다.

## 실행 종료

검사 중인 작성본이 모든 기계 검사를 통과하면 실행 기록을 `essay-history`에 보관하고 활성 상태를 제거한다. 사용자 채택본은 별도로 `application_state.py select --kind essay`로 기록하며 자동 채택하지 않는다.

```bash
python scripts/essay_hook.py finish --workspace "/path/to/job-workspace"
```

`finish`도 전체 검사를 다시 수행하며 실패하면 상태 파일을 보존한다. 상태를 확인하려면 다음 명령을 사용한다.

```bash
python scripts/essay_hook.py status --workspace "/path/to/job-workspace"
```

## 버전 전환과 작업 재개

같은 회사의 다음 버전은 기존 실행을 보관하고 새 경로를 지정한다. 기존 조건과 같은 경우에도 전체 문항 제한과 규칙 파일을 전달한다.

```bash
python scripts/essay_hook.py advance --workspace "워크스페이스" \
  --plan "시즌/회사/02_작성중/03_설계.md" \
  --draft "시즌/회사/02_작성중/04_답변.md" --limit "1:0:1500"
```

새 버전은 작성 설계 검증부터 다시 시작한다. 다른 지원 건에는 `advance`를 사용할 수 없다. 다른 회사 작업으로 옮기거나 현재 버전의 등록 조건을 고쳐야 하면 먼저 실행 상태를 보존한다.

```bash
python scripts/essay_hook.py suspend --workspace "워크스페이스"
```

반환된 `run_id`를 기록한다. 기존 작성 파일과 실행 상태는 보존되며 완료로 처리하지 않는다. 다른 실행이 활성 상태가 아닐 때 보관한 작업을 재개할 수 있다.

```bash
python scripts/essay_hook.py resume --workspace "워크스페이스" --run-id "반환된 실행 ID" --rebind
```

`--rebind`는 새 Codex 작업에서 기존 실행을 명시적으로 인계할 때만 사용한다. 같은 작업의 사용자 응답 후에는 일반 `resume`을 사용한다. 워크스페이스당 하나의 자소서 실행을 활성화하는 방식이며 여러 작업의 동시 편집을 조정하는 시스템은 아니다.

## 한계

훅은 체크포인트의 참과 거짓을 스스로 판단할 수 없다. 문항과 소재가 실제로 어울리는지, 성찰이 사건에서 자연스럽게 도출되는지와 사용자가 채택한 표현을 지켰는지는 반드시 의미 검토로 판정한다. 훅은 그 의미 검토를 건너뛴 채 파일 존재나 글자 수만으로 완료를 선언하는 일을 막는 보조 장치다.

프로젝트 훅은 사용자의 신뢰와 검토를 거쳐 실행되는 로컬 명령이다. 비밀이나 개인 자료를 출력하지 않고 워크스페이스 내부의 등록된 두 Markdown 파일과 실행 상태만 읽고 쓴다.

# 자소서 훅

자소서 작성 지침을 읽었다는 선언만으로 작업이 끝나지 않도록 Codex의 `PostToolUse`와 `Stop` 훅을 사용한다. 훅은 의미 판단을 대신하지 않는다. 작성자가 남긴 문항별 판정과 근거가 기계 판독 가능한지, 실제 저장본이 그 판정과 구조 및 글자 수 조건을 충족하는지를 종료 직전에 다시 확인한다.

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

`--limit`은 `문항ID:최소:최대` 형식이며 공백 포함 기준이다. 기업이 최소 글자 수를 정하지 않았다면 최소값을 `0`으로 둔다. 모든 문항을 등록하되 부분 초안에서 `deferred`인 문항은 실제 `text` 답변 블록 수에 포함하지 않는다.

실행 상태는 `.chwippohaja/runs/essay-current.json`에 저장한다. 세션 ID는 첫 훅 호출 때 자동으로 결합되며 다른 Codex 작업의 훅 호출에는 반응하지 않는다. 새 자소서 버전을 만들 때는 `start`를 다시 실행해 새 대상 파일로 바꾼다.

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
- 두 체크포인트의 문항 ID와 순서 일치
- `valid` 문항 수와 실제 `text` 답변 블록 수 일치
- 각 답변 첫 줄의 명사형 대괄호 요약
- 기업이 별도 형식을 요구하지 않은 본문의 서술식 구조
- 문항별 최소 및 최대 글자 수
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

최신 작성본이 모든 기계 검사를 통과한 뒤에만 실행 상태를 제거한다.

```bash
python scripts/essay_hook.py finish --workspace "/path/to/job-workspace"
```

`finish`도 전체 검사를 다시 수행하며 실패하면 상태 파일을 보존한다. 상태를 확인하려면 다음 명령을 사용한다.

```bash
python scripts/essay_hook.py status --workspace "/path/to/job-workspace"
```

## 한계

훅은 체크포인트의 참과 거짓을 스스로 판단할 수 없다. 문항과 소재가 실제로 어울리는지, 성찰이 사건에서 자연스럽게 도출되는지와 사용자가 채택한 표현을 지켰는지는 반드시 의미 검토로 판정한다. 훅은 그 의미 검토를 건너뛴 채 파일 존재나 글자 수만으로 완료를 선언하는 일을 막는 보조 장치다.

프로젝트 훅은 사용자의 신뢰와 검토를 거쳐 실행되는 로컬 명령이다. 비밀이나 개인 자료를 출력하지 않고 워크스페이스 내부의 등록된 두 Markdown 파일과 실행 상태만 읽고 쓴다.

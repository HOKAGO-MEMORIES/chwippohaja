# 공고 조사 훅

공고 분석과 기업 리서치가 파일 이름만 갖춘 얕은 문서로 끝나거나, 여러 대상 중 일부를 누락하고 전체 완료로 보고하는 일을 Codex의 `PostToolUse`와 `Stop` 훅으로 막는다. 훅은 검색이나 사실 판단을 대신하지 않는다. 조사 대상을 고정하고 각 지원 건의 로컬 산출물, 미완료 사유와 최종 집계를 다시 검사하는 실행 장치다.

## 설치 범위

훅은 Codex에서 실제로 연 취업 프로젝트의 `.codex/hooks.json`에만 설치한다. 기존 훅은 보존하고 `chwippohaja-research-hook` 항목만 추가하거나 갱신한다.

```bash
python scripts/install_research_hooks.py "/path/to/job-workspace"
```

Codex 프로젝트가 활성 시즌 같은 하위 폴더라면 해당 경로를 함께 지정한다.

```bash
python scripts/install_research_hooks.py "/path/to/job-workspace" \
  --project-root "/path/to/job-workspace/2026 하반기"
```

설치 후 프로젝트를 신뢰하고 Codex의 `/hooks` 화면에서 설정을 검토해 활성화한다. 설정을 바꾼 뒤에는 새 Codex 작업에서 시작하는 편이 안전하다. 생성되는 설정에는 macOS 및 Linux용 `python3` 명령과 Windows용 `py -3` 명령이 함께 들어간다.

## 조사 대상 고정

공고 조사를 시작하기 전에 이번 실행의 지원 건 폴더를 모두 등록한다. 한 건을 조사할 때도 등록한다.

```bash
python scripts/research_hook.py start \
  --workspace "/path/to/job-workspace" \
  --application "2026 하반기/회사A" \
  --application "2026 하반기/회사B" \
  --expected-total 2
```

Drive나 Notion 반영까지 요청받았으면 `--require-service google_drive` 또는 `--require-service notion`을 추가한다. 요청되지 않은 연결은 넣지 않는다. 기본값은 로컬 산출물 검증이며, 외부 반영을 요구한 실행은 실제 재조회 후 `application_state.py sync` 기록까지 일치해야 완료된다.

`--expected-total`은 등록한 `--application` 수와 정확히 같아야 한다. 지원 건은 워크스페이스의 활성 시즌 아래에 있어야 하며 실행 중 대상 목록을 바꿀 수 없다. 활성 실행이 이미 있으면 새 `start`로 덮어쓰지 않는다.

`현재 공고 전부`나 `오늘 추가된 공고`처럼 탐색 자체가 열린 요청은 [공고와 연결 서비스](posting-and-connectors.md)의 전수 범위와 집계 기준으로 후보 탐색을 먼저 끝낸다. 사이트, 필터, 페이지 범위와 원본 수를 확정한 뒤 최종 조사 대상을 훅에 등록한다. 이 훅은 등록 전의 검색 범위가 사이트 전체였는지 스스로 증명하지 못한다.

## 검사 동작

`PostToolUse`는 등록된 기업 폴더 안의 공고 분석이나 기업 리서치 파일을 편집한 경우에만 검사한다. 두 문서가 모두 생겼는데 다음 기준을 통과하지 못하면 같은 작업에서 수정하도록 차단한다.

- 기업명, 지원 직무와 확인일 또는 기준일
- 공고 분석의 주요 업무, 지원 자격, 전형 또는 제출 조건과 마감
- 기업 리서치의 사업 또는 서비스, 가치 또는 일하는 방식, 최근 동향, 지원자와 직무의 연결 및 출처
- 공고 분석의 출처 URL 한 개 이상과 실질 내용 220자 이상
- 기업 리서치의 서로 다른 출처 URL 두 개 이상과 실질 내용 320자 이상
- 형식적인 제목이나 반복 `TBD`만으로 채운 문서가 아님

직무의 공백, 슬래시와 가운데점 같은 구분자 차이는 허용한다. 관리 직무와 공식 세부 직무가 실제로 다르면 분석 문서에 둘 다 기록한다.

`Stop`은 활성 공고 조사 실행에 대해 다음을 확인한다.

- 등록한 모든 대상이 `완료`, `부분 완료`, `실패` 또는 `미시도` 중 하나로 집계됨
- 완료 대상은 기업별 로컬 검사기가 `complete`이며 요청에 포함한 외부 서비스의 현재 파일 반영도 확인됨
- 미완료 대상을 목록에서 빼거나 다른 대상으로 교체하지 않음
- 여러 대상이거나 미완료 대상이 있을 때 최종 보고의 전체 수와 상태별 수가 실제 검사 결과와 일치함
- 미완료 상태에서 `전체 완료`, `모두 반영` 또는 `누락 없음`이라고 주장하지 않음

다음 명령으로 훅 호출을 기다리지 않고 전체 대상을 검사할 수 있다.

```bash
python scripts/research_hook.py check --workspace "/path/to/job-workspace"
```

## 부분 완료와 실패

접근 제한이나 원문 부재로 완료할 수 없는 대상은 조용히 제외하지 않는다. 실제 상태와 시도를 기록한다.

```bash
python scripts/research_hook.py defer \
  --workspace "/path/to/job-workspace" \
  --application "2026 하반기/회사B" \
  --status failed \
  --reason "공식 채용 페이지가 종료되어 직무 원문을 확인할 수 없음" \
  --attempt "기업 공식 채용 목록과 공고 번호를 확인했으나 원문 없음" \
  --attempt "공식 홈페이지와 제공된 첨부 파일에서 동일 공고를 교차 검색했으나 찾지 못함"
```

`partial`과 `failed`에는 서로 다른 실제 조사 시도 두 개 이상이 필요하다. 검색 결과 한 번만 확인한 뒤 실패로 끝낼 수 없다. `not_attempted`는 이번 실행에서 시작하지 못한 대상에만 쓴다. 사유는 원인과 남은 범위를 알 수 있도록 구체적으로 적는다.

지원 직무나 대상 공고를 사용자가 결정해야 하면 다음처럼 대기한다.

```bash
python scripts/research_hook.py defer \
  --workspace "/path/to/job-workspace" \
  --application "2026 하반기/회사B" \
  --status waiting_user \
  --reason "서로 다른 두 직무가 한 공고에 있어 조사 대상을 결정할 수 없음" \
  --question "백엔드와 데이터 직무 중 어느 지원서를 기준으로 조사할까요?"
```

사용자 답변이나 연결 복구로 보류 사유가 해결되면 해당 대상만 다시 활성화한다. 새 Codex 작업으로 인계할 때는 `--rebind`를 추가한다.

```bash
python scripts/research_hook.py resume \
  --workspace "/path/to/job-workspace" \
  --application "2026 하반기/회사B"
```

## 종료와 보고

모든 대상이 로컬 검사와 요청된 외부 반영 조건을 통과했는지 먼저 확인한다. `partial` 또는 `waiting_user`로 보류한 대상은 파일이 완성돼도 자동 완료로 바뀌지 않는다. 사유를 해결한 뒤 해당 대상에 `resume`을 실행해 재검사한다.

```bash
python scripts/research_hook.py finish --workspace "/path/to/job-workspace"
```

`finish`는 성공해도 실행 상태를 바로 지우지 않고 최종 보고 가능 상태로 표시한다. 여러 대상의 최종 집계 보고를 `Stop` 훅이 확인한 뒤에만 실행 상태를 보관하고 닫는다. 현재 상태는 다음 명령으로 확인한다.

```bash
python scripts/research_hook.py status --workspace "/path/to/job-workspace"
```

여러 대상을 처리했거나 미완료 대상이 있으면 최종 보고에 다음 다섯 줄을 실제 값과 함께 포함한다.

```text
전체 대상: 4
완료: 2
부분 완료: 1
실패: 1
미시도: 0
```

그 아래에 대상별 산출물, 실패 사유와 남은 확인 항목을 적는다. `waiting_user`는 집계상 부분 완료이며 실행 상태를 유지한다.

## 한계

훅은 URL에 적힌 내용이 사실인지, 출처가 충분히 권위 있는지, 기업과 지원자의 접점 해석이 타당한지를 스스로 판단하지 못한다. 공식 원문 대조와 의미 검토는 반드시 별도로 수행한다. 최소 글자 수와 제목 수는 얕은 문서의 완료 선언을 막는 하한선이지 조사 품질의 충분조건이 아니다.

프로젝트 훅은 사용자의 신뢰와 검토를 거쳐 실행되는 로컬 명령이다. 인증 정보와 개인 자료를 출력하지 않고 등록된 기업 폴더와 `.chwippohaja/runs`의 실행 상태만 읽고 쓴다.

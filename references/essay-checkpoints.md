# 자소서 체크포인트

자소서 작성 설계와 초안의 상태를 말로만 선언하지 않도록 기계 판독 가능한 체크포인트를 사용한다. 의미의 타당성을 자동 판정하는 도구가 아니라, 문항별 판정과 근거를 빠뜨린 채 다음 단계로 넘어가는 일을 차단하는 도구다.

## 공통 형식

작성 설계 또는 초안의 검토 기록에 다음 블록을 정확히 하나 둔다.

````markdown
<!-- chwippohaja:essay-checkpoint:start -->
```json
{
  "schema_version": 1,
  "phase": "pre_draft",
  "document_status": "ready_full",
  "questions": []
}
```
<!-- chwippohaja:essay-checkpoint:end -->
````

JSON의 설명을 대신하는 자연어 작성 설계와 검토 근거도 문서에 함께 남긴다. JSON 값만 채우고 실제 근거를 생략하지 않는다.

## 초안 전 체크포인트

`phase`는 `pre_draft`다. 문항별 객체에는 다음 필드를 기록한다.

```json
{
  "id": "1",
  "question_type": "학습",
  "subquestions": ["문항의 필수 하위 질문"],
  "experience_question": true,
  "reflection_required": false,
  "material_fit": "direct",
  "material_fit_reason": "부족했던 지식과 이를 익혀 적용한 과정이 직접 드러난다.",
  "evidence": ["확인된 사실과 출처"],
  "missing_information": [],
  "follow_up_questions": [],
  "action": "write"
}
```

- `question_type`: 문항의 핵심 동사를 기준으로 정한 유형이다. 예를 들어 학습, 원칙, 소통, 개선, 지원동기처럼 기록한다.
- `material_fit`: `direct`, `conditional_resolved`, `unsuitable`, `missing`
- `material_fit_reason`: 기술명이나 주제의 유사성이 아니라 해당 경험의 실제 행동이 문항 유형을 어떻게 증명하는지 적는다.
- `action`: `write`, `defer`
- `write`: 소재가 직접 적합하거나 조건부 적합이 확인된 보조 근거로 해소됐고, 직접 근거가 있으며 미확정 정보가 없을 때만 사용한다.
- `defer`: 소재가 부적합하거나 필요한 경험이 없을 때 사용한다. 필요한 정보와 사용자 질문을 모두 기록한다.
- `reflection_required`: 문항이 배움, 느낀 점, 판단 변화나 경험의 의미를 직접 요구하는지 나타낸다.
- `experience_question`: 최종 후보에서 구체적인 경험의 의미를 확인해야 하는 문항인지 나타낸다.

문서 상태는 질문별 행동에서 결정한다.

- 모두 `write`: `ready_full`
- `write`와 `defer`가 함께 있음: `ready_partial`
- 모두 `defer`: `blocked`

다음 명령이 성공하기 전에는 답변 본문을 작성하지 않는다.

```bash
python scripts/validate_essay_checkpoint.py 작성설계.md
```

## 초안 검토 체크포인트

초안 본문을 임시로 만든 뒤 내용 검토와 표현 검토를 수행하고 `phase`가 `draft_review`인 블록을 기록한다.

작성한 문항의 예시는 다음과 같다.

```json
{
  "id": "1",
  "answer_status": "valid",
  "answer_present": true,
  "experience_question": true,
  "reflection_required": false,
  "fatal_issues": [],
  "recommended_issues": [],
  "missing_information": [],
  "follow_up_questions": [],
  "content_checks": {
    "all_subquestions_answered": true,
    "question_type_fit_verified": true,
    "facts_verified": true,
    "role_verified": true,
    "material_fit_verified": true,
    "judgment_action_result_connected": true,
    "reader_effect_clear": true,
    "reflection_requirement_met": null,
    "experience_meaning_present": true
  }
}
```

보류한 문항에는 답변을 만들지 않는다.

```json
{
  "id": "2",
  "answer_status": "deferred",
  "answer_present": false,
  "experience_question": true,
  "reflection_required": true,
  "fatal_issues": [],
  "recommended_issues": [],
  "missing_information": ["의견 차이를 조율한 실제 경험"],
  "follow_up_questions": ["의견 차이가 있었고 본인이 조율한 경험을 알려주세요."]
}
```

문서 수준에는 표현과 글자 수 검토 상태를 함께 기록한다.

`content_checks`의 판단 기준은 다음과 같다.

- `question_type_fit_verified`: 문항의 핵심 동사와 소재에서 실제로 드러나는 행동이 일치한다.
- `material_fit_verified`: 키워드가 아니라 확인된 판단, 행동과 결과로 소재 적합성을 검토했다.
- `judgment_action_result_connected`: 본인의 판단이 행동으로 이어지고 결과와의 인과관계가 성립한다.
- `reader_effect_clear`: 구현 세부를 모두 알지 못해도 문제와 실제 전후 변화를 이해할 수 있다.
- `reflection_requirement_met`: 문항이 직접 요구한 배움이나 느낀 점에 답했다.
- `experience_meaning_present`: 사건에서 도출된 구체적인 이해가 드러난다.

```json
"style_review": {
  "validator_run": true,
  "structural_passed": true,
  "candidates_reviewed": true,
  "character_count_checked": true
}
```

저장하는 모든 초안과 수정본에는 버전별 수정 기록도 넣는다. 첫 버전은 `previous_version`을 `null`로 두고, 이후 버전은 실제 이전 파일명을 기록한다.

```json
"revision": {
  "previous_version": null,
  "purpose": "문항에 맞는 첫 유효 초안 작성",
  "issue_ids": [],
  "changes": ["확인된 소재로 첫 답변 작성"],
  "resolved_issues": [],
  "remaining_issues": [],
  "remaining_fatal_issues": [],
  "character_count_impact": "첫 버전 850자",
  "all_identified_issues_reviewed": true
}
```

`changes`에는 문구 교체 목록만 쓰지 않고 판단, 정보 또는 구조가 실제로 어떻게 달라졌는지 적는다. 검토에서 발견한 전체 이슈를 확인하기 전에는 `all_identified_issues_reviewed`를 `true`로 두지 않는다. 우선순위가 높은 몇 건만 고친 채 남은 필수 문제를 생략해서는 안 되며, 미해결 치명 이슈가 하나라도 있으면 저장 가능한 초안으로 통과하지 않는다.

문서 상태는 다음과 같다.

- 모든 문항이 `valid`: `valid_draft`
- `valid`와 `deferred`가 함께 있음: `partial_draft`
- 하나라도 `needs_revision`: `needs_revision`
- 모두 `deferred`: `blocked`
- 모든 문항이 `valid`이고 최종 표현과 제출 형식까지 검증함: `final_candidate`

`needs_revision`은 저장할 결과가 아니라 자동 수정과 재검사의 입력이다. 오류를 수정할 수 없고 새로운 사용자 사실이 필요하면 해당 문항을 `deferred`로 바꾸고 이유와 질문을 기록한다. `needs_revision`과 모든 문항이 보류된 `blocked`는 검사 실패로 반환한다.

초안 검토 블록도 같은 명령으로 검사한다.

```bash
python scripts/validate_essay_checkpoint.py 자소서.md
```

종료 코드가 0이 아니면 문서 상태를 완료로 보고하거나 다음 단계로 넘어가지 않는다.

일부 문항만 보류된 `partial_draft`는 통과할 수 있다. 이때는 유효한 답변만 본문에 싣고 보류 문항에는 답변을 만들지 않는다. 문항별 완료와 보류 수, 필요한 경험 조건과 사용자 질문을 기록해 번호가 붙은 `부분초안`으로 저장한다. 사용자 답변을 받은 다음에는 이전 파일을 덮어쓰지 않고 다음 번호의 새 버전에서 전체 문항을 다시 검사한다.

## 근거 연결

새 작성 설계는 문서 수준에 `evidence_mapping_required: true`를 둔다. 각 write 문항에는 하위 질문별 `evidence_map`을 작성한다.

```json
"evidence_map": [
  {
    "subquestion": "문항의 필수 하위 질문 원문",
    "source": "공통자료/경력_프로젝트_소재.md#F1",
    "claim": "해당 원본에서 사용자에게 확인된 행동과 결과"
  }
]
```

작성본의 valid 문항에는 `answer_evidence`를 추가한다.

```json
"answer_evidence": [
  {
    "source": "공통자료/경력_프로젝트_소재.md#F1",
    "quote": "실제 답변 본문에 들어 있는 핵심 주장 구절"
  }
]
```

검사기는 모든 하위 질문에 출처와 확인된 주장이 연결됐는지 확인한다. 자소서 훅은 답변의 source가 작성 설계에 등록됐는지, quote가 실제 답변 본문에 존재하는지도 확인한다. source는 실제로 읽은 사실 원본의 위치 또는 사실 ID여야 한다. 이 검사는 출처 문서의 진위나 인용의 의미를 자동으로 판정하지 않는다.

기존 체크포인트에 evidence_mapping_required가 없으면 기존 형식으로 검사한다. 새 작성 설계와 주요 수정에서 근거 연결을 추가하며, 이전 파일을 일괄 수정하지 않는다.

## 판정의 한계

검사기는 소재가 실제로 적합한지, 성찰이 자연스러운지와 문장이 좋은지를 판단하지 않는다. 다음 항목은 반드시 원문과 대조해 사람이 읽는 의미 검토로 판정한다.

- 문항과 소재의 직접적인 연결
- 문항의 핵심 동사와 소재에서 실제로 드러나는 행동의 일치
- 본인의 판단과 팀의 결과 구분
- 사건에서 도출된 구체적인 이해
- 사용자가 채택한 문안과 수정 이력
- 기업과 직무 연결의 사실성

검사 통과는 판정 기록의 형식이 완성됐다는 뜻이다. 거짓 판정이나 빈약한 근거를 정당화하지 않는다.

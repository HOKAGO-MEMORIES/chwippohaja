# 자소서 체크포인트

자소서 작성 설계와 초안의 상태를 말로만 선언하지 않도록 기계 판독 가능한 체크포인트를 사용한다. 의미의 타당성을 자동 판정하는 도구가 아니라, 문항별 판정과 근거를 빠뜨린 채 다음 단계로 넘어가는 일을 차단하는 도구다.

## 공통 형식

작성 설계 또는 초안의 검토 기록에 다음 블록을 정확히 하나 둔다.

````markdown
<!-- chwippohaja:essay-checkpoint:start -->
```json
{
  "schema_version": 2,
  "evidence_mapping_required": true,
  "phase": "pre_draft",
  "document_status": "ready_full",
  "questions": []
}
```
<!-- chwippohaja:essay-checkpoint:end -->
````

자연어 판단 결론은 아래 writing_brief와 reader_review에 짧게 기록한다. 같은 설명을 별도 장문으로 반복하거나 내부 문답 전체를 저장하지 않는다. 체크포인트는 제출 본문에 포함하지 않는다.

## 버전과 실행 환경

새 설계와 주요 수정본은 `schema_version: 2`를 사용한다. 기존 버전 1 파일은 호환 검사를 유지하며 일괄 수정하지 않는다. 새 버전으로 수정할 때는 설계와 답변을 모두 버전 2로 검토한다. 훅은 두 문서의 스키마가 다르면 거절한다. 훅 실행 상태 파일의 버전은 별개이며 변경하지 않는다.

버전 2에서는 작성 설계의 `evidence_mapping_required: true`, write 문항의 `writing_brief`와 `detail_selection`, valid 답변의 `reader_review`와 `answer_evidence`를 필수로 검사한다. 이전 템플릿을 사용했더라도 새 문서에서는 이 항목을 추가한다. 과거 버전 1 통과 결과를 새 독해 검토 통과로 보고하지 않는다.

스크립트 실행이 불가능한 환경에서는 같은 기준을 수동 대조하고 본문을 제공한다. 자동 검사·계산 미실행 항목을 명시하고 `validator_run` 등 실행 사실을 임의로 true로 바꾸지 않는다. 수동 내용 검토와 기계 검사 통과는 서로 다른 결과다.

## 짧은 작성 설명과 독해 검토

write 문항에는 다음 형태를 사용한다. 예시는 가상 사실이며 실제 문서에는 확인된 자료로 바꾼다. 상세 판단 기준은 [주장과 문맥](essay-composition.md)의 짧은 설명, 정보 선택과 본문만으로 연결 검토를 따른다.

```json
"writing_brief": {
  "direct_answer": "글 수정 때 반복하던 전체 프로그램 배포를 없앴다.",
  "context": "내용만 바뀌어도 전체 프로그램을 다시 배포해야 했다.",
  "judgment_action": "내용과 프로그램의 변경을 나누어 처리하도록 구성했다.",
  "outcome": "글 수정은 내용 갱신만으로 반영할 수 있게 됐다."
},
"detail_selection": [
  "반복 작업의 전후 변화를 남긴다. 개선 문항의 직접 성과이기 때문이다.",
  "단일 갱신 시간은 뺀다. 이전 시간과 비교되지 않아 속도 개선을 증명하지 못한다."
]
```

`direct_answer`는 모든 write 문항에 필요하다. 경험형(`experience_question: true`)에는 `context`, `judgment_action`, `outcome`도 필요하다. 경험형이 아닌 가치관·포부 문항에는 불필요한 과거 사건을 만들지 않고 나머지 필드를 생략할 수 있다. 개인 기준·기업 근거·계획은 해당 하위 질문별 evidence_map으로 구분한다. 보류 문항에는 완성된 설명을 강제하지 않는다.

valid 답변에는 다음처럼 본문에서 읽히는 내용과 문항 적합성 근거를 기록한다. summary의 필수 필드는 writing_brief와 같다. 요약만 가능하다고 통과시키지 않는다. 행동의 목적과 앞의 문제에 답하는 결과가 본문에 연결되는지 확인한다. 설계의 의도로 빠진 맥락을 메우지 않는다.

```json
"reader_review": {
  "summary": {
    "direct_answer": "글 갱신에 필요했던 전체 배포 작업을 제거했다.",
    "context": "글 하나를 고쳐도 프로그램 전체를 다시 배포해야 했다.",
    "judgment_action": "지원자가 내용 갱신과 프로그램 배포를 분리했다.",
    "outcome": "내용만 고칠 때 전체 프로그램을 다시 배포할 필요가 없어졌다."
  },
  "question_fit": "개선 문항에 대해 이전의 불편, 본인의 변경과 제거된 작업을 설명한다.",
  "issues": [
    {
      "id": "R1",
      "quote": "갱신에 38초가 걸렸습니다.",
      "problem": "이전 소요 시간이 없어 개선 효과를 알 수 없다.",
      "status": "resolved",
      "resolution": "수치를 덜어내고 없어진 배포 작업을 명시했다. 수정 본문에서 전후 작업 차이를 확인했다."
    }
  ]
}
```

issues는 핵심 답·본인 기여·인과관계의 이해를 막는 실제 문제만 담는다. 없는 이슈를 만들지 않으며 발견되지 않으면 빈 배열로 둔다. `quote`에는 문제가 있었던 실제 본문 구절을 남긴다. 해결된 구절은 수정 전 인용이므로 최신 본문에 그대로 남을 필요는 없다. `resolution`에는 실제 변경과 다시 읽은 결과를 기록하고 revision의 `issue_ids`, `resolved_issues`에 같은 ID를 연결한다. 미해결은 `status: open`으로 남기고 해당 문항을 needs_revision으로 처리한다. open이 남은 valid 답변은 거절된다. 취향 수준의 변경은 기존 recommended_issues와 수정 기록에서 처리한다.

이 검사는 설명·검토 기록이 비어 있거나 서로 모순되는 상태를 거절한다. 문장이 존재한다는 이유만으로 그 설명의 사실성이나 설득력을 자동 인정하지 않는다.

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

스크립트 실행이 가능한 환경에서는 다음 명령이 성공한 뒤 답변 본문을 작성한다.

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

검사기를 실행했으나 종료 코드가 0이 아니면 오류를 고치기 전 기계 검사 완료로 보고하지 않는다. 실행 불가 환경의 수동 검토는 위 예외를 따른다.

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

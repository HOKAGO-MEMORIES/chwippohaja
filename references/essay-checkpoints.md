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
  "subquestions": ["문항의 필수 하위 질문"],
  "experience_question": true,
  "reflection_required": false,
  "material_fit": "direct",
  "evidence": ["확인된 사실과 출처"],
  "missing_information": [],
  "follow_up_questions": [],
  "action": "write"
}
```

- `material_fit`: `direct`, `conditional_resolved`, `unsuitable`, `missing`
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
    "facts_verified": true,
    "role_verified": true,
    "material_fit_verified": true,
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

```json
"style_review": {
  "validator_run": true,
  "structural_passed": true,
  "candidates_reviewed": true,
  "character_count_checked": true
}
```

문서 상태는 다음과 같다.

- 모든 문항이 `valid`: `valid_draft`
- `valid`와 `deferred`가 함께 있음: `partial_draft`
- 하나라도 `needs_revision`: `needs_revision`
- 모두 `deferred`: `blocked`
- 모든 문항이 `valid`이고 최종 표현과 제출 형식까지 검증함: `final_candidate`

`needs_revision`은 저장할 결과가 아니라 자동 수정과 재검사의 입력이다. 오류를 수정할 수 없고 새로운 사용자 사실이 필요하면 해당 문항을 `deferred`로 바꾸고 이유와 질문을 기록한다.

초안 검토 블록도 같은 명령으로 검사한다.

```bash
python scripts/validate_essay_checkpoint.py 자소서.md
```

종료 코드가 0이 아니면 문서 상태를 완료로 보고하거나 다음 단계로 넘어가지 않는다.

## 판정의 한계

검사기는 소재가 실제로 적합한지, 성찰이 자연스러운지와 문장이 좋은지를 판단하지 않는다. 다음 항목은 반드시 원문과 대조해 사람이 읽는 의미 검토로 판정한다.

- 문항과 소재의 직접적인 연결
- 본인의 판단과 팀의 결과 구분
- 사건에서 도출된 구체적인 이해
- 사용자가 채택한 문안과 수정 이력
- 기업과 직무 연결의 사실성

검사 통과는 판정 기록의 형식이 완성됐다는 뜻이다. 거짓 판정이나 빈약한 근거를 정당화하지 않는다.

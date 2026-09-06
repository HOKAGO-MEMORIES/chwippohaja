# 문항별 형식과 계산 규칙

기업 또는 사용자가 기본 자소서 형식과 다른 요구를 했을 때 읽는다. 사실, 문항 충실도와 역할 검증은 생략할 수 없다. 여기서 조정하는 것은 실제 제출 형식과 계산 방법이다.

## 기본값과 예외

기본값은 명사형 대괄호 요약, 서술식 본문, 공백 포함 문자 수와 LF 줄바꿈이다. 기업이나 사용자가 소제목을 금지하거나 목록 답변을 요구하면 그 요구를 따른다.

지원 건의 `01_공고_JD/자소서_규칙.json`에 문항 ID를 키로 기록한다. 기본값을 그대로 쓰는 문항은 생략할 수 있다. 기본값과 다른 규칙에는 공식 안내의 URL·문서 위치 또는 사용자의 명시적 요구를 `source`로 기록한다.

```json
{
  "1": {
    "summary": "forbidden",
    "body": "prose",
    "unit": "utf8_bytes",
    "whitespace": "include",
    "line_endings": "lf",
    "source": "공식 문항 안내: 소제목 금지, UTF-8 바이트 기준"
  },
  "2": {
    "summary": "optional",
    "body": "list",
    "source": "사용자가 제공한 문항 원문에서 목록 형식 요구"
  }
}
```

| 필드 | 기본값 | 가능한 값 |
| --- | --- | --- |
| summary | required | required, optional, forbidden |
| body | prose | prose, list, any |
| unit | characters | characters, utf8_bytes, utf16_units |
| whitespace | include | include, exclude |
| line_endings | lf | lf, crlf, remove |

`exclude`는 공백과 탭 및 줄바꿈을 포함한 모든 공백 문자를 제외한다. 줄바꿈만 제외하는 사이트는 `whitespace: include`, `line_endings: remove`로 지정한다. UTF-16 단위와 UTF-8 바이트는 문자 수와 다르다. 기업이 말한 바이트의 인코딩이나 계산 방식을 확인하지 못했으면 추측해 지정하지 않는다. 지원 화면과 계산 결과를 대조하고 미확인 조건은 남긴다.

## 동일 규칙으로 검사

훅의 `start`와 `advance`에 `--rules "규칙 파일"`을 전달한다. 파일 내용은 실행 상태에 복사되므로 실행 중 규칙 파일만 바꿔 기존 검증 기준을 조용히 변경하지 않는다. 같은 버전의 규칙을 수정해야 하면 실행을 보존해 중단한 뒤 새 실행을 시작하고 전체 검사를 다시 수행한다.

표현 검사에도 같은 파일을 사용한다.

```bash
python scripts/validate_essay_style.py --strict --rules "자소서_규칙.json" "자소서_작성본.md"
```

이 명령은 `draft_review`의 문항과 답변 블록을 대응시켜 기업별 형식을 검사하고, 영어와 가운데점 등의 검토 후보도 JSON으로 반환한다. `--plain`, `--no-summary`와 혼용하지 않는다. 기본 형식이면 기존 `--strict` 명령을 그대로 사용할 수 있다.

단독 계산 예시:

```bash
python scripts/count_essay_characters.py --json --unit utf8_bytes --line-endings lf "자소서.md"
```

`characters`와 `bytes`는 원래 값이고 `measured`가 선택한 규칙의 계산 결과다. 훅도 `measured`를 등록한 최소·최대값과 비교한다. 요약과 실제 입력할 소제목은 답변 블록에 포함해 계산한다.

## 답변과 문항 연결

새 문서는 여는 코드 펜스에 문항 ID를 넣는다.

````markdown
```text question=1
[핵심 요약 문구]
확인된 근거로 작성한 답변 본문
```
````

등록 문항, 작성 설계와 검토 기록은 정확히 같은 ID를 포함해야 한다. 보류 문항도 등록하되 본문은 만들지 않는다. ID를 붙인 답변 블록은 순서가 바뀌어도 해당 문항의 조건으로 검사한다. ID 중복, 미등록 문항과 태그가 없는 블록의 혼용은 실패한다.

기존의 ID 없는 `text` 블록은 `valid` 문항 순서로 읽는 호환 모드를 유지한다. 새 버전부터 ID를 붙여 모호함을 없앤다. 문항의 실제 원문과 ID가 맞는지는 원문을 대조한다.

## 기계 판정의 한계

명백한 정중형 서술 종결은 구조 오류로 찾지만 한 글자만으로 명사형 여부를 단정하지 않는다. `수요`, `필요`처럼 요로 끝나는 명사는 허용한다. 애매한 종결, 자연스러운 소제목과 본문의 문장 완결성은 의미 검토에서 판정한다. 영어와 가운데점 후보는 금지 목록이 아니며 문맥별 유지 또는 수정 근거를 남긴다.

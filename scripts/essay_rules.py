"""Question-specific submission format and counting rules, without network I/O."""

import json
from pathlib import Path
from typing import Any

from count_essay_characters import answer_blocks, count_blocks, measure
from validate_essay_style import analyze, SUMMARY


DEFAULT = {"summary": "required", "body": "prose", "unit": "characters",
           "whitespace": "include", "line_endings": "lf"}
CHOICES = {"summary": {"required", "optional", "forbidden"},
           "body": {"prose", "list", "any"},
           "unit": {"characters", "utf8_bytes", "utf16_units"},
           "whitespace": {"include", "exclude"},
           "line_endings": {"lf", "crlf", "remove"}}


def validate_rules(rules: Any, identifiers: list[str]) -> dict[str, Any]:
    if not isinstance(rules, dict) or set(rules) - set(identifiers):
        raise ValueError("형식 규칙은 등록된 문항 ID만 사용하는 객체여야 합니다.")
    for identifier, rule in rules.items():
        if not isinstance(rule, dict) or set(rule) - (set(DEFAULT) | {"source"}):
            raise ValueError(f"{identifier}: 알 수 없는 형식 규칙입니다.")
        for key, options in CHOICES.items():
            if key in rule and (not isinstance(rule[key], str) or rule[key] not in options):
                raise ValueError(f"{identifier}: {key} 규칙이 올바르지 않습니다.")
        if any(rule.get(key, default) != default for key, default in DEFAULT.items()):
            if not isinstance(rule.get("source"), str) or not rule["source"].strip():
                raise ValueError(f"{identifier}: 기본값과 다른 규칙에는 기업 안내 또는 사용자 요청의 출처가 필요합니다.")
    return rules


def load_rules(path: Path | None, identifiers: list[str]) -> dict[str, Any]:
    return validate_rules(json.loads(path.read_text(encoding="utf-8")) if path else {}, identifiers)


def check_answers(source: str, questions: list[dict], limits: list[dict],
                  rules: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    blocks = answer_blocks(source)
    valid = [q for q in questions if q.get("answer_status") == "valid"]
    if not blocks:
        errors.append("자소서: text 코드 블록이 없습니다.")
    if len(blocks) != len(valid):
        errors.append(f"valid 답변 {len(valid)}개와 실제 답변 블록 {len(blocks)}개가 다릅니다.")
    tagged = any(b["id"] is not None for b in blocks)
    if tagged:
        ids = [b["id"] for b in blocks]
        if None in ids or len(ids) != len(set(ids)) or set(ids) != {q["id"] for q in valid}:
            errors.append("답변 블록 ID는 모든 valid 문항 ID와 중복 없이 정확히 일치해야 합니다.")
        mapped = {b["id"]: b["text"] for b in blocks}
    else:
        mapped = {q["id"]: b["text"] for q, b in zip(valid, blocks)}
    limits_by_id = {item["id"]: item for item in limits}
    validate_rules(rules, list(limits_by_id))
    counts = []
    style_blocks = []
    totals: dict[str, int] = {}
    for question in valid:
        identifier = question["id"]
        if identifier not in mapped or identifier not in limits_by_id:
            continue
        body = mapped[identifier]
        rule = {**DEFAULT, **rules.get(identifier, {})}
        style = analyze(body, plain=True, require_summary=rule["summary"] == "required")
        style_blocks.append({**style["blocks"][0], "id": identifier})
        for key, value in style["totals"].items():
            totals[key] = totals.get(key, 0) + value
        structural = dict(style["totals"])
        if rule["body"] != "prose":
            structural["outline_lines"] = 0
        if any(structural[key] for key in ("missing_summaries", "declarative_summaries",
                                           "punctuated_summaries", "outline_lines")):
            errors.append(f"자소서 {identifier}번: 대괄호 요약 또는 서술식 본문 구조 검사를 통과하지 못했습니다 "
                          f"(요약 누락 {structural['missing_summaries']}, 서술형 요약 {structural['declarative_summaries']}, "
                          f"문장부호 요약 {structural['punctuated_summaries']}, 개조식 행 {structural['outline_lines']}).")
        if rule["summary"] == "forbidden" and any(SUMMARY.fullmatch(line.strip()) for line in body.splitlines()):
            errors.append(f"자소서 {identifier}번: 기업 또는 사용자가 금지한 대괄호 소제목이 있습니다.")
        if rule["body"] == "list" and not style["totals"]["outline_lines"]:
            errors.append(f"자소서 {identifier}번: 요구된 목록 형식이 없습니다.")
        measured = measure(body, rule["unit"], rule["whitespace"], rule["line_endings"])
        row = count_blocks([body])[0]
        row.update({"block": len(counts) + 1, "id": identifier, "measured": measured,
                    "unit": rule["unit"], "whitespace": rule["whitespace"], "line_endings": rule["line_endings"]})
        counts.append(row)
        limit = limits_by_id[identifier]
        if measured < limit["min"]:
            errors.append(f"자소서 {identifier}번: {measured} {rule['unit']}로 최소 {limit['min']}보다 짧습니다.")
        if limit["max"] is not None and measured > limit["max"]:
            errors.append(f"자소서 {identifier}번: {measured} {rule['unit']}로 최대 {limit['max']}를 초과했습니다.")
    return {"errors": errors, "counts": counts, "style_totals": totals,
            "style_blocks": style_blocks, "answers": mapped}

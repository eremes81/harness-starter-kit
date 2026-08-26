#!/usr/bin/env python3
# ============================================================================
#  decision_graph_to_mermaid.py — 결정 기록(정형 데이터) → Mermaid graph 변환
# ----------------------------------------------------------------------------
#  책 7장 '심화(선택): 정형 데이터는 스크립트로 처리하기' 절의 전체 실행본.
#
#  왜:
#    - 입력이 이미 정형 데이터(필드가 고정된 표·카드)라면 AI를 부를 이유가 없다.
#      정해진 규칙대로 값을 읽어 변환하는 작은 스크립트가 더 빠르고 예측 가능하다.
#    - 변환은 두 단계로 끝난다: 노드 선언 → 엣지. 입력에 없는 노드는
#      출력에 절대 등장하지 않는다. (환각이 원천적으로 불가능)
#    - 단, '입력이 정말 정형인가'는 변환 코드가 보증하지 못한다. 그래서 변환 전에
#      입력 스키마 검사가 문지기를 선다. 스키마가 어긋나면 변환하지 않고
#      명확한 오류로 멈춘다. (정해진 로직대로 '잘못된 결과'를 내는 사고 방지)
#
#  입력(JSON 배열 — 결정 1건 = 객체 1개):
#    [
#      {"id": "D2026_Q3_001",
#       "title": "주간 회고는 금요일 오후에 고정",
#       "relations": [{"type": "supersedes", "target": "D2026_Q2_004"}]},
#      ...
#    ]
#    - id       : 결정 ID. 공백 없는 토큰(한글·영문·숫자·_·.·-)만. 중복 금지.
#    - title    : 결정 제목 한 줄. 따옴표(")가 있어도 된다 — 변환기가 escape한다.
#    - relations: 관계 목록(선택). type = 관계 이름(공백 없는 단어 권장),
#                 target = 상대 결정의 id. 입력 안에 실제로 있는 id만 허용.
#
#  사용법:
#    python decision_graph_to_mermaid.py decisions.json              # stdout으로 출력
#    python decision_graph_to_mermaid.py decisions.json --out 그래프.mmd
#    python decision_graph_to_mermaid.py - < decisions.json          # stdin 입력
#
#  의존성: 파이썬 표준 라이브러리만.
# ============================================================================
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# ----------------------------------------------------------------------------
# 입력 스키마 — 이 스크립트가 아는 '정형'의 전부. 여기서 벗어나면 변환하지 않는다.
# ----------------------------------------------------------------------------
KNOWN_DECISION_KEYS = {"id", "title", "relations"}
KNOWN_RELATION_KEYS = {"type", "target"}
_ID_OK = re.compile(r"^[\w.\-]+$")  # 한글·영문·숫자·_·.·- 만. 공백·괄호·따옴표 금지.


@dataclass
class Relation:
    type: str
    target: str


@dataclass
class Decision:
    id: str
    title: str
    relations: list[Relation] = field(default_factory=list)


def escape_label(text: str) -> str:
    """Mermaid 노드 라벨용 따옴표 escape. `"`를 그대로 넣으면 ["..."] 문법이 깨진다."""
    return text.replace('"', "#quot;")


def validate(records) -> tuple[list[str], list[str]]:
    """입력 스키마 검사. (errors, warnings)를 돌려준다. errors가 있으면 변환 금지."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(records, list):
        return ([f"최상위가 배열이 아닙니다({type(records).__name__}). "
                 "결정 기록은 JSON 배열이어야 합니다."], warnings)
    if not records:
        warnings.append("결정이 0건입니다. 빈 그래프(graph LR 한 줄)가 출력됩니다.")

    ids: set[str] = set()
    for i, rec in enumerate(records):
        where = f"레코드 #{i + 1}"
        if not isinstance(rec, dict):
            errors.append(f"{where}: 객체가 아닙니다({type(rec).__name__}).")
            continue
        # 스키마가 바뀌었는지 알리는 경고 — 모르는 필드는 조용히 무시하지 않는다.
        unknown = set(rec) - KNOWN_DECISION_KEYS
        if unknown:
            warnings.append(f"{where}: 스키마 밖 필드 {sorted(unknown)} — "
                            "입력 스키마가 바뀌었는지 확인하세요. (이번 변환에서는 무시)")
        for key in ("id", "title"):
            v = rec.get(key)
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{where}: 필수 필드 '{key}'가 없거나 비었습니다.")
        rid = rec.get("id")
        if isinstance(rid, str) and rid.strip():
            if not _ID_OK.match(rid):
                errors.append(f"{where}: id '{rid}'에 Mermaid에서 깨지는 문자"
                              "(공백·따옴표·괄호 등)가 있습니다.")
            elif rid in ids:
                errors.append(f"{where}: id '{rid}' 중복. 결정 ID는 유일해야 합니다.")
            else:
                ids.add(rid)
        title = rec.get("title")
        if isinstance(title, str) and "\n" in title:
            errors.append(f"{where}: title에 줄바꿈이 있습니다. 한 줄 제목만 허용합니다.")
        rels = rec.get("relations", [])
        if not isinstance(rels, list):
            errors.append(f"{where}: relations는 배열이어야 합니다.")
            continue
        for j, rel in enumerate(rels):
            rwhere = f"{where} relations #{j + 1}"
            if not isinstance(rel, dict):
                errors.append(f"{rwhere}: 객체가 아닙니다({type(rel).__name__}).")
                continue
            unknown_r = set(rel) - KNOWN_RELATION_KEYS
            if unknown_r:
                warnings.append(f"{rwhere}: 스키마 밖 필드 {sorted(unknown_r)} — "
                                "입력 스키마가 바뀌었는지 확인하세요. (이번 변환에서는 무시)")
            for key in ("type", "target"):
                v = rel.get(key)
                if not isinstance(v, str) or not v.strip():
                    errors.append(f"{rwhere}: 필수 필드 '{key}'가 없거나 비었습니다.")
            rtype = rel.get("type")
            if isinstance(rtype, str) and rtype.strip():
                if "|" in rtype or "\n" in rtype:
                    errors.append(f"{rwhere}: type '{rtype}'에 '|'나 줄바꿈이 있습니다. "
                                  "엣지 라벨 문법이 깨집니다.")
                elif re.search(r"\s", rtype):
                    warnings.append(f"{rwhere}: type '{rtype}'에 공백이 있습니다 — "
                                    "일부 구버전 렌더러가 공백 들어간 엣지 라벨에서 깨집니다. "
                                    "공백 없는 단어 하나를 권장합니다.")

    # target은 id를 전부 모은 뒤 2차로 검사한다 — 입력에 없는 노드를 차단하는 검사.
    for i, rec in enumerate(records):
        if not isinstance(rec, dict) or not isinstance(rec.get("relations", []), list):
            continue
        for j, rel in enumerate(rec.get("relations", [])):
            if not isinstance(rel, dict):
                continue
            tgt = rel.get("target")
            if isinstance(tgt, str) and tgt.strip() and tgt not in ids:
                errors.append(f"레코드 #{i + 1} relations #{j + 1}: target '{tgt}'는 "
                              "입력에 없는 id입니다. 입력에 없는 노드는 출력에 넣지 않습니다.")
    return errors, warnings


def load_decisions(records) -> list[Decision]:
    """검증을 통과한 레코드를 Decision 객체로. 제목의 따옴표는 여기서 escape한다."""
    return [
        Decision(
            id=rec["id"],
            title=escape_label(rec["title"]),
            relations=[Relation(type=r["type"], target=r["target"])
                       for r in rec.get("relations", [])],
        )
        for rec in records
    ]


# 결정 기록(정형 데이터) -> Mermaid graph 변환. AI 불필요, 결정론적.
def to_mermaid(decisions):
    lines = ["graph LR"]
    # 1) 노드 선언: id와 제목을 그대로. 지어내지 않는다.
    for d in decisions:
        lines.append(f'    {d.id}["{d.title}"]')
    # 2) 엣지: 관계 타입을 화살표 라벨로.
    for d in decisions:
        for rel in d.relations:
            lines.append(f'    {d.id} -->|{rel.type}| {rel.target}')
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="decision_graph_to_mermaid",
        description="결정 기록(JSON) → Mermaid graph 변환 (AI 불필요·결정론적, 표준 라이브러리만)")
    p.add_argument("input", help="결정 기록 JSON 파일 경로 ('-'면 stdin)")
    p.add_argument("--out", default="", help="Mermaid 텍스트를 저장할 파일 (생략하면 stdout)")
    args = p.parse_args(argv)

    # 1) 읽기
    try:
        if args.input == "-":
            raw = sys.stdin.read().lstrip("﻿")  # BOM 제거
        else:
            raw = Path(args.input).read_text(encoding="utf-8-sig")
    except OSError as e:
        sys.stderr.write(f"[!] 입력을 읽지 못했습니다: {e}\n")
        return 2

    # 2) JSON 파싱
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[!] JSON이 아닙니다: {e}\n")
        sys.stderr.write("    정형 데이터 변환기는 입력이 스키마대로일 때만 동작합니다.\n")
        return 2

    # 3) 입력 스키마 검사 — 어긋나면 변환하지 않는다
    errors, warnings = validate(records)
    for w in warnings:
        sys.stderr.write(f"[~] {w}\n")
    if errors:
        for e in errors:
            sys.stderr.write(f"[!] {e}\n")
        sys.stderr.write(f"[!] 스키마 검사 실패 {len(errors)}건 — 변환하지 않았습니다. "
                         "'입력이 정말 정형인가'부터 확인하세요.\n")
        return 2

    # 4) 변환 (두 단계: 노드 선언 → 엣지)
    text = to_mermaid(load_decisions(records))

    # 5) 출력 — 파일 쓰기는 --out을 명시한 경우만
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        n_edges = sum(len(r.get("relations", [])) for r in records)
        print(f"[OK] Mermaid 저장: {args.out}  (노드 {len(records)}·엣지 {n_edges})")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

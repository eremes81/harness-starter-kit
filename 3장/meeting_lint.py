#!/usr/bin/env python3
# ============================================================================
#  meeting_lint.py  —  회의록 양식 검사기 (커밋 전 훅용)
# ----------------------------------------------------------------------------
#  책 3장 「회의록 양식을 자동으로 검사하기」 절의 전체 실행본.
#
#  왜:
#    - "## 결정" 섹션이 없거나 결정이 줄글 한 문단에 섞여 있으면
#      파서(decision_parser.py)가 안정적으로 뽑아내기 어렵다.
#    - 양식을 권고로만 두면 바쁜 날 슬그머니 건너뛰게 되고,
#      한 번 건너뛴 양식은 다음 주에도 무너지기 쉽다.
#    → 커밋 전 훅에 걸어 강제한다. 양식을 어기면 커밋 자체가 막힌다.
#
#  검사 3종:
#    ① 꼬리표(frontmatter) — 필수 항목 4개 + category 허용값
#    ② 필수 섹션 — ## 안건 / ## 결정 / ## 액션 아이템 / ## 다음 회의
#    ③ 결정 슬롯 — "- D1: …"처럼 D번호 형식으로 채워져 있는가
#
#  사용법:
#    python meeting_lint.py meetings/2026-06-08_planning.md
#      통과 → "[OK] frontmatter 4/4, 섹션 4/4, 결정 슬롯 1건 감지. 커밋 허용." (종료 0)
#      위반 → "[FAIL] 양식 위반 N건 — 커밋 차단." + 위반 목록 (종료 1 — 훅에 걸면 커밋이 막힌다)
#
#  운영 팁: 처음 운영한 뒤 오탐(false positive)이 보이면 아래 상수 세 줄만
#           팀 표준에 맞게 고친다. 검사 로직은 손댈 필요가 없다.
#
#  의존성: 파이썬 표준 라이브러리만.
# ============================================================================
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# --- 상수: 팀 표준에 맞게 이 세 줄만 고쳐 쓴다 ------------------------------
REQUIRED_FRONTMATTER = ["type", "date", "category", "attendees"]
ALLOWED_CATEGORIES = {"planning", "review", "sync", "retro", "adhoc"}
REQUIRED_SECTIONS = ["## 안건", "## 결정", "## 액션 아이템", "## 다음 회의"]


# --- 헬퍼 -------------------------------------------------------------------
def parse_markdown(path):
    """회의록 파일을 (frontmatter 딕셔너리, 본문 문자열)로 분리한다."""
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return {}, text  # 꼬리표가 아예 없으면 필수 항목 전부가 "누락"으로 잡힌다
    fm = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip()
    return fm, text[m.end():]


def extract_section(body, header):
    """header 섹션의 본문(다음 '## ' 헤더 직전까지)을 돌려준다."""
    start = body.find(header)
    if start < 0:
        return ""
    start += len(header)
    nxt = body.find("\n## ", start)
    return body[start:nxt] if nxt >= 0 else body[start:]


def count_decision_slots(body):
    """'## 결정' 섹션에서 D번호 형식("- D…")으로 적힌 결정 슬롯 수를 센다."""
    block = extract_section(body, "## 결정")
    return sum(1 for l in block.split("\n") if l.strip().startswith("- D"))


# --- 검사 3종 (책 본문 발췌 구간) --------------------------------------------
def lint(meeting_note_path):
    """검사 3종을 돌려 위반 목록을 돌려준다. 빈 리스트 = 통과."""
    fm, body = parse_markdown(meeting_note_path)
    errors = []
    for key in REQUIRED_FRONTMATTER:        # ① 꼬리표 필수 항목
        if key not in fm: errors.append(f"frontmatter 누락: {key}")
    if fm.get("category") not in ALLOWED_CATEGORIES:
        errors.append(f"category 값 부적합: {fm.get('category')}")
    for section in REQUIRED_SECTIONS:       # ② 필수 섹션
        if section not in body: errors.append(f"섹션 누락: {section}")
    if "## 결정" in body:                   # ③ 결정 슬롯이 D1/D2 형식인가
        block = extract_section(body, "## 결정")
        if not any(l.strip().startswith("- D") for l in block.split("\n")):
            errors.append("결정 슬롯 비어 있음 (D1, D2... 형식 필요)")
    return errors                            # ← 비면 통과, 채워지면 커밋이 막힌다


# --- 실행부 -----------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="meeting_lint",
        description="회의록 양식 검사기 — 커밋 전 훅에 걸어 양식 위반을 입구에서 되돌린다")
    ap.add_argument("path", help="검사할 회의록(.md) 경로")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.path):
        sys.stderr.write(f"[!] 파일 없음: {args.path}\n")
        return 2

    errors = lint(args.path)

    # 통과·차단 어느 쪽이든 무엇을 얼마나 봤는지 집계를 함께 남긴다.
    fm, body = parse_markdown(args.path)
    fm_ok = sum(1 for k in REQUIRED_FRONTMATTER if k in fm)
    sec_ok = sum(1 for s in REQUIRED_SECTIONS if s in body)
    slots = count_decision_slots(body)

    if errors:
        print(f"[FAIL] 양식 위반 {len(errors)}건 — 커밋 차단. ({args.path})")
        for e in errors:
            print(f"  - {e}")
        print(f"  (frontmatter {fm_ok}/{len(REQUIRED_FRONTMATTER)}, "
              f"섹션 {sec_ok}/{len(REQUIRED_SECTIONS)}, 결정 슬롯 {slots}건)")
        return 1

    print(f"[OK] frontmatter {fm_ok}/{len(REQUIRED_FRONTMATTER)}, "
          f"섹션 {sec_ok}/{len(REQUIRED_SECTIONS)}, 결정 슬롯 {slots}건 감지. 커밋 허용.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

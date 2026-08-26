#!/usr/bin/env python3
# ============================================================================
#  decision_parser.py  —  회의록 결정 슬롯 → 4필드 추출 + owner [MISSING] 반려
# ----------------------------------------------------------------------------
#  책 3장 '결정 네 필드를 자동으로 추출하기' 절의 전체 실행본.
#
#  왜:
#    - 회의에서 결정은 났는데 '누가 책임지고 왜 그렇게 정했는지'가 문장 사이에 녹아
#      회의실 문을 나서는 순간 증발한다.
#    - 주인 없는 결정은 결정이 아니라 희망 사항이다. 책임자 없는 결정을 조용히
#      통과시키는 게 가장 위험하다.
#    → 양식 검사(meeting_lint.py)를 통과한 회의록의 결정 슬롯(D1, D2...)을
#      decision(무엇을)·owner(누가 책임)·rationale(왜)·follow_up(다음 행동)
#      4필드로 분해하고, owner를 찾지 못하면 버리지도 알아서 채우지도 않고
#      [MISSING]으로 신고한 뒤 pending 생성을 보류하고 작성자에게 반려한다.
#
#  하는 일 (기본 실행):
#    1) "## 결정" 슬롯에서 결정마다 4필드 추출 (+ id·source_meeting·category)
#    2) JSON 배열로 출력 (책 본문의 실행 로그와 같은 형식)
#    3) owner가 있는 결정만 pending/ 후보 파일 생성.
#       owner가 [MISSING]이면 경고 라인을 출력 맨 위에 붙이고 반려한다(exit 1).
#
#  분담선: 결정의 존재는 사람이 D 슬롯으로 선언한다. 파서는 구조화와 누락 신고만
#  맡는다. follow_up 연결도 액션 아이템의 @owner 표기로만 잇는다(추측 금지).
#  양식이 무너진 자유 서술 회의록은 --emit-prompt로 AI 보조 경로를 쓴다:
#      python decision_parser.py meetings/양식불량.md --emit-prompt   # 출력을 웹 챗봇에 붙여넣기
#
#  사용법:
#    python decision_parser.py meetings/2026-06-08_planning.md
#    python decision_parser.py meetings/노트.md --pending-dir pending
#    python decision_parser.py meetings/노트.md --dry-run    # 파일 안 만들고 확인만
#
#  종료 코드: 0 = 전부 pending 후보 생성 / 1 = owner [MISSING] 반려 포함 / 2 = 입력·양식 오류
#
#  의존성: 파이썬 표준 라이브러리만.
# ============================================================================
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

MISSING = "[MISSING]"

# 책 3장 본문에 실린 'AI 보조 프롬프트 전문' (문자 그대로 내장).
# 양식이 무너진 회의록은 이 프롬프트로 웹 챗봇/AI CLI에 맡긴다(--emit-prompt가
# [회의록 본문 붙여넣음] 자리를 실제 본문으로 채워 출력한다).
AI_ASSIST_PROMPT = """\
아래 회의록의 "## 결정" 슬롯을 읽고 결정마다 4개 필드를
추출하라: decision, owner, rationale, follow_up.
- owner를 본문에서 특정할 수 없으면 반드시 "[MISSING]"으로 표기.
  추측해서 채우지 말 것.
- rationale은 본문에 적힌 근거만 인용. 없으면 "[MISSING]".
- follow_up은 액션 아이템 또는 다음 분기 언급과 연결.
JSON 배열로만 출력.

[회의록 본문 붙여넣음]
"""

# pending 후보 파일 양식 (책 본문 "pending 생성" 블록과 같은 구조)
PENDING_TEMPLATE = """\
---
name: {name}
description: {description}
status: pending
owner: {owner}
category: {category}
created: {created}
---
## 결정
{decision}
## 근거
{rationale}
## 후속 액션
- [ ] @{owner}: {follow_up}
"""

SLOT_RE = re.compile(r"^-\s*(D\d+)\s*[:：]\s*(.+)$")            # - D1: 결정 한 문장
OWNER_RE = re.compile(r"\(\s*(?:소유자|owner)\s*[:：]\s*([^)]+?)\s*\)")  # (소유자: 이름)
RATIONALE_RE = re.compile(r"\[\s*근거\s*[:：]\s*(.+?)\s*\]", re.DOTALL)  # [근거: ...]
ACTION_RE = re.compile(r"^-\s*(?:\[.\]\s*)?@([^\s:：]+)\s*[:：]\s*(.+)$")  # - @이름: 할 일


def parse_markdown(path: Path):
    """회의록에서 (frontmatter dict, 본문 str)을 돌려준다."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip()
    return fm, m.group(2)


def extract_section(body: str, heading: str):
    """'## 결정' 같은 헤딩부터 다음 '## ' 헤딩 전까지의 블록. 헤딩이 없으면 None."""
    out, inside, found = [], False, False
    for line in body.split("\n"):
        if line.strip().startswith("## "):
            inside = line.strip() == heading
            found = found or inside
            continue
        if inside:
            out.append(line)
    return "\n".join(out) if found else None


def parse_slots(section: str):
    """결정 섹션에서 D 슬롯별 (id, 원문 덩어리) 목록을 모은다. 들여쓴 연속 줄 포함."""
    slots, cur = [], None
    for line in section.split("\n"):
        s = line.strip()
        m = SLOT_RE.match(s)
        if m:
            cur = {"id": m.group(1), "raw": m.group(2)}
            slots.append(cur)
        elif cur is not None and s:
            cur["raw"] += "\n" + s
    return slots


def parse_actions(section):
    """액션 아이템 섹션에서 (@담당자, 할 일) 목록을 모은다."""
    assigned = []
    for line in (section or "").split("\n"):
        m = ACTION_RE.match(line.strip())
        if m:
            assigned.append((m.group(1), m.group(2).strip()))
    return assigned


def slot_to_fields(slot, actions, fm, source_name):
    """슬롯 하나를 4필드로 분해한다. 모르는 칸은 [MISSING] — 추측해서 채우지 않는다."""
    raw = slot["raw"]

    owner = MISSING
    m = OWNER_RE.search(raw)
    if m:
        owner = m.group(1).strip()
        raw = OWNER_RE.sub("", raw, count=1)

    rationale = MISSING
    m = RATIONALE_RE.search(raw)
    if m:
        rationale = re.sub(r"\s+", " ", m.group(1)).strip()
        raw = RATIONALE_RE.sub("", raw, count=1)

    decision = re.sub(r"\s+", " ", raw.split("\n")[0]).strip()

    # follow_up은 액션 아이템의 @owner 표기로만 연결한다. owner를 모르면 잇지 않는다.
    follow_up = MISSING
    if owner != MISSING:
        mine = [text for handle, text in actions if handle == owner]
        if mine:
            follow_up = " / ".join(mine)

    return {
        "id": slot["id"],
        "decision": decision,
        "owner": owner,
        "rationale": rationale,
        "follow_up": follow_up,
        "source_meeting": source_name,
        "category": fm.get("category") or MISSING,
    }


def render_pending(d, created):
    follow = d["follow_up"] if d["follow_up"] != MISSING else "(후속 액션 미기재)"
    return PENDING_TEMPLATE.format(
        name=f"decision_{created}_{d['id']}",
        description=d["decision"].rstrip(".").strip() or d["decision"],
        owner=d["owner"], category=d["category"], created=created,
        decision=d["decision"], rationale=d["rationale"], follow_up=follow,
    )


def cmd_emit_prompt(note: Path) -> int:
    body = note.read_text(encoding="utf-8", errors="ignore").rstrip("\n")
    sys.stdout.write(AI_ASSIST_PROMPT.replace("[회의록 본문 붙여넣음]", body))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="decision_parser",
        description="회의록 결정 슬롯을 4필드(decision·owner·rationale·follow_up)로 추출 (표준 라이브러리만)")
    ap.add_argument("meeting_note", help="양식 검사를 통과한 회의록(.md)")
    ap.add_argument("--pending-dir", default="pending", help="pending 후보 생성 폴더 (기본: ./pending)")
    ap.add_argument("--dry-run", action="store_true", help="pending 파일을 만들지 않고 추출 결과만 출력")
    ap.add_argument("--force", action="store_true", help="이미 있는 pending 파일 덮어쓰기")
    ap.add_argument("--emit-prompt", action="store_true",
                    help="AI 보조 프롬프트에 회의록 본문을 채워 출력 (양식 불량 회의록용)")
    args = ap.parse_args(argv)

    note = Path(args.meeting_note)
    if not note.is_file():
        sys.stderr.write(f"[!] 파일 없음: {note}\n")
        return 2

    if args.emit_prompt:
        return cmd_emit_prompt(note)

    fm, body = parse_markdown(note)
    if not fm:
        sys.stderr.write("[!] frontmatter 없음 — meeting_lint.py 통과본인지 확인하세요.\n")
        return 2
    section = extract_section(body, "## 결정")
    if section is None:
        sys.stderr.write('[!] "## 결정" 섹션 없음 — meeting_lint.py 통과본인지 확인하세요.\n')
        return 2
    slots = parse_slots(section)
    if not slots:
        sys.stderr.write("[!] 결정 슬롯에 D1, D2... 형식이 없습니다. "
                         "자유 서술 회의록은 --emit-prompt로 AI 보조 경로를 사용하세요.\n")
        return 2

    actions = parse_actions(extract_section(body, "## 액션 아이템"))
    decisions = [slot_to_fields(s, actions, fm, note.name) for s in slots]
    missing = [d for d in decisions if d["owner"] == MISSING]

    # owner가 빈 결정이 있으면 경고 라인을 출력 맨 위에 붙인다.
    if missing:
        n, k = len(decisions), len(missing)
        scope = f"{n}건 모두" if k == n else f"{n}건 중 {k}건"
        print(f"경고: 결정 {scope} owner {MISSING}. pending 승격 전")
        print("   회의 진행자에게 owner 확정 요청 필요.")
        print()

    print(json.dumps(decisions, ensure_ascii=False, indent=2))

    created = fm.get("date") or _dt.date.today().isoformat()
    for d in decisions:
        if d["owner"] == MISSING:
            print(f"[반려] {d['id']}: owner={MISSING} → pending 생성 보류. 작성자에게 owner 확정 요청.")
            continue
        if args.dry_run:
            print(f"[DRY] {d['id']}: owner={d['owner']}. pending 생성 생략(--dry-run).")
            continue
        out = Path(args.pending_dir) / f"decision_{created}_{d['id']}.md"
        if out.exists() and not args.force:
            print(f"[SKIP] {d['id']}: 이미 존재 → {out} (덮어쓰려면 --force)")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_pending(d, created), encoding="utf-8")
        print(f"[OK] {d['id']}: owner={d['owner']}. pending 후보 생성.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

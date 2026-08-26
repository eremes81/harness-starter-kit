#!/usr/bin/env python3
# ============================================================================
#  promote.py  —  pending 후보 결정을 정식 결정으로 승격 + 색인 갱신
# ----------------------------------------------------------------------------
#  책 3장 '주 1회 검수하고 승격하기' 절의 전체 실행본.
#
#  왜:
#    - 파서를 통과한 결정은 pending/ 에서 1주를 묵힌다(가역 구간).
#    - 주간 리뷰에서 "승격"이 결정되면 두 가지가 한 번에 일어나야 한다.
#      ① 파일 이동: pending/ → decisions/<주제>/  (정식 결정 폴더)
#      ② 색인 갱신: decisions/_index.json 에 트리거 키워드 등록
#         → 다음에 관련 주제를 입력하면 이 결정과 근거가 자동 주입된다.
#    - 이 둘을 손으로 하면 하나가 빠진다. 스크립트가 한 번에 처리한다.
#
#  사용법:
#    python promote.py pending/decision_2026-06-08_D1.md
#    python promote.py pending/decision_2026-06-08_D1.md --dry-run   # 미리보기
#
#  안전 원칙 (책 본문과 동일):
#    - owner 가 없거나 [MISSING] 이면 승격을 거부한다.
#      (주인 없는 결정은 결정이 아니라 희망 사항이다.)
#    - status 가 pending 이 아니면 거부한다(이중 승격 방지).
#    - 승격은 비가역 구간의 시작이다. 검수가 끝난 뒤에만 실행할 것.
#
#  의존성: 파이썬 표준 라이브러리만.
# ============================================================================
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# --- 주제 분류 규칙 ----------------------------------------------------------
# "폴더 슬러그": [트리거 키워드, ...]  (첫 키워드 = 대표 트리거)
# 카드 본문에 키워드가 하나라도 보이면 그 주제로 분류하고(다수 일치 우선),
# 색인에는 키워드 목록 전체를 트리거 정규식으로 등록한다.
# 팀의 주제가 늘면 여기 한 줄씩 추가한다 — 이 표가 곧 정식 결정 폴더 구조다.
TOPIC_RULES = {
    "onboarding": ["온보딩", "온보딩 자료", "신규 고객"],
    "helpdesk":   ["헬프데스크", "FAQ", "고객 문의"],
    "meeting":    ["회의록", "회의 양식"],
}

INDEX_NAME = "_index.json"


def _today() -> str:
    return _dt.date.today().isoformat()


def _err(msg: str) -> int:
    sys.stderr.write(f"[!] {msg}\n")
    return 2


def _rel(path) -> str:
    """cwd 기준 상대 경로를 / 구분자로. (실행 로그와 같은 표기)"""
    try:
        rel = os.path.relpath(path)
    except ValueError:  # 다른 드라이브 등 상대화 불가
        rel = str(path)
    return rel.replace(os.sep, "/")


def _parse_frontmatter(text: str) -> dict:
    """카드 머리글(---...---)을 key: value 딕셔너리로. (표준 라이브러리만)"""
    m = re.search(r"^---\s*\n(.*?)\n---\s*$", text, re.DOTALL | re.MULTILINE)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if mm:
            data[mm.group(1)] = mm.group(2).split(" #")[0].strip()
    return data


def _classify(text: str):
    """카드 전문에서 TOPIC_RULES 키워드를 세어 가장 많이 맞은 주제를 고른다.
    반환: (주제 슬러그, 트리거 키워드 목록) — 일치가 없으면 (None, [])."""
    best, best_hits = None, 0
    for topic, keywords in TOPIC_RULES.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best, best_hits = topic, hits
    return (best, TOPIC_RULES[best]) if best else (None, [])


def _mark_promoted(text: str) -> str:
    """머리글의 status: pending → active 로 바꾸고 promoted 날짜를 남긴다.
    본문(결정·근거·후속 액션)은 한 글자도 건드리지 않는다."""
    return re.sub(r"^status:\s*pending\s*$",
                  f"status: active\npromoted: {_today()}",
                  text, count=1, flags=re.MULTILINE)


def _update_index(decisions_dir: Path, entry: dict) -> Path:
    """decisions/_index.json 에 승격 결정을 등록(같은 name 이면 교체)."""
    index_path = decisions_dir / INDEX_NAME
    index = {"generated": "", "count": 0, "entries": []}
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            pass  # 색인이 깨져 있으면 새로 만든다 (승격 자체를 막지 않는다)
    entries = [e for e in index.get("entries", []) if e.get("name") != entry["name"]]
    entries.append(entry)
    index = {"generated": _today(), "count": len(entries), "entries": entries}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return index_path


def cmd_promote(args) -> int:
    src = Path(args.pending_file)

    # --- 승격 전 검사 3종: 파일 → status → owner --------------------------
    if not src.is_file():
        return _err(f"파일 없음: {src}")
    text = src.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    if not fm:
        return _err(f"카드 머리글(---...---)을 읽을 수 없음: {src}")

    status = fm.get("status", "")
    if status != "pending":
        return _err(f"status 가 pending 이 아님({status or '없음'}). "
                    "이미 승격됐거나 후보 카드가 아닙니다.")

    owner = fm.get("owner", "")
    if not owner or owner == "[MISSING]":
        return _err("owner 가 비어 있음([MISSING]). 주인 없는 결정은 승격할 수 없습니다. "
                    "회의 진행자에게 owner 확정을 요청하세요.")

    # --- 목적지 결정: 주제 분류 → decisions/<주제>/ -----------------------
    decisions_dir = (Path(args.decisions_dir) if args.decisions_dir
                     else src.resolve().parent.parent / "decisions")
    topic, keywords = _classify(text)
    if topic is None:
        # 키워드 미등록 주제 → category 폴더로 승격하되 트리거는 비워 둔다.
        topic = fm.get("category") or "general"
    dest_dir = decisions_dir / topic
    dest = dest_dir / src.name
    if dest.exists() and not args.force:
        return _err(f"이미 존재: {_rel(dest)} (덮어쓰려면 --force)")

    trigger = "|".join(keywords)
    if args.dry_run:
        print(f"[DRY-RUN] 이동 예정: {_rel(src)} → {_rel(dest)}")
        print(f"[DRY-RUN] 색인 등록 예정: trigger=({trigger or '없음'})")
        return 0

    # --- ① 파일 이동 (정식 결정 폴더에 먼저 쓰고, 성공한 뒤 pending 제거) --
    os.makedirs(dest_dir, exist_ok=True)
    dest.write_text(_mark_promoted(text), encoding="utf-8")
    src.unlink()
    print(f"[PROMOTE] → {_rel(dest)}")

    # --- ② 색인 갱신 -------------------------------------------------------
    _update_index(decisions_dir, {
        "name": fm.get("name") or src.stem,
        "file": f"{topic}/{src.name}",
        "topic": topic,
        "trigger": trigger,
        "owner": owner,
        "category": fm.get("category", ""),
        "created": fm.get("created", ""),
        "promoted": _today(),
        "description": fm.get("description", ""),
    })
    if trigger:
        print(f"[INDEX] 색인 등록: trigger=({trigger})")
        print(f'[OK] 다음에 "{keywords[0]}" 입력 시 이 결정과 근거 자동 주입.')
    else:
        print("[INDEX] 색인 등록: trigger=(없음)")
        print(f"[OK] 승격 완료. TOPIC_RULES 에 '{topic}' 키워드를 추가하면 자동 주입이 켜집니다.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="promote",
        description="주간 리뷰에서 승격이 결정된 pending 카드를 정식 결정으로 이동하고 색인을 갱신 (표준 라이브러리만)")
    p.add_argument("pending_file", help="승격할 후보 카드 (예: pending/decision_2026-06-08_D1.md)")
    p.add_argument("--decisions-dir", default="",
                   help="정식 결정 폴더 (기본: pending/ 옆의 decisions/)")
    p.add_argument("--dry-run", action="store_true", help="이동·색인 없이 결과만 미리 본다")
    p.add_argument("--force", action="store_true", help="목적지에 같은 파일이 있어도 덮어쓴다")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return cmd_promote(args)


if __name__ == "__main__":
    raise SystemExit(main())

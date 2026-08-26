#!/usr/bin/env python3
# ============================================================================
#  lint_frontmatter.py  —  꼬리표(frontmatter) 검사기
# ----------------------------------------------------------------------------
#  책 2장 「심화(선택): 꼬리표 검사를 AI에게 맡기기」 절의 전체 실행본.
#
#  왜:
#    - 문서가 수십 장으로 늘면 "꼬리표를 제대로 안 단 문서"를 손으로 찾는
#      일 자체가 무리가 된다.
#    - 표준은 만들어 둔다고 저절로 지켜지지 않는다. 검사기는 그 사실을
#      드러내는 장치다.
#    - 허용 값은 코드에 박지 않고 같은 폴더의 _STANDARD.md에서 읽어 온다.
#      → 표준을 고치면 코드를 다시 손대지 않아도 검사 기준이 함께 바뀐다.
#
#  검사 항목 (출력 태그):
#    [NO-FM]    맨 앞 ---…--- 꼬리표 자체가 없음
#    [MISSING]  필수 필드(title·owner·status) 누락, 또는 active인데 updated 없음
#    [STATUS]   _STANDARD.md 허용 값 밖의 status
#    [STALE]    status가 active인데 updated가 90일 넘게 안 바뀜
#
#  사용법:
#    python lint_frontmatter.py [문서폴더]        # 기본: 현재 폴더
#    - 폴더 아래 모든 .md를 하위 폴더까지 검사한다 (_STANDARD.md 자신은 제외).
#    - 같은 폴더에 표준 문서 _STANDARD.md가 있어야 한다. 예:
#        status: allowed = ["draft", "active", "deprecated"]
#        updated: YYYY-MM-DD (따옴표 없이)
#    - 위반이 없으면 아무것도 출력하지 않는다. 위반은 파일별로 한 줄씩 찍힌다.
#
#  의존성: 파이썬 표준 라이브러리만. (PyYAML 있으면 파싱이 더 견고하나 없어도 동작)
# ============================================================================
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except Exception:
    _HAVE_YAML = False


def parse_frontmatter(md: Path):
    """문서 맨 앞의 ---…--- YAML 꼬리표를 dict로 돌려준다. 꼬리표가 없으면 None."""
    text = md.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")  # BOM 제거
    m = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    if _HAVE_YAML:
        # updated: 2026-09-12처럼 적혀 있으면 PyYAML이 자동으로 날짜 타입으로 파싱한다.
        # — 이 말은 절반만 맞다. 작성자가 따옴표를 붙인 "2026-09-12"는 문자열로
        #   파싱되므로, 날짜 뺄셈 전에 as_date()로 두 표기를 모두 정규화해야 안전하다.
        try:
            data = yaml.safe_load(block)
            if isinstance(data, dict):
                return data
        except Exception:
            pass  # 깨진 YAML은 아래 소박한 파서로 한 번 더 읽어 본다
    # PyYAML이 없거나 실패한 경우: "key: value" 한 줄짜리만 소박하게 읽는다.
    data = {}
    for line in block.splitlines():
        mm = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not mm:
            continue
        val = mm.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]  # 둘러싼 따옴표만 벗긴다 (값은 문자열 그대로 둔다)
        data[mm.group(1)] = val
    return data if data else None


def as_date(v):
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        return datetime.date.fromisoformat(v.strip())
    return None


def load_allowed(standard_md: Path):
    """status 허용 값을 _STANDARD.md에서 읽어 온다 — 코드에 박지 않는다.

    표준 문서에 아래 형식의 한 줄이 있으면 된다.
        status: allowed = ["draft", "active", "deprecated"]
    """
    if not standard_md.is_file():
        sys.stderr.write(
            f"[!] 표준 문서가 없습니다: {standard_md}\n"
            "    허용 status 값은 코드가 아니라 표준 문서가 정합니다. 같은 폴더에 이런 한 줄을 두세요:\n"
            '    status: allowed = ["draft", "active", "deprecated"]\n')
        raise SystemExit(2)
    text = standard_md.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"status\s*:\s*allowed\s*=\s*\[([^\]]*)\]", text)
    if not m:
        sys.stderr.write(
            f"[!] 표준 문서에서 허용 값 줄을 찾지 못했습니다: {standard_md}\n"
            '    형식: status: allowed = ["draft", "active", "deprecated"]\n')
        raise SystemExit(2)
    allowed = [v.strip().strip("'\"") for v in m.group(1).split(",") if v.strip()]
    if not allowed:
        sys.stderr.write(f"[!] 허용 status 값이 비어 있습니다: {standard_md}\n")
        raise SystemExit(2)
    return allowed


# ── 실행 ────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(
    prog="lint_frontmatter",
    description="폴더 아래 모든 .md의 맨 앞 YAML 꼬리표를 검사한다 "
                "(필수 필드 누락 · 허용 밖 status · active 90일 방치)")
ap.add_argument("root", nargs="?", default=".",
                help="검사할 문서 폴더 (기본: 현재 폴더). 같은 폴더에 _STANDARD.md 필요")
args = ap.parse_args()

ROOT = Path(args.root)
if not ROOT.is_dir():
    sys.stderr.write(f"[!] 폴더가 없습니다: {ROOT}\n")
    raise SystemExit(2)

allowed = load_allowed(ROOT / "_STANDARD.md")  # 허용 값은 표준 문서가 정한다
today = datetime.date.today()

# ── 책 본문 궤적 메모: Claude 첫 출력의 ③은 아래 모양이었다 ─────────────────
#     if fm.get("status") == "active":                  # ③ active인데 오래 방치
#         age = (today - fm["updated"]).days   # ← 여기가 깨진다
#         if age > 90:
#             print(f"[STALE]   {md}: {age}d")
#   어떤 작성자는 updated: 2026-09-12(날짜로 파싱), 어떤 작성자는 "2026-09-12"
#   (문자열로 파싱)라고 적어서 뺄셈에서 TypeError가 났다. 그래서 아래 루프의
#   ③은 as_date()로 두 표기를 모두 정규화한 "STALE 검사 교체분"이다.

for md in ROOT.rglob("*.md"):            # 폴더 안 모든 문서를
    if md.name == "_STANDARD.md":        # 표준 문서 자신은 검사 대상이 아니다
        continue
    fm = parse_frontmatter(md)           # 맨 앞 ---…--- 꼬리표를 읽어
    if fm is None:
        print(f"[NO-FM]   {md}"); continue            # 꼬리표 자체가 없음
    for f in ["title", "owner", "status"]:            # ① 필수 필드 누락
        if f not in fm:
            print(f"[MISSING] {md}: {f}")
    if fm.get("status") not in allowed:               # ② 허용 밖 status
        print(f"[STATUS]  {md}: {fm.get('status')}")  #    (allowed는 _STANDARD.md에서 읽어 옴)
    # STALE 검사 교체분
    if fm.get("status") == "active":                  # ③ active인데 오래 방치
        upd = as_date(fm.get("updated"))
        if upd is None:
            print(f"[MISSING] {md}: updated")
        elif (today - upd).days > 90:
            print(f"[STALE]   {md}: {(today - upd).days}d")

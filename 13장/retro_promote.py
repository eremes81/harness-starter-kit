#!/usr/bin/env python3
# ============================================================================
#  retro_promote.py  —  재발 교훈을 점수로 줄 세워 '재발 방지 규칙' 블록 자동 갱신
# ----------------------------------------------------------------------------
#  책 13장 '재발 교훈을 점수로 줄 세워 최신 상태 유지하기' 절의 전체 실행본.
#
#  왜:
#    - 루프를 몇 달 돌리면 규칙이 쌓여, 항상 로드되는 문서(CLAUDE.md 등)의
#      맨 윗자리를 무엇이 차지할지 손으로 고르게 된다. 그러면 신선도가 깨진다.
#    - 한 번 지정한 규칙은 눌러앉고, 요즘 매주 다시 터지는 교훈은 아래에 묻힌다.
#    → 맨 위 블록을 손으로 관리하지 않는다. 재발 횟수와 최근성으로 점수를 매겨
#      상위 몇 개만 이 스크립트가 자동으로 다시 써 넣는다.
#
#  무엇을 하나:
#    - retro/ 회고(.md)에서 재발 기록을 모은다. (아래 '기록 규약' 참조)
#    - 교훈마다 점수를 매긴다. (점수식은 --help 끝에 표시)
#    - 대상 문서의 <!-- 자동 생성 구역 --> ~ <!-- /자동 생성 구역 --> 사이를
#      점수순 상위 N개 목록으로 통째로 다시 쓴다.
#    - 이 블록은 사람이 손으로 고치지 않는다. 이 스크립트만 다시 쓴다.
#      (사람이 새 규칙을 넣고 싶으면 블록 아래 일반 규칙 목록에 적는다.
#       그 규칙도 계속 재발하면 다음 회고에서 점수를 받아 블록으로 올라온다.)
#
#  기록 규약 (회고 파일 안에서 재발 1건으로 세는 줄):
#    ① "- 재발: <교훈 한 문장>"  ← 권장. 같은 교훈은 같은 문장으로 적는다.
#       (문장이 곧 그룹 키다. 문장이 다르면 다른 교훈으로 센다.)
#    ② "## 반복 발견" / "## 패턴 발견" 제목 아래의 불릿도 재발 1건으로 센다.
#       "- 합계가 또 어긋남 → 손으로 정정 → 3회째"처럼 화살표가 있으면
#       첫 화살표 앞부분을 교훈 문장으로 삼고, 문장 끝의 "(두 번째)"/"(3회째)"
#       같은 횟수 표기는 떼고 센다(횟수는 날짜별 기록에서 자동 집계).
#    - 기록 날짜 = 파일명의 날짜. daily/2026-07-01.md 또는 weekly/2026-W27.md
#      (주간 파일은 그 주 금요일로 본다). 날짜 없는 파일은 건너뛰고 알린다.
#
#  사용법 (Claude에게 "재발 방지 블록 갱신해줘"라고 하면 대신 실행):
#    python 13장/retro_promote.py                # retro/ 스캔 → CLAUDE.md 블록 갱신
#    python 13장/retro_promote.py --dry-run      # 문서를 건드리지 않고 블록만 출력
#    python 13장/retro_promote.py --demo         # 책 13장 예시 데이터로 자가 검증
#    옵션: --retro-dir --doc --window(관측창 일수, 기본 90) --decay(감쇠 k, 기본 1.0)
#          --top(상위 N, 기본 5) --today(YYYY-MM-DD, 재현 테스트용)
#
#  안전: 대상 문서에 자동 생성 구역 표식이 없으면 아무것도 쓰지 않고,
#        붙여 넣을 표식을 안내한 뒤 오류로 종료한다. 재발 기록이 0건이어도
#        (경로·규약 문제일 수 있으므로) 문서를 건드리지 않는다.
#
#  의존성: 파이썬 표준 라이브러리만.
# ============================================================================
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RETRO = REPO_ROOT / "retro"
DEFAULT_DOC = REPO_ROOT / "CLAUDE.md"

# --- 블록 표식: 책 13장 본문에 실린 모양 그대로 ---------------------------
BLOCK_START = """\
<!-- 자동 생성 구역 / 손으로 고치지 마세요.
retro_promote 스크립트가 갱신합니다 -->"""
BLOCK_END = "<!-- /자동 생성 구역 -->"
BLOCK_HEADING = "## 재발 방지 규칙 (자동 갱신)"

# 문서 안에서 기존 블록을 찾는 패턴. 시작 표식이 한 줄로 붙어 있어도 잡는다.
BLOCK_RE = re.compile(r"<!--\s*자동 생성 구역.*?-->.*?<!--\s*/자동 생성 구역\s*-->",
                      re.DOTALL)

# 책 13장 본문의 예시 블록. --demo 가 이것과 문자 단위로 일치하는지 자가 검증한다.
EXAMPLE_BLOCK = """\
<!-- 자동 생성 구역 / 손으로 고치지 마세요.
retro_promote 스크립트가 갱신합니다 -->
## 재발 방지 규칙 (자동 갱신)
1. 보고서 제출 전 부서별 합계 대조 — 영업3팀 컬럼 양식 밀림 주의 (재발 3)
2. 회의록은 채널에 흩어진 사본을 한곳에 모은 뒤 추출 (재발 2)
<!-- /자동 생성 구역 -->
""".rstrip("\n")

# 점수식 (책 13장). --help 끝에 그대로 표시된다.
FORMULA = """\
교훈 점수
=  Σ  max(0, 1 − k × 경과일 / 관측창 )
각 재발 기록

재발한 횟수가 많으면 더하는 항이 많아져 점수가 올라가고, 최근에 재발했다면
각 항의 값도 높다. 한동안 안 터진 교훈은 점수가 가라앉아 블록 밖으로 밀려난다.
관측창(기본 90일)·감쇠 k·상위 N은 보편 정답이 아니라 운영하며 맞추는 값이다."""

# --- 회고 파일 파싱 ---------------------------------------------------------
DATE_IN_NAME = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
WEEK_IN_NAME = re.compile(r"(\d{4})-W(\d{1,2})", re.IGNORECASE)
RECUR_LINE = re.compile(r"^[-*]\s*재발\s*:\s*(.+)$")
HEADING_LINE = re.compile(r"^#{1,6}\s*(.+)$")
BULLET_LINE = re.compile(r"^[-*]\s+(.+)$")
COUNT_SUFFIX = re.compile(r"\s*\([^()]*(?:회째|번째)\)\s*$")  # 예: "(두 번째)", "(3회째)"
REPEAT_SECTIONS = ("반복 발견", "패턴 발견")


def date_from_name(name: str):
    """파일명에서 기록 날짜를 읽는다. 주간(YYYY-Www)은 그 주 금요일로 본다."""
    m = DATE_IN_NAME.search(name)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = WEEK_IN_NAME.search(name)
    if m:
        try:
            return _dt.date.fromisocalendar(int(m.group(1)), int(m.group(2)), 5)
        except ValueError:
            return None
    return None


def collect_records(retro_dir: Path):
    """retro_dir 아래 .md 를 훑어 {교훈 문장: 재발 날짜 집합} 을 만든다.

    같은 교훈이 같은 날짜에 여러 번 적혀 있어도(일간에 적고 주간이 다시 집계)
    하루 1건으로만 센다 — 집계의 중복이 재발 횟수를 부풀리지 않게 하기 위해서다.
    """
    records: dict[str, set] = {}
    skipped, n_files = [], 0
    for md in sorted(retro_dir.rglob("*.md")):
        if md.name.lower() == "readme.md":
            continue
        day = date_from_name(md.name)
        if day is None:
            skipped.append(str(md.relative_to(retro_dir)))
            continue
        n_files += 1
        in_repeat = False
        for raw in md.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            h = HEADING_LINE.match(line)
            if h:
                in_repeat = any(k in h.group(1) for k in REPEAT_SECTIONS)
                continue
            lesson = None
            m = RECUR_LINE.match(line)
            if m:
                lesson = m.group(1)
            elif in_repeat:
                b = BULLET_LINE.match(line)
                if b:
                    lesson = b.group(1).split(" → ")[0]  # 화살표 앞 = 교훈 문장
            if lesson:
                key = COUNT_SUFFIX.sub("", " ".join(lesson.split())).strip()
                if key and key not in ("-", "(없음)"):
                    records.setdefault(key, set()).add(day)
    return records, skipped, n_files


# --- 점수화·블록 생성 -------------------------------------------------------
def rank(records: dict, today: _dt.date, window: int, decay: float) -> list:
    """교훈마다 점수를 매겨 점수순으로 정렬한다. 점수 0은 블록 후보에서 뺀다."""
    ranked = []
    for lesson, dates in records.items():
        score = 0.0
        for d in dates:
            age = max((today - d).days, 0)
            score += max(0.0, 1.0 - decay * age / window)
        if score > 0:
            ranked.append({"lesson": lesson, "count": len(dates),
                           "score": score, "last": max(dates)})
    ranked.sort(key=lambda r: (-r["score"], -r["last"].toordinal(), r["lesson"]))
    return ranked


def render_block(items: list) -> str:
    """자동 생성 구역 전체(표식 포함)를 책 13장 본문의 모양대로 만든다."""
    lines = [BLOCK_START, BLOCK_HEADING]
    if not items:
        lines.append("(관측창 안의 재발 기록 없음 — 전부 블록 밖으로 밀려남)")
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it['lesson']} (재발 {it['count']})")
    lines.append(BLOCK_END)
    return "\n".join(lines)


def update_doc(doc: Path, block: str) -> int:
    """문서 안의 자동 생성 구역만 통째로 교체한다. 표식이 없으면 쓰지 않는다."""
    if not doc.is_file():
        sys.stderr.write(f"[!] 대상 문서 없음: {doc}\n")
        return 2
    try:
        text = doc.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        sys.stderr.write(f"[!] UTF-8 로 읽을 수 없는 문서: {doc} — 인코딩을 확인하세요.\n")
        return 2
    if not BLOCK_RE.search(text):
        sys.stderr.write(
            f"[!] {doc.name} 에 자동 생성 구역 표식이 없어 아무것도 쓰지 않았습니다.\n"
            "    항상 로드되는 문서의 맨 위쪽에 아래 표식을 붙여 넣은 뒤 다시 실행하세요:\n\n"
            + BLOCK_START + "\n" + BLOCK_END + "\n")
        return 2
    new_text = BLOCK_RE.sub(lambda _m: block, text, count=1)
    if new_text == text:
        print(f"[완료] 블록 변경 없음 (이미 최신): {doc}")
        return 0
    doc.write_text(new_text, encoding="utf-8")
    print(f"[완료] 재발 방지 블록 갱신: {doc}")
    return 0


# --- 데모: 책 13장 예시 재현 -------------------------------------------------
def cmd_demo(today: _dt.date, window: int, decay: float, top: int) -> int:
    """13장 본문의 두 재발 항목으로 블록을 생성해 책의 예시와 대조한다."""
    demo_days = {
        "보고서 제출 전 부서별 합계 대조 — 영업3팀 컬럼 양식 밀림 주의": (2, 9, 16),
        "회의록은 채널에 흩어진 사본을 한곳에 모은 뒤 추출": (5, 12),
    }
    records = {lesson: {today - _dt.timedelta(days=n) for n in days}
               for lesson, days in demo_days.items()}
    block = render_block(rank(records, today, window, decay)[:top])
    print(block)
    if block == EXAMPLE_BLOCK:
        print("\n[완료] 책 13장 본문의 예시 블록과 문자 그대로 일치합니다.")
        return 0
    sys.stderr.write("\n[!] 책 예시 블록과 불일치 — 블록 포맷이 책과 어긋났습니다.\n")
    return 1


# --- CLI --------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="retro_promote",
        description="회고의 재발 교훈을 점수로 줄 세워 '재발 방지 규칙' 블록을 자동 갱신 "
                    "(표준 라이브러리만)",
        epilog=FORMULA, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--retro-dir", default=str(DEFAULT_RETRO),
                   help="회고 폴더 (기본: 저장소의 retro/)")
    p.add_argument("--doc", default=str(DEFAULT_DOC),
                   help="블록을 다시 쓸 대상 문서 (기본: 저장소의 CLAUDE.md)")
    p.add_argument("--window", type=int, default=90, help="관측창 일수 (기본 90)")
    p.add_argument("--decay", type=float, default=1.0, help="감쇠 계수 k (기본 1.0)")
    p.add_argument("--top", type=int, default=5, help="블록에 남길 상위 개수 (기본 5)")
    p.add_argument("--today", default="",
                   help="기준일 YYYY-MM-DD (기본: 오늘. 재현 테스트용)")
    p.add_argument("--dry-run", action="store_true",
                   help="문서를 건드리지 않고 생성될 블록만 출력")
    p.add_argument("--demo", action="store_true",
                   help="책 13장 예시 데이터로 블록을 만들어 본문 예시와 대조")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.today:
        try:
            today = _dt.date.fromisoformat(args.today)
        except ValueError:
            sys.stderr.write(f"[!] --today 형식 오류: {args.today} (예: 2026-08-26)\n")
            return 2
    else:
        today = _dt.date.today()

    if args.demo:
        return cmd_demo(today, args.window, args.decay, args.top)

    retro_dir = Path(args.retro_dir)
    if not retro_dir.is_dir():
        sys.stderr.write(f"[!] 회고 폴더 없음: {retro_dir}\n")
        return 2

    records, skipped, n_files = collect_records(retro_dir)
    for name in skipped:
        print(f"  [건너뜀] 파일명에서 날짜를 못 읽음: {name}")
    total = sum(len(v) for v in records.values())
    if not records:
        sys.stderr.write(
            f"[!] 재발 기록 0건 (회고 {n_files}개 파일) — 문서는 건드리지 않았습니다.\n"
            "    회고에 \"- 재발: <교훈 한 문장>\" 줄이 있는지, 경로가 맞는지 확인하세요.\n")
        return 2

    ranked = rank(records, today, args.window, args.decay)
    print(f"[완료] 회고 {n_files}개 파일 스캔 → 재발 기록 {total}건 · 교훈 {len(records)}개 "
          f"(기준일 {today}, 관측창 {args.window}일)")
    for it in ranked:
        print(f"   - {it['score']:5.2f}  재발 {it['count']}  최근 {it['last']}  {it['lesson']}")

    block = render_block(ranked[:args.top])
    if args.dry_run:
        print()
        print(block)
        return 0
    return update_doc(Path(args.doc), block)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# ============================================================================
#  retro_check.py  —  SessionStart 훅: 회고가 밀렸으면 세션 시작 시 알림
# ----------------------------------------------------------------------------
#  무엇을 하나 (책 "루프 엔지니어링" 장의 실물):
#    - 세션을 시작할 때 retro/ 안의 가장 최근 회고 날짜를 본다.
#    - 마지막 회고가 STALE_DAYS 일 넘게 밀렸으면(또는 하나도 없으면),
#      "회고가 밀렸습니다 — 지금 한 장 남기시겠어요?"를 컨텍스트로 주입한다.
#
#  왜:
#    - 회고는 하네스가 스스로 자라는 '연료'인데, "시간 날 때"로 두면 안 한다.
#    - 세션 시작 때 한 번 찔러 주면 루프가 실제로 굴러간다. (수동 폴더 → 자동 루프)
#
#  안전: 무슨 일이 있어도 exit 0. retro/ 가 없으면 조용히 종료.
# ============================================================================
from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
RETRO_DIR = REPO_ROOT / "retro"
STALE_DAYS = 7  # 마지막 회고가 이보다 오래되면 알림


def emit(text: str) -> None:
    """SessionStart 규약대로 additionalContext 주입 후 종료."""
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    if not RETRO_DIR.is_dir():
        sys.exit(0)

    # daily/ 와 weekly/ 안의 회고 .md 중 가장 최근 수정 시각을 찾는다.
    # (파일명 형식이 달라도 수정 시각으로 보면 견고하다.)
    md_files = list((RETRO_DIR / "daily").glob("*.md")) + list((RETRO_DIR / "weekly").glob("*.md"))
    md_files = [f for f in md_files if f.name != ".gitkeep"]

    now = datetime.now()
    if not md_files:
        return emit(
            "[회고 알림] 아직 작성된 회고가 없습니다. 이 하네스는 회고로 자랍니다 — "
            "괜찮으시면 지금 이번 주 회고를 한 장 남기자고 제안하세요(retro/weekly/)."
        )

    newest = max(md_files, key=lambda f: f.stat().st_mtime)
    days = (now - datetime.fromtimestamp(newest.stat().st_mtime)).days
    if days >= STALE_DAYS:
        return emit(
            f"[회고 알림] 마지막 회고가 약 {days}일 전입니다(가장 최근: {newest.name}). "
            "반복되는 교훈을 규칙으로 승격할 시점입니다 — 사용자에게 이번 주 회고를 "
            "1줄로 제안하세요. (밀렸다고 다그치지 말고 가볍게.)"
        )
    # 최근에 했으면 아무 것도 하지 않는다(조용히 종료).
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

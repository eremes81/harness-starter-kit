#!/usr/bin/env python3
# ============================================================================
#  sync_agent_docs.py  —  CLAUDE.md 를 AGENTS.md · GEMINI.md 로 복사(사본 동기화)
# ----------------------------------------------------------------------------
#  왜 필요한가:
#    AI 코딩 에이전트마다 "세션 시작 때 자동으로 읽는 지침 파일" 이름이 다르다.
#      - Claude Code            → CLAUDE.md
#      - OpenAI Codex, Grok Build, Cursor 등 → AGENTS.md
#      - Gemini CLI             → GEMINI.md
#    셋을 손으로 따로 관리하면 반드시 어긋난다. 그래서 **CLAUDE.md 하나만 원본**으로
#    두고, 나머지 둘은 이 스크립트가 자동으로 만든 사본으로 유지한다.
#
#  언제 실행하나:
#    - build_manifest.py 가 끝날 때 자동으로 호출된다(따로 기억할 필요 없음).
#    - CLAUDE.md 를 직접 고쳤다면: python scripts/sync_agent_docs.py
#    - 어긋났는지만 보려면:      python scripts/sync_agent_docs.py --check
#
#  의존성: 파이썬 표준 라이브러리만.
# ============================================================================
from __future__ import annotations

import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "CLAUDE.md"

# 사본 파일 → (어느 도구가 읽는지) 설명. 머리말에 그대로 들어간다.
MIRRORS = {
    "AGENTS.md": "OpenAI Codex · Grok Build · Cursor 등 AGENTS.md 규약을 따르는 에이전트",
    "GEMINI.md": "Gemini CLI",
}

HEADER = (
    "<!-- ⚠ 자동 생성 사본입니다. 원본은 CLAUDE.md 입니다.\n"
    "     이 파일은 {who} 가 세션 시작 때 자동으로 읽습니다.\n"
    "     고치려면 CLAUDE.md 를 고친 뒤  python scripts/build_manifest.py  를 실행하세요.\n"
    "     (scripts/sync_agent_docs.py 가 다시 복사합니다. 여기를 직접 고치면 다음 동기화 때 사라집니다.) -->\n\n"
)


def render(name: str) -> str:
    """원본 CLAUDE.md 본문 앞에 사본 머리말을 붙인 내용을 만든다."""
    body = SOURCE.read_text(encoding="utf-8")
    return HEADER.format(who=MIRRORS[name]) + body


def sync(check_only: bool = False) -> list[str]:
    """사본을 갱신한다. check_only 면 갱신 없이 어긋난 파일 이름만 돌려준다."""
    stale: list[str] = []
    if not SOURCE.exists():
        return list(MIRRORS)
    for name in MIRRORS:
        target = REPO_ROOT / name
        wanted = render(name)
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == wanted:
            continue
        stale.append(name)
        if not check_only:
            target.write_text(wanted, encoding="utf-8", newline="\n")
    return stale


def main(argv: list[str] | None = None) -> int:
    # 다른 스크립트가 import 해서 쓸 때 stdout 을 건드리지 않도록, 직접 실행일 때만 UTF-8 로 감싼다.
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass
    argv = sys.argv[1:] if argv is None else argv
    check_only = "--check" in argv
    stale = sync(check_only=check_only)
    if check_only:
        if stale:
            print(f"[어긋남] CLAUDE.md 와 다른 사본: {', '.join(stale)} → python scripts/sync_agent_docs.py")
            return 1
        print("[확인] AGENTS.md · GEMINI.md 가 CLAUDE.md 와 일치합니다.")
        return 0
    if stale:
        print(f"[완료] 사본 갱신: {', '.join(stale)}  (원본 = CLAUDE.md)")
    else:
        print("[완료] 사본 변경 없음 (이미 최신)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

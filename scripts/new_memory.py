#!/usr/bin/env python3
# ============================================================================
#  new_memory.py  —  새 메모리(.md) 한 장을 템플릿으로 만들어 준다
# ----------------------------------------------------------------------------
#  사용 예 (Claude 에게 "새 규칙 메모리 만들어줘"라고 하면 대신 실행해 줍니다):
#     python scripts/new_memory.py rule  보고서-먼저-목차부터
#     python scripts/new_memory.py decision  주간회고는-금요일오후
#     python scripts/new_memory.py feedback  장황한설명-금지
#
#  type 은 rule | decision | feedback | concept 중 하나.
#  만든 뒤에는 build_manifest.py 를 다시 돌려야 훅이 인식합니다.
# ============================================================================
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TYPE_TO_DIR = {
    "rule": "rules",
    "decision": "decisions",
    "feedback": "feedback",
    "concept": "concepts",
}

TEMPLATE = """\
---
name: {slug}
type: {mtype}
title: 한 줄 제목을 여기에 적으세요
keywords: [키워드1, 키워드2, 키워드3]
score: 10
updated: YYYY-MM-DD
---

# {title_placeholder}

<!-- 이 메모리가 '언제' 떠올라야 하는지가 keywords 입니다.
     위 keywords 중 하나라도 프롬프트에 들어오면 이 본문이 자동 주입됩니다. -->

여기에 규칙/결정/피드백 내용을 적으세요. 핵심은 짧게.

**왜:** (이 규칙이 왜 생겼는지 — 가장 중요)

**어떻게 적용:** (다음에 같은 상황에서 무엇을 다르게 할지)
"""


def main() -> None:
    if len(sys.argv) < 3:
        print("사용법: python scripts/new_memory.py <rule|decision|feedback|concept> <슬러그>")
        sys.exit(1)

    mtype, slug = sys.argv[1].lower(), sys.argv[2].strip()
    if mtype not in TYPE_TO_DIR:
        print(f"[오류] type 은 {list(TYPE_TO_DIR)} 중 하나여야 합니다. (입력: {mtype})")
        sys.exit(1)

    target_dir = REPO_ROOT / "memory" / TYPE_TO_DIR[mtype]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{slug}.md"
    if target.exists():
        print(f"[오류] 이미 있습니다: {target.relative_to(REPO_ROOT)}")
        sys.exit(1)

    target.write_text(
        TEMPLATE.format(slug=slug, mtype=mtype, title_placeholder="제목"),
        encoding="utf-8",
    )
    print(f"[완료] 생성: {target.relative_to(REPO_ROOT)}")
    print("       내용을 채운 뒤 'python scripts/build_manifest.py' 를 실행하세요.")


if __name__ == "__main__":
    main()

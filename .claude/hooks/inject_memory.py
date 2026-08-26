#!/usr/bin/env python3
# ============================================================================
#  inject_memory.py  —  UserPromptSubmit 훅: JIT(Just-In-Time) 메모리 주입
# ----------------------------------------------------------------------------
#  무엇을 하나:
#    - 사용자가 보낸 프롬프트를 읽는다.
#    - memory/_jit_manifest.json 에 등록된 각 메모리(atom)의 키워드 정규식과
#      프롬프트를 대조한다.
#    - 매칭된 메모리의 본문을 additionalContext 로 주입한다.
#      → Claude 가 "지금 이 대화에 관련된 우리 팀/내 규칙"을 알고 답하게 된다.
#
#  왜 이렇게(왜 > 어떻게):
#    - 모든 메모리를 항상 컨텍스트에 넣으면 토큰이 낭비되고 핵심이 묻힌다.
#    - "관련될 때만" 꺼내 주입하는 것이 JIT. 책 본문의 '회고 루프'가
#      쌓은 규칙을 실제 대화에 자동 연결하는 다리.
#
#  안전 원칙:
#    - 무슨 일이 있어도 exit 0. 훅이 실패해도 사용자 프롬프트 흐름을 막지 않는다.
#    - 외부 라이브러리 의존 없음(파이썬 표준 라이브러리만). 받아서 바로 동작.
# ============================================================================
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

# Windows 콘솔의 한글 깨짐 방지(표준 출력/에러를 UTF-8 로 강제)
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# 이 훅 파일 위치 기준으로 저장소 루트를 계산한다.
#   <root>/.claude/hooks/inject_memory.py  →  parents[2] == <root>
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "memory" / "_jit_manifest.json"
LOG_PATH = REPO_ROOT / "memory" / "_injection_log.txt"
GUARD_PATH = REPO_ROOT / "memory" / "_guard.json"

# 비용 가드(책 "비용 가드"): 매 호출에 자동으로 붙는 컨텍스트에 천장을 씌운다.
#   - MAX_MATCHES: 한 번에 주입할 최대 메모리 개수(개수 상한)
#   - MAX_BODY:    메모리 한 개당 최대 주입 길이(길이 상한)
# memory/_guard.json 이 있으면 그 값으로 덮어쓴다(없으면 아래 기본값).
MAX_MATCHES = 5
MAX_BODY = 6000
try:
    _g = json.loads(GUARD_PATH.read_text(encoding="utf-8"))
    MAX_MATCHES = int(_g.get("max_items", MAX_MATCHES))
    MAX_BODY = int(_g.get("max_chars", MAX_BODY))
except Exception:
    pass


def emit_empty() -> None:
    """주입할 것이 없으면 빈 출력으로 조용히 종료(흐름을 막지 않음)."""
    sys.exit(0)


def safe_log(hits: list[str], prompt: str) -> None:
    """어떤 메모리가 언제 주입됐는지 한 줄 로그. 실패해도 무시."""
    try:
        head = prompt[:80].replace("\n", " ")
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"hits: {' '.join(hits)} | prompt_head: {head}\n")
    except Exception:
        pass


def main() -> None:
    # 1) Claude Code 가 stdin 으로 넘긴 JSON 페이로드를 읽는다.
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return emit_empty()
        payload = json.loads(raw)
    except Exception:
        return emit_empty()

    prompt = payload.get("prompt", "") if isinstance(payload, dict) else ""
    if not prompt:
        return emit_empty()

    # 2) 매니페스트(등록된 메모리 목록)를 읽는다.
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        atoms = manifest.get("atoms", [])
    except Exception:
        return emit_empty()

    # 3) 점수 높은 순으로 보고, 프롬프트와 키워드 정규식이 맞으면 후보에 담는다.
    atoms = sorted(atoms, key=lambda a: a.get("score", 0), reverse=True)
    matches = []
    for atom in atoms:
        if len(matches) >= MAX_MATCHES:
            break
        try:
            if re.search(atom["regex"], prompt, re.IGNORECASE):
                matches.append(atom)
        except (re.error, KeyError):
            continue

    if not matches:
        return emit_empty()

    # 4) 매칭된 메모리 본문을 모아 주입 텍스트를 만든다.
    chunks, hits = [], []
    for atom in matches:
        try:
            body = (REPO_ROOT / atom["path"]).read_text(encoding="utf-8")
        except Exception:
            continue
        if len(body) > MAX_BODY:
            body = body[:MAX_BODY] + "\n\n[...이하 생략]\n"
        name = atom.get("name", "?")
        score = atom.get("score", 0)
        chunks.append(
            f"\n\n=== [메모리 주입] {name} (score {score}) ===\n\n"
            f"{body}\n\n=== /끝 {name} ===\n"
        )
        hits.append(name)

    if not chunks:
        return emit_empty()

    safe_log(hits, prompt)

    # 5) Claude Code 규약대로 additionalContext 로 돌려준다.
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "".join(chunks),
        }
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit_empty()

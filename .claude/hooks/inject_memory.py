#!/usr/bin/env python3
# ============================================================================
#  inject_memory.py  —  프롬프트 훅: JIT(Just-In-Time) 메모리 주입
# ----------------------------------------------------------------------------
#  어디서 도나 (같은 파일 하나로 네 곳 다 동작):
#    - Claude Code   : UserPromptSubmit  (.claude/settings.json)
#    - OpenAI Codex  : UserPromptSubmit  (.codex/hooks.json)
#    - Gemini CLI    : BeforeAgent       (.gemini/settings.json)
#    - Grok Build    : UserPromptSubmit  (.claude/settings.json 을 그대로 읽음)
#    네 도구 모두 stdin 으로 JSON 을 주고, stdout 의
#    hookSpecificOutput.additionalContext 를 컨텍스트로 붙이는 같은 규약을 쓴다.
#
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

# 비용 가드(책 8장 "비용 가드"): 매 호출에 자동으로 붙는 컨텍스트에 천장을 씌운다.
#   - max_matches:   한 번에 주입할 최대 메모리 개수(가드 A, 개수 상한)
#   - max_atom_body: 메모리 한 개당 최대 주입 길이(가드 B, 길이 상한)
# 기본값은 책 본문에 실린 값과 같다(3개 · 6000자).
# memory/_guard.json 이 있으면 그 값으로 덮어쓴다.
MAX_MATCHES = 3
MAX_BODY = 6000
try:
    _g = json.loads(GUARD_PATH.read_text(encoding="utf-8"))
    # 정식 키는 max_matches/max_atom_body. 예전 이름(max_items/max_chars)도 함께 받는다.
    MAX_MATCHES = int(_g.get("max_matches", _g.get("max_items", MAX_MATCHES)))
    MAX_BODY = int(_g.get("max_atom_body", _g.get("max_chars", MAX_BODY)))
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
    # 1) 에이전트가 stdin 으로 넘긴 JSON 페이로드를 읽는다.
    #    ⚠ 반드시 바이트로 읽어 UTF-8 로 해석한다. sys.stdin.read() 는 Windows 에서
    #      콘솔 기본 인코딩(cp949 등)으로 풀기 때문에, 한글 프롬프트가 깨져
    #      키워드 매칭이 조용히 실패한다(실측: 2026-09-05, Python 3.10/Windows).
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        if not raw.strip():
            return emit_empty()
        payload = json.loads(raw)
    except Exception:
        return emit_empty()
    if not isinstance(payload, dict):
        return emit_empty()

    # 도구마다 필드 이름이 조금씩 다를 수 있어 넓게 받는다.
    #   Claude Code / Codex / Gemini CLI = "prompt"
    prompt = ""
    for key in ("prompt", "user_prompt", "userPrompt", "message"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            prompt = val
            break
    if not prompt:
        return emit_empty()

    # 들어온 이벤트 이름을 그대로 돌려준다(Gemini CLI 는 BeforeAgent, 나머지는 UserPromptSubmit).
    event_name = (
        payload.get("hook_event_name")
        or payload.get("hookEventName")
        or "UserPromptSubmit"
    )

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

    # 5) 공통 규약대로 additionalContext 로 돌려준다.
    #    (stdout 에는 이 JSON 외에 아무것도 찍지 않는다 — 로그는 파일로만.)
    output = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": "".join(chunks),
        }
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False))
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit_empty()

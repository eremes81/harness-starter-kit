#!/usr/bin/env python3
# ============================================================================
#  kit_selfcheck.py  —  키트 무결성 · 이식성 자체 검사 (받은 그대로 도는가?)
# ----------------------------------------------------------------------------
#  무엇을 검사하나 (전부 표준 라이브러리, 네트워크 없음):
#    1. 문법      : 키트 안의 모든 .py 가 컴파일되는가
#    2. 설정      : 에이전트별 설정(.claude/.codex/.gemini)이 올바른 JSON 이고
#                   가리키는 훅 파일이 실제로 있는가
#    3. 훅 E2E    : 네 에이전트(Claude Code · Codex · Gemini CLI · Grok Build)가
#                   보내는 모양의 JSON 을 stdin 으로 넣었을 때 관련 메모리가 주입되는가
#                   — 한글 프롬프트 · UTF-8 · Windows 기본 인코딩 그대로
#    4. 결정성    : 임시 사본에서 매니페스트를 다시 만들었을 때 지금 파일과 같은가
#    5. 사본 동기 : AGENTS.md · GEMINI.md 가 CLAUDE.md 와 일치하는가
#    6. 자동 블록 : CLAUDE.md 의 "자주 적용되는 규칙" 이 매니페스트 상위와 같은가
#    7. 공개 게이트: 메일주소·전화번호·개인 홈 경로 등이 섞여 있지 않은가
#    8. 표준 라이브러리 : 외부 패키지 import 가 문서화된 것 외에 없는가
#    9. 실행기    : python / python3 중 무엇이 있는가 (정보)
#
#  사용법:
#    python scripts/kit_selfcheck.py             # 전부 검사, 실패가 있으면 종료코드 1
#    python scripts/kit_selfcheck.py --terms 파일  # 공개 게이트에 금칙어 목록(한 줄 하나) 추가
#
#  이 스크립트는 키트 파일을 바꾸지 않는다(임시 폴더에서만 재생성).
# ============================================================================
from __future__ import annotations

import io
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROMPT = "이번 주 회고 좀 도와줄래?"   # README "동작 확인 30초" 와 같은 문장
EXPECT_ATOM = "주간회고-금요일오후"           # 그 문장에 딸려 나와야 하는 메모리

# 에이전트별 stdin 모양(공식 문서 기준). 이벤트 이름이 다른 건 Gemini 뿐.
CONTRACTS = {
    "Claude Code": {"hook_event_name": "UserPromptSubmit", "prompt": SAMPLE_PROMPT, "cwd": "."},
    "OpenAI Codex": {"hook_event_name": "UserPromptSubmit", "prompt": SAMPLE_PROMPT, "turn_id": "t1"},
    "Gemini CLI": {"hook_event_name": "BeforeAgent", "prompt": SAMPLE_PROMPT, "session_id": "s1"},
    "Grok Build": {"hookEventName": "UserPromptSubmit", "prompt": SAMPLE_PROMPT, "workspaceRoot": "."},
}

CONFIGS = {
    ".claude/settings.json": ["hooks", "UserPromptSubmit"],
    ".codex/hooks.json": ["hooks", "UserPromptSubmit"],
    ".gemini/settings.json": ["hooks", "BeforeAgent"],
}

# 외부 패키지 import 가 허용된 파일(파일 머리에 pip install 안내가 있는 것 — 책 「코드 색인」과 일치)
DOCUMENTED_EXTERNAL = {
    "6장/card_graph.py": {"networkx"},
    "8장/build_cache.py": {"pandas", "openpyxl"},
}
# 있으면 쓰고 없어도 도는 패키지: import 가 try/except 로 감싸져 있어야 통과
OPTIONAL_IF_GUARDED = {"yaml"}

# 공개 게이트 기본 패턴 (예시 도메인은 허용)
GATE_PATTERNS = [
    ("이메일 주소", re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("휴대전화 번호", re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b")),
    ("개인 홈 경로", re.compile(r"(?:[A-Za-z]:\\Users\\[^\\\s]+|/Users/[^/\s]+|/home/[^/\s]+)")),
]
GATE_SKIP_DIRS = {".git", "__pycache__"}
GATE_SKIP_FILES = {"memory/_injection_log.txt", "scripts/kit_selfcheck.py"}  # 검사 패턴 자체는 제외

results: list[tuple[str, str, str]] = []   # (상태, 항목, 설명)


def ok(item: str, note: str = "") -> None:
    results.append(("PASS", item, note))


def fail(item: str, note: str = "") -> None:
    results.append(("FAIL", item, note))


def info(item: str, note: str = "") -> None:
    results.append(("INFO", item, note))


def py_files() -> list[Path]:
    out = []
    for p in REPO_ROOT.rglob("*.py"):
        if any(part in GATE_SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


def rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT)).replace("\\", "/")


def clean_env() -> dict:
    """사용자 환경의 UTF-8 강제 설정을 지운 '맨몸' 환경 — 받는 사람 PC 와 같은 조건."""
    env = dict(os.environ)
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    return env


# 1. 문법 -------------------------------------------------------------------
def check_compile() -> None:
    bad = []
    for p in py_files():
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{rel(p)}: {e}")
    if bad:
        fail("1 문법(py_compile)", "; ".join(bad))
    else:
        ok("1 문법(py_compile)", f"{len(py_files())}개 파일")


# 2. 설정 -------------------------------------------------------------------
def check_configs() -> None:
    for name, path in CONFIGS.items():
        f = REPO_ROOT / name
        if not f.exists():
            fail(f"2 설정 {name}", "파일 없음")
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            fail(f"2 설정 {name}", f"JSON 오류: {e}")
            continue
        node = data
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if not node:
            fail(f"2 설정 {name}", f"{'.'.join(path)} 항목 없음")
            continue
        # 명령이 가리키는 훅 파일이 실제로 있는지
        missing = []
        for entry in node:
            for h in entry.get("hooks", []):
                for cmd_key in ("command", "commandWindows"):
                    cmd = h.get(cmd_key, "")
                    for token in re.findall(r"\.claude/hooks/\w+\.py", cmd):
                        if not (REPO_ROOT / token).exists():
                            missing.append(token)
        if missing:
            fail(f"2 설정 {name}", f"없는 훅 파일 참조: {sorted(set(missing))}")
        else:
            ok(f"2 설정 {name}", "JSON · 훅 경로 OK")


# 3. 훅 E2E -----------------------------------------------------------------
def run_hook(script: str, payload: dict) -> tuple[dict | None, str]:
    p = subprocess.run(
        [sys.executable, str(REPO_ROOT / script)],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True, env=clean_env(), cwd=str(REPO_ROOT), timeout=30,
    )
    out = p.stdout.decode("utf-8", errors="replace")
    if not out.strip():
        return None, f"출력 없음 (rc={p.returncode}, stderr={p.stderr[:120]!r})"
    try:
        return json.loads(out), ""
    except Exception as e:  # noqa: BLE001
        return None, f"JSON 아님: {e}: {out[:80]!r}"


def check_hooks_e2e() -> None:
    log = REPO_ROOT / "memory" / "_injection_log.txt"
    had_log = log.exists()
    for agent, payload in CONTRACTS.items():
        data, err = run_hook(".claude/hooks/inject_memory.py", payload)
        if data is None:
            fail(f"3 훅 E2E {agent}", err)
            continue
        h = data.get("hookSpecificOutput", {})
        want_event = payload.get("hook_event_name") or payload.get("hookEventName")
        if h.get("hookEventName") != want_event:
            fail(f"3 훅 E2E {agent}", f"이벤트 이름 불일치: {h.get('hookEventName')} ≠ {want_event}")
        elif EXPECT_ATOM not in h.get("additionalContext", ""):
            fail(f"3 훅 E2E {agent}", f"'{EXPECT_ATOM}' 가 주입되지 않음")
        else:
            ok(f"3 훅 E2E {agent}", f"{want_event} → {len(h['additionalContext'])}자 주입")
    # SessionStart (회고 알림) — 출력이 없거나 올바른 JSON 이면 통과
    data, err = run_hook(".claude/hooks/retro_check.py", {"hook_event_name": "SessionStart", "source": "startup"})
    if data is None and "출력 없음" not in err:
        fail("3 훅 E2E SessionStart(retro_check)", err)
    else:
        ok("3 훅 E2E SessionStart(retro_check)", "조용히 종료" if data is None else "회고 알림 주입")
    # 검사로 생긴 로그는 되돌린다
    if not had_log and log.exists():
        try:
            log.unlink()
        except Exception:
            pass


# 4. 결정성 -----------------------------------------------------------------
def check_determinism() -> None:
    watch = ["memory/_jit_manifest.json", "CLAUDE.md", "AGENTS.md", "GEMINI.md"]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "kit"
        shutil.copytree(REPO_ROOT, tmp, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        p = subprocess.run([sys.executable, str(tmp / "scripts" / "build_manifest.py")],
                           capture_output=True, env=clean_env(), cwd=str(tmp), timeout=60)
        if p.returncode != 0:
            fail("4 결정성(build_manifest)", f"rc={p.returncode} {p.stderr.decode('utf-8', 'replace')[:200]}")
            return
        diff = [w for w in watch
                if (tmp / w).read_bytes() != (REPO_ROOT / w).read_bytes()]
    if diff:
        fail("4 결정성(build_manifest)", f"재생성 결과가 현재 파일과 다름: {diff} → python scripts/build_manifest.py 실행 후 커밋")
    else:
        ok("4 결정성(build_manifest)", "재생성 = 현재 파일")


# 5. 사본 동기 ---------------------------------------------------------------
def check_mirrors() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import sync_agent_docs  # type: ignore
        stale = sync_agent_docs.sync(check_only=True)
    except Exception as e:  # noqa: BLE001
        fail("5 사본 동기(AGENTS/GEMINI)", f"검사 실패: {e}")
        return
    if stale:
        fail("5 사본 동기(AGENTS/GEMINI)", f"어긋남: {stale}")
    else:
        ok("5 사본 동기(AGENTS/GEMINI)", "CLAUDE.md 와 일치")


# 6. 자동 블록 ---------------------------------------------------------------
def check_hot_block() -> None:
    try:
        atoms = json.loads((REPO_ROOT / "memory" / "_jit_manifest.json").read_text(encoding="utf-8"))["atoms"]
        text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        fail("6 자동 블록(CLAUDE.md)", str(e))
        return
    m = re.search(r"<!-- BEGIN_HOT_AUTO -->(.*?)<!-- END_HOT_AUTO -->", text, re.S)
    if not m:
        fail("6 자동 블록(CLAUDE.md)", "표식 없음")
        return
    listed = re.findall(r"^- \*\*(\d+)\*\*", m.group(1), re.M)
    top = [str(a["score"]) for a in sorted(atoms, key=lambda a: a["score"], reverse=True)[:8]]
    if listed != top:
        fail("6 자동 블록(CLAUDE.md)", f"점수열 불일치: 블록 {listed} ≠ 매니페스트 {top}")
    else:
        ok("6 자동 블록(CLAUDE.md)", f"상위 {len(listed)}개 일치")


# 7. 공개 게이트 -------------------------------------------------------------
def check_public_gate(extra_terms: list[str]) -> None:
    hits = []
    patterns = list(GATE_PATTERNS) + [(f"금칙어 '{t}'", re.compile(re.escape(t))) for t in extra_terms if t]
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file() or any(part in GATE_SKIP_DIRS for part in p.parts):
            continue
        if rel(p) in GATE_SKIP_FILES:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue  # 바이너리 등
        for label, rx in patterns:
            for m in rx.finditer(text):
                hits.append(f"{rel(p)}: {label} '{m.group(0)[:40]}'")
    if hits:
        fail("7 공개 게이트", " | ".join(hits[:8]) + (" …" if len(hits) > 8 else ""))
    else:
        ok("7 공개 게이트", f"메일·전화·홈경로 0건 (금칙어 {len(extra_terms)}개 추가 검사)")


# 8. 표준 라이브러리 -----------------------------------------------------------
def check_stdlib_only() -> None:
    std = getattr(sys, "stdlib_module_names", None)
    if not std:
        info("8 표준 라이브러리", "Python 3.10+ 에서만 검사 가능")
        return
    offenders = []
    for p in py_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        mods = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w]*)", text, re.M))
        allowed = DOCUMENTED_EXTERNAL.get(rel(p), set())
        local = {"sync_agent_docs"}  # 키트 안 스크립트끼리의 import
        ext = {m for m in mods if m not in std and m not in allowed and m not in local}
        for m in list(ext):
            # try: 블록 안의 선택적 import(PyYAML 등)는 없어도 동작하므로 허용
            if m in OPTIONAL_IF_GUARDED and re.search(
                    r"try:\s*
(?:[^
]*
){0,3}?\s*import " + re.escape(m) + r"", text):
                ext.discard(m)
        if ext:
            offenders.append(f"{rel(p)}: {sorted(ext)}")
    if offenders:
        fail("8 표준 라이브러리", "; ".join(offenders))
    else:
        ok("8 표준 라이브러리", f"필수 외부 패키지 없음 (파일 머리에 문서화된 예외 {sum(len(v) for v in DOCUMENTED_EXTERNAL.values())}건 · 선택적 PyYAML 허용)")


# 9. 실행기 ------------------------------------------------------------------
def check_launchers() -> None:
    found = [n for n in ("python", "python3") if shutil.which(n)]
    info("9 실행기", f"이 PC: {', '.join(found) or '없음'} / 설정은 python → python3 순으로 시도")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    extra_terms: list[str] = []
    if "--terms" in argv:
        i = argv.index("--terms")
        if i + 1 < len(argv):
            try:
                extra_terms = [ln.strip() for ln in Path(argv[i + 1]).read_text(encoding="utf-8").splitlines()
                               if ln.strip() and not ln.startswith("#")]
            except Exception as e:  # noqa: BLE001
                print(f"[!] 금칙어 파일을 읽지 못함: {e}")
    print(f"하네스 스타터 키트 자체검사 — {REPO_ROOT}")
    print(f"Python {sys.version.split()[0]} · {sys.platform}\n")
    check_compile()
    check_configs()
    check_hooks_e2e()
    check_determinism()
    check_mirrors()
    check_hot_block()
    check_public_gate(extra_terms)
    check_stdlib_only()
    check_launchers()

    width = max(len(r[1]) for r in results)
    for status, item, note in results:
        mark = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️ "}[status]
        print(f"{mark} {item.ljust(width)}  {note}")
    fails = sum(1 for r in results if r[0] == "FAIL")
    passes = sum(1 for r in results if r[0] == "PASS")
    print(f"\n결과: PASS {passes} · FAIL {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

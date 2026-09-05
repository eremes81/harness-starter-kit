#!/usr/bin/env python3
# ============================================================================
#  build_manifest.py  —  memory/ 안의 메모리(.md)를 스캔해 _jit_manifest.json 생성
# ----------------------------------------------------------------------------
#  무엇을 하나:
#    - memory/{rules,decisions,feedback,concepts}/*.md 를 모두 읽는다.
#    - 각 파일 맨 위 YAML frontmatter(name/keywords/score 등)를 파싱한다.
#    - keywords 를 정규식으로 바꿔 memory/_jit_manifest.json 을 다시 쓴다.
#      → 이 매니페스트를 inject_memory.py 훅이 읽어 JIT 주입한다.
#
#  언제 실행하나:
#    - 새 메모리를 추가/수정했을 때. Claude 에게 "매니페스트 다시 만들어줘"
#      라고 하면 이 스크립트를 대신 실행해 줍니다. (터미널 직접 사용 불필요)
#
#  의존성: 파이썬 표준 라이브러리만. (PyYAML 등 설치 불필요)
# ============================================================================
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = REPO_ROOT / "memory"
MANIFEST_PATH = MEMORY_DIR / "_jit_manifest.json"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
HOT_TOP_N = 8  # CLAUDE.md 상단에 자동 노출할 상위 규칙 개수

# 스캔 대상 카테고리(폴더). 책의 메모리 분류와 일치.
CATEGORIES = ["rules", "decisions", "feedback", "concepts"]

# 스캔할 메모리 루트. 개인 memory/ 와 (있으면) 팀 공유 team_memory/atoms/ 를
# 하나의 색인으로 합친다. 두 곳 다 훅이 자동 주입한다.
MEMORY_ROOTS = [
    ("personal", MEMORY_DIR),
    ("team", REPO_ROOT / "team_memory" / "atoms"),
]


def parse_frontmatter(text: str) -> dict:
    """파일 맨 위 '--- ... ---' YAML 블록을 아주 단순하게 파싱한다.

    지원: 한 줄 스칼라(name: x), 인라인 리스트(keywords: [a, b, c]).
    표준 라이브러리만으로 처리하려고 의도적으로 단순하게 만들었다.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    meta: dict = {}
    for line in block.splitlines():
        line = line.rstrip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            items = [v.strip().strip("'\"") for v in val[1:-1].split(",")]
            meta[key] = [v for v in items if v]
        else:
            meta[key] = val.strip("'\"")
    return meta


def build_regex(keywords: list[str]) -> str:
    """키워드 목록을 (a|b|c) 형태의 정규식 문자열로 만든다."""
    escaped = [re.escape(k) for k in keywords if k]
    return "(" + "|".join(escaped) + ")" if escaped else ""


def main() -> None:
    atoms = []
    for scope, root in MEMORY_ROOTS:
        for cat in CATEGORIES:
            cat_dir = root / cat
            if not cat_dir.is_dir():
                continue
            for md in sorted(cat_dir.glob("*.md")):
                meta = parse_frontmatter(md.read_text(encoding="utf-8"))
                keywords = meta.get("keywords") or []
                if isinstance(keywords, str):
                    keywords = [keywords]
                regex = build_regex(keywords)
                if not regex:
                    print(f"  [건너뜀] keywords 없음 → {md.name}")
                    continue
                atoms.append({
                    "name": meta.get("name", md.stem),
                    "scope": scope,
                    "title": meta.get("title", ""),
                    "regex": regex,
                    "path": str(md.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "score": int(float(meta.get("score", 10))),
                })

    atoms.sort(key=lambda a: a["score"], reverse=True)
    MANIFEST_PATH.write_text(
        json.dumps({"atoms": atoms}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[완료] 메모리 {len(atoms)}개 등록 → {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    for a in atoms:
        tag = "[팀]" if a["scope"] == "team" else "[개인]"
        print(f"   - {a['score']:>3} {tag} {a['name']}  {a['regex']}")

    update_hot_block(atoms)
    sync_mirror_docs()


def sync_mirror_docs() -> None:
    """CLAUDE.md 를 AGENTS.md(Codex·Grok 등) · GEMINI.md(Gemini CLI) 로 복사한다.
    지침 파일 이름만 다를 뿐 내용은 하나여야 하므로, 여기서 항상 같이 갱신한다."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sync_agent_docs import sync
        stale = sync()
        if stale:
            print(f"[완료] 지침 사본 갱신: {', '.join(stale)} (원본 = CLAUDE.md)")
    except Exception as e:  # 사본 동기화 실패가 매니페스트 생성을 막지는 않는다
        print(f"[주의] 지침 사본 동기화 실패: {e} → python scripts/sync_agent_docs.py")


def update_hot_block(atoms: list) -> None:
    """CLAUDE.md 의 <!-- BEGIN_HOT_AUTO -->..<!-- END_HOT_AUTO --> 사이를
    점수 상위 규칙 목록으로 교체한다. 자가개선 루프를 눈에 보이게 만드는 부분."""
    if not CLAUDE_MD.exists():
        return
    text = CLAUDE_MD.read_text(encoding="utf-8")
    begin, end = "<!-- BEGIN_HOT_AUTO -->", "<!-- END_HOT_AUTO -->"
    if begin not in text or end not in text:
        return
    lines = []
    for a in atoms[:HOT_TOP_N]:
        tag = "팀" if a["scope"] == "team" else "개인"
        title = a.get("title") or a["name"]
        lines.append(f"- **{a['score']}** ({tag}) — {title}")
    block = begin + "\n" + "\n".join(lines) + "\n" + end
    new = re.sub(re.escape(begin) + r".*?" + re.escape(end), block, text, flags=re.S)
    CLAUDE_MD.write_text(new, encoding="utf-8")
    print(f"[완료] CLAUDE.md 자주 적용 규칙 {min(HOT_TOP_N, len(atoms))}개 자동 갱신")


if __name__ == "__main__":
    main()

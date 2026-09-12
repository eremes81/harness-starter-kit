#!/usr/bin/env python3
# pip install networkx
# ============================================================================
#  card_graph.py  —  카드 관계 그래프 검사: 순환 의존·고아 카드·깨진 링크
#  책 6장의 전체 실행본 (카드 관계 그래프 검사: 순환 의존·고아 카드·깨진 링크)
# ----------------------------------------------------------------------------
#  왜:
#    - 카드가 수백 장으로 늘면 '서로 물고 도는 관계'(순환 의존)는 머리로 못 잡는다.
#    - 아무도 가리키지 않는 고아 카드, 존재하지 않는 카드를 가리키는 깨진 링크가 쌓인다.
#    → 카드를 노드로, 관계를 엣지로 방향 그래프를 만들면 셋 다 함수 호출로 찾아낸다.
#
#  서브커맨드 (Claude에게 "카드 그래프 검사해줘 / 이 카드 역참조 찾아줘"라고 하면 대신 실행):
#    check   카드 폴더 전체 검사 (순환 의존·고아 카드·깨진 링크)
#    impact  카드 ID 하나의 역참조 — 그래프의 반대 방향을 훑어
#            "이 카드를 바꾸면 어떤 카드를 다시 봐야 하는가"의 후보 목록을 띄운다
#
#  읽는 카드: 결정·규칙 카드(.yaml/.yml/.md). 관계는 두 곳에서 모은다.
#    ① 카드의 관계 필드 — supersedes / relates_to / affects / requires / ...
#    ② 본문의 명시 링크 — [[카드ID]]  (실제 카드 목록에 없는 이름 = 깨진 링크)
#
#  원칙: 도구는 이상 징후와 검토 후보를 찾아 줄 뿐이다. '아무도 가리키지 않는 카드'가
#        반드시 쓸모없는 카드는 아니므로, 관계와 상태의 최종 변경은 사람이 결정한다.
#        (이 스크립트는 리포트만 출력하고 어떤 파일도 고치지 않는다.)
#
#  의존성: networkx (파일 머리의 pip 한 줄). 그 외는 파이썬 표준 라이브러리만.
# ============================================================================
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

if importlib.util.find_spec("networkx") is None:
    sys.stderr.write("[!] networkx가 없습니다. 먼저 설치하세요: pip install networkx\n")
    sys.exit(2)

# ── 책 발췌 구간 (그대로) ────────────────────────────────────────────────────
import networkx as nx
# G: 카드를 노드로,
# affects/requires/... 관계를 엣지로 만든 방향 그래프
def find_cycles(G):           # 순환 의존 (A→B→C→A)
    return list(nx.simple_cycles(G))
def find_orphans(G):          # 아무도 안 가리키는 고아 카드 = 폐기 후보
    return [n for n in G.nodes if G.in_degree(n) == 0]
# ── 발췌 끝. 아래는 실제 카드 폴더에서 그래프 G를 만드는 부분 ────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = str(REPO_ROOT / "governance" / "decisions")

# 엣지로 인정하는 관계 필드 (작성자가 관계를 직접 적어 둔 의미적 연결)
REL_KEYS = ("supersedes", "superseded_by", "relates_to", "affects",
            "requires", "conflicts_with", "depends_on", "blocks")

FRONTMATTER_RX = re.compile(r"^---\s*\n(.*?)\n---\s*$", re.DOTALL | re.MULTILINE)
LIST_REL_RX = re.compile(rf"^\s*-\s*({'|'.join(REL_KEYS)})\s*:\s*(.+)$")
INLINE_REL_RX = re.compile(rf"^({'|'.join(REL_KEYS)})\s*:\s*(.+)$")
BLOCK_KEY_RX = re.compile(rf"^({'|'.join(REL_KEYS)})\s*:\s*(?:#.*)?$")
ANY_KEY_RX = re.compile(r"^[A-Za-z_]+\s*:")
LIST_ITEM_RX = re.compile(r"^\s+-\s*(.+)$")
WIKI_LINK_RX = re.compile(r"\[\[([^\[\]]+)\]\]")


def _clean(raw: str) -> str:
    """값 뒤 주석·따옴표·쉼표를 벗긴다. 템플릿 자리표시(D...)면 빈 문자열."""
    val = re.sub(r"\s+#.*$", "", raw).strip().strip(",").strip("\"'").strip()
    if not val or val.endswith("..."):
        return ""
    return val


def _card_block(text: str) -> str:
    """--- ... --- 프런트매터가 있으면 그 블록, 없으면 전문."""
    m = FRONTMATTER_RX.search(text)
    return m.group(1) if m else text


def _relations(block: str):
    """관계 필드를 (관계이름, 대상ID) 목록으로 모은다. 주석 줄은 관계가 아니다."""
    rels, pending = [], None
    for raw in block.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if m := LIST_REL_RX.match(raw):          # - supersedes: D...
            pending = None
            if t := _clean(m.group(2)):
                rels.append((m.group(1), t))
        elif m := BLOCK_KEY_RX.match(stripped):  # affects:  (값은 다음 줄 리스트)
            pending = m.group(1)
        elif m := INLINE_REL_RX.match(stripped):  # affects: D...
            pending = None
            if t := _clean(m.group(2)):
                rels.append((m.group(1), t))
        elif pending and (m := LIST_ITEM_RX.match(raw)):  #   - D...
            if t := _clean(m.group(1)):
                rels.append((pending, t))
        elif ANY_KEY_RX.match(stripped):         # 다른 키 시작 → 리스트 종료
            pending = None
    return rels


def _field(block: str, key: str) -> str:
    m = re.search(rf"^{key}\s*:\s*([^#\n]+)", block, re.MULTILINE)
    return m.group(1).strip().strip("\"'") if m else ""


def build_graph(decisions_dir: str):
    """카드 폴더를 읽어 (그래프 G, 카드 메타, 관계 목록, 깨진 링크)를 만든다."""
    cards, rels = {}, []
    for name in sorted(os.listdir(decisions_dir)):
        if not name.lower().endswith((".yaml", ".yml", ".md")):
            continue
        text = Path(decisions_dir, name).read_text(encoding="utf-8", errors="ignore")
        block = _card_block(text)
        cid = _field(block, "decision_id") or os.path.splitext(name)[0]
        cards[cid] = {"file": name, "status": _field(block, "status") or "unknown"}
        rels += [(cid, k, t) for k, t in _relations(block)]
        # 본문의 명시 링크 [[...]]도 엣지 후보 (자기 자신 링크는 제외)
        rels += [(cid, "link", t) for t in WIKI_LINK_RX.findall(text)
                 if _clean(t) and _clean(t) != cid]
    G = nx.DiGraph()
    G.add_nodes_from(cards)
    broken = []
    for src, key, target in rels:
        if target in cards:
            G.add_edge(src, target)
        else:
            broken.append((src, key, target))  # 실제 카드 목록에 없는 이름
    return G, cards, rels, broken


def _load(args):
    if not os.path.isdir(args.dir):
        sys.stderr.write(f"[!] 카드 폴더 없음: {args.dir}\n")
        sys.exit(2)
    return build_graph(args.dir)


def cmd_check(args) -> int:
    G, cards, _rels, broken = _load(args)
    print(f"# 카드 그래프 검사: {args.dir}")
    print(f"  카드(노드) {G.number_of_nodes()}장 · 관계(엣지) {G.number_of_edges()}개")

    cycles = find_cycles(G)
    print(f"\n[1] 순환 의존 — 서로 물고 도는 관계 ({len(cycles)}건)")
    for cyc in cycles:
        print("  " + " → ".join(cyc + [cyc[0]]))
    if not cycles:
        print("  (없음)")

    orphans = sorted(find_orphans(G))
    print(f"\n[2] 고아 카드 — 아무도 가리키지 않음 ({len(orphans)}건)")
    for n in orphans:
        print(f"  {n}  (status={cards[n]['status']}, file={cards[n]['file']})")
    if orphans:
        print("  ※ 고아 = 폐기 '후보'일 뿐. 독립적으로 의미 있는 정책일 수 있다.")
    else:
        print("  (없음)")

    print(f"\n[3] 깨진 링크 — 존재하지 않는 카드를 가리킴 ({len(broken)}건)")
    for src, key, target in broken:
        print(f"  {src} --{key}--> {target}  (카드 없음)")
    if not broken:
        print("  (없음)")

    total = len(cycles) + len(orphans) + len(broken)
    if total:
        print(f"\n[!] 검토 후보 {total}건. 도구는 후보를 찾을 뿐 — 관계·상태의 최종 변경은 사람이 결정한다.")
    else:
        print("\n[OK] 이상 징후 없음 (순환 0 · 고아 0 · 깨진 링크 0).")
    return 0


def cmd_impact(args) -> int:
    G, _cards, rels, _broken = _load(args)
    cid = args.id
    if cid not in G:
        sys.stderr.write(f"[!] 카드 없음: {cid} — ID가 한 글자라도 틀리면 역참조는 0건이 된다.\n")
        return 2
    preds = sorted(G.predecessors(cid))
    print(f"# 역참조: \"{cid}\" 를 가리키는 카드 (그래프의 반대 방향)")
    for p in preds:
        keys = sorted({k for s, k, t in rels if s == p and t == cid})
        print(f"  {p}  ({', '.join(keys)})")
    if not preds:
        print("  (없음 — 이 카드를 가리키는 카드가 없다.)")
        return 0
    print(f"\n[=] {len(preds)}장이 이 카드를 참조 = 이 카드를 바꾸면 다시 봐야 할 후보.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="card_graph",
                                description="카드 관계 그래프 검사 — 순환 의존·고아 카드·깨진 링크 (networkx)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="폴더 전체 검사 (순환·고아·깨진 링크)")
    pc.add_argument("--dir", default=DEFAULT_DIR)
    pc.set_defaults(func=cmd_check)

    pi = sub.add_parser("impact", help="카드 ID의 역참조 (이걸 바꾸면 어디를 다시 보나)")
    pi.add_argument("id")
    pi.add_argument("--dir", default=DEFAULT_DIR)
    pi.set_defaults(func=cmd_impact)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

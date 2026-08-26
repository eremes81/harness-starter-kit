#!/usr/bin/env python3
# ============================================================================
#  decision_track.py  —  결정 카드 박제 + grep 영향 역추적 (책 "의사결정 추적")
# ----------------------------------------------------------------------------
#  왜:
#    - "전에 이거 결정했었나?"를 못 찾아 같은 논의를 반복한다.
#    - 결정의 근거(rationale)·책임자(owner)가 회의록 한 줄로만 남아 6개월 뒤 사라진다.
#    - 한 결정을 바꿀 때 "어디가 흔들리나"를 사람 기억에 의존한다.
#    → 결정을 카드(YAML)로 박제하고, ID로 grep 역추적하면 이 셋이 해결된다.
#
#  서브커맨드 (Claude에게 "결정 카드 만들어줘 / 이 결정 영향 추적해줘"라고 하면 대신 실행):
#    new    새 결정 카드 생성 (필수 5칸: id·title·status·owner·rationale)
#    find   새 결정 전, 같은 주제 과거 결정 검색 (중복·충돌 점검)
#    trace  결정 ID로 영향 범위 역추적 ("이걸 바꾸면 어디가 흔들리나")
#    index  결정 폴더를 스캔해 _index.json 갱신 (status 집계)
#
#  의존성: 파이썬 표준 라이브러리만. (PyYAML 있으면 파싱이 더 견고하나 없어도 동작)
# ============================================================================
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
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

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = str(REPO_ROOT / "governance" / "decisions")

CARD_TEMPLATE = """\
---
# === 필수 5칸 (회의 직후 바로 채운다) ===
decision_id: {decision_id}
title: {title}
status: active            # active / superseded / deprecated
owner: {owner}            # 이 결정을 책임지는 사람(발의·소유자). 비면 [MISSING]
rationale:
  - {rationale}           # 6개월 뒤 "왜 그랬지?"에 답하는 칸. 여러 줄 가능.

# === 선택 (구현 단계에서 채운다. 비워둬도 카드는 살아 있다) ===
created: {created}
scope: []                 # 이 결정이 닿는 범위(사람·문서·시스템)
content: |
  (결정 내용을 한두 문장으로. 예외가 있으면 여기 명시.)
affected_files: []        # 영향받는 파일/문서. 모르면 "[확인 필요]".
related_decisions:        # 그래프 간선. 실제 ID만, 추측 금지.
  # - supersedes: D...    # 이 결정이 대체한 과거 결정
  # - relates_to: D...    # 관련 결정
---
"""


def _today() -> str:
    return _dt.date.today().isoformat()


def _quarter(date_str: str) -> str:
    try:
        d = _dt.date.fromisoformat(date_str)
    except Exception:
        return "Q?"
    return f"Q{(d.month - 1) // 3 + 1}"


def _next_seq(decisions_dir: str, year: str, quarter: str) -> int:
    if not os.path.isdir(decisions_dir):
        return 1
    pat = re.compile(rf"D{year}_{quarter}_(\d+)", re.IGNORECASE)
    seqs = [int(m.group(1)) for name in os.listdir(decisions_dir)
            if (m := pat.search(name))]
    return (max(seqs) + 1) if seqs else 1


def cmd_new(args) -> int:
    created = args.created or _today()
    did = args.id
    if not did:
        did = f"D{created[:4]}_{_quarter(created)}_{_next_seq(args.dir, created[:4], _quarter(created)):03d}"
    card = CARD_TEMPLATE.format(
        decision_id=did, title=args.title or "(제목 미정)",
        owner=args.owner or "[MISSING]", rationale=args.rationale or "(근거 미정)",
        created=created,
    )
    if args.stdout:
        sys.stdout.write(card)
        return 0
    os.makedirs(args.dir, exist_ok=True)
    out = os.path.join(args.dir, f"{did}.yaml")
    if os.path.exists(out) and not args.force:
        sys.stderr.write(f"[!] 이미 존재: {out} (덮어쓰려면 --force)\n")
        return 2
    Path(out).write_text(card, encoding="utf-8")
    print(f"[OK] 결정 카드 생성: {out}")
    print(f"     decision_id = {did}  → 필수 5칸(특히 owner·rationale)을 먼저 확정하세요.")
    return 0


def _search(roots, pattern, exts):
    """rg 있으면 rg, 없으면 표준 라이브러리로 파일을 훑어 매칭 경로 반환."""
    if shutil.which("rg"):
        cmd = ["rg", "-l", "-i", pattern]
        for e in exts:
            cmd += ["--glob", f"*.{e}"]
        cmd += list(roots)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return [ln for ln in res.stdout.splitlines() if ln.strip()], "rg"
        except Exception:
            pass
    rx = re.compile(re.escape(pattern), re.IGNORECASE)
    ext_set = {"." + e.lower() for e in exts}
    hits = []
    for root in roots:
        paths = [root] if os.path.isfile(root) else [
            os.path.join(dp, f) for dp, _d, fs in os.walk(root) for f in fs]
        for p in paths:
            if ext_set and os.path.splitext(p)[1].lower() not in ext_set:
                continue
            try:
                if rx.search(Path(p).read_text(encoding="utf-8", errors="ignore")):
                    hits.append(p)
            except Exception:
                continue
    return hits, "python"


def cmd_find(args) -> int:
    roots = args.roots or [args.dir]
    exts = [e.strip(".") for e in args.ext.split(",") if e.strip()]
    hits, engine = _search(roots, args.term, exts)
    print(f"# 과거 결정 검색: \"{args.term}\"  (engine={engine})")
    if not hits:
        print("  (매칭 없음 — 같은 주제 과거 결정이 안 보입니다.)")
        return 0
    for h in hits:
        print(f"  {h}")
    print(f"\n[!] {len(hits)}건 매칭. 새 결정이 이들과 충돌/중복인지 먼저 확인하세요.")
    return 0


def cmd_trace(args) -> int:
    roots = args.roots or [str(REPO_ROOT)]
    exts = [e.strip(".") for e in args.ext.split(",") if e.strip()]
    hits, engine = _search(roots, args.id, exts)
    print(f"# 영향 역추적: \"{args.id}\"  (engine={engine})")
    if not hits:
        print("  (매칭 없음) ⚠ ID가 한 글자라도 틀리면 0건. 색인에서 실명을 먼저 확인하세요.")
        return 0
    for h in hits:
        print(f"  {h}")
    print(f"\n[=] {len(hits)}곳이 이 ID를 참조 = 이걸 바꾸면 흔들리는 지점.")
    return 0


def _load_card(path):
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^---\s*\n(.*?)\n---\s*$", text, re.DOTALL | re.MULTILINE)
    block = m.group(1) if m else text
    if _HAVE_YAML:
        try:
            return yaml.safe_load(block) or {}
        except Exception:
            pass
    data = {}
    for line in block.splitlines():
        mm = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if mm and mm.group(2).strip() and not mm.group(2).strip().startswith("#"):
            data[mm.group(1)] = mm.group(2).strip()
    return data


def cmd_index(args) -> int:
    if not os.path.isdir(args.dir):
        sys.stderr.write(f"[!] 폴더 없음: {args.dir}\n")
        return 2
    by_status, cards = {}, []
    for name in sorted(os.listdir(args.dir)):
        if not name.lower().endswith((".yaml", ".yml")):
            continue
        data = _load_card(os.path.join(args.dir, name))
        did = data.get("decision_id") or os.path.splitext(name)[0]
        status = str(data.get("status", "unknown")).split("#")[0].strip()
        by_status[status] = by_status.get(status, 0) + 1
        cards.append({"decision_id": did, "status": status,
                      "created": str(data.get("created", "")).strip(), "file": name})
    index = {"generated": _today(), "count": len(cards),
             "by_status": by_status, "cards": cards}
    out = os.path.join(args.dir, "_index.json")
    Path(out).write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 색인 갱신: {out}  (카드 {len(cards)}건, by_status={by_status})")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="decision_track",
                                description="결정 카드 박제 + grep 영향 역추적 (표준 라이브러리만)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pn = sub.add_parser("new", help="새 결정 카드 생성")
    pn.add_argument("--dir", default=DEFAULT_DIR)
    pn.add_argument("--id", default="")
    pn.add_argument("--title", default="")
    pn.add_argument("--owner", default="")
    pn.add_argument("--rationale", default="")
    pn.add_argument("--created", default="")
    pn.add_argument("--stdout", action="store_true")
    pn.add_argument("--force", action="store_true")
    pn.set_defaults(func=cmd_new)

    pf = sub.add_parser("find", help="과거 결정 검색")
    pf.add_argument("term")
    pf.add_argument("--dir", default=DEFAULT_DIR)
    pf.add_argument("--roots", nargs="*")
    pf.add_argument("--ext", default="yaml,yml,md")
    pf.set_defaults(func=cmd_find)

    pt = sub.add_parser("trace", help="ID로 영향 역추적")
    pt.add_argument("id")
    pt.add_argument("--roots", nargs="*")
    pt.add_argument("--ext", default="yaml,yml,md")
    pt.set_defaults(func=cmd_trace)

    pi = sub.add_parser("index", help="_index.json 갱신")
    pi.add_argument("--dir", default=DEFAULT_DIR)
    pi.set_defaults(func=cmd_index)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

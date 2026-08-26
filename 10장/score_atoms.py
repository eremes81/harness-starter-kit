#!/usr/bin/env python3
# ============================================================================
#  score_atoms.py  —  카드 점수화: 인용 빈도·수동 가중치·최신성 → 한 점수
# ----------------------------------------------------------------------------
#  책 10장 「자주 쓰는 규칙을 우선순위 위로 올리기」 절의 전체 실행본.
#
#  왜:
#    - 카드가 수백 개로 늘어나면 매 세션 모든 카드를 읽힐 수는 없다.
#      "무엇을 먼저 볼 것인가"를 정하는 숫자가 필요하다.
#    - 기준은 세 가지다.
#        1) 인용 빈도(cited_count)         — 실제 업무에서 얼마나 자주 호출되나
#        2) 수동 가중치(manual_weight, 0~5) — 횟수로 안 드러나는 중요도를 사람이 표시
#        3) 최신성(updated)                — 최근 갱신된 규칙에 약간의 우선권(90일 지나면 0)
#    - 점수가 낮다고 자동 폐기하지 않는다. 점수는 노출 우선순위일 뿐,
#      폐기 여부는 맥락을 아는 사람이 판단한다.
#
#  사용법 (Claude에게 "카드 점수 매겨줘"라고 하면 대신 실행):
#    python 10장/score_atoms.py                            # team_memory/atoms 상위 10개
#    python 10장/score_atoms.py --dir memory               # 다른 카드 폴더 지정
#    python 10장/score_atoms.py --out scores_latest.json   # 최신 점수 캐시 저장(그림 10-2)
#
#  카드 형식: .md 프론트매터(YAML)에 아래 키를 둔다. 빈 키는 0으로 본다.
#    cited_count: 12        # 인용 빈도 (회의록·회고 로그 집계로 갱신)
#    manual_weight: 3       # 수동 가중치 0~5
#    updated: 2026-07-01    # 마지막 갱신일 (이 키가 없으면 그 카드는 건너뛰고 경고)
#
#  의존성: 파이썬 표준 라이브러리만. (PyYAML 있으면 파싱이 더 견고하나 없어도 동작)
# ============================================================================
from __future__ import annotations

import argparse
import datetime
import json
import re
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
DEFAULT_DIR = REPO_ROOT / "team_memory" / "atoms"


def _read_front_matter(path: Path) -> dict:
    """카드(.md) 머리의 YAML 프론트매터를 dict로 읽는다."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    if _HAVE_YAML:
        try:
            data = yaml.safe_load(block)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    data = {}
    for line in block.splitlines():
        mm = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if mm:
            data[mm.group(1)] = mm.group(2).split("#")[0].strip()
    return data


def _to_int(value, default: int = 0) -> int:
    """프론트매터 값(문자열일 수 있다)을 정수로. 못 읽으면 default."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def load_atoms(atoms_dir: Path) -> list[dict]:
    """폴더의 카드(.md)를 훑어 점수 계산에 필요한 필드만 추린다.

    updated가 없거나 날짜(YYYY-MM-DD)로 못 읽는 카드는 건너뛰고 경고한다.
    카드 한 장의 결함 때문에 점수 계산 전체가 멈추지 않게 하기 위해서다.
    """
    if not atoms_dir.is_dir():
        sys.stderr.write(f"[!] 카드 폴더가 없습니다: {atoms_dir}\n")
        sys.exit(2)
    atoms: list[dict] = []
    for path in sorted(atoms_dir.rglob("*.md")):
        if path.name.startswith("_") or path.name.lower() == "readme.md":
            continue
        fm = _read_front_matter(path)
        updated = str(fm.get("updated", "")).strip()
        try:
            datetime.date.fromisoformat(updated)
        except ValueError:
            sys.stderr.write(f"[!] 건너뜀(updated 없음/형식 오류): {path.name}\n")
            continue
        weight = _to_int(fm.get("manual_weight"))
        if not 0 <= weight <= 5:
            sys.stderr.write(
                f"[!] manual_weight는 0~5 — {path.name}의 {weight}을(를) 범위로 잘라 반영\n")
            weight = min(5, max(0, weight))
        atoms.append({
            "name": str(fm.get("name") or path.stem),
            "cited_count": _to_int(fm.get("cited_count")),
            "manual_weight": weight,
            "updated": updated,
            "file": path.relative_to(atoms_dir).as_posix(),
        })
    return atoms


# --- 아래 score()·정렬·출력 줄은 책 10장 발췌 코드와 같은 줄이다 -------------
def score(atom, today):
    freq = atom.get("cited_count", 0)        # 1) 인용 빈도
    weight = atom.get("manual_weight", 0)    # 2) 수동 가중치(0~5)
    days = (today - datetime.date.fromisoformat(atom["updated"])).days
    recency = max(0, 90 - days) / 90         # 3) 최신성 (90일 지나면 0)
    return freq * 1.0 + weight * 20.0 + recency * 10.0   # ← 세 기준에 가중치


def _parse_args():
    p = argparse.ArgumentParser(
        prog="score_atoms",
        description="카드 점수화: 인용 빈도·수동 가중치·최신성 → 한 점수 (표준 라이브러리만)")
    p.add_argument("--dir", default=str(DEFAULT_DIR),
                   help="카드(.md) 폴더 (기본: team_memory/atoms)")
    p.add_argument("--out", default="",
                   help="최신 점수 캐시(JSON) 저장 경로 (예: scores_latest.json). 지정할 때만 쓴다.")
    return p.parse_args()


args = _parse_args()
atoms = load_atoms(Path(args.dir))
today = datetime.date.today()

print(f"# 카드 점수 상위 10  (기준일 {today} · 카드 {len(atoms)}건 · "
      f"점수 = 빈도*1.0 + 가중치*20.0 + 최신성*10.0)")
if not atoms:
    print("  (점수 매길 카드가 없습니다 — --dir 경로와 카드의 updated 칸을 확인하세요.)")
    sys.exit(0)

ranked = sorted(atoms, key=lambda a: score(a, today), reverse=True)
for a in ranked[:10]:                        # 상위 10개만 눈으로 검증
    print(round(score(a, today), 1), a["name"])
if len(ranked) > 10:
    print(f"  ... 외 {len(ranked) - 10}건 (점수는 폐기 기준이 아니라 노출 우선순위다)")

# 상위 10개가 팀이 실제로 자주 참고하는 규칙과 다르면 계산식이 잘못 맞춰진 것이다.
# 가중치 상수(1.0·20.0·10.0)를 조정하고 다시 확인한다.

if args.out:
    cache = {"generated": today.isoformat(), "count": len(ranked),
             "atoms": [{**a, "score": round(score(a, today), 1)} for a in ranked]}
    Path(args.out).write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(f"\n[OK] 점수 캐시 저장: {args.out}")

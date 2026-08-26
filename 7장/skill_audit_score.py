#!/usr/bin/env python3
# ============================================================================
#  skill_audit_score.py  —  버전 관리 로그로 도구 사용 점수 산출 (큐레이션 후보 좁히기)
# ----------------------------------------------------------------------------
#  책 7장 「안 쓰는 도구를 데이터로 골라내기」 절의 전체 실행본.
#
#  왜:
#    - 도구 목록이 불어나면 "이거 안 쓰니까 빼자"를 기억에 의존하게 된다.
#    - 도구의 산출물은 버전 관리(git)에 커밋되므로, 로그에 사용 흔적이 남는다.
#    - 그 흔적을 0~100 점수로 환산하면 큐레이션 후보를 데이터로 좁힐 수 있다.
#    → 단, 점수는 후보를 좁혀 줄 뿐이다. 최종 결정은 사람이 한다.
#
#  어떻게 (두 매칭 병행 — 커밋 메시지에 도구 이름이 항상 들어간다는 보장이 없으므로):
#    (1) 커밋 메시지의 도구 이름 키워드 매칭             — 느슨, 가중치 1.0
#    (2) 변경 경로가 도구 폴더·산출물 패턴에 속하는지 매칭 — 엄격, 가중치 2.0
#    점수 = 최근일수록 큰 가중(감쇠율 0.9) − 방치 감점(stale 1일당 0.5) → 0~100 클램프.
#    산출물 패턴(artifact)을 아예 잡을 수 없는 도구(조회·읽기 전용)는 confidence=LOW로
#    표시하고 자동 후보에서 제외 — "측정 불가 — 수동 점검"으로 따로 묶는다.
#
#  사용법:
#    python skill_audit_score.py --repo <git 저장소> --tools tools.json [--window 90]
#    tools.json = [{"name": "도구명", "artifact": ["산출물 경로 패턴", ...]}, ...]
#                 (artifact를 빈 리스트로 두면 조회·읽기 전용 = confidence LOW)
#
#  주의: 계수 0.9 / 0.5 / 8 과 판정 문턱은 보편 공식이 아니라 저자 작업 사본에 맞춘
#        운용 기준이다. 커밋 습관·산출물 패턴이 다르면 조정한다.
#        절대 점수보다 "도구 간 상대 순위"와 "confidence 구분"이 본질이다.
#
#  의존성: 파이썬 표준 라이브러리만. (git 명령이 PATH에 있어야 한다)
# ============================================================================
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# 판정 문턱 (운용 기준 — 자기 저장소에 맞춰 조정. 정답 아님)
KEEP_MIN = 40.0   # 이 점수 이상 = 유지
WATCH_MIN = 10.0  # 이 점수 이상 = 관찰, 미만 = 큐레이션 후보


def git_log_entries(repo_path, window=90):
    """최근 window일 커밋을 파싱해 {days_ago, message, paths} 목록으로 돌려준다.

    message는 소문자로 정규화(느슨 매칭용), paths는 구분자를 /로 통일한다.
    """
    cmd = ["git", "-C", str(repo_path), "log", f"--since={window} days ago",
           "--date=short", "--name-only", "--pretty=format:@@@%ad|%s"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", check=False)
    except FileNotFoundError:
        sys.stderr.write("[!] git 명령을 찾을 수 없습니다. git 설치·PATH를 확인하세요.\n")
        raise SystemExit(2)
    if res.returncode != 0:
        sys.stderr.write(f"[!] git log 실패 — git 저장소가 맞습니까?: {repo_path}\n")
        if res.stderr.strip():
            sys.stderr.write(f"    {res.stderr.strip().splitlines()[0]}\n")
        raise SystemExit(2)

    today = _dt.date.today()
    entries, cur = [], None
    for line in res.stdout.splitlines():
        if line.startswith("@@@"):                    # 커밋 헤더: @@@날짜|메시지
            date_s, _, msg = line[3:].partition("|")
            try:
                d = _dt.date.fromisoformat(date_s)
            except ValueError:
                cur = None                            # 날짜가 깨진 커밋은 건너뛴다
                continue
            cur = {"days_ago": max(0, (today - d).days),
                   "message": msg.lower(), "paths": []}
            entries.append(cur)
        elif line.strip() and cur is not None:        # 헤더 아래 = 변경된 파일 경로
            cur["paths"].append(line.strip().replace("\\", "/"))
    return entries


def score_tools(repo_path, tools, window=90):
    """도구별 [이름, 점수, 마지막 사용 경과일(None=측정 안 됨), confidence]를
    점수 오름차순으로 돌려준다."""
    hits = defaultdict(list)  # 도구명 -> [(경과일, 가중치), ...]
    for e in git_log_entries(repo_path, window):     # 90일 커밋의 날짜·변경경로
        days_ago = e["days_ago"]
        for t in tools:
            name = t["name"].lower()
            if name in e["message"]:                 # 커밋 메시지 키워드 = 느슨 매칭
                hits[t["name"]].append((days_ago, 1.0))
            in_path = any(name in p.lower() for p in e["paths"]) or \
                      any(pat in p for p in e["paths"]
                          for pat in t.get("artifact", []))   # 느슨+엄격 매칭
            if in_path:
                hits[t["name"]].append((days_ago, 2.0))  # 엄격 매칭 가중
    rows = []
    for t in tools:
        h = hits[t["name"]]
        measured = bool(h)
        last_used = min(d for d, _w in h) if measured else window  # 미측정 = window일 취급
        recency = sum(w * (1 - 0.9 * (d / window)) for d, w in h)  # 0.9 = 최근일 가중 감쇠율
        stale_penalty = max(0, (last_used - 14)) * 0.5            # 0.5 = stale 1일당 감점
        score = max(0, min(100, recency * 8 - stale_penalty))    # 8 = 점수 스케일 계수
        confidence = "HIGH" if t.get("artifact") else "LOW"  # artifact 없으면 측정 불가
        rows.append([t["name"], round(score, 1),
                     last_used if measured else None, confidence])
    rows.sort(key=lambda r: r[1])   # 점수 오름차순 = 후보 먼저
    return rows


def load_tools(path):
    """도구 목록 JSON을 읽고 스키마를 검사한다. 깨졌으면 명확히 알리고 종료."""
    p = Path(path)
    if not p.is_file():
        sys.stderr.write(f"[!] 도구 목록 파일 없음: {path}\n")
        raise SystemExit(2)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        sys.stderr.write(f"[!] JSON 파싱 실패: {path} ({ex})\n")
        raise SystemExit(2)
    # 스키마 검사 — 입력이 "정말 정형인가"는 스크립트가 아니라 여기서 먼저 판정한다.
    if not isinstance(data, list) or not data:
        sys.stderr.write("[!] tools.json은 비어 있지 않은 배열이어야 합니다.\n")
        raise SystemExit(2)
    seen = set()
    for i, t in enumerate(data):
        if not isinstance(t, dict) or not isinstance(t.get("name"), str) or not t["name"].strip():
            sys.stderr.write(f"[!] tools[{i}]: name(비어 있지 않은 문자열)이 필요합니다.\n")
            raise SystemExit(2)
        art = t.get("artifact", [])
        if not isinstance(art, list) or not all(isinstance(x, str) and x for x in art):
            sys.stderr.write(f"[!] tools[{i}] \"{t['name']}\": artifact는 문자열 배열이어야 합니다.\n")
            raise SystemExit(2)
        if t["name"] in seen:
            sys.stderr.write(f"[!] tools[{i}]: 도구명 중복 — \"{t['name']}\"\n")
            raise SystemExit(2)
        seen.add(t["name"])
    return data


def verdict(score, confidence):
    """점수·신뢰도 → 판정 제안 문자열. (제안일 뿐, 최종 결정은 사람이 한다)"""
    if confidence == "LOW":
        return "수동 점검"
    if score >= KEEP_MIN:
        return "유지"
    if score >= WATCH_MIN:
        return "관찰"
    return "큐레이션 후보"


def _fmt_last(last_used):
    return "측정 안 됨" if last_used is None else f"{last_used}일 전"


def _print_rows(rows):
    if not rows:
        print("  (해당 도구 없음)")
        return
    print(f"  {'tool':<24} {'audit_score':>11}  {'last_used':<10} {'confidence':<10} 판정(제안)")
    for name, score, last, conf in rows:
        print(f"  {name:<24} {score:>11.1f}  {_fmt_last(last):<10} {conf:<10} "
              f"{verdict(score, conf)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="skill_audit_score",
        description="버전 관리 로그로 도구별 사용 점수(0~100)·confidence를 산출해 "
                    "큐레이션 후보를 좁힌다 (표준 라이브러리만)")
    p.add_argument("--repo", default=".", help="git 저장소 경로 (기본: 현재 폴더)")
    p.add_argument("--tools", required=True,
                   help='도구 목록 JSON: [{"name": ..., "artifact": [...]}, ...]')
    p.add_argument("--window", type=int, default=90, help="로그 파싱 구간(일, 기본 90)")
    args = p.parse_args(argv)
    if args.window <= 0:
        sys.stderr.write("[!] --window는 1 이상이어야 합니다.\n")
        return 2

    tools = load_tools(args.tools)
    rows = score_tools(args.repo, tools, args.window)
    high = [r for r in rows if r[3] == "HIGH"]
    low = [r for r in rows if r[3] == "LOW"]

    print(f"# 도구 사용 감사: 최근 {args.window}일  (repo={args.repo}, 도구 {len(tools)}개)")
    print("# 점수 오름차순 = 큐레이션 후보 먼저. 계수(0.9/0.5/8)·문턱은 운용 기준 — 저장소에 맞춰 조정.")
    print()
    print("## 점수 비교 가능 (confidence=HIGH)")
    _print_rows(high)
    print()
    print("## 측정 불가 — 수동 점검 (confidence=LOW, 자동 후보에서 제외)")
    _print_rows(low)
    print()
    print("[!] 점수가 낮은 이유가 \"정말 안 써서\"인지 \"측정이 도구를 못 잡아서\"인지는 "
          "사람이 가른다. 숫자는 후보를 좁힐 뿐, 최종 결정은 사람 몫.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

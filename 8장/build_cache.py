#!/usr/bin/env python3
# ============================================================================
#  build_cache.py  —  무거운 원천을 가벼운 텍스트 캐시(.md)로 굽는 사전 스크립트
# ----------------------------------------------------------------------------
#  책 8장 '무거운 원천을 미리 가벼운 텍스트로 굽기' 절의 전체 실행본
#
#  왜:
#    - 수십 MB 스프레드시트 같은 '읽기 비싼 원천'을 AI에게 매번 통째로 읽히면
#      그때마다 원본 전체가 입력 토큰으로 들어간다.
#    - 정작 스키마 확인·요약 수준의 질의에 필요한 건 컬럼 구조와 요약 몇 줄이다.
#    → 원천을 이 스크립트로 한 번만 읽어 가벼운 .md 캐시로 구워 두고,
#      AI 질의는 원본 대신 캐시를 읽힌다. 호출당 입력 토큰이 구조적으로 준다.
#
#  사용법 (Claude에게 "정산표 캐시 다시 구워줘"라고 하면 대신 실행):
#    python 8장/build_cache.py            # 원본이 캐시보다 새로울 때만 굽는다
#    python 8장/build_cache.py --force    # 원본이 안 바뀌었어도 강제로 다시 굽는다
#    - 원본이 있는 폴더에서 실행한다. 캐시는 그 아래 cache/ 에 생긴다.
#    - 자기 원본에 맞게 쓰려면: 아래 SRC·DST 상수와, 발췌 구간의
#      read_excel(...)·open(...) 안 경로 문자열을 함께 바꾼다.
#
#  안전 원칙:
#    - 캐시에 적는 요약 통계는 원본에서 계산한 실제 값만 쓴다. 지어내지 않는다.
#    - 원본 전체가 필요한 작업(원문 대조 검증·한 셀의 정확한 값 확인)에는
#      이 캐시를 쓰지 않는다 — 그때만 원본을 따로 읽힌다.
#
#  의존성: pandas + openpyxl (발췌에 등장하는 외부 패키지). 그 외는 표준 라이브러리만.
# ============================================================================
# pip install pandas openpyxl
from __future__ import annotations

import datetime as _dt
import importlib.util
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── 경로: 발췌와 같은 기본값 ─────────────────────────────────────────────────
#    (바꿀 때는 아래 발췌 구간의 read_excel(...)·open(...) 문자열도 함께 바꾼다)
SRC = "대형_정산표.xlsx"   # 무거운 원본 — 읽기 비싼 파일
DST = "cache/정산표.md"    # 구워 낼 가벼운 텍스트 캐시

# ── 인자 점검: 경로 인자는 받지 않는다 (옵션은 --force 하나) ─────────────────
_args = sys.argv[1:]
FORCE = "--force" in _args
_unknown = [a for a in _args if a != "--force"]
if _unknown:
    sys.exit(
        f"[build_cache] 알 수 없는 인자: {' '.join(_unknown)}\n"
        f"  이 스크립트는 경로 인자를 받지 않습니다. 원본·캐시 경로는 파일 안의\n"
        f"  SRC·DST 상수와 발췌 구간의 경로 문자열을 함께 바꿔 쓰세요. (옵션: --force)"
    )

# ── 원본 점검: 없으면 명확한 메시지로 종료 ──────────────────────────────────
if not os.path.exists(SRC):
    sys.exit(
        f"[build_cache] 원본이 없습니다: {SRC}\n"
        f"  실행 위치(작업 폴더)에 원본을 두거나, SRC와 발췌 구간의 경로를\n"
        f"  자기 원본에 맞게 바꾼 뒤 다시 실행하세요."
    )

# ── '원본이 바뀔 때만 실행한다'를 코드로: 캐시가 원본보다 새로우면 굽지 않는다 ──
if not FORCE and os.path.exists(DST) and os.path.getmtime(DST) >= os.path.getmtime(SRC):
    print(f"[SKIP] 캐시가 이미 최신입니다: {DST}")
    print("       원본이 바뀔 때만 다시 굽습니다. 강제로 다시 구우려면: --force")
    sys.exit(0)

# ── 의존성 점검: import 전에 확인해 명확한 메시지로 종료 ────────────────────
for _pkg in ("pandas", "openpyxl"):
    if importlib.util.find_spec(_pkg) is None:
        sys.exit(
            f"[build_cache] 외부 패키지가 없습니다: {_pkg}\n"
            f"  설치: pip install pandas openpyxl"
        )


def _num(v) -> str:
    """원본에서 계산한 값을 그대로 적는 표시용 포맷 — 값 자체는 바꾸지 않는다."""
    try:
        i = int(v)
        if i == v:                        # 정수 값이면 천 단위 콤마만 붙인다
            return f"{i:,}"
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return f"{float(v):,.2f}"         # 소수는 둘째 자리까지 표시
    except (TypeError, ValueError):
        return str(v)


def _mtime(path: str) -> str:
    return _dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")


# ─────────────────────────────────────────────────────────────────────────────
#  여기부터가 책 발췌의 골자 흐름이다(발췌 주석 두 줄 포함, 그대로 유지).
# ─────────────────────────────────────────────────────────────────────────────
# build_cache.py — 무거운 원천을 가벼운 텍스트 캐시로 굽는 사전 스크립트(골자)
# 원본이 바뀔 때만 실행한다. AI 질의는 이 스크립트가 아니라 결과 .md를 읽는다.

import pandas as pd

df = pd.read_excel("대형_정산표.xlsx")   # 무거운 원천(읽기 비쌈)을 1회만 연다

lines = ["# 정산표 캐시(자동 생성)", ""]
lines.append(f"- 행 수: {len(df)}  / 컬럼 수: {len(df.columns)}")
lines.append(f"- 원본: {SRC} · {os.path.getsize(SRC):,}바이트 · 수정시각 {_mtime(SRC)}")
lines.append("")
lines.append("## 컬럼 스키마")
for col in df.columns:                    # 컬럼명·타입·결측만 추린 가벼운 스키마
    lines.append(f"- `{col}` · {df[col].dtype} · 결측 {df[col].isna().sum()}건")

# 필요하면 숫자 컬럼 요약(합계·최솟값·최댓값 등)을 몇 줄 더 덧붙인다.
# 단, 요약 통계는 '원본에서 계산한 실제 값'만 적는다 — 지어내지 않는다.
_num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
if _num_cols:
    lines.append("")
    lines.append("## 숫자 컬럼 요약 — 원본에서 계산한 실제 값")
    for col in _num_cols:
        vals = df[col].dropna()
        if vals.empty:
            lines.append(f"- `{col}` · 값 없음(전부 결측)")
            continue
        lines.append(f"- `{col}` · 합계 {_num(vals.sum())}"
                     f" · 최솟값 {_num(vals.min())} · 최댓값 {_num(vals.max())}")

lines.append("")                          # 파일 끝 개행
os.makedirs(os.path.dirname(DST) or ".", exist_ok=True)
open("cache/정산표.md", "w", encoding="utf-8").write("\n".join(lines))

# ── 결과 보고: 원본 대비 캐시 크기(실측값) ──────────────────────────────────
_src_size = os.path.getsize(SRC)
_dst_size = os.path.getsize(DST)
_ratio = f" (약 1/{_src_size // _dst_size})" if 0 < _dst_size < _src_size else ""
print(f"[OK] 캐시 생성: {DST}")
print(f"     원본 {_src_size:,}바이트 → 캐시 {_dst_size:,}바이트{_ratio}")
print("     스키마·요약 수준의 질의는 이제 원본 대신 이 캐시를 읽히면 됩니다.")

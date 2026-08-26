#!/usr/bin/env python3
# ============================================================================
#  price_check.py  —  공개 토큰 단가로 호출 비용을 계산 (책 "비용 가드")
# ----------------------------------------------------------------------------
#  정직성 원칙: 지어낸 절감액을 만들지 않는다.
#    - 단가는 사용자가 **공식 가격표에서 직접 채워 넣는 값**이다.
#    - 이 스크립트는 그 단가에 토큰 수를 곱하는 산술만 한다.
#    - 단가가 비어 있으면(null) 계산을 거부한다 → 가짜 숫자가 나올 수 없다.
#
#  사용법 (Claude에게 "이 호출 비용 계산해줘"라고 하면 대신 실행):
#    1) 단가 표 틀 만들기:  python scripts/price_check.py --init-prices governance/cost/prices.json
#    2) 공식 가격 페이지의 1M 토큰당 USD를 prices.json에 채운다 (_source_url·_as_of도)
#    3) 계산:  python scripts/price_check.py governance/cost/prices.json --model sonnet --in 40000 --out 600
#
#  의존성: 파이썬 표준 라이브러리만.
# ============================================================================
import argparse
import json
import sys
from pathlib import Path

# 단가 표 '틀'. 값은 비워 둔다 — 지어낸 숫자를 넣지 않기 위함.
PRICE_TEMPLATE = {
    "_note": "1M(100만) 토큰당 USD. 공식 가격 페이지에서 직접 채울 것. 시점에 따라 변동.",
    "_source_url": "",
    "_as_of": "",
    "models": {
        "opus":   {"in": None, "out": None, "cached_in": None},
        "sonnet": {"in": None, "out": None, "cached_in": None},
        "haiku":  {"in": None, "out": None, "cached_in": None},
    },
}


def init_prices(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(PRICE_TEMPLATE, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"단가 표 틀을 만들었습니다: {path}")
    print("공식 가격 페이지의 1M 토큰당 USD를 채우고 _source_url·_as_of도 적으세요.")


def cost(prices, model, in_tok, out_tok, cached_in):
    m = prices["models"].get(model)
    if m is None:
        sys.exit(f"단가 표에 '{model}' 모델이 없습니다.")
    for k in ("in", "out"):
        if m.get(k) is None:
            sys.exit(f"'{model}.{k}' 단가가 비어 있습니다. prices.json을 먼저 채우세요.")
    fresh_in = max(in_tok - cached_in, 0)
    c_in = fresh_in / 1_000_000 * m["in"]
    c_out = out_tok / 1_000_000 * m["out"]
    c_cache = 0.0
    if cached_in:
        if m.get("cached_in") is None:
            sys.exit(f"'{model}.cached_in' 단가가 비어 있습니다(캐시 read 단가).")
        c_cache = cached_in / 1_000_000 * m["cached_in"]
    return {
        "model": model,
        "fresh_input_usd": round(c_in, 6),
        "cached_input_usd": round(c_cache, 6),
        "output_usd": round(c_out, 6),
        "total_usd": round(c_in + c_out + c_cache, 6),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prices", nargs="?", help="단가 표 JSON 경로")
    ap.add_argument("--init-prices", metavar="PATH", help="단가 표 틀 생성")
    ap.add_argument("--model")
    ap.add_argument("--in", dest="in_tok", type=int, default=0)
    ap.add_argument("--out", dest="out_tok", type=int, default=0)
    ap.add_argument("--cached-in", dest="cached_in", type=int, default=0)
    a = ap.parse_args()

    if a.init_prices:
        init_prices(a.init_prices)
        return
    if not (a.prices and a.model):
        ap.error("prices.json 경로와 --model 이 필요합니다 (또는 --init-prices).")

    prices = json.loads(Path(a.prices).read_text(encoding="utf-8"))
    print(json.dumps(cost(prices, a.model, a.in_tok, a.out_tok, a.cached_in), ensure_ascii=False, indent=2))
    sys.stderr.write(f"[price_check] 단가 출처: {prices.get('_source_url') or '(미기입)'}  "
                     f"확인일: {prices.get('_as_of') or '(미기입)'}\n")


if __name__ == "__main__":
    main()

# governance — 거버넌스 층 (비용 · 의사결정)

혼자 잠깐 쓸 때는 필요 없습니다. AI를 **일에 정착시키고 팀으로 확장**하면,
"How to(쓰는 법)"를 넘어 **운용·거버넌스**가 필요해집니다. 이 폴더가 그 실물입니다.
(책 후반부: 비용 가드 · 의사결정 추적)

## 1. 비용 가드 (돈이 새지 않게)

AI 비용은 대부분 "매 호출에 자동으로 붙는 컨텍스트"에서 샙니다. 두 장치로 막습니다.

- **컨텍스트 천장** — `memory/_guard.json` 의 `max_matches`(개수)·`max_atom_body`(글자 수). 기본값 3개·6000자.
  주입 훅(`inject_memory.py`)이 이 값으로 **개수·길이 상한**을 강제합니다. 늘리면 정확도↑ 비용↑.
- **비용 계산기** — `scripts/price_check.py`.
  ```
  python scripts/price_check.py --init-prices governance/cost/prices.json   # 단가 표 틀
  # → 공식 가격 페이지의 1M 토큰당 USD를 채운다 (_source_url·_as_of도)
  python scripts/price_check.py governance/cost/prices.json --model sonnet --in 40000 --out 600
  ```
  > **정직성**: 단가는 사용자가 공식표에서 직접 채웁니다. 스크립트는 곱셈만 하고,
  > 단가가 비어 있으면 계산을 거부합니다 — 지어낸 절감액이 나올 수 없습니다.

## 2. 의사결정 추적 (결정이 사라지지 않게)

결정을 카드(YAML)로 박제하고, ID로 grep 역추적합니다. `scripts/decision_track.py`.

```
# 새 결정 전, 같은 주제 과거 결정부터 검색 (중복·충돌 점검)
python scripts/decision_track.py find "회고 주기"

# 새 결정 카드 (필수 5칸: id·title·status·owner·rationale)
python scripts/decision_track.py new --title "주간 회고는 금요일" --owner jiwon --rationale "고정 슬롯이 있어야 루프가 돈다"

# 이 결정을 바꾸면 어디가 흔들리나 (ID 역추적)
python scripts/decision_track.py trace D2026_Q3_001 --roots .

# 색인 갱신 (status 집계)
python scripts/decision_track.py index
```

카드는 `governance/decisions/` 에 쌓입니다. 핵심 3칸:
- **owner** — 이 결정을 책임지는 사람. 비면 `[MISSING]` 으로 남아 반려 신호가 된다.
- **rationale** — 6개월 뒤 "왜 그랬지?"에 답하는 칸. 가장 중요.
- **related_decisions** — 결정 사이의 간선. `supersedes`/`relates_to` 로 그래프를 만든다.

> `memory/decisions/`(가벼운 주입용 결정)와 `governance/decisions/`(추적용 정식 카드)는 다릅니다.
> 전자는 대화에 자동으로 떠오르는 습관, 후자는 "누가·왜 정했고 바꾸면 어디가 흔들리나"의 기록.

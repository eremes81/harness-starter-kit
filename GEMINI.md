<!-- ⚠ 자동 생성 사본입니다. 원본은 CLAUDE.md 입니다.
     이 파일은 Gemini CLI 가 세션 시작 때 자동으로 읽습니다.
     고치려면 CLAUDE.md 를 고친 뒤  python scripts/build_manifest.py  를 실행하세요.
     (scripts/sync_agent_docs.py 가 다시 복사합니다. 여기를 직접 고치면 다음 동기화 때 사라집니다.) -->

# 내 하네스 — AI 에이전트 세션 가이드

> 이 파일은 AI 코딩 에이전트가 **세션을 시작할 때 자동으로 읽습니다.**
> Claude Code 는 이 `CLAUDE.md` 를, OpenAI Codex·Grok Build 는 `AGENTS.md` 를, Gemini CLI 는 `GEMINI.md` 를 읽는데
> 뒤의 둘은 **이 파일의 자동 사본**입니다(`scripts/sync_agent_docs.py`). 고칠 곳은 언제나 이 파일 하나입니다.
> "매번 설명하지 않아도 알아야 하는 것"만 짧게 담습니다. 길어지면 메모리로 위임하세요.
> (책 부록 스타터 키트의 예시 내용입니다. `[[대괄호]]` 부분을 당신 것으로 바꾸세요.)

## 나는 누구이고, 무슨 일을 하나

- **이름/역할**: [[예: 김지원 / 마케팅팀 기획자]]
- **주로 하는 일**: [[예: 주간 보고서, 캠페인 기획서, 외부 제휴 메일 작성]]
- **이 폴더의 목적**: [[예: 반복되는 문서 업무를 Claude 와 함께 처리하는 작업 공간]]

## 기본 규칙

- **언어**: 한국어 기본. 외국어가 필요하면 영어만.
- **답변 방식**: 결론·요약을 먼저. 긴 배경 설명은 묻기 전엔 짧게. (메모리 `장황한설명-금지` 참고)
- **확인보다 실행**: 방향이 분명하면 먼저 해보고, 애매할 때만 묻는다.

## 이 작업 공간이 동작하는 방식 (하네스)

1. **세션 시작** → AI 가 이 파일을 자동으로 읽는다.
2. **내가 말을 걸 때마다** → `.claude/hooks/inject_memory.py` 훅이 돌아,
   내 말과 관련된 메모리(`memory/` 안의 규칙·결정·피드백)를 **그때그때 자동 주입**한다.
3. **회고** → 한 주를 `retro/` 에 정리하고, 반복되는 교훈을 `memory/` 규칙으로 승격한다.
4. 승격된 규칙은 다음부터 관련 대화에서 자동으로 다시 떠오른다. → **루프가 돈다.**

## 🔥 자주 적용되는 규칙 (자동 갱신 — 직접 수정 금지)

> 아래 목록은 `scripts/build_manifest.py` 가 메모리 점수 순으로 **자동으로 채웁니다.**
> 손으로 고치지 마세요. 점수가 바뀌면 목록도 바뀝니다. (책 "자가개선" 장의 실물)
> 작업 전, 매칭되는 규칙이 있으면 1초 점검.

<!-- BEGIN_HOT_AUTO -->
- **30** (팀) — 팀 커밋 메시지는 [이름]으로 시작한다
- **28** (팀) — shared/ 공통 규칙은 회고 합의 후에만 바꾼다
- **25** (개인) — AI 산출물을 결정·보고·제출에 반영하기 전 3중 게이트
- **20** (개인) — 보고서·문서 작성은 본문보다 목차(구조)를 먼저 합의한다
- **15** (개인) — 결과를 먼저, 설명은 짧게 — 변경 요약 표면 충분
- **12** (개인) — 주간 회고는 매주 금요일 오후에 고정한다
- **10** (개인) — 베이스라인 — 도입 전에 잰 기준값 (없으면 "줄었다"를 말할 수 없다)
<!-- END_HOT_AUTO -->

## 메모리 구조 (`memory/`)

| 폴더 | 무엇을 담나 |
|------|------------|
| `rules/` | 반복 적용할 작업 규칙 (예: 보고서는 목차부터) |
| `decisions/` | 한 번 정한 결정 (예: 주간 회고는 금요일 오후) |
| `feedback/` | 나의 협업 선호·피드백 (예: 설명은 짧게) |
| `concepts/` | 자주 쓰는 개념·용어 정의 |

- 새 메모리 만들기: AI 에게 "새 규칙 메모리 만들어줘"라고 하면 `scripts/new_memory.py` 로 생성.
- 메모리를 추가/수정한 뒤에는 "매니페스트 다시 만들어줘" → `scripts/build_manifest.py` 가 재생성.
- 각 메모리의 `keywords:` 가 **언제 그 메모리가 떠오를지**를 정합니다. 가장 중요한 필드.

## 팀으로 쓸 때 (선택: `team_memory/`)

혼자면 위 `memory/` 만으로 충분합니다. 여러 명이 같은 하네스를 쓰면 `team_memory/` 를 켭니다.

- `team_memory/atoms/` = **팀 공유 규칙**. 개인 `memory/` 와 함께 자동 주입되며, 보통 score 를 높여 팀 규칙이 먼저 뜬다.
- `team_memory/shared/` = 팀 공통 규칙(커밋·용어·흐름). **직접 수정 금지 — 회고 합의 후에만.**
- `team_memory/<이름>/context.md` = 사람별 협업 스타일. 세션 시작 시 아래 절차로 식별해 로드.
- 자세히: `team_memory/README.md`.

### 세션 시작 시 사용자 식별 (팀 모드일 때만)
1. 현재 작업 공간 등 단서로 `team_memory/users.md` 에서 사람을 특정한다.
2. 특정되면 `team_memory/<이름>/context.md` 를 읽어 스타일을 맞춘다.
3. **겹치거나 모르면 추측하지 말고 되묻는다.** (오인 방지)

## 거버넌스로 쓸 때 (선택: `governance/`)

정착·확장 단계에서 켜는 운용 층입니다. 자세히: `governance/README.md`.

- **비용 가드** — `memory/_guard.json`(주입 개수·길이 상한, 훅이 강제) + `scripts/price_check.py`(정직한 비용 계산기).
- **의사결정 추적** — `scripts/decision_track.py`(new/find/trace/index) → `governance/decisions/` 카드(owner·rationale·역추적). "이 결정 바꾸면 어디가 흔들리나"를 grep으로.

## 폴더 구조

```
harness-starter-kit/
├─ CLAUDE.md              ← (이 파일) 세션 시작 자동 로드 — 원본
├─ AGENTS.md · GEMINI.md ← 위 파일의 자동 사본 (Codex·Grok / Gemini 용, 직접 수정 X)
├─ README.md             ← 처음 받았을 때 읽는 설치/사용법
├─ .claude/
│  ├─ settings.json      ← 훅 연결 설정 (Claude Code · Grok Build 가 읽음)
│  └─ hooks/
│     ├─ inject_memory.py   ← 관련 메모리 자동 주입(핵심) — 네 에이전트 공용
│     └─ retro_check.py     ← 세션 시작 시 회고 밀림 알림(루프 엔지니어링)
├─ .codex/hooks.json     ← 같은 훅을 OpenAI Codex 에 연결
├─ .gemini/settings.json ← 같은 훅을 Gemini CLI 에 연결
├─ memory/               ← 내 규칙·결정·피드백·개념 (= 하네스의 기억)
│  └─ _jit_manifest.json ← 훅이 읽는 색인 (자동 생성물, 직접 수정 X)
├─ team_memory/          ← (선택) 팀 공유 규칙·팀원별 공간
├─ governance/           ← (선택) 거버넌스: 비용 가드 · 의사결정 추적
├─ scripts/              ← 매니페스트·메모리·비용계산·결정추적 도우미
└─ retro/               ← 일간·주간 회고 (루프의 연료)
```

## 주의

- `memory/_jit_manifest.json` 과 `memory/_injection_log.txt` 는 **자동 생성물**. 손으로 고치지 말 것.
- `AGENTS.md` · `GEMINI.md` 도 자동 생성물(이 파일의 사본). 고칠 것은 `CLAUDE.md` 뿐.
- 받은 그대로 도는지 확인: `python scripts/kit_selfcheck.py` (문법·설정·훅 E2E·공개 게이트·문서 목차 10종).
- 개인정보·회사 기밀을 메모리에 적었다면, 이 폴더를 공개(git push)하기 전에 반드시 점검.

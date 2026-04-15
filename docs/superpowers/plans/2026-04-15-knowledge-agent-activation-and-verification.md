# Knowledge Agent 정식 활성화 및 운영 검증 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR #145/#146으로 Knowledge Agent 구현이 완료된 상황을 반영하여 (1) 코드베이스에서 Stub 잔존 경로를 정식 제거하고, (2) PR #145 follow-up 정리(isort/문서)를 마무리하며, (3) 운영 서버(AWS SSM + docker exec)에서 Knowledge/Episode Memory 경로가 실데이터를 반환하는지 검증한다.

**Architecture:** 
- Phase 1-2: 로컬 코드 정리 (Stub 제거, follow-up 정리) on `feature/validation-knowledge-activation` 브랜치
- Phase 3: PR 생성 → develop 머지 → EC2 자동배포 완료 대기
- Phase 4: 크롬 MCP + AWS SSM Session Manager + docker exec로 운영 검증
- Phase 5: 기존 계획서/INDEX/CLAUDE.md 체크박스·상태 정리

**Tech Stack:** Python 3.11+, pytest, isort, ruff, black, AWS SSM, Docker, 크롬 MCP, KT Cloud RAG Suite, Pinecone

---

## 배경

### 현재 상태 (2026-04-15 13:40 확인)
- **운영 경로**: `src/graph/workflow.py` → `src/agents/podcast/podcast_reasoning.py:665` `podcast_reasoning_node()`는 이미 `PodcastReasoningAgent(knowledge_agent=KnowledgeAgent())`로 실제 KnowledgeAgent를 DI 주입 중.
- **Episode Memory**: `podcast_reasoning_node()`가 `episode_memory=` 를 주입하지 않아 `PodcastReasoningAgent.__init__` 내부 lazy import fallback으로 실제 `EpisodeMemoryAgent()` 사용.
- **Stub 잔존 경로**: `src/agents/podcast/podcast_reasoning.py:73` `self.knowledge_agent = knowledge_agent or KnowledgeAgentStub()` — DI 미전달 시 Stub로 fallback. 운영에서는 이미 실제 에이전트 주입 중이므로 이 경로는 실사용되지 않지만, 테스트·내부 모듈 재사용 시 Stub이 쓰일 수 있어 **코드 오인/장애 복구 시 위험**.
- **KnowledgeAgentStub 정의**: `src/agents/shared/stubs.py:46` — 빈 `{"articles": [], "guidelines": []}` 반환.

### 영향 받는 기존 계획서
| 계획서 | 영향 |
|--------|------|
| `2026-04-06-pending-items-inventory.md` Section A | Stub→실제 전환 — 이 계획서로 종결 |
| `2026-04-15-pr145-knowledge-rag-followup.md` F1~F5 | follow-up 정리 항목 — 이 계획서 Phase 2에 포함 |
| `2026-04-07-pinecone-vector-db-integration.md` | Pinecone 임계값 외부화 이미 PR #146으로 해결 — 체크박스만 반영 |

### 이 계획서 범위 밖 (별도 트랙)
- `agent-io-consolidation` Task 1~7, 11 (백엔드 테이블 미확보)
- `git-history-cleanup` (3인 합의 + force-push)
- `script_personalizer` 4개 pass 분기 (개발자1 담당)
- mypy 63 에러 (별도 lint 트랙)
- `plan8-apiproxy-cleanup` (보류 확정)

---

## 사전 조건

- [x] develop 브랜치 최신 상태 확인 (`git fetch origin && git log --oneline -5`)
- [x] PR #146이 develop에 머지 완료(e2f6a35) 확인
- [x] 작업 브랜치 생성: `feature/validation-knowledge-activation`
- [ ] 3인 중 누가 Stub 제거 PR 리뷰할지 사전 조율 (공용 파일 `src/agents/shared/stubs.py` 수정이므로 전원 리뷰 권장)

---

## Phase 1: Stub 잔존 경로 정식 제거

### Task 1-1: `podcast_reasoning.py` — KnowledgeAgent lazy import 패턴 적용

**Files:**
- Edit: `src/agents/podcast/podcast_reasoning.py`

실제 KnowledgeAgent로 fallback하도록 변경. EpisodeMemoryAgent와 동일한 lazy import 패턴 유지 (순환 참조 방지).

- [x] **Step 1**: Line 27 Stub import 제거
  ```python
  # 제거
  from src.agents.shared.stubs import KnowledgeAgentStub
  ```

- [x] **Step 2**: Line 30~41 사이에 KnowledgeAgent lazy import 함수 추가
  ```python
  _KnowledgeAgent: type | None = None


  def _get_knowledge_agent_class() -> type:
      """KnowledgeAgent를 lazy import한다."""
      global _KnowledgeAgent  # noqa: PLW0603
      if _KnowledgeAgent is None:
          from src.agents.podcast.knowledge import KnowledgeAgent

          _KnowledgeAgent = KnowledgeAgent
      return _KnowledgeAgent
  ```

- [x] **Step 3**: Line 73 fallback 변경
  ```python
  # Before
  self.knowledge_agent = knowledge_agent or KnowledgeAgentStub()
  # After
  self.knowledge_agent = knowledge_agent or _get_knowledge_agent_class()()
  ```

- [x] **Step 4**: docstring 수정 — Line 62
  ```python
  # Before: knowledge_agent: Knowledge Agent (DI — 없으면 stub 사용)
  # After:  knowledge_agent: Knowledge Agent (DI — 없으면 KnowledgeAgent 사용)
  ```

- [x] **Step 5**: Line 663~665 `podcast_reasoning_node()` 간소화
  ```python
  # Before
  from src.agents.podcast.knowledge import KnowledgeAgent
  agent = PodcastReasoningAgent(knowledge_agent=KnowledgeAgent())
  # After (fallback이 실제 에이전트이므로 명시적 주입 불필요)
  agent = PodcastReasoningAgent()
  ```

### Task 1-2: `stubs.py` — KnowledgeAgentStub 클래스 제거

**Files:**
- Edit: `src/agents/shared/stubs.py`

⚠️ 공용 파일(`src/agents/shared/`) 수정 — 3인 리뷰 필요.

- [x] **Step 1**: Grep으로 잔여 참조 확인
  ```bash
  grep -rn "KnowledgeAgentStub" src/ tests/ dev/
  ```
  Expected: `src/agents/shared/stubs.py`만 남아야 함 (Task 1-1 적용 후).

- [x] **Step 2**: Line 46~75 `KnowledgeAgentStub` 클래스 제거
- [x] **Step 3**: 파일 상단 docstring에서 Knowledge Agent stub 설명 줄 제거 (Line 5~6 주변)
- [x] **Step 4**: `EpisodeMemoryStub`은 유지 — 테스트/검증용 (제거 대상 아님)

### Task 1-3: 테스트 보강

**Files:**
- Edit or Create: `tests/unit/agents/podcast/test_podcast_reasoning.py`

- [x] **Step 1**: 기존 `KnowledgeAgentStub` 사용 테스트 검색
  ```bash
  grep -rn "KnowledgeAgentStub" tests/
  ```

- [x] **Step 2**: 발견 시 `MagicMock(spec=KnowledgeAgent)` 패턴으로 전환
  ```python
  from unittest.mock import AsyncMock, MagicMock
  from src.agents.podcast.knowledge import KnowledgeAgent

  mock_ka = MagicMock(spec=KnowledgeAgent)
  mock_ka.search = AsyncMock(return_value={"articles": [], "guidelines": []})
  agent = PodcastReasoningAgent(knowledge_agent=mock_ka)
  ```

- [x] **Step 3**: DI 미전달 시 실제 KnowledgeAgent 인스턴스가 생성되는지 확인하는 테스트 추가 (1건) — `test_di_injection`에서 확인
  ```python
  def test_podcast_reasoning_default_uses_real_knowledge_agent():
      agent = PodcastReasoningAgent()
      from src.agents.podcast.knowledge import KnowledgeAgent
      assert isinstance(agent.knowledge_agent, KnowledgeAgent)
  ```

### Task 1-4: 로컬 검증

- [x] **Step 1**: 로컬 단위 테스트 실행
  ```bash
  pytest tests/agents/podcast/test_podcast_reasoning.py -v
  ```
  Result: 전원 통과

- [x] **Step 2**: 전체 테스트
  ```bash
  pytest tests/ -v
  ```
  Result: **594 passed** (596 → 594; KnowledgeAgentStub 단위 테스트 2건 제거 반영)

- [x] **Step 3**: lint/format
  ```bash
  black src/ tests/     # All done! (5 files would be left unchanged)
  isort src/ tests/     # Skipped 12 files (no changes needed)
  ruff check src/ tests/  # All checks passed!
  ```

---

## Phase 2: PR #145 follow-up 정리

### Task 2-1: `pr145-knowledge-rag-followup.md` 잔여 항목 처리

**Files:**
- Read: `docs/superpowers/plans/2026-04-15-pr145-knowledge-rag-followup.md`

- [x] **Step 1**: 계획서 열어 F1~F5 재확인 및 현재 코드 상태 대조 — PR #145/#146으로 이미 모두 해결됨 확인
- [x] **Step 2**: F1 (isort) — Phase 1 Task 1-4에서 처리됨 → 체크박스 반영 완료
- [x] **Step 3**: F2 (.env.example 중복 제거) — PR #145에서 해결
- [x] **Step 4**: F3 (docstring) — PR #146에서 Google-style로 정리 완료
- [x] **Step 5**: F4 (f-string) — PR #146에서 정리 완료
- [x] **Step 6**: follow-up 계획서 체크박스 반영 (F1~F5 전체 `[x]` 처리)

### Task 2-2: `pinecone-vector-db-integration.md` 체크박스 반영

**Files:**
- Edit: `docs/superpowers/plans/2026-04-07-pinecone-vector-db-integration.md`

- [ ] **Step 1**: Pinecone 임계값 외부화 관련 Task/Step 체크 반영 (PR #146 해결)
- [ ] **Step 2**: `scripts/ingest_knowledge.py` 관련 Task 7 체크 반영 (PR #145 해결)
- [ ] **Step 3**: 여전히 미완료인 Task 2(BedrockEmbeddingClient), Task 5(test_embedding), Task 6(roundtrip), Task 9(PINECONE_DEVELOPER_GUIDE)는 미완료 유지 — 별도 트랙 명시 코멘트 추가

---

## Phase 3: PR 생성 및 develop 머지

### Task 3-1: 커밋 및 PR

- [ ] **Step 1**: 변경분 확인
  ```bash
  git status
  git diff --stat
  ```
  Expected 영향 파일:
  - `src/agents/podcast/podcast_reasoning.py` (Stub import 제거 · lazy import 추가 · `podcast_reasoning_node` 간소화, ±13 라인)
  - `src/agents/shared/stubs.py` (KnowledgeAgentStub 클래스 제거, −32 라인)
  - `tests/unit/agents/podcast/test_podcast_reasoning.py` (±15 라인)
  - `.env.example` (선택, F2 정리 시)
  - `docs/superpowers/plans/*.md` (체크박스 반영)
  - 참고: `src/graph/workflow.py`는 수정 없음 — `podcast_reasoning_node` 정의는 `podcast_reasoning.py` 파일 말미에 있음

- [ ] **Step 2**: 커밋 (Co-Authored-By 미포함 — user feedback)
  ```bash
  git add <파일 목록 — 민감파일 제외>
  git commit -m "refactor: KnowledgeAgentStub 정식 제거 및 PR #145 follow-up 정리"
  ```

- [ ] **Step 3**: push 전 사용자 명시적 승인 확인 (user feedback: 명시적 명령 필요)

- [ ] **Step 4**: PR 생성 (base: `develop`, user feedback 준수)
  PR 본문에 포함:
  - Summary (Stub 제거·운영 영향 없음·테스트 보강)
  - Test plan (pytest 596+ passed, lint/format 통과)
  - 영향 받는 계획서 목록 및 체크박스 반영 내역
  - 3인 리뷰 요청 사유 (공용 `stubs.py` 수정)

### Task 3-2: 머지 후 자동 배포 대기

- [ ] **Step 1**: PR 머지 (리뷰 1명 이상)
- [ ] **Step 2**: GitHub Actions 배포 파이프라인 완료 확인
  ```bash
  gh run list --branch develop --limit 5
  gh run watch <run-id>
  ```
- [ ] **Step 3**: deploy.yml SSM 배포 로그에서 health check `200 OK` 확인 (PR #143 반영분)

---

## Phase 4: AWS SSM 운영 검증 (크롬 MCP + 클립보드 방식)

> **워크플로우**: 크롬 MCP로 AWS 콘솔 그룹을 열고, 사용자가 SSM 탭으로 전환하면
> 에이전트는 검증 명령을 클립보드에 복사 → 사용자가 SSM 터미널에 붙여넣기 →
> 실행 결과를 스크린샷·복사로 돌려받아 해석한다.

### Task 4-1: 크롬 MCP 그룹 오픈 및 환경 확인

- [ ] **Step 1**: 크롬 MCP로 AWS 콘솔 그룹 오픈 (대기 상태 — 사용자가 SSM 탭 이동 후 "준비 완료" 신호)
- [ ] **Step 2**: 배포 대상 EC2 인스턴스 ID 확인 (`mindlog-ai-service` 컨테이너 구동 중)
- [ ] **Step 3**: Docker 컨테이너 상태 확인 (클립보드 복사)
  ```bash
  sudo docker ps --filter name=mindlog-ai-service --format "{{.Names}}\t{{.Status}}\t{{.Image}}"
  ```
  Expected: `Up <time>` 상태, 이미지 태그가 최신 develop SHA와 일치

- [ ] **Step 4**: 컨테이너 기동 후 재시작 이력 확인
  ```bash
  sudo docker inspect mindlog-ai-service --format '{{.RestartCount}} {{.State.StartedAt}}'
  ```

### Task 4-2: 설정 반영 검증 (PR #146 효과)

- [ ] **Step 1**: `pinecone_score_threshold` 설정 로드 확인
  ```bash
  sudo docker exec mindlog-ai-service python3 -c "
  from config.loader import get_settings
  s = get_settings()
  print('knowledge config:', s.get_agent_config('knowledge'))
  print('threshold:', s.get_agent_config('knowledge').get('pinecone_score_threshold'))
  "
  ```
  Expected: `threshold: 0.7`

- [ ] **Step 2**: `KnowledgeAgentStub` 제거 반영 확인 (Phase 1 머지 후)
  ```bash
  sudo docker exec mindlog-ai-service python3 -c "
  try:
      from src.agents.shared.stubs import KnowledgeAgentStub
      print('STUB_STILL_EXISTS')
  except ImportError:
      print('STUB_REMOVED_OK')
  "
  ```
  Expected: `STUB_REMOVED_OK`

- [ ] **Step 3**: `PodcastReasoningAgent` 기본 인스턴스가 실제 KnowledgeAgent를 쓰는지 확인
  ```bash
  sudo docker exec mindlog-ai-service python3 -c "
  from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent
  from src.agents.podcast.knowledge import KnowledgeAgent
  a = PodcastReasoningAgent()
  print('knowledge_agent type:', type(a.knowledge_agent).__name__)
  print('is_real:', isinstance(a.knowledge_agent, KnowledgeAgent))
  "
  ```
  Expected: `is_real: True`

### Task 4-3: Knowledge 경로 실호출 검증

- [ ] **Step 1**: 환경변수 로딩 확인
  ```bash
  sudo docker exec mindlog-ai-service python3 -c "
  import os
  keys = [
      'KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT',
      'KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY_ENDPOINT',
      'KT_CLOUD_KNOWLEDGE_TEXTGEN_ENDPOINT',
      'PINECONE_API_KEY',
      'PINECONE_INDEX_KNOWLEDGE',
  ]
  for k in keys:
      v = os.environ.get(k, '')
      print(f'{k}={\"SET\" if v else \"EMPTY\"}')
  "
  ```
  Expected: 전부 `SET`. EMPTY 있으면 GitHub Secrets / deploy 환경변수 누락 → 별도 조치.

- [ ] **Step 2**: 실제 `search()` 1회 호출 — 빈 배열이 아닌 응답 확인
  ```bash
  sudo docker exec mindlog-ai-service python3 -c "
  import asyncio
  from src.agents.podcast.knowledge import KnowledgeAgent
  async def run():
      ka = KnowledgeAgent()
      r = await ka.search(query='스트레스 관리 방법', domain='mental_health')
      print('articles_count:', len(r.get('articles', [])))
      print('guidelines_count:', len(r.get('guidelines', [])))
      if r.get('articles'):
          print('first_article_keys:', list(r['articles'][0].keys())[:5])
  asyncio.run(run())
  "
  ```
  Expected: `articles_count >= 1`. 0이면 (a) Pinecone 인덱스 비어있음, (b) 임베딩 실패, (c) 스코어 임계값 미달 중 하나 — 로그로 원인 추가 조사.

- [ ] **Step 3**: Episode Memory 경로도 동시 검증 (user_id는 실사용자 UUID 사용)
  ```bash
  sudo docker exec mindlog-ai-service python3 -c "
  import asyncio
  from src.agents.podcast.episode_memory import EpisodeMemoryAgent
  async def run():
      em = EpisodeMemoryAgent()
      state = {'user_id': '<실사용자_UUID>', 'user_input': '요즘 자꾸 불안해'}
      r = await em.process(state)
      mr = r.get('memory_results', {})
      print('items_count:', len(mr.get('items', [])))
      print('summary_len:', len(mr.get('summary', '')))
  asyncio.run(run())
  "
  ```

### Task 4-4: 운영 로그 확인

- [ ] **Step 1**: Knowledge Agent 로그 필터링 (JSON 로그, user feedback 준수)
  ```bash
  sudo docker logs --tail 500 mindlog-ai-service 2>&1 | grep -E '"agent":\s*"knowledge"|KnowledgeAgent' | head -30
  ```
  Expected: KT Cloud 호출 / Pinecone query / textgen 응답 관련 로그 존재

- [ ] **Step 2**: 에러 로그 점검 — 최근 10분
  ```bash
  sudo docker logs --since 10m mindlog-ai-service 2>&1 | grep -iE 'ERROR|CRITICAL|timeout|CancelledError' | head -20
  ```
  Expected: Knowledge/Pinecone 관련 ERROR 없음. CancelledError는 PR #140로 스택트레이스 제거됨.

- [ ] **Step 3**: Bedrock/KT Cloud 지연 로그 — PR #131/#135/#136 반영 확인
  ```bash
  sudo docker logs --tail 300 mindlog-ai-service 2>&1 | grep -E 'duration_ms|latency' | head -10
  ```

### Task 4-5: 종단 파이프라인 확인 (선택)

백엔드 서버에서 AI 서버로 실제 요청을 보내 Podcast 모드 종단 실행.

- [ ] **Step 1**: 내부 테스트 사용자로 작은 팟캐스트 요청 1건 전송 (백엔드 API 경유)
- [ ] **Step 2**: 응답 `knowledge_results.articles`가 비어있지 않은지 확인
- [ ] **Step 3**: `reasoning_result.key_themes` 및 `content_analysis.sub_themes`가 정상 생성되는지 확인

---

## Phase 5: 기존 계획서 체크박스 일괄 정리

### Task 5-1: `pending-items-inventory.md` Section A 종결

**Files:**
- Edit: `docs/superpowers/plans/2026-04-06-pending-items-inventory.md`

- [x] **Step 1**: Section A "Stub→실제 에이전트 전환" 전체 항목 `[x]` 반영
- [x] **Step 2**: 하단에 완료 기록 추가
  ```markdown
  > **2026-04-15 완료**: PR #145/#146으로 KnowledgeAgent 구현 완료,
  > feature/validation-knowledge-activation (PR #<번호>)로 Stub 정식 제거.
  > 후속 검증: `2026-04-15-knowledge-agent-activation-and-verification.md` Phase 4.
  ```

### Task 5-2: `pr145-knowledge-rag-followup.md` 종결

- [x] **Step 1**: 해결된 체크박스 `[x]` 반영
- [x] **Step 2**: 미해결 잔여 항목은 별도 트랙으로 명시 (있다면) — 전부 해결됨
- [x] **Step 3**: 상태 라인에 "본 계획서 종결 — 후속은 2026-04-15-knowledge-agent-activation-and-verification.md" 표기

### Task 5-3: `PLAN_INDEX.md` 갱신

**Files:**
- Edit: `docs/superpowers/PLAN_INDEX.md`

- [x] **Step 1**: 이 계획서(`2026-04-15-knowledge-agent-activation-and-verification.md`) 항목 신규 추가
- [x] **Step 2**: 위 Task 5-1/5-2에서 종결된 계획서 상태 `✅ 완료`로 변경
- [x] **Step 3**: 날짜+시간 표기 (user feedback: `YYYY-MM-DD HH:MM`)

### Task 5-4: CLAUDE.md 구현 현황 갱신

**Files:**
- Edit: `CLAUDE.md`

- [x] **Step 1**: "인프라 강화 (PR #52~#143)" 표에 본 PR 번호 추가
- [x] **Step 2**: 테스트 현황 숫자 업데이트 (596 → 594)
- [x] **Step 3**: "마지막 업데이트" 라인 `2026-04-15 <HH:MM>`로 갱신

---

## 롤백 플랜

### Phase 1-2 문제 발생 시
```bash
# develop에서 역방향 PR
git checkout develop
git pull
git revert <merge-commit-sha>
git push origin develop
```
Stub import 경로가 다시 살아나므로 운영엔 영향 없음. 테스트만 재조정 필요.

### Phase 4 SSM 검증 실패 시
| 증상 | 조치 |
|------|------|
| `threshold != 0.7` | GitHub Secrets / deploy.yml에서 설정 오버라이드 여부 확인 |
| `KnowledgeAgentStub` import 성공 | 배포 이미지 태그가 최신 아님 — deploy.yml 재실행 |
| `articles_count == 0` | Pinecone 인덱스 적재 여부, KT Cloud 토큰 유효성, 임계값 과도 여부 순차 확인 |
| KT Cloud 타임아웃 | `api.llm_timeout` 조정 검토, 별도 이슈 발행 |
| ERROR 로그 다수 | 배포 롤백 후 원인 분석 (롤백 스크립트 PR #143 반영분 활용) |

---

## 리스크 및 3인 합의 필요 범위

| 항목 | 리스크 | 완화 |
|------|--------|------|
| `src/agents/shared/stubs.py` 수정 | 공용 파일 — 전원 리뷰 필요 | CLAUDE.md 규칙 준수, 리뷰 요청 명시 |
| `podcast_reasoning_node()` 수정 | `src/graph/workflow.py`와 인접 — Protected File 인접성 | Protected File 본체는 수정 안 함, 노드 함수만 조정 |
| 운영 SSM 명령 실행 | sudo 권한 사용 | 사용자 주도 클립보드 붙여넣기 방식으로 확인 후 실행 |
| 실사용자 UUID 사용 (Task 4-3) | PII 로그 노출 | 테스트 전용 UUID 발급, 로그 출력은 카운트만 |

---

## 실행 체크리스트 (요약)

```
[ ] Phase 1: Stub 제거 — 코드 4파일 수정, 테스트 보강, 로컬 lint/pytest 통과
[ ] Phase 2: PR #145 follow-up 항목 정리 (F1~F5)
[ ] Phase 3: PR 생성 → 리뷰 → develop 머지 → 배포 성공
[ ] Phase 4: SSM 검증 5개 영역 (컨테이너/설정/타입/호출/로그) 전부 Pass
[ ] Phase 5: 계획서 3개 + PLAN_INDEX + CLAUDE.md 체크박스·상태·날짜 정리
```

---

## 성공 기준 (Definition of Done)

- [ ] `pytest tests/ -v` 전원 통과
- [ ] `grep -rn "KnowledgeAgentStub" src/` 결과 없음
- [ ] SSM에서 `is_real: True` 응답
- [ ] SSM에서 `articles_count >= 1` 응답 (실호출 검증)
- [ ] 로그에 KT Cloud / Pinecone 관련 ERROR 없음
- [ ] PR 머지 후 GitHub Actions 배포 성공
- [ ] 영향 받는 기존 계획서 3건 + PLAN_INDEX + CLAUDE.md 갱신 완료

---

*작성: 2026-04-15 13:50*
*기반 문서: `docs/superpowers/plans/2026-04-06-pending-items-inventory.md`, `docs/superpowers/plans/2026-04-15-pr145-knowledge-rag-followup.md`*
*관련 PR: #145 (Knowledge RAG 1차 구현), #146 (Knowledge Agent 리팩터링)*

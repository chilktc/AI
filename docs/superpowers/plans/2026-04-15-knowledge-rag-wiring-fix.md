# Knowledge RAG 결과 파이프라인 연결 수정 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR #145~#150에서 복구된 Knowledge Agent의 `search()` 결과가 Podcast Reasoning 추론 LLM과 Script Generator의 스크립트 생성에 실제로 반영되도록 상태 키·포맷 매핑과 phase별 주입 로직을 수정한다.

**Architecture:**
- Podcast Reasoning은 `_build_phase_context`에서 `knowledge_result["articles"]`의 실제 내용(title/content/source)을 phase별 역할에 맞춰 LLM에 주입한다(ToT=제목, CoT=근거 요약).
- Script Generator는 존재하지 않는 `state["knowledge_context"]` 대신 AgentState 정의 필드 `state["knowledge_results"]`를 읽고, `search()`의 `{"articles": [...]}` 구조에서 `_synthesis` 기사 또는 상위 기사 내용을 `knowledge_summary`로 조합한다.
- Knowledge Agent의 search 경로에 관측성(vector match/backend fetch 괴리 경고)·설정 외부화(`pinecone_top_k`)·Backend URL 기본값 정합성을 보완한다.

**Tech Stack:** Python 3.11+, pytest + pytest-asyncio, LangGraph StateGraph, KT Cloud RAG Suite(Parser/Embedding/TextGen) + Pinecone

**브랜치/PR 분리 (담당자별):**
- **Part A — 개발자3 (Podcast Reasoning)**: `feature/validation-knowledge-reasoning-injection`
- **Part B — 개발자1 (Script Generator)**: `feature/analysis-knowledge-script-wiring`
- **Part C — 개발자1 (Knowledge Agent 보완)**: `feature/analysis-knowledge-agent-observability`
- 각 Part는 독립 PR로 `develop`에 올린다. Part A→B 순서로 머지해야 실제 연결 흐름이 완성된다 (Part A만 머지해도 Reasoning LLM은 이미 근거를 받음).

**선행 확인:**
- 현재 develop 기준 `src/agents/podcast/knowledge.py:43-44`는 `KT_CLOUD_KNOWLEDGE_PARSE_*` env로 확정 (PR #150, 2026-04-15 머지).
- AgentState 정의 필드는 `knowledge_results` 뿐이며 `knowledge_context`는 존재하지 않음 (`src/models/agent_state.py:46`).
- `KnowledgeAgent.search()`의 반환 스키마: `{"articles": [{id, title, content, score, domain, source, page}...], "guidelines": []}` (`src/agents/podcast/knowledge.py:361-395`). `_synthesis` 기사가 존재할 경우 `articles[0]`에 삽입됨 (`id="_synthesis"`, `source="KT RAG Suite TextGen"`).

---

## 배경: 코드 리뷰에서 확정된 3개 Critical 버그

리뷰 로그: 2026-04-15 본 계획서 직전 대화 참조.

1. **Bug 1 — Script Generator 잘못된 state 키** (`src/agents/podcast/script_generator.py:115`)
   `state.get("knowledge_context", {})` — AgentState에 없는 필드라 항상 `{}` 반환.

2. **Bug 2 — search() vs process() 포맷 불일치** (`src/agents/podcast/script_generator.py:294`)
   `knowledge_context.get("knowledge_results", {}).get("synthesis")` — legacy `process()` 포맷을 기대하지만 런타임 경로인 `search()`는 `{"articles": [...]}`를 top-level로 반환.

3. **Bug 3 — Reasoning LLM에 지식 내용 미전달** (`src/agents/podcast/podcast_reasoning.py:475-477`)
   `f"- {article_count}건 발견"` — 기사 내용을 전혀 주입하지 않아 GoT/ToT/CoT 모두 RAG 근거 없이 추론.

부가 개선 (Suggestions)도 Part C에서 일부 반영한다.

---

## Part A — Podcast Reasoning 컨텍스트 주입 (개발자3)

### 사전 준비

- [ ] **A-0: 작업 브랜치 생성**

```bash
git fetch origin
git checkout develop
git pull origin develop
git checkout -b feature/validation-knowledge-reasoning-injection
```

---

### Task A1: ToT phase에서 knowledge 제목 목록 주입 — 실패 테스트 작성

**Files:**
- Modify test: `tests/agents/podcast/test_podcast_reasoning.py` (파일 맨 아래에 추가)

- [ ] **Step 1: 실패 테스트 추가**

다음 코드를 `tests/agents/podcast/test_podcast_reasoning.py` 파일 맨 끝에 append 한다:

```python
# === Knowledge Result — phase별 주입 ===


def test_build_phase_context_got_knowledge_count_only(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """GoT phase: knowledge_result가 있어도 건수만 포함되고 원문·제목은 포함되지 않는다."""
    knowledge_result = {
        "articles": [
            {
                "id": "doc1",
                "title": "CBT 인지왜곡",
                "content": "인지왜곡은 자동적 사고의 일종으로 ...",
                "score": 0.88,
                "source": "CBT Handbook",
            }
        ],
        "guidelines": [],
    }
    context = agent_with_stubs._build_phase_context(
        phase="GoT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        knowledge_result=knowledge_result,
    )
    assert "[관련 전문 지식]" in context
    assert "1건 발견" in context
    # GoT은 건수만 — 제목/본문 노출 금지 (노드 오염 방지)
    assert "CBT 인지왜곡" not in context
    assert "인지왜곡은 자동적 사고" not in context


def test_build_phase_context_tot_knowledge_titles(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """ToT phase: 기사 제목이 포함되지만 본문은 포함되지 않는다."""
    knowledge_result = {
        "articles": [
            {"id": "doc1", "title": "CBT 인지왜곡", "content": "본문A", "source": "A"},
            {"id": "doc2", "title": "DBT 감정조절", "content": "본문B", "source": "B"},
        ],
        "guidelines": [],
    }
    context = agent_with_stubs._build_phase_context(
        phase="ToT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        knowledge_result=knowledge_result,
    )
    assert "[관련 전문 지식 — 제목 참고]" in context
    assert "CBT 인지왜곡" in context
    assert "DBT 감정조절" in context
    # 본문은 ToT에 주입 금지
    assert "본문A" not in context
    assert "본문B" not in context


def test_build_phase_context_cot_knowledge_with_synthesis(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """CoT phase: _synthesis 기사가 있으면 그 content를 요약 근거로 사용한다."""
    knowledge_result = {
        "articles": [
            {
                "id": "_synthesis",
                "title": "검색 결과 종합",
                "content": "번아웃은 만성 스트레스 누적으로 발생하며 CBT가 효과적이다.",
                "score": 1.0,
                "source": "KT RAG Suite TextGen",
            },
            {"id": "doc1", "title": "CBT 인지왜곡", "content": "본문A", "source": "A"},
        ],
        "guidelines": [],
    }
    context = agent_with_stubs._build_phase_context(
        phase="CoT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        knowledge_result=knowledge_result,
    )
    assert "[관련 전문 지식 — 근거]" in context
    assert "번아웃은 만성 스트레스" in context  # synthesis content 주입


def test_build_phase_context_cot_knowledge_fallback_to_top_articles(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """CoT phase: _synthesis 없으면 상위 기사 title+content 일부를 근거로 주입한다."""
    knowledge_result = {
        "articles": [
            {
                "id": "doc1",
                "title": "CBT 인지왜곡",
                "content": "인지왜곡은 자동적 사고의 일종입니다. " * 30,  # 200자 넘김
                "score": 0.88,
                "source": "CBT Handbook",
            },
            {
                "id": "doc2",
                "title": "DBT 감정조절",
                "content": "DBT는 변증법적 행동치료입니다.",
                "score": 0.75,
                "source": "DBT Manual",
            },
        ],
        "guidelines": [],
    }
    context = agent_with_stubs._build_phase_context(
        phase="CoT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        knowledge_result=knowledge_result,
    )
    assert "[관련 전문 지식 — 근거]" in context
    assert "CBT 인지왜곡" in context
    assert "CBT Handbook" in context
    assert "DBT 감정조절" in context
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_tot_knowledge_titles -v
pytest tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_cot_knowledge_with_synthesis -v
```

기대: 두 테스트 모두 FAIL — 현재 구현은 phase와 무관하게 `"- N건 발견"`만 주입하므로 `"[관련 전문 지식 — 제목 참고]"`, `"[관련 전문 지식 — 근거]"` 섹션이 존재하지 않는다.

---

### Task A2: `_build_phase_context`에 phase별 knowledge 주입 로직 구현

**Files:**
- Modify: `src/agents/podcast/podcast_reasoning.py:475-477`

- [ ] **Step 1: 기존 지식 주입 블록을 phase별 분기로 교체**

`src/agents/podcast/podcast_reasoning.py`의 475~477번 줄 기존 블록:

```python
        if knowledge_result and knowledge_result.get("articles"):
            article_count = len(knowledge_result["articles"])
            parts.append(f"[관련 전문 지식]\n- {article_count}건 발견")
```

를 아래 코드로 치환한다 (동일 들여쓰기 유지: `if phase == "GoT":` 블록과 같은 8 space):

```python
        if knowledge_result and knowledge_result.get("articles"):
            articles = knowledge_result["articles"]
            article_count = len(articles)

            if phase == "GoT":
                # GoT: 건수만 — 그래프 노드 오염 방지 (memory와 동일 원칙)
                parts.append(f"[관련 전문 지식]\n- {article_count}건 발견")

            elif phase == "ToT":
                # ToT: 제목 목록 — 구조 다양성 힌트 (상위 5건까지)
                lines = ["[관련 전문 지식 — 제목 참고]"]
                for a in articles[:5]:
                    title = a.get("title") or "제목 없음"
                    lines.append(f"- {title}")
                lines.append(
                    "→ 위 전문 자료에서 다루는 관점을 대안 생성 시 참고하되, "
                    "구조 다양성을 유지하세요."
                )
                parts.append("\n".join(lines))

            elif phase == "CoT":
                # CoT: 근거 주입 — _synthesis 기사 우선, 없으면 상위 기사 요약 (상위 3건)
                lines = ["[관련 전문 지식 — 근거]"]
                synthesis_article = next(
                    (a for a in articles if a.get("id") == "_synthesis"),
                    None,
                )
                if synthesis_article:
                    summary_text = str(synthesis_article.get("content", ""))[:500]
                    if summary_text:
                        lines.append(f"[종합 요약]\n{summary_text}")
                else:
                    for a in articles[:3]:
                        title = a.get("title") or "제목 없음"
                        content = str(a.get("content", ""))[:200]
                        source = a.get("source") or "출처 불명"
                        if content:
                            lines.append(f"\n- [{title}] {content}... (출처: {source})")

                # 헤더만 있고 실제 근거가 없으면 섹션 생략
                if len(lines) > 1:
                    lines.append(
                        "→ 위 전문 자료에 기반하여 근거 있는 스크립트 핵심 메시지를 구성하세요."
                    )
                    parts.append("\n".join(lines))
```

- [ ] **Step 2: 4개 신규 테스트 + 기존 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py -v -k "build_phase_context" --tb=short
```

기대: 모든 `build_phase_context_*` 테스트 PASS (신규 4개 포함). 기존 memory 관련 테스트도 영향 없음.

- [ ] **Step 3: 전체 파이프라인 회귀 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py -v --tb=short
```

기대: 전부 PASS.

- [ ] **Step 4: 커밋**

```bash
git add src/agents/podcast/podcast_reasoning.py tests/agents/podcast/test_podcast_reasoning.py
git commit -m "fix: Podcast Reasoning에서 Knowledge 결과를 phase별 LLM 컨텍스트에 실제 주입

- GoT: 건수만 유지 (노드 오염 방지)
- ToT: 상위 5건 제목 주입 (구조 다양성 힌트)
- CoT: _synthesis 기사 우선 / 미존재 시 상위 3건 title+content 200자 주입

기존에는 'N건 발견' 카운트만 주입되어 RAG 근거가 추론 LLM에 전혀 도달하지 못하던 버그 수정."
```

---

### Task A3: PR 생성 (Part A 완료)

- [ ] **Step 1: 테스트 + lint 최종 확인**

```bash
pytest tests/ -x --tb=short
ruff check src/agents/podcast/podcast_reasoning.py tests/agents/podcast/test_podcast_reasoning.py
black --check src/agents/podcast/podcast_reasoning.py tests/agents/podcast/test_podcast_reasoning.py
```

기대: 전체 테스트 PASS, lint 0건.

- [ ] **Step 2: push 및 PR 생성 (base=develop)**

```bash
git push -u origin feature/validation-knowledge-reasoning-injection

/opt/homebrew/bin/gh pr create --base develop --title "fix: Podcast Reasoning phase별 Knowledge RAG 근거 주입" --body "$(cat <<'EOF'
## Summary
- Podcast Reasoning `_build_phase_context`가 `knowledge_result["articles"]` 내용을 LLM에 주입하지 않던 버그 수정.
- GoT/ToT/CoT phase별 역할(오염방지/구조다양성/근거주입)에 맞춰 노출 단위를 분리.

## 배경
- PR #145~#150으로 KnowledgeAgent.search() 경로가 운영에서 동작하도록 복구됨(articles_count>=1).
- 그러나 Reasoning이 기사 본문·제목을 LLM에 전혀 주입하지 않아 RAG 근거가 최종 스크립트에 닿지 못함.

## 변경 사항
- `src/agents/podcast/podcast_reasoning.py:475~` phase별 분기 추가
  - GoT: `N건 발견` 카운트만 (기존 유지)
  - ToT: 상위 5건 제목 + "구조 다양성 참고" 지시
  - CoT: `_synthesis` 기사 content 500자 우선 / 없으면 상위 3건 `[title] content 200자… (출처)` 주입
- 기존 Memory 처리 패턴(GoT=건수, ToT=메타, CoT=원문)과 동일 컨벤션 적용
- 신규 단위 테스트 4개

## Test plan
- [x] `pytest tests/agents/podcast/test_podcast_reasoning.py -v` → 신규 4개 포함 전부 PASS
- [x] `pytest tests/ -x --tb=short` 회귀 없음
- [x] `ruff check` / `black --check`
- [ ] CI 통과

## 후속 (Part B — 개발자1 도메인)
- Script Generator가 `state["knowledge_context"]` 오키 + `synthesis` legacy 포맷을 읽어 Reasoning의 RAG 결과가 스크립트에 반영 안 되는 버그 별도 PR에서 수정 예정.
EOF
)"
```

- [ ] **Step 3: PR URL 기록 및 develop 머지 대기**

PR URL을 기록하고 개발자1/2 리뷰를 기다린다. 머지 후 Part B 착수.

---

## Part B — Script Generator state 키 + articles 매핑 수정 (개발자1)

> **담당 변경**: Script Generator는 개발자1 도메인이므로, Part B는 개발자1이 수행하거나 개발자3이 작성한 계획을 개발자1에게 전달해 PR로 받는다. 계획 내용은 담당자와 무관하게 동일.

### 사전 준비

- [ ] **B-0: 작업 브랜치 생성 (개발자1)**

```bash
git fetch origin
git checkout develop
git pull origin develop
git checkout -b feature/analysis-knowledge-script-wiring
```

---

### Task B1: Script Generator가 state["knowledge_results"]를 읽는 실패 테스트 작성

**Files:**
- Modify test: `tests/agents/podcast/test_script_generator.py` (파일 맨 아래에 추가)

- [ ] **Step 1: 실패 테스트 추가**

다음 코드를 `tests/agents/podcast/test_script_generator.py` 맨 끝에 append:

```python
# === Knowledge Results 주입 경로 ===


def test_script_generator_reads_knowledge_results_state_key() -> None:
    """ScriptGenerator는 AgentState 정의 필드 knowledge_results를 읽어야 한다.

    - state['knowledge_results']['articles']의 _synthesis 기사 content가
      knowledge_summary로 세그먼트 prompt에 포함되어야 한다.
    - state['knowledge_context']는 AgentState에 없는 키이므로 폴백 경로가
      남아 있으면 안 된다 (기본 문구 '사용 가능한 전문 지식이 없습니다' 방지).
    """
    agent = ScriptGeneratorAgent()

    state: AgentState = {
        "content_analysis": {
            "main_theme": "번아웃 회복",
            "sub_themes": [],
            "emotional_journey": {"start_emotion": "지침"},
            "target_duration": 2,
        },
        "segment_plan": [
            {
                "segment_id": "seg_001",
                "segment_type": "intro",
                "duration_minutes": 1,
                "key_points": ["번아웃 정의"],
                "emotional_tone": "calm",
                "transition_hint": "본론",
            }
        ],
        "knowledge_results": {
            "articles": [
                {
                    "id": "_synthesis",
                    "title": "검색 결과 종합",
                    "content": "번아웃은 만성 스트레스로 인한 소진 상태이며 CBT가 효과적이다.",
                    "score": 1.0,
                    "source": "KT RAG Suite TextGen",
                }
            ],
            "guidelines": [],
        },
    }

    captured: dict[str, str] = {}

    async def _fake_generate_segment_script(
        self, segment, episode_title, main_theme, emotional_journey,
        previous_context, knowledge_context, revision_feedback="",
    ):
        # 구현이 knowledge_context로 전달하는 값을 포착 (현재 시그니처 유지)
        captured["knowledge_context"] = repr(knowledge_context)
        return {**segment, "script_text": "테스트 스크립트"}

    with patch.object(
        ScriptGeneratorAgent,
        "_generate_segment_script",
        new=_fake_generate_segment_script,
    ), patch.object(
        ScriptGeneratorAgent,
        "_generate_title",
        new=AsyncMock(return_value="테스트 제목"),
    ), patch.object(
        ScriptGeneratorAgent,
        "_extract_insights",
        new=AsyncMock(return_value=[]),
    ):
        import asyncio

        asyncio.run(agent.process(state))

    # knowledge_results가 실제로 세그먼트 생성기에 전달되었는지 확인
    assert "번아웃은 만성 스트레스" in captured["knowledge_context"], (
        "knowledge_results의 _synthesis content가 세그먼트 생성기에 전달되어야 함"
    )


def test_script_generator_synthesis_extraction_from_articles() -> None:
    """_generate_segment_script에서 articles 구조로부터 knowledge_summary를 뽑는다."""
    import asyncio

    agent = ScriptGeneratorAgent()

    # articles[0] == _synthesis 기사
    knowledge_context_with_synthesis = {
        "articles": [
            {
                "id": "_synthesis",
                "title": "검색 결과 종합",
                "content": "번아웃은 CBT로 회복 가능하다.",
                "source": "KT RAG Suite TextGen",
            },
            {"id": "d1", "title": "CBT", "content": "본문", "source": "A"},
        ],
        "guidelines": [],
    }

    prompt_capture: dict[str, str] = {}

    async def _fake_call_llm_json(self, system_prompt, user_message, **kwargs):
        prompt_capture["user_message"] = user_message
        return {
            "segment_id": "seg_001",
            "script_text": "생성된 스크립트",
            "tags": [],
        }

    segment = {
        "segment_id": "seg_001",
        "segment_type": "body",
        "duration_minutes": 2,
        "key_points": ["핵심"],
        "emotional_tone": "calm",
        "transition_hint": "마무리",
    }

    with patch.object(
        ScriptGeneratorAgent, "call_llm_json", new=_fake_call_llm_json
    ):
        asyncio.run(
            agent._generate_segment_script(
                segment=segment,
                episode_title="T",
                main_theme="번아웃",
                emotional_journey={"start_emotion": "지침"},
                previous_context="",
                knowledge_context=knowledge_context_with_synthesis,
            )
        )

    assert "번아웃은 CBT로 회복 가능하다" in prompt_capture["user_message"], (
        "articles[0]=_synthesis의 content가 prompt에 포함되어야 함"
    )


def test_script_generator_synthesis_fallback_when_no_synthesis() -> None:
    """_synthesis 기사가 없으면 상위 기사 title+content를 조합해 summary를 만든다."""
    import asyncio

    agent = ScriptGeneratorAgent()

    knowledge_context_plain = {
        "articles": [
            {"id": "d1", "title": "CBT 인지왜곡", "content": "자동적 사고 이론", "source": "A"},
            {"id": "d2", "title": "DBT 감정조절", "content": "변증법적 치료", "source": "B"},
        ],
        "guidelines": [],
    }

    prompt_capture: dict[str, str] = {}

    async def _fake_call_llm_json(self, system_prompt, user_message, **kwargs):
        prompt_capture["user_message"] = user_message
        return {"segment_id": "seg_001", "script_text": "x", "tags": []}

    segment = {
        "segment_id": "seg_001",
        "segment_type": "body",
        "duration_minutes": 2,
        "key_points": [],
        "emotional_tone": "calm",
        "transition_hint": "",
    }

    with patch.object(
        ScriptGeneratorAgent, "call_llm_json", new=_fake_call_llm_json
    ):
        asyncio.run(
            agent._generate_segment_script(
                segment=segment,
                episode_title="T",
                main_theme="마음",
                emotional_journey={},
                previous_context="",
                knowledge_context=knowledge_context_plain,
            )
        )

    # 상위 기사의 title 또는 content가 prompt에 포함
    assert "CBT 인지왜곡" in prompt_capture["user_message"]
    assert "자동적 사고 이론" in prompt_capture["user_message"]
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/agents/podcast/test_script_generator.py::test_script_generator_reads_knowledge_results_state_key -v
pytest tests/agents/podcast/test_script_generator.py::test_script_generator_synthesis_extraction_from_articles -v
pytest tests/agents/podcast/test_script_generator.py::test_script_generator_synthesis_fallback_when_no_synthesis -v
```

기대:
- 첫 번째 테스트 FAIL — `state.get("knowledge_context", {})` 경로를 타고 빈 dict가 전달되어 `"번아웃은 만성 스트레스"`가 포함되지 않음.
- 두 번째·세 번째 테스트 FAIL — 현재 구현은 `knowledge_context.get("knowledge_results", {}).get("synthesis")`만 확인하므로 `articles` 내용을 prompt에 넣지 않음.

---

### Task B2: state 키를 `knowledge_results`로 수정하고 articles 매핑 구현

**Files:**
- Modify: `src/agents/podcast/script_generator.py:115` (state 키 교체)
- Modify: `src/agents/podcast/script_generator.py:290-296` (synthesis 추출 로직 교체)

- [ ] **Step 1: state 키 수정 (L115)**

`src/agents/podcast/script_generator.py`의 115번 줄:

```python
        knowledge_context: dict[str, Any] = cast(dict[str, Any], state.get("knowledge_context", {}))
```

를 다음으로 교체 (변수명은 호환성 위해 유지하되 출처만 정정):

```python
        # AgentState 정의 필드는 knowledge_results — Podcast Reasoning이 여기에 기록
        # (src/models/agent_state.py:46, src/agents/podcast/podcast_reasoning.py:165)
        knowledge_context: dict[str, Any] = cast(
            dict[str, Any], state.get("knowledge_results", {})
        )
```

- [ ] **Step 2: synthesis 추출 로직 교체 (L290-296)**

`src/agents/podcast/script_generator.py`의 290~296번 줄 기존 블록:

```python
        # 지식 요약
        knowledge_summary = "사용 가능한 전문 지식이 없습니다."
        if knowledge_context and isinstance(knowledge_context, dict):
            synthesis = knowledge_context.get("knowledge_results", {}).get("synthesis")
            if synthesis:
                knowledge_summary = synthesis
```

를 다음으로 교체:

```python
        # 지식 요약 — KnowledgeAgent.search() 반환 스키마 {"articles": [...]} 기준.
        # 1순위: _synthesis 기사 (TextGen 종합 요약) content
        # 2순위: 상위 3건 기사의 [title] content 150자 조합
        # 3순위: 기본 문구
        knowledge_summary = "사용 가능한 전문 지식이 없습니다."
        if knowledge_context and isinstance(knowledge_context, dict):
            articles = knowledge_context.get("articles", [])
            synthesis_article = next(
                (a for a in articles if a.get("id") == "_synthesis"),
                None,
            )
            if synthesis_article:
                synth_content = str(synthesis_article.get("content", ""))
                if synth_content:
                    knowledge_summary = synth_content
            elif articles:
                summaries = [
                    f"- [{a.get('title', '제목 없음')}] "
                    f"{str(a.get('content', ''))[:150]}"
                    for a in articles[:3]
                    if a.get("content")
                ]
                if summaries:
                    knowledge_summary = "\n".join(summaries)
```

- [ ] **Step 3: 신규 테스트 3개 통과 확인**

```bash
pytest tests/agents/podcast/test_script_generator.py -v -k "knowledge" --tb=short
```

기대: 3개 전부 PASS.

- [ ] **Step 4: 전체 Script Generator 테스트 회귀 확인**

```bash
pytest tests/agents/podcast/test_script_generator.py -v --tb=short
```

기대: 전부 PASS. `knowledge_context` 라벨로 된 기존 live 테스트(L63)는 빈 dict 폴백 경로이므로 영향 없음.

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/script_generator.py tests/agents/podcast/test_script_generator.py
git commit -m "fix: Script Generator가 knowledge_results를 읽고 articles 구조에서 synthesis 추출

- state['knowledge_context'] (AgentState에 없는 키) → state['knowledge_results']로 교체
- legacy process() 포맷인 knowledge_results.synthesis 참조 → search() 포맷인 articles[] 기반 매핑
  1순위: id='_synthesis' 기사의 content (TextGen 종합 요약)
  2순위: 상위 3건 기사의 [title] content 150자 조합
  3순위: 기본 문구

이전에는 knowledge_context 키 부재로 항상 {}가 반환되어 지식이 스크립트에 전혀 반영되지 않던 버그."
```

---

### Task B3: 기존 live 테스트의 state 키도 정합성 맞추기

**Files:**
- Modify: `tests/agents/podcast/test_script_generator.py:63` (`knowledge_context` → `knowledge_results`)

- [ ] **Step 1: 라이브 테스트 키 교체**

`tests/agents/podcast/test_script_generator.py:63` 줄의

```python
        "knowledge_context": {},
```

을 다음으로 교체:

```python
        "knowledge_results": {},
```

- [ ] **Step 2: live 테스트 실행 (Ollama 미사용 환경에서는 skip 확인만)**

```bash
pytest tests/agents/podcast/test_script_generator.py -v -m "not live"
```

기대: live 마크가 없는 테스트는 PASS, live 테스트는 fixture skip.

- [ ] **Step 3: 커밋**

```bash
git add tests/agents/podcast/test_script_generator.py
git commit -m "test: Script Generator live 테스트 state 키 knowledge_results로 정렬"
```

---

### Task B4: PR 생성 (Part B 완료)

- [ ] **Step 1: 최종 확인**

```bash
pytest tests/ -x --tb=short
ruff check src/agents/podcast/script_generator.py tests/agents/podcast/test_script_generator.py
black --check src/agents/podcast/script_generator.py tests/agents/podcast/test_script_generator.py
```

- [ ] **Step 2: push 및 PR 생성**

```bash
git push -u origin feature/analysis-knowledge-script-wiring

/opt/homebrew/bin/gh pr create --base develop --title "fix: Script Generator가 knowledge_results 상태 키·articles 포맷 사용하도록 수정" --body "$(cat <<'EOF'
## Summary
- Script Generator가 AgentState에 정의된 `knowledge_results` 필드를 읽고, `KnowledgeAgent.search()`의 `{"articles": [...]}` 반환 포맷에서 요약을 추출하도록 정정.
- 기존 `state['knowledge_context']` + `.knowledge_results.synthesis` legacy 경로는 모두 무동작(빈 dict) 상태였음.

## 배경 (Part A 후속)
- Part A(PR #<TBD>)에서 Podcast Reasoning이 `state['knowledge_results']`에 `{"articles":[...]}`를 기록하도록 경로 확인됨.
- 그러나 Script Generator는 `state['knowledge_context']`(AgentState 미정의 키)를 읽고 있었고, 내부 추출도 legacy `process()` 포맷의 `synthesis` 키만 확인하여 RAG 결과가 세그먼트 prompt에 전혀 들어가지 못함.

## 변경 사항
- `src/agents/podcast/script_generator.py:115` `knowledge_context` → `knowledge_results` 키 교체
- `src/agents/podcast/script_generator.py:290~` articles 기반 요약 추출 (_synthesis 기사 > 상위 3건 조합 > 기본 문구)
- `tests/agents/podcast/test_script_generator.py` 신규 유닛 테스트 3개 + 기존 live 픽스처 키 정합화

## Test plan
- [x] `pytest tests/agents/podcast/test_script_generator.py -v` → 신규 3개 포함 전부 PASS
- [x] `pytest tests/ -x --tb=short` 회귀 없음
- [x] `ruff check` / `black --check`
- [ ] CI 통과
- [ ] 배포 후 `knowledge_summary`가 "사용 가능한 전문 지식이 없습니다." 외 실제 요약으로 기록되는지 로그 확인

## 관련
- 선행 PR: <Part A PR URL>
- 선행 히스토리: PR #145, #146, #147, #148, #149, #150 (KT Cloud RAG 연동 및 env 정합성)
EOF
)"
```

- [ ] **Step 3: develop 머지 확인**

Part A가 이미 머지되었다면 Part B 머지 후 실제 파이프라인에서 Reasoning의 `knowledge_results`가 Script Generator의 prompt까지 이어진다.

---

## Part C — Knowledge Agent 관측성·설정 정리 (개발자1, 선택적)

> **우선순위 주의:** Part C는 Critical이 아닌 Suggestion 범주. Part A/B 머지 이후 여유 있을 때 별도 PR로 진행한다. Part A/B 머지 없이 이 Part만 선행해도 체감 효과가 없다.

### 사전 준비

- [ ] **C-0: 작업 브랜치 생성**

```bash
git fetch origin
git checkout develop
git pull origin develop
git checkout -b feature/analysis-knowledge-agent-observability
```

---

### Task C1: Pinecone match > 0 이지만 RDB 문서 0건일 때 경고 로깅

**Files:**
- Modify: `src/agents/podcast/knowledge.py:355-358`
- Modify test: `tests/agents/podcast/test_knowledge.py` (말미에 추가)

- [ ] **Step 1: 실패 테스트 추가**

```python
# === 관측성: vector matches > 0 && documents == 0 ===


@pytest.mark.asyncio
async def test_search_warns_when_matches_but_no_backend_docs(
    agent: KnowledgeAgent, caplog
) -> None:
    """Pinecone match가 있는데 Backend RDB에서 문서가 0건이면 경고 로그를 남긴다."""
    import logging

    caplog.set_level(logging.WARNING)

    # env 설정되어 있다고 가정하고 내부 헬퍼들을 mock
    agent.kt_embedding_endpoint = "https://mock"
    agent.kt_embedding_token = "t"

    agent._parse_query = AsyncMock(return_value="번아웃")  # type: ignore[method-assign]
    agent._embed_query = AsyncMock(return_value=[0.1] * 5)  # type: ignore[method-assign]
    agent._query_pinecone = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": "chunk-1", "score": 0.91}]
    )
    agent._fetch_documents_from_backend = AsyncMock(return_value=[])  # type: ignore[method-assign]
    agent._generate_synthesis = AsyncMock(return_value="")  # type: ignore[method-assign]

    result = await agent.search("번아웃 회복", domain="mental_health")

    assert result == {"articles": [], "guidelines": []}
    # 핵심 단서가 포함된 경고 로그 검증
    assert any(
        "RDB 원문 조회" in rec.message
        and "matches=1" in rec.message
        and "documents=0" in rec.message
        for rec in caplog.records
        if rec.levelno == logging.WARNING
    ), "Pinecone 매치는 있는데 RDB 문서가 0건이면 경고 필요"
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/agents/podcast/test_knowledge.py::test_search_warns_when_matches_but_no_backend_docs -v
```

기대: FAIL — 현재 구현은 조용히 빈 articles를 반환.

- [ ] **Step 3: knowledge.py search()에 경고 로깅 추가**

`src/agents/podcast/knowledge.py`의 354~358번 줄을 찾아 (`# 3-1. Backend RDB: ...` 주석 아래):

```python
            # 3-1. Backend RDB: Pinecone top_k chunk_id로 원문 조회
            chunk_ids = [m.get("id") for m in matches if m.get("id")]
            score_map = {m.get("id"): m.get("score", 0.0) for m in matches if m.get("id")}
            documents = await self._fetch_documents_from_backend(chunk_ids)  # type: ignore[arg-type]
```

바로 아래(`# 4. 결과를 articles 구조로 매핑 ...` 주석 앞)에 다음 블록을 삽입:

```python
            # 관측성: vector match는 있으나 RDB 문서 0건인 경우
            # (backend 장애 / Pinecone-RDB 인덱스 불일치 의심)
            if chunk_ids and not documents:
                self.logger.warning(
                    "[KnowledgeAgent] Pinecone match가 있으나 Backend RDB 원문 0건 "
                    "(matches=%d, documents=0, domain=%s). "
                    "Pinecone-RDB 인덱스 정합성 또는 Backend 연결 상태 점검 필요.",
                    len(chunk_ids),
                    domain,
                )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_knowledge.py::test_search_warns_when_matches_but_no_backend_docs -v
```

기대: PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/knowledge.py tests/agents/podcast/test_knowledge.py
git commit -m "feat: KnowledgeAgent — Pinecone match > 0 && RDB 문서 0건 경고 로깅

Backend 장애 또는 Pinecone-RDB 인덱스 불일치 조기 탐지."
```

---

### Task C2: `pinecone_top_k` settings.yaml 외부화

**Files:**
- Modify: `config/settings.yaml` (`agents.knowledge` 섹션)
- Modify: `src/agents/podcast/knowledge.py:61-62, 556`
- Modify test: `tests/agents/podcast/test_knowledge.py`

- [ ] **Step 1: settings.yaml에 top_k 추가**

`config/settings.yaml`의 `agents.knowledge` 블록을 다음처럼 변경:

```yaml
  knowledge:
    model: sonnet
    max_tokens: 2048
    pinecone_score_threshold: 0.7  # Pinecone 유사도 필터 임계값
    pinecone_top_k: 5              # Pinecone top_k (이전: 코드 하드코딩 5)
```

- [ ] **Step 2: knowledge.py __init__에 top_k 로드 추가**

`src/agents/podcast/knowledge.py`의 56~61번 줄(`self.pinecone_score_threshold` 로드 블록) 바로 아래에:

```python
        self.pinecone_score_threshold: float = float(cfg.get("pinecone_score_threshold", 0.7))
        self.pinecone_top_k: int = int(cfg.get("pinecone_top_k", 5))
```

- [ ] **Step 3: `_query_pinecone` 시그니처/호출부에 반영**

`src/agents/podcast/knowledge.py`의 556번 줄:

```python
    async def _query_pinecone(self, vector: list[float], domain: str, top_k: int = 5) -> list[dict]:
```

를 다음으로 교체:

```python
    async def _query_pinecone(
        self, vector: list[float], domain: str, top_k: int | None = None
    ) -> list[dict]:
```

그리고 메서드 본문 `host = await self._get_pinecone_host()` 바로 위에 다음 라인 추가:

```python
        effective_top_k = top_k if top_k is not None else self.pinecone_top_k
```

그리고 `json=` 딕셔너리의 `"topK": top_k,` 를 `"topK": effective_top_k,` 로 교체.

- [ ] **Step 4: 회귀 테스트**

```bash
pytest tests/agents/podcast/test_knowledge.py -v
```

기대: 기존 + C1 추가분 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add config/settings.yaml src/agents/podcast/knowledge.py
git commit -m "refactor: KnowledgeAgent pinecone_top_k 설정 외부화 (settings.yaml)"
```

---

### Task C3: `BACKEND_API_URL` 기본값을 CLAUDE.md 규약과 정합

**Files:**
- Modify: `src/agents/podcast/knowledge.py:673`

> **검토 필수:** 이 변경은 기존 운영 동작과 부딪힐 수 있다. 실제 Backend에서 `/api/internal/knowledge` 라우트와 `/greenroom/ingest/ai/internal/knowledge` 라우트 중 어느 쪽이 정답인지 **백엔드 팀과 합의 후** 진행한다. 합의 전에는 이 Task를 스킵한다.

- [ ] **Step 1: 백엔드 팀 확인 결과 기록**

백엔드 팀 확인 내용을 PR 설명에 기록한 뒤 아래 Step 진행. 확인 결과 `/greenroom/ingest/ai`가 맞다면:

`src/agents/podcast/knowledge.py:673`:

```python
        backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8080/api")
        url = f"{backend_url}/internal/knowledge"
```

을 `src/api/backend_resources.py`의 상수로 교체하거나, 최소한 CLAUDE.md 규약에 맞춘 기본값으로 변경:

```python
        # CLAUDE.md API 규약 — Backend는 /greenroom/ingest/ai prefix 사용
        backend_url = os.getenv(
            "BACKEND_API_URL", "http://localhost:8080/greenroom/ingest/ai"
        )
        url = f"{backend_url}/internal/knowledge"
```

> 만약 백엔드 팀이 `/api`가 정답이라고 회신하면 Task C3은 스킵하고 CLAUDE.md(또는 `.env.example`) 쪽 문구를 별도 PR로 정합화한다.

- [ ] **Step 2: 커밋 또는 스킵**

```bash
git add src/agents/podcast/knowledge.py
git commit -m "fix: KnowledgeAgent BACKEND_API_URL 기본값 /greenroom/ingest/ai로 정합화 (백엔드 팀 합의)"
```

---

### Task C4: PR 생성 (Part C)

- [ ] **Step 1: 최종 점검**

```bash
pytest tests/ -x --tb=short
ruff check src/ config/
black --check src/ tests/
```

- [ ] **Step 2: push + PR 생성**

```bash
git push -u origin feature/analysis-knowledge-agent-observability

/opt/homebrew/bin/gh pr create --base develop --title "refactor: KnowledgeAgent 관측성 경고 + pinecone_top_k 외부화" --body "$(cat <<'EOF'
## Summary
- Pinecone match > 0 && Backend RDB 문서 0건 시 경고 로그 (조기 인덱스 불일치 탐지)
- `pinecone_top_k` settings.yaml 외부화 (기존 하드코딩 5)
- (합의 시) Backend URL 기본값 CLAUDE.md 규약 정합화

## 동기
- PR #146에서 `pinecone_score_threshold`만 외부화되고 top_k는 남아 있어 운영 튜닝 대칭 결여.
- 운영 빈 결과 이슈 발생 시 Pinecone 실패인지 Backend 연결 실패인지 로그로 구분 불가.

## Test plan
- [x] 신규 관측성 경고 단위 테스트 PASS
- [x] `pytest tests/ -x --tb=short` 회귀 없음
- [ ] CI 통과
EOF
)"
```

---

## 전체 Self-Review

### 1. Spec coverage (코드 리뷰 결과 대비)

| 리뷰 항목 | 심각도 | 계획 반영 | Task |
|----------|-------|----------|------|
| Bug 1: script_generator state["knowledge_context"] 오키 | Critical | ✅ | B2 Step 1 |
| Bug 2: .knowledge_results.synthesis legacy 포맷 불일치 | Critical | ✅ | B2 Step 2 |
| Bug 3: Reasoning LLM에 article count만 주입 | Critical | ✅ | A2 |
| Suggestion 1: .env.example 주석 PARSE/PARSER 혼동 | Maintainability | ⏭ | PR #150에서 주석 정리 완료 — 추가 작업 불필요 |
| Suggestion 2: search()에 user_context 미전달 (process 대비 회귀) | Correctness | ⏭ | 계획 제외 (Knowledge RAG의 applicability 평가는 `search()` 경로에서는 현재 불필요 — Reasoning이 judgment 수행; 추후 별도 PR) |
| Suggestion 3: vector > 0 && docs == 0 경고 | Observability | ✅ | C1 |
| Suggestion 4: BACKEND_API_URL 기본값 /api vs /greenroom | Consistency | 🟡 (조건부) | C3 (백엔드 합의 시) |
| Suggestion 5: pinecone_top_k 외부화 | Maintainability | ✅ | C2 |
| Suggestion 6: process() 계열 dead code | Dead Code | ⏭ | 계획 제외 (영향도 크고 별도 리팩토링 PR 필요 — 본 계획 scope 벗어남) |
| Suggestion 7: search() 단위 테스트 없음 | Test Coverage | ✅ (부분) | C1 + B1의 search 경로 mock 테스트 |

### 2. Placeholder scan

- "TBD"/"TODO" 사용처 확인: **1건** — Part A PR 본문 "선행 PR: <Part A PR URL>"은 실행 시점에 실제 URL 치환 필요. 이는 PR 본문 편집이며 코드 placeholder가 아님.
- "add appropriate error handling" 등 모호 지시어: **없음**
- "similar to Task N": **없음** (모든 Task에 완전한 코드 포함)
- 정의되지 않은 타입/함수 참조: **없음**

### 3. Type consistency

- `knowledge_result` 파라미터: `dict[str, Any] | None` 일관 사용 ✅
- `articles` 필드 구조: `list[dict[str, Any]]` (id/title/content/score/source) 일관 ✅
- `knowledge_context` 지역 변수명은 Part B Step 1 주석으로 출처 명시하며 유지 — 함수 시그니처 변경 최소화 ✅
- `_synthesis` 기사 판별 조건 `a.get("id") == "_synthesis"` A2, B2 공통 ✅

---

## 실행 순서 권고

1. **Part A 먼저** — 개발자3(현재 브랜치 사용자)이 바로 진행 가능. 머지 후 Reasoning LLM이 근거 기반 추론 시작.
2. **Part B** — 개발자1에게 계획서 공유하여 PR 요청. Part A 머지 이후 머지해야 전체 파이프라인에서 체감 가능.
3. **Part C** — Part A/B 머지 안정화 이후 여유 있을 때. C3는 백엔드 팀 합의 선행.

**완료 기준 (Definition of Done):**
- 운영 환경에서 `knowledge_summary`가 "사용 가능한 전문 지식이 없습니다." 외의 실제 요약 문자열로 로그 남음.
- Reasoning CoT phase의 LLM 입력에 `[관련 전문 지식 — 근거]` 섹션이 실제 기사 내용과 함께 기록됨 (LangSmith trace 확인).
- Script Generator 세그먼트 prompt에 기사 content snippet이 포함됨.

---

*작성일: 2026-04-15*
*기반 조사: 2026-04-15 코드 리뷰 (본 대화), PR #145~#150 (develop 머지 완료분)*

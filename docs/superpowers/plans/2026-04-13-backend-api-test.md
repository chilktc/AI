# Backend API 전수 테스트 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chrome MCP의 AWS SSM 터미널을 통해 AI→Backend 발신 API 10개를 전수 테스트하고, 에러 로그를 수집·분석한다.

**Architecture:** Chrome MCP로 브라우저의 AWS SSM Session Manager 탭을 제어한다. SSM 터미널에서 Python 스크립트(`/tmp/test_backend_apis.py`)를 생성·실행하여 BackendClient가 호출하는 모든 엔드포인트를 직접 검증한다. 각 API의 HTTP 상태코드와 응답 본문을 수집하여 에러를 탐지하고 결과를 JSON으로 저장한다.

**Tech Stack:** Chrome MCP (`mcp__Claude_in_Chrome__*`), AWS SSM Session Manager, Python 3.11, httpx

---

## 엔드포인트 및 페이로드 기준 (2026-04-13 확정)

> ⚠️ **계획서 작성 기준 소스코드**: `src/api/client.py`, `src/api/backend_resources.py`, `src/api/contracts.py`, `src/api/graph_cumulative.py`
> 엔드포인트·페이로드는 이 파일들에서 직접 추출하여 작성. 소스코드와 이 계획서 간 불일치 발견 시 소스코드가 진실 소스.

### graph_nodes 주의사항

> ⚠️ **graph_nodes(API #2, #3)는 반드시 정확히 작동해야 한다.**
> - PUT 페이로드: `{ "user_id", "type": "graph_cumulative", "data": {"nodes": [...], "links": [...]} }` — `session_id`, `timestamp` 미포함 (백엔드 거부 확인됨)
> - 노드 타임스탬프 형식: `strftime('%Y-%m-%dT%H:%M:%S')` — timezone suffix(`+00:00`) 없이 (백엔드 거부 확인됨, PR #94 수정)
> - 노드 구조: `label`, `grp`(소문자), `weight`(float), `mention_count`(int), `trend`(rising|stable|falling), `first_seen`, `last_seen`
> - 응답 기준: `{"code": "ok"}` — `put_graph_cumulative()` 내부 검증 기준

---

## 테스트 대상 API 목록

| # | 메서드 | 엔드포인트 | BackendClient 메서드 | 담당 에이전트 |
|---|--------|-----------|---------------------|-------------|
| 1 | GET | `/internal/users/{user_id}/profile` | `get_user_profile()` | ScriptPersonalizer |
| 2 | GET | `/greenroom/ingest/ai/graph_nodes?user_id=X` | `load_graph_cumulative()` | Visualization |
| 3 | PUT | `/greenroom/ingest/ai/graph_nodes` | `put_graph_cumulative()` | Visualization |
| 4 | POST | `/greenroom/ingest/ai/podcast_metadata` | `save(RESOURCE_PODCAST_METADATA)` | routes/podcasts.py |
| 5 | POST | `/greenroom/ingest/ai/emotion_logs` | `save(RESOURCE_EMOTION_LOG)` | routes/podcasts.py |
| 6 | POST | `/greenroom/ingest/ai/visualizations` | `save(RESOURCE_VISUALIZATION)` | routes/podcasts.py |
| 7 | POST | `/greenroom/ingest/ai/learning` | `save(RESOURCE_LEARNING)` | LearningAgent |
| 8 | POST | `/greenroom/ingest/ai/content_analyses` | `save(RESOURCE_CONTENT_ANALYSIS)` | ContentAnalyzerAgent |
| 9 | POST | `/greenroom/ingest/ai/mind-frequencies` | `ingest_mind_frequencies()` | ContentAnalyzerAgent |
| 10 | POST | `/greenroom/ingest/ai/podcast_episodes` | `ingest_podcast_episodes()` | routes/podcasts.py |

---

## 관련 파일

- `src/api/client.py` — BackendClient (테스트 대상 HTTP 호출 로직)
- `src/api/contracts.py` — SaveRequest, SaveResponse, GraphCumulativeData 스키마
- `src/api/backend_resources.py` — RESOURCE_*, TYPE_* 상수
- `config/settings.yaml` — `api.timeout: 10`, `api_base_url` 기본값
- `config/loader.py` — `Settings.api_base_url` (환경변수 `BACKEND_API_URL` 오버라이드)
- `tests/api/e2e/test_backend_integration.py` — 기존 e2e 테스트 참고

---

## Task 1: SSM 탭 접근 및 환경 확인

**Files:** 없음 (Chrome MCP 조작만)

- [ ] **Step 1: SSM 탭 확인**

  ```
  Chrome MCP: mcp__Claude_in_Chrome__tabs_context_mcp
  ```
  목적: 현재 열린 탭 목록에서 AWS SSM Session Manager 탭 ID 확인.
  예상 출력: `"title": "AWS Systems Manager"` 또는 `"Session Manager"` 포함 탭.

- [ ] **Step 2: 백엔드 URL 확인**

  SSM 터미널 탭으로 전환 후 아래 명령 입력:
  ```bash
  echo "BACKEND_API_URL=${BACKEND_API_URL:-http://localhost:8080/greenroom/ingest/ai}"
  ```
  예상 출력: `BACKEND_API_URL=http://10.x.x.x:8080/greenroom/ingest/ai`

  URL을 확인하여 이후 모든 Task에서 `BASE_URL` 변수로 사용한다.

- [ ] **Step 3: Python 및 httpx 설치 확인**

  ```bash
  python3 --version && python3 -c "import httpx; print('httpx OK:', httpx.__version__)"
  ```
  예상 출력:
  ```
  Python 3.11.x
  httpx OK: 0.2x.x
  ```
  httpx가 없으면: `pip3 install httpx --quiet`

---

## Task 2: 테스트 스크립트 생성

**Files:** `/tmp/test_backend_apis.py` (원격 서버에 생성)

- [ ] **Step 1: 스크립트 파일 생성**

  SSM 터미널에서 아래 명령을 실행하여 `/tmp/test_backend_apis.py` 파일을 생성한다.

  ```bash
  cat > /tmp/test_backend_apis.py << 'PYEOF'
  import asyncio
  import json
  import os
  import sys
  from datetime import datetime

  import httpx

  BASE_URL = os.environ.get(
      "BACKEND_API_URL", "http://localhost:8080/greenroom/ingest/ai"
  )
  HOST = BASE_URL.split("/greenroom")[0]  # e.g., http://10.x.x.x:8080

  USER_ID = "00000000-test-0000-0000-000000000001"
  SESSION_ID = "00000000-test-0000-sess-000000000001"
  NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") + "Z"

  RESULTS: list[dict] = []


  async def call(name: str, method: str, url: str, body: dict | None = None) -> None:
      async with httpx.AsyncClient(timeout=10.0) as client:
          try:
              if method == "GET":
                  resp = await client.get(url)
              elif method == "POST":
                  resp = await client.post(url, json=body)
              elif method == "PUT":
                  resp = await client.put(url, json=body)
              else:
                  raise ValueError(f"Unsupported method: {method}")

              status = resp.status_code
              try:
                  data = resp.json()
              except Exception:
                  data = resp.text

              ok = status in (200, 201)
              RESULTS.append(
                  {"api": name, "method": method, "url": url, "status": status, "ok": ok, "response": data}
              )
              icon = "✅" if ok else "❌"
              print(f"{icon} [{status}] {name}")
              if not ok:
                  print(f"   응답: {json.dumps(data, ensure_ascii=False)[:400]}")

          except Exception as exc:
              RESULTS.append(
                  {"api": name, "method": method, "url": url, "status": None, "ok": False, "error": str(exc)}
              )
              print(f"❌ [ERR] {name} → {exc}")


  async def main() -> None:
      print(f"\n{'='*55}")
      print(f"  Backend API 전수 테스트")
      print(f"  BASE_URL : {BASE_URL}")
      print(f"  HOST     : {HOST}")
      print(f"  USER_ID  : {USER_ID}")
      print(f"  시작 시각 : {NOW}")
      print(f"{'='*55}\n")

      # ── 1. 사용자 프로필 조회 ──────────────────────────────
      await call(
          "GET /internal/users/{user_id}/profile",
          "GET",
          f"{HOST}/internal/users/{USER_ID}/profile",
      )

      # ── 2. 누적 그래프 조회 ───────────────────────────────
      await call(
          "GET /graph_nodes (누적 그래프 조회)",
          "GET",
          f"{BASE_URL}/graph_nodes?user_id={USER_ID}",
      )

      # ── 3. 누적 그래프 저장 ───────────────────────────────
      # ⚠️ session_id, timestamp 미포함 — 백엔드 거부 확인됨 (PR #94)
      # ⚠️ 타임스탬프: strftime('%Y-%m-%dT%H:%M:%S') — +00:00 suffix 없이 (백엔드 거부 확인됨)
      # ⚠️ 노드 구조: label, grp(소문자), weight(float), mention_count, trend, first_seen, last_seen
      # ⚠️ 성공 응답: {"code": "ok"}
      await call(
          "PUT /graph_nodes (누적 그래프 저장)",
          "PUT",
          f"{BASE_URL}/graph_nodes",
          {
              "user_id": USER_ID,
              "type": "graph_cumulative",
              "data": {
                  "nodes": [
                      {
                          "label": "테스트노드",
                          "grp": "test_group",
                          "weight": 0.5,
                          "mention_count": 1,
                          "trend": "stable",
                          "first_seen": NOW,
                          "last_seen": NOW,
                      }
                  ],
                  "links": [],
              },
          },
      )

      # ── 4. 팟캐스트 메타데이터 저장 ──────────────────────
      await call(
          "POST /podcast_metadata",
          "POST",
          f"{BASE_URL}/podcast_metadata",
          {
              "user_id": USER_ID,
              "session_id": SESSION_ID,
              "type": "podcast_metadata",
              "data": {
                  "type": "podcast_metadata",
                  "episode_id": "ep_test_plan001",
                  "episode_title": "API 테스트 에피소드",
                  "total_duration": 4,
                  "total_words": 800,
                  "script_text": "테스트 스크립트 내용입니다.",
                  "key_insights": ["인사이트1", "인사이트2"],
                  "themes": ["테스트", "멘탈케어"],
                  "reasoning_depth": "standard",
                  "cover_image_url": None,
                  "trace_id": "trace_plan001",
                  "correlation_id": "corr_plan001",
              },
              "timestamp": NOW,
          },
      )

      # ── 5. 감정 로그 저장 ─────────────────────────────────
      await call(
          "POST /emotion_logs",
          "POST",
          f"{BASE_URL}/emotion_logs",
          {
              "user_id": USER_ID,
              "session_id": SESSION_ID,
              "type": "emotion_log",
              "data": {
                  "log_id": "elog_plan001",
                  "mode": "podcast",
                  "episode_id": "ep_test_plan001",
                  "primary_emotion": "anxiety",
                  "intensity": 0.6,
                  "valence": -0.3,
                  "arousal": 0.7,
                  "secondary_emotions": ["stress"],
                  "tone_recommendation": "supportive_neutral",
                  "trace_id": "trace_plan001",
              },
              "timestamp": NOW,
          },
      )

      # ── 6. 시각화 메타 저장 ───────────────────────────────
      await call(
          "POST /visualizations",
          "POST",
          f"{BASE_URL}/visualizations",
          {
              "user_id": USER_ID,
              "session_id": SESSION_ID,
              "type": "visualization",
              "data": {
                  "visualization_id": "vis_plan001",
                  "mode": "podcast",
                  "episode_id": "ep_test_plan001",
                  "s3_key": "vis/test/plan001.png",
                  "cdn_url": "https://test-cdn.example.com/plan001.png",
                  "image_prompt": "A calming landscape with soft colors",
                  "interpretation_text": "테스트 해석 텍스트",
                  "primary_emotion": "anxiety",
                  "palette": "cool_blue",
                  "style_tags": ["realistic", "landscape"],
                  "trace_id": "trace_plan001",
              },
              "timestamp": NOW,
          },
      )

      # ── 7. 학습 데이터 저장 ───────────────────────────────
      await call(
          "POST /learning",
          "POST",
          f"{BASE_URL}/learning",
          {
              "user_id": USER_ID,
              "session_id": SESSION_ID,
              "type": "learning",
              "data": {
                  "mode": "podcast",
                  "learning_data": {
                      "preferred_topics": ["업무스트레스", "멘탈케어"],
                      "emotional_patterns": ["불안", "과부하"],
                      "interaction_style": "analytical",
                  },
              },
              "timestamp": NOW,
          },
      )

      # ── 8. 콘텐츠 분석 저장 ───────────────────────────────
      await call(
          "POST /content_analyses",
          "POST",
          f"{BASE_URL}/content_analyses",
          {
              "user_id": USER_ID,
              "session_id": SESSION_ID,
              "type": "content_analysis",
              "data": {
                  "main_theme": "업무 스트레스",
                  "sub_themes": ["번아웃", "시간 관리"],
                  "target_duration": 4,
                  "narrative_structure": "personal_story",
                  "depth_level": "moderate",
                  "emotional_journey": {
                      "opening": "공감과 인정",
                      "development": "원인 탐색",
                      "climax": "해결 전략",
                      "closing": "희망과 동기부여",
                      "journey_type": "healing",
                  },
                  "confidence": 0.85,
              },
              "timestamp": NOW,
          },
      )

      # ── 9. mind-frequencies 수집 ──────────────────────────
      # ⚠️ 경로: /mind-frequencies (tickets/ prefix 없음 — backend_resources.py 확인됨, PR #96 수정)
      await call(
          "POST /mind-frequencies",
          "POST",
          f"{BASE_URL}/mind-frequencies",
          {
              "session_id": SESSION_ID,
              "keywords": ["업무스트레스", "번아웃"],
              "description": "테스트 mind-frequency 데이터",
          },
      )

      # ── 10. 팟캐스트 에피소드 수집 ───────────────────────
      # ⚠️ 3개 파라미터만 전송: session_id, image_url, text(str)
      # ⚠️ user_id/id/created_at 백엔드 자동 채움 — AI 서버 전송 불필요 (PR #96 수정)
      await call(
          "POST /podcast_episodes",
          "POST",
          f"{BASE_URL}/podcast_episodes",
          {
              "session_id": SESSION_ID,
              "image_url": "https://test-cdn.example.com/plan001.png",
              "text": "테스트 에피소드 전체 스크립트 텍스트입니다.",
          },
      )

      # ── 결과 요약 ─────────────────────────────────────────
      total = len(RESULTS)
      passed = sum(1 for r in RESULTS if r["ok"])
      failed = [r for r in RESULTS if not r["ok"]]

      print(f"\n{'='*55}")
      print(f"  결과 요약: {passed}/{total} 통과")
      print(f"{'='*55}")

      if failed:
          print(f"\n❌ 실패 API ({len(failed)}개):")
          for r in failed:
              print(f"\n  [{r.get('status', 'ERR')}] {r['api']}")
              print(f"  {r['method']} {r['url']}")
              if "error" in r:
                  print(f"  에러: {r['error']}")
              elif "response" in r:
                  print(f"  응답: {json.dumps(r['response'], ensure_ascii=False)[:400]}")
      else:
          print("\n✅ 모든 API 정상!")

      # JSON 결과 파일 저장
      out_path = "/tmp/backend_api_test_result.json"
      with open(out_path, "w", encoding="utf-8") as f:
          json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
      print(f"\n전체 결과 저장: {out_path}")


  if __name__ == "__main__":
      asyncio.run(main())
  PYEOF
  echo "스크립트 생성 완료: $(wc -l < /tmp/test_backend_apis.py)줄"
  ```

  예상 출력: `스크립트 생성 완료: 210줄` (대략)

- [ ] **Step 2: 스크립트 문법 확인**

  ```bash
  python3 -m py_compile /tmp/test_backend_apis.py && echo "문법 OK"
  ```
  예상 출력: `문법 OK`

---

## Task 3: 스크립트 실행 및 에러 수집

**Files:** 없음 (원격 실행)

- [ ] **Step 1: 스크립트 실행**

  ```bash
  BACKEND_API_URL="${BACKEND_API_URL}" python3 /tmp/test_backend_apis.py 2>&1 | tee /tmp/backend_api_test.log
  ```

  예상 정상 출력 (각 줄):
  ```
  ✅ [200] GET /internal/users/{user_id}/profile
  ✅ [200] GET /graph_nodes (누적 그래프 조회)
  ✅ [200] PUT /graph_nodes (누적 그래프 저장)
  ✅ [201] POST /podcast_metadata
  ✅ [201] POST /emotion_logs
  ✅ [201] POST /visualizations
  ✅ [201] POST /learning
  ✅ [201] POST /content_analyses
  ✅ [200] POST /mind-frequencies
  ✅ [201] POST /podcast_episodes
  결과 요약: 10/10 통과
  ```

  에러 발생 시 `❌` 행 아래에 상태코드와 응답 본문이 출력된다.

- [ ] **Step 2: 로그 파일 전체 확인**

  ```bash
  cat /tmp/backend_api_test.log
  ```

- [ ] **Step 3: JSON 결과 파일 확인**

  ```bash
  cat /tmp/backend_api_test_result.json
  ```

  출력된 JSON을 Claude 컨텍스트로 가져와서 에러 패턴 분석에 사용한다.

---

## Task 4: 에러 로그 분석 및 분류

**Files:** 없음 (분석만)

- [ ] **Step 1: 실패 API 목록 추출**

  ```bash
  python3 -c "
  import json
  with open('/tmp/backend_api_test_result.json') as f:
      results = json.load(f)
  failed = [r for r in results if not r['ok']]
  print(f'실패: {len(failed)}/{len(results)}')
  for r in failed:
      print(f'  [{r.get(\"status\",\"ERR\")}] {r[\"api\"]}')
      resp = r.get('response') or r.get('error', '')
      print(f'    {str(resp)[:200]}')
  "
  ```

- [ ] **Step 2: 에러 유형 분류**

  수집된 에러를 아래 유형으로 분류한다:

  | 유형 | 증상 | 원인 추정 |
  |------|------|----------|
  | **연결 실패** | `ConnectError` / `TimeoutException` | EC2 보안 그룹, 포트, 서버 미실행 |
  | **400 Bad Request** | 응답에 `VALIDATION_ERROR` | 요청 본문 스키마 불일치 |
  | **404 Not Found** | 응답에 `NOT_FOUND` | 엔드포인트 경로 불일치 |
  | **422 Unprocessable** | FastAPI validation error | 필드 타입·필수값 오류 |
  | **500 Server Error** | 응답에 `SERVER_ERROR` | 백엔드 내부 처리 오류 |
  | **기타** | 그 외 상태코드 | 상황별 판단 |

- [ ] **Step 3: 백엔드 서버 로그 확인 (에러 발생 시)**

  에러가 있을 경우 백엔드 서버의 애플리케이션 로그를 확인한다:

  ```bash
  # 컨테이너 환경인 경우
  docker logs <backend_container_name> --tail 100 2>&1 | grep -E "ERROR|WARN|Exception"

  # systemd 서비스인 경우
  journalctl -u mind-log-backend --since "5 minutes ago" -p err

  # 직접 로그 파일인 경우
  tail -100 /var/log/mind-log/backend.log | grep -E "ERROR|WARN"
  ```

- [ ] **Step 4: 결과 정리**

  아래 형식으로 에러 로그를 정리하여 보고한다:

  ```
  === Backend API 테스트 결과 (YYYY-MM-DD HH:MM) ===

  통과: N/10
  실패: M개

  [실패 목록]
  1. POST /podcast_metadata
     상태: 422
     응답: {"detail": [...]}
     원인: emotional_journey 키 불일치 (climax/closing 미인식)

  2. ...
  ```

---

## 검증 기준

| 항목 | 기준 |
|------|------|
| 전수 통과 | 10/10 API 모두 2xx 응답 |
| 허용 에러 | 테스트 user_id 미존재로 인한 `GET /profile` 404 (프로덕션 데이터 없을 경우) |
| 실패 기준 | POST/PUT API에서 422·500 발생 시 즉시 원인 분석 필요 |
| 결과물 | `/tmp/backend_api_test_result.json` 저장 완료 |

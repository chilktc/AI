# Mode A 부활 구현 완료 후 수동 테스트 가이드

> 작성일: 2026-04-09
> 전제: `docs/superpowers/plans/2026-04-09-mode-a-revival-graph-cumulative.md` 계획 완료 후 수행
> 환경: AWS SSM (Instance: i-02631e0888c49b0b7, t7-mindlog-prod-app-2)
> 참조: `docs/guides/BE_API_TEST_RESULT_2026-04-08.md` (1차 API 테스트 결과)

---

## 핵심 설계 원칙 — 스키마 불변

> **구조가 바뀌어도 스키마는 바뀌지 않는다.**
>
> - AI 서버가 PUT에 보내는 SaveRequest 포맷(`user_id`, `session_id`, `type`, `data`, `timestamp`)은 변하지 않는다.
> - BE가 GET으로 돌려주는 nodes/links 필드명(`label`, `grp`, `weight`, `mention_count`, `trend`, `first_seen`, `last_seen`)은 변하지 않는다.
> - 변한 것은 **누가 EMA를 계산하는가**뿐이다 (Mode B: BE → Mode A: AI 서버).

---

## 테스트 환경

| 항목 | 값 |
|------|-----|
| AI 서버 포트 | 8000 |
| BE 서버 URL | `http://${BACKEND_HOST}:8080/api/v1` |
| STORAGE_MODE | `proxy` |
| 테스트 방식 | AWS SSM Session Manager → curl / Python |

### 테스트용 유저

| 유저 | user_id | 상태 |
|------|---------|------|
| 기존 유저 | `9f3b9560-331d-11f1-b83f-02c91128bc03` | 누적 데이터 있음 |
| 신규 유저 | `9f3b9c5e-331d-11f1-b83f-02c91128bc03` | 데이터 없음 (404 반환) |

---

## 테스트 순서 및 예상 결과

| # | 테스트 | API | 예상 |
|---|--------|-----|------|
| 1 | 기존 유저 GET | GET /graph_nodes | ✅ 200 + nodes/links 데이터 |
| 2 | 신규 유저 GET | GET /graph_nodes | ✅ 404 (에러 아님, 정상 케이스) |
| 3 | EMA 계산 후 PUT | PUT /graph_nodes | ✅ `{"code":"ok","message":"성공"}` |
| 4 | 결과 재조회 | GET /graph_nodes | ✅ PUT한 데이터가 반영된 응답 |
| 5 | graph_analyses POST | POST /graph_analyses | ✅ 200 (백엔드 수정 전제) |

---

## Test 1 — 기존 유저 누적 그래프 조회 (GET)

**확인 포인트:** BE가 돌려주는 응답 구조가 `BE_API_TEST_RESULT_2026-04-08.md` Test 1과 동일한지 검증한다.

### 요청

```bash
curl -s "http://${BACKEND_HOST}:8080/api/v1/graph_nodes?user_id=9f3b9560-331d-11f1-b83f-02c91128bc03" | python3 -m json.tool
```

### 예상 응답

```json
{
  "code": "ok",
  "message": "성공",
  "data": {
    "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
    "type": "graph_cumulative",
    "data": {
      "nodes": [
        {
          "label": "번아웃",
          "grp": "EMOTIONAL_EXHAUSTION",
          "weight": 0.86,
          "mention_count": 5,
          "trend": "increasing",
          "first_seen": "2026-04-01T00:10:00",
          "last_seen": "2026-04-08T00:35:00"
        }
      ],
      "links": [
        {
          "source_label": "업무 과부하",
          "source_grp": "WORK_STRUCTURE",
          "target_label": "번아웃",
          "target_grp": "EMOTIONAL_EXHAUSTION",
          "weight": 6,
          "relationship": "causes",
          "first_seen": "2026-04-01T00:30:00",
          "last_seen": "2026-04-08T00:45:00"
        }
      ]
    }
  }
}
```

**체크리스트:**
- [ ] HTTP 200 반환
- [ ] `code == "ok"`
- [ ] `data.data.nodes` 배열 존재 (비어있지 않음)
- [ ] nodes 각 항목에 `label`, `grp`, `weight`, `mention_count`, `trend`, `first_seen`, `last_seen` 필드 존재
- [ ] links 각 항목에 `source_label`, `source_grp`, `target_label`, `target_grp`, `weight`, `relationship` 필드 존재

> `grp` 값이 UPPER_CASE로 반환돼도 정상. AI 코드에서 `.lower()`로 정규화 처리한다.

---

## Test 2 — 신규 유저 GET (404 케이스)

**확인 포인트:** 404가 에러가 아닌 정상 케이스로 처리되는지 검증한다.
AI 코드(`load_graph_cumulative`)는 404 수신 시 `GraphCumulativeData(nodes=[], links=[])`를 반환하여 빈 누적 상태로 EMA 계산을 시작한다.

### 요청

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "http://${BACKEND_HOST}:8080/api/v1/graph_nodes?user_id=9f3b9c5e-331d-11f1-b83f-02c91128bc03"
```

### 예상 응답

```
404
```

**체크리스트:**
- [ ] HTTP 404 반환 (500이면 BE 버그)
- [ ] AI 코드 동작 확인 (로그): `INFO` 레벨 신규 노드 삽입 로그 (`mention_count=1`, `trend="stable"`)
- [ ] PUT이 정상 실행됨 (Test 3 결과로 간접 확인)

---

## Test 3 — EMA 계산 결과 PUT (Mode A 핵심)

**확인 포인트:**
1. AI 서버가 SaveRequest 포맷으로 PUT을 전송한다.
2. BE 응답이 `{"code":"ok","message":"성공"}`이다.
3. 스키마가 `BE_API_TEST_RESULT_2026-04-08.md` Test 2와 동일하다.

### 요청 (기존 유저 기준 EMA 적용 예시)

> 전제: Test 1에서 `번아웃` 노드의 기존 `weight=0.86`, `mention_count=5`.
> 이번 에피소드에서 `번아웃` intensity=0.9.
> EMA 계산: `0.3 × 0.9 + 0.7 × 0.86 = 0.27 + 0.602 = 0.872`

```bash
curl -s -X PUT "http://${BACKEND_HOST}:8080/api/v1/graph_nodes" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
    "session_id": "sess_mode_a_test_001",
    "type": "graph_cumulative",
    "data": {
      "nodes": [
        {
          "label": "번아웃",
          "grp": "emotional_exhaustion",
          "weight": 0.872,
          "mention_count": 6,
          "trend": "increasing",
          "first_seen": "2026-04-01T00:10:00",
          "last_seen": "2026-04-09T10:00:00+00:00"
        }
      ],
      "links": [
        {
          "source_label": "업무 과부하",
          "source_grp": "work_structure",
          "target_label": "번아웃",
          "target_grp": "emotional_exhaustion",
          "weight": 7,
          "relationship": "causes",
          "first_seen": "2026-04-01T00:30:00",
          "last_seen": "2026-04-09T10:00:00+00:00"
        }
      ]
    },
    "timestamp": "2026-04-09T10:00:00+00:00"
  }' | python3 -m json.tool
```

### 예상 응답

```json
{
  "code": "ok",
  "message": "성공"
}
```

**체크리스트:**
- [ ] HTTP 200 반환
- [ ] 응답 body에 `"code": "ok"` 존재
- [ ] `"success"` 필드 없어도 AI 코드가 정상 처리 (인라인 `body.get("code") == "ok"` 검증)
- [ ] `session_id` 필드 포함 요청 수용 (BE_API_TEST_RESULT Test 2와 달리 session_id 포함)
- [ ] `timestamp` 필드 포함 요청 수용

> **스키마 불변 확인:** PUT 요청 body의 `user_id`, `type`, `data.nodes`, `data.links` 필드 구조는
> `BE_API_TEST_RESULT_2026-04-08.md` Test 2와 동일하다. `session_id`와 `timestamp` 추가만 차이.

---

## Test 4 — PUT 결과 재조회 (GET으로 검증)

**확인 포인트:** Test 3에서 PUT한 EMA 계산 값이 BE DB에 반영됐는지 확인한다.

### 요청

```bash
curl -s "http://${BACKEND_HOST}:8080/api/v1/graph_nodes?user_id=9f3b9560-331d-11f1-b83f-02c91128bc03" | python3 -m json.tool
```

### 예상 응답 (변경된 필드만 표시)

```json
{
  "code": "ok",
  "data": {
    "data": {
      "nodes": [
        {
          "label": "번아웃",
          "weight": 0.872,
          "mention_count": 6,
          "trend": "increasing",
          "last_seen": "2026-04-09T10:00:00+00:00"
        }
      ],
      "links": [
        {
          "weight": 7,
          "last_seen": "2026-04-09T10:00:00+00:00"
        }
      ]
    }
  }
}
```

**체크리스트:**
- [ ] `번아웃` 노드의 `weight`가 EMA 계산값(`0.872`)으로 갱신됨
- [ ] `mention_count`가 6으로 증가 (5 → 6)
- [ ] `last_seen`이 Test 3에서 보낸 시각으로 갱신됨
- [ ] `first_seen`은 변경 없음 (`2026-04-01T00:10:00` 유지)
- [ ] links `weight`가 7로 증가 (6 → 7)

---

## Test 5 — graph_analyses POST (기존 경로 유지 확인)

**확인 포인트:** `_publish_graph_to_backend()` 경로는 Mode A 구현 후에도 변경되지 않는다.
BE가 SaveRequest 포맷을 수용하도록 수정된 경우 ✅, 미수정이면 ❌ 400.

### 요청

```bash
curl -s -X POST "http://${BACKEND_HOST}:8080/api/v1/graph_analyses" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
    "session_id": "sess_mode_a_test_001",
    "type": "graph_analyses",
    "data": {
      "got_result": {
        "nodes": [
          {"label": "번아웃", "grp": "emotional_exhaustion", "intensity": 0.9}
        ],
        "edges": []
      }
    },
    "timestamp": "2026-04-09T10:00:00+00:00"
  }' | python3 -m json.tool
```

### 예상 응답 (BE 수정 완료 시)

```json
{
  "code": "ok",
  "message": "성공"
}
```

**체크리스트:**
- [ ] HTTP 200 반환 (400이면 BE 미수정 상태)
- [ ] 이 엔드포인트의 스키마 미해결 시: 계획서 `## 전제 조건` 항목에 기록하고 BE팀 추적

---

## AI 서버 로그로 흐름 확인

### SSM에서 AI 서버 로그 확인

```bash
# Docker 환경
docker logs <ai-container-name> --tail 50 -f

# systemd 환경
journalctl -u ai-server -n 50 -f
```

### 정상 흐름 로그 예시 (기존 유저)

```
INFO  graph_cumulative - 누적 그래프 갱신 완료 (user=9f3b9560-..., nodes=2, links=1, ep=ep_xxx)
```

### 신규 유저 로그 예시

```
INFO  graph_cumulative - GoT 노드가 비어있어 누적 갱신을 건너뜁니다
# 또는 (신규 유저 + 정상 GoT):
WARNING graph_cumulative - 기존 누적 데이터 조회 실패 — 신규 사용자로 처리 후 진행 (user=9f3b9c5e-...)
INFO  graph_cumulative - 누적 그래프 갱신 완료 (user=9f3b9c5e-..., nodes=1, links=0, ep=ep_xxx)
```

> `WARNING`이 출력되더라도 뒤따르는 `INFO`(갱신 완료)가 있으면 정상이다.
> GET 404(신규 유저)는 `load_graph_cumulative()`가 `GraphCumulativeData()`를 반환하여 경고 없이 처리된다.

### PUT 실패 로그

```
WARNING graph_cumulative - 누적 그래프 PUT 실패 (user=...)
```

---

## 단위 테스트로 스키마 불변 확인

계획 완료 후 테스트 전체 실행:

```bash
PYTHONPATH=. pytest tests/api/test_graph_cumulative.py -v
# 예상: ~21개 통과 (test_source_target_alias_accepted 제외)

PYTHONPATH=. pytest tests/ --tb=short 2>&1 | tail -5
# 예상: 기존 532개 + 신규 테스트 전부 passed
```

**스키마 관련 테스트 항목:**

| 테스트 | 검증 내용 |
|--------|----------|
| `test_new_node_inserted` | 신규 노드 필드(label, grp, weight, mention_count, trend, first_seen, last_seen) 정상 생성 |
| `test_existing_node_ema_applied` | EMA 공식 정확성, mention_count 증가, first_seen 불변 |
| `test_existing_grp_uppercase_normalized` | BE 응답 UPPER_CASE grp 정규화 처리 |
| `test_new_edge_inserted` | 신규 엣지 필드(source_label, source_grp, target_label, target_grp, weight, relationship) 정상 생성 |
| `test_existing_edge_weight_incremented` | 엣지 weight 누적 카운트, first_seen 불변 |
| `test_success_new_user` | 신규 유저 → PUT 정상 실행, mention_count=1, trend="stable" |
| `test_new_user_404_returns_empty_data_not_error` | 404 → 에러 아님, PUT 정상 진행 |

---

## 이전 테스트 대비 변경점 요약

| 항목 | BE_API_TEST_RESULT_2026-04-08 | Mode A 구현 후 |
|------|------------------------------|----------------|
| GET /graph_nodes | ✅ 응답 확인 | ✅ 동일 (스키마 불변) |
| PUT /graph_nodes | ✅ BE 노션 스키마로 테스트 | ✅ SaveRequest 포맷으로 테스트 (session_id, timestamp 추가) |
| PUT 응답 처리 | 수동 확인 | `body.get("code") == "ok"` 인라인 검증 |
| POST /graph_analyses | ❌ SaveRequest 포맷 400 | ✅ BE 수정 후 성공 예상 |
| POST /graph_nodes/episodes | ❌ 404 | **제거됨** (Mode A 전환으로 미사용) |
| EMA 계산 위치 | BE 담당 (Mode B) | **AI 서버 담당** (Mode A) |

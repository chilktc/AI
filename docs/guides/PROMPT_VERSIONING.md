# 프롬프트 버전 관리 가이드

> 프롬프트 YAML의 멀티버전 관리, 핀닝, 라이브 테스트 방법을 설명한다.

---

## 버전 핀닝

### 현재 핀닝 버전 (2026-03-13)

| 에이전트 | 핀닝 버전 | 설정 위치 |
|---------|---------|----------|
| Content Analyzer | v2.1.0 | `config/settings.yaml` → `prompts.versions.content_analyzer` |
| Podcast Reasoning | v3.0.0 | `config/settings.yaml` → `prompts.versions.podcast_reasoning` |
| Batch Validator | v2.3.0 | `config/settings.yaml` → `prompts.versions.batch_validator` |
| 기타 에이전트 | v1.0.0 | `prompts.versions.default` 기본값 |

### 핀닝 방법

`config/settings.yaml`의 `prompts.versions` 섹션에서 에이전트별 버전을 지정한다:

```yaml
prompts:
  versions:
    default: "1.0.0"              # 글로벌 기본
    content_analyzer: "2.1.0"     # 에이전트별 오버라이드
    podcast_reasoning: "3.0.0"
    batch_validator: "2.3.0"
```

미지정 에이전트는 YAML 파일의 `default_version` → `prompts.versions.default` 순으로 fallback한다.

---

## YAML 파일 구조

### 프로덕션 (핀닝 버전만)

```yaml
# prompts/podcast/content_analyzer.yaml
default_version: "2.1.0"
versions:
  "2.1.0":
    system_prompt: |
      (프롬프트 내용)
```

### 아카이브

이전 버전 전체 이력은 `prompts/{mode}/_archive/` 폴더에 보존:

```
prompts/podcast/_archive/
├── batch_validator.yaml      # v1.1.0 ~ v2.6.0 전체
├── content_analyzer.yaml     # v1.1.0 ~ v3.4.0 전체
└── podcast_reasoning.yaml    # v1.1.0 ~ v3.4.0 전체
```

---

## 라이브 테스트

### 단일 조합 실행

```bash
python3 -m dev.live_tests.run_prompt_iteration \
  --ca-version 2.1.0 \
  --pr-version 3.0.0 \
  --bv-version 2.3.0 \
  --iteration 1 \
  --round 4
```

### CLI 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--ca-version` | Content Analyzer 버전 | settings.yaml 핀닝 값 |
| `--pr-version` | Podcast Reasoning 버전 | settings.yaml 핀닝 값 |
| `--bv-version` | Batch Validator 버전 | settings.yaml 핀닝 값 |
| `--version` | 3개 에이전트 공통 버전 (후방 호환) | — |
| `--iteration` | 반복 번호 (결과 파일명에 사용) | 1 |
| `--round` | 라운드 번호 | 3 |

### 결과 파일

결과는 `dev/live_tests/results/`에 JSON으로 저장된다:

```
dev/live_tests/results/
├── prompt_iter_1.json ~ prompt_iter_30.json      # Round 1-3 (Ollama)
└── prompt_iter_openai_31.json ~ _58.json         # Round 4 (OpenAI)
```

---

## 최적화 이력 요약

### Round 1-3 (Ollama gpt-oss:20b)

- **Round 1** (Iter 1-10): 3개 에이전트 공통 버전으로 스윕 → v1.5.0 최적
- **Round 2** (Iter 11-20): 에이전트 독립 버전 스윕 → CA v2.1.0 + PR v2.0.0 + BV v1.5.0
- **Round 3** (Iter 21-30): 상위 4개 조합 확률적 검증 → 조합 A(CA 2.0 + PR 2.0 + BV 1.5) 최적 (평균 BV 0.903)

### Round 4 (OpenAI gpt-4o-mini)

- **Phase 3A**: CA/PR/BV 각각 독립 스윕 (Iter 31-52)
- **Phase 3B-3C**: 상위 3개 조합 통계 검증 (Iter 53-58)
- **최종 확정**: CA v2.1.0 + PR v3.0.0 + BV v2.3.0 (평균 BV 0.863 +/- 0.006)

### 종합 비교

| 조합 | 프로바이더 | 평균 BV Score | 표준편차 |
|------|----------|-------------|---------|
| CA 2.0 + PR 2.0 + BV 1.5 | Ollama | 0.903 | 0.047 |
| CA 2.1 + PR 3.0 + BV 2.3 | OpenAI | 0.863 | 0.006 |

> Round 4 확정 조합(OpenAI)은 점수는 소폭 낮지만 분산이 매우 작아 안정적이다.

---

*마지막 업데이트: 2026-03-13*

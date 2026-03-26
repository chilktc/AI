# Changelog v26

> **날짜**: 2026-03-26
> **요약**: Docker 배포 차단 해제 + Visualization Agent settings 기반 전환 + Bedrock Converse API 마이그레이션 + CRISIS 선점 버그 수정

---

## 변경 유형: 배포 인프라 수정 + 버그 픽스 + 리팩토링

### 배경

2026-03-24 이후 AWS 인스턴스에서 AI 서버가 중단된 상태. Docker 이미지 빌드 시
`sentence-transformers`가 PyTorch + CUDA (~2.5GB)를 설치하며 OOM Kill/디스크 부족 반복.
추가로 PR #34 머지 후 Visualization Agent TypeError, 프롬프트 핀닝 소실,
CRISIS 선점 경로 AttributeError 등 런타임 에러 다수 발견.

### 변경 내용

#### 코드 수정 (7개 파일)

| 파일 | 변경 |
|------|------|
| `requirements.txt` | `sentence-transformers>=3.0.0` 삭제 (import 0건 확인, PyTorch/CUDA 의존성 제거 → Docker OOM 해소) |
| `config/settings.yaml` | 프롬프트 버전 핀닝 3줄 복원 (CA 2.1.0, PR 3.0.0, BV 2.3.0), `visualization.image_model`/`image_region` 추가 |
| `src/agents/podcast/visualization.py` | 하드코딩 6건 제거 (모델/버킷/리전/경로/재시도) → settings.yaml 기반 전환, `model` 파라미터 TypeError 해결, `SKIP_VISUALIZATION` 환경변수 복원, `self.logger` 복원 |
| `src/graph/workflow.py` | `cancel_waiter = None` 삭제 (CRISIS 경로 AttributeError 해결), `_safety_deep_crisis`에서 `required_in_script` 활용 (법적 고지/상담 번호 전달) |
| `src/agents/shared/llm_client.py` | `_generate_bedrock()`: `invoke_model` + Anthropic 전용 포맷 → Converse API 전환 (모든 Bedrock 모델 지원) |
| `src/agents/shared/base_agent.py` | `call_image_gen()`: Bedrock 이미지 분기 추가 (`_generate_image_bedrock` + `_generate_image_openai` 분리), 기존 OpenAI 경로 완전 보존 |
| `prompts/podcast/batch_validator.yaml` | PR #34가 덮어쓴 19줄 단순 파일 → `_archive/`에서 멀티버전 원본 복원 (16개 버전, default v2.3.0) |

#### 테스트 수정 (3개 파일)

| 파일 | 변경 |
|------|------|
| `tests/agents/shared/test_llm_client.py` | Bedrock mock: `invoke_model` → `converse` 응답 구조, `anthropic_version` 검증 → `system`/`messages` 검증 |
| `tests/agents/podcast/test_visualization_agent.py` | Bedrock 반환 포맷(`image_binary`) 적용, settings 기반 모델 검증, `SKIP_VISUALIZATION` 테스트 추가 |
| `tests/agents/conversation/test_knowledge.py` | 팟캐스트모드 기준으로 전환 (stub `search()` 인터페이스 + `process()` 폴백 검증) |
| `tests/graph/test_e2e_mock_pipeline.py` | 팟캐스트 그래프 노드 기대값 `script_generator` → `tier2_podcast` (실제 구조 반영) |

### Visualization Agent 하드코딩 제거 상세

| 항목 | 변경 전 (하드코딩) | 변경 후 (settings 기반) |
|------|-------------------|----------------------|
| S3 리전 | `'ap-northeast-2'` | `os.getenv('AWS_REGION', settings.bedrock_region)` |
| S3 버킷 | `"t7-mindlog-ai-assets"` | `settings.s3_bucket` |
| LLM 모델 | `"anthropic.claude-3-5-sonnet-20240620-v1:0"` | 제거 (settings.yaml `visualization.model` 자동 사용) |
| 이미지 모델 | `"amazon.titan-image-generator-v1"` | `settings.get_agent_config("visualization")["image_model"]` |
| S3 경로 | `"ai-generated/"` | `settings.s3_upload_prefix` |
| 재시도 횟수 | `self.max_retries = 2` | `settings.max_retries` |

### Bedrock Converse API 마이그레이션

`llm_client.py`의 `_generate_bedrock()` 내부 구현 변경. public 시그니처 변경 없음.

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| API | `invoke_model` | `converse` |
| 요청 포맷 | `anthropic_version` + Messages API (Claude 전용) | 통합 `messages`/`system`/`inferenceConfig` (모든 모델) |
| 응답 파싱 | `content[0]["text"]` | `output.message.content[0]["text"]` |
| 토큰 필드 | `input_tokens`/`output_tokens` | `inputTokens`/`outputTokens` |
| 지원 모델 | Anthropic Claude만 | Claude, Llama, Titan, Mistral, Nova, GPT 등 |

### CRISIS 선점 버그 수정

| 버그 | 원인 | 수정 |
|------|------|------|
| `AttributeError: 'NoneType' has no attribute 'done'` | `cancel_waiter = None` 할당 후 `finally`에서 `.done()` 호출 | `cancel_waiter = None` 라인 삭제 (cancel_waiter는 항상 Future 유지) |
| 위기 시 법적 고지/상담 번호 미전달 | `safety_result.get("crisis_response")` — 키 없음 → 항상 기본 메시지 | `safety_flags["required_in_script"]` 활용 |

### 영향 범위

- **Breaking Change**: 없음 (모든 public 인터페이스 유지)
- **Protected File**: `workflow.py` 수정 — CRISIS 경로 전용, 정상 흐름(safe/warning) 무영향. 3인 합의 리뷰 필요
- **공용 인프라**: `base_agent.py` (`call_image_gen` 시그니처: `model: str` → `model: str | None`, 기본값 변경), `llm_client.py` (내부 구현만 변경). 전원 리뷰 필요
- **Docker 이미지**: ~9.1GB → 예상 ~3-4GB (PyTorch+CUDA 제거)

### 검증 결과

- 유닛 테스트: 298/298 통과 (backend e2e 제외)
- Visualization 테스트: 4/4 통과 (SKIP_VISUALIZATION 테스트 신규 추가)
- Bedrock Converse 테스트: 1/1 통과
- Knowledge 테스트: 4/4 통과 (팟캐스트모드 기준 재작성)
- 그래프 구조 테스트: 2/2 통과 (노드명 수정)

### 전체 파일 변경 요약

| 구분 | 파일 수 |
|------|--------|
| 코드 수정 | 7 |
| 테스트 수정 | 4 |
| 프롬프트 복원 | 1 |
| 문서 삭제 | 1 (DEPLOY_FIX_v26.md → CHANGELOG_v26.md로 대체) |
| **합계** | **13** |

---

*마지막 업데이트: 2026-03-26*

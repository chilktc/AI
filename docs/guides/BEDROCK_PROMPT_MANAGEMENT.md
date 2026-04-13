# Bedrock Prompt Management 적용 가이드

> 작성일: 2026-04-08  
> 관련 문서: `docs/guides/PROMPT_VERSIONING.md`, `src/agents/shared/prompt_loader.py`

---

## 개요

Amazon Bedrock Prompt Management는 프롬프트를 AWS 내에서 관리하고 ARN으로 참조하는 네이티브 기능이다.
현재 프로젝트의 YAML 파일 기반 시스템과 비교하여 언제, 어떻게 적용할지 정리한다.

---

## 현재 구조 vs Bedrock Prompt Management

### 현재 구조 (YAML 파일 기반)

```
prompts/podcast/batch_validator.yaml  ← git으로 버전 관리
    ↓
PromptLoader.load("podcast", "batch_validator", version="2.3.0")
    ↓
에이전트에서 프롬프트 문자열 사용
```

- 버전 관리: git + YAML `versions` 키
- 버전 핀닝: `config/settings.yaml` → `prompts.versions`
- 캐싱: `PromptLoader._cache` (인메모리)
- 로컬 개발: 파일 직접 편집, AWS 자격증명 불필요

### Bedrock Prompt Management 적용 시

```
AWS Bedrock Prompt Management
    ARN: arn:aws:bedrock:ap-northeast-2:123456:prompt/BATCH_VALIDATOR
    버전 1, 2, 3 ... (AWS에서 관리)
        ↓
PromptLoader가 boto3로 ARN 호출 → 프롬프트 문자열 반환
    ↓
에이전트에서 동일하게 사용 (호출부 코드 변경 없음)
```

`PromptLoader` 내부 구현만 교체하면 되며, 에이전트의 `loader.load(...)` 호출부는 변경하지 않아도 된다.

---

## 기능 비교

| 기능 | 현재 (YAML) | Bedrock |
|------|-------------|---------|
| 버전 관리 | git + `versions` 키 | AWS 내부 버전 번호 |
| 버전 핀닝 | `settings.yaml` | settings.yaml에 ARN 버전 저장 |
| 팀 공유 | git 협업 (PR 리뷰, diff 비교) | IAM 권한 |
| 캐싱 | 인메모리 자동 캐싱 | boto3 호출 (캐싱 직접 구현 필요) |
| 로컬 개발 | 파일 직접 편집 | 인터넷 + AWS 자격증명 필요 |
| 비개발자 편집 | 불가 (git 필요) | AWS 콘솔에서 직접 편집 가능 |
| 환경 분리 | `PROMPT_DIR` 환경변수 | 환경별 ARN 버전 |
| 비용 | 없음 | Bedrock API 호출 비용 발생 |

---

## 전환 시 적용 방식

`PromptLoader`는 공용 인프라 (인터페이스 변경 금지)이므로, **내부 구현만 교체**한다.
에이전트 코드(`loader.load(...)` 호출부)는 전혀 변경하지 않는다.

### settings.yaml 설정 예시

```yaml
prompts:
  backend: "bedrock"              # "local"(현재) or "bedrock"
  bedrock_region: "ap-northeast-2"
  arns:
    batch_validator: "arn:aws:bedrock:ap-northeast-2:123456789:prompt/BATCH_VALIDATOR"
    content_analyzer: "arn:aws:bedrock:ap-northeast-2:123456789:prompt/CONTENT_ANALYZER"
    podcast_reasoning: "arn:aws:bedrock:ap-northeast-2:123456789:prompt/PODCAST_REASONING"
  versions:                       # Bedrock 버전 번호 (1, 2, 3...)
    batch_validator: "3"          # 현재 v2.3.0 해당
    content_analyzer: "2"         # 현재 v2.1.0 해당
    podcast_reasoning: "3"        # 현재 v3.1.0 해당
```

### boto3 호출 패턴 (참고)

```python
import boto3

bedrock_agent = boto3.client("bedrock-agent", region_name="ap-northeast-2")

response = bedrock_agent.get_prompt(
    promptIdentifier="arn:aws:bedrock:ap-northeast-2:123456789:prompt/BATCH_VALIDATOR",
    promptVersion="3"
)

prompt_text = response["variants"][0]["templateConfiguration"]["text"]["text"]
```

---

## 전환 검토 시점

현재 바로 전환할 필요는 없다. 아래 조건 중 하나 이상 해당할 때 검토한다.

| 조건 | 설명 |
|------|------|
| 비개발자 편집 필요 | 기획자·PM이 AWS 콘솔에서 직접 프롬프트 수정 |
| git 분리 요구 | 보안 정책상 프롬프트 내용을 git 히스토리에서 완전 제거 |
| 실시간 교체 | 프로덕션 배포 중 재시작 없이 프롬프트 교체 필요 |
| 멀티 리전 배포 | 리전별 다른 프롬프트 버전 적용 |

---

## 현재 권장사항

현재 시스템은 이미 멀티버전 + 핀닝 + 보안 검증이 완성되어 있으므로 유지한다.

로컬/개발 환경 분리가 필요한 경우, `PROMPT_DIR` 환경변수로 디렉토리를 분리하는 것으로 충분하다.

```bash
# 프로덕션 환경에서 별도 디렉토리 사용
PROMPT_DIR=prompts_prod python -m uvicorn src.api.main:app
```

---

*참고: [AWS Bedrock Prompt Management 공식 문서](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management.html)*

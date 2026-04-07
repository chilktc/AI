# Changelog v24

> **날짜**: 2026-03-13
> **요약**: API_SPEC.md 구조 분할 리팩토링 (v1.2 → v2.0)

---

## 변경 유형: 문서 구조 리팩토링 (코드 로직 변경 없음)

### 배경

`docs/architecture/API_SPEC.md`가 1,865행으로 비대해져 유지보수·탐색이 어려움.
v1.2에서 분산된 3개 문서(API_FLOW.md, BACKEND_API_CONTRACT.md, 원본 API_SPEC.md)를 통합한 결과.

### 변경 내용

#### 신규 생성 (4개)

| 파일 | 설명 |
|------|------|
| `docs/architecture/API_ARCHITECTURE.md` | 서버 구조, 미들웨어, 파이프라인 실행 흐름 (Phase 0~3) |
| `docs/architecture/API_ENDPOINTS_RECEIVING.md` | 수신 API (Backend→AI) 9개 엔드포인트 상세 |
| `docs/architecture/API_ENDPOINTS_INTERNAL.md` | 발신 API (AI→Backend) 5개 + Load API |
| `docs/architecture/API_COMMON.md` | 스트리밍 이벤트, 에러 코드, 재시도 정책 |

#### 대폭 수정 (1개)

| 파일 | 변경 |
|------|------|
| `docs/architecture/API_SPEC.md` | 1,865행 → ~200행 랜딩 페이지로 변환. 버전 v1.2 → v2.0 |

#### 참조 갱신 (4개)

| 파일 | 변경 |
|------|------|
| `CLAUDE.md` | API_SPEC.md 버전 v1.2 → v2.0 (5개 문서 모음) |
| `docs/INDEX.md` | API_SPEC.md 단일 항목 → 5개 문서 항목 |
| `docs/architecture/PROJECT_STRUCTURE.md` | 디렉토리 트리에 4개 신규 파일 추가 |
| `src/api/backend_resources.py` | docstring 버전 v1.2 → v2.0 |

#### changelog 인덱스

| 파일 | 변경 |
|------|------|
| `docs/changelog/INDEX.md` | v24 항목 추가 |

### 분할 전략: 4+1 구조

```
API_SPEC.md (랜딩 페이지, ~200행)
├── API_ARCHITECTURE.md (아키텍처 흐름)
├── API_ENDPOINTS_RECEIVING.md (수신 API 상세)
├── API_ENDPOINTS_INTERNAL.md (발신 API 상세)
└── API_COMMON.md (공통 에러/스트리밍/재시도)
```

### 영향 범위

- **코드 로직 변경**: 0건
- **문서 내용 변경**: 0건 (구조만 재배치)
- **총 파일 변경**: 10개 (신규 4 + 수정 1 + 참조 갱신 4 + changelog 1)

---

*마지막 업데이트: 2026-03-13*

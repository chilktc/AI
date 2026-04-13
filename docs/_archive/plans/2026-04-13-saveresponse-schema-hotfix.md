# SaveResponse 스키마 유연화 (긴급 핫픽스)

**상태**: ✅ 임시 해결 완료 (장기 해결책 검토 대기)  
**작성 일자**: 2026-04-13 07:35 UTC  
**담당자**: AI 개발팀  
**관련 PR/커밋**: d4626bc  
**상위 계획**: Plan #27 Backend API 전수 테스트 (후속 이슈)

---

## 문제 정의

### 증상

AWS 환경에서 팟캐스트 에피소드 저장 시 연속 실패:

```
ValidationError: 1 validation error for SaveResponse
success
  Field required [type=missing, 
  input_value={'code': 'ok', 'message': '성공'}, 
  input_type=dict]
```

영향 범위:
- `emotion_logs` 저장 실패
- `content_analyses` 저장 실패
- `podcast_episodes` 저장 실패 (400 Bad Request 동시 발생)
- `learning` 저장 실패
- `visualizations` 저장 실패

---

## 근본 원인

백엔드 save API 응답 형식 변경:

| 시기 | 응답 형식 | SaveResponse 매칭 |
|------|---------|-----------------|
| 기존 (동작함) | `{'success': true, 'id': '...', 'message': '...'}` | ✅ |
| 현재 (실패) | `{'code': 'ok', 'message': '성공'}` | ❌ success 필드 누락 |

**의문점**: Plan #27 실행 중 백엔드 API 계약이 변경되었나? 아니면 배포 중 실수?

---

## 해결 방안

### 1. 임시 해결책 ✅ (완료)

**SaveResponse를 양쪽 형식 모두 수용하도록 유연화**

```python
class SaveResponse(BaseModel):
    """데이터 저장 응답 스키마.
    
    백엔드 API 응답 형식 변경 대응:
    - 이전: {'success': true, 'id': '...', 'message': '...'}
    - 현재: {'code': 'ok', 'message': '성공'}
    두 형식 모두 수용하도록 유연하게 설계.
    """
    
    success: bool | None = None  # 선택: 성공 여부
    code: str | None = None      # 선택: 응답 코드 ('ok', 'error' 등)
    id: str | None = None        # 선택: 생성된 리소스 ID
    message: str | None = None   # 선택: 응답 메시지
```

**장점**:
- 즉시 배포 가능 (5분)
- 기존 형식 호환 유지
- 새 형식 수용

**단점**:
- 임시 방편 (근본 해결 X)
- 응답 검증 약화

---

### 2. 장기 해결책 📋 (검토 필요)

**선택지 A: 백엔드 API 계약 명확화**
- 백엔드 팀과 save API 응답 형식 확정
- Swagger/OpenAPI 문서 동기화
- 배포 전 E2E 테스트 추가

**선택지 B: AI 서버 캐싱**
- 백엔드 응답 래핑 (save 통과 여부 판정)
- response.code == 'ok' OR response.success == True로 통합 검증

**선택지 C: API 버전 분리**
- `/api/v2/save` 새 엔드포인트 (명확한 응답 스키마)
- `/api/v1/save` 레거시 유지
- 점진적 마이그레이션

---

## 실행 항목

| 항목 | 담당 | 상태 | 비고 |
|------|------|------|------|
| SaveResponse 유연화 | AI 팀 | ✅ 완료 | d4626bc 커밋 |
| 백엔드 API 응답 형식 확정 | 백엔드 팀 | 🔲 대기 | save API 스키마 명확화 필수 |
| 400 Bad Request 원인 파악 | 백엔드 팀 | 🔲 대기 | podcast_episodes 저장 실패 (별도 이슈) |
| 통합 테스트 | AI 팀 | ⏳ 진행 중 | 임시 해결 후 재테스트 필요 |

---

## 배포 영향

- **AI 서버**: 즉시 재배포 가능 (contracts.py 변경)
- **백엔드**: 변경 불필요 (응답 형식은 현재대로 유지)
- **프론트엔드**: 영향 없음

---

## 추적 항목

- [ ] AWS 환경에서 save 재시도 성공 확인
- [ ] 백엔드 팀과 API 계약 확정 회의
- [ ] 장기 해결책 선택 및 일정 수립
- [ ] E2E 테스트에 save API 응답 형식 테스트 케이스 추가

---

## 참고

- **로그 위치**: AWS EC2 `/var/log/mindlog-ai-service.log`
- **에러 샘플**: `emotion_logs`, `content_analyses`, `podcast_episodes`, `learning`, `visualizations` 모두 동일 패턴
- **관련 코드**: `src/api/client.py:83` (SaveResponse 검증 로직)

---

*Plan #30 — 긴급 핫픽스. 임시 해결책 완료, 백엔드 협의 대기 중.*

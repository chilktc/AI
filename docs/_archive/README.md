# _archive — 완료/폐기 문서 보관

> 이 디렉토리의 파일들은 **삭제가 아니라 이동**된 것이다. git 이력이 보존되어 있다.
> 현재 개발에는 영향 없으며, 역사적 참고 자료로만 존재한다.

## 구조

| 폴더 | 내용 |
|------|------|
| `plans/` | 완료된 구현 계획서 17개 |
| `specs/` | 완료된 설계서 5개 (설계 결정 배경은 `docs/WHY.md` 참조) |
| `changelog/` | 구 changelog v1~v24 (15개) |
| `misc/` | 아카이브된 가이드, 보고서, 기타 문서 |

## 언제 여기를 보나

- 삭제된 기능(대화모드, Mode A 등)의 **원래 구현 계획**을 참고할 때
- 과거 의사결정 **과정**이 궁금할 때 (결정 자체는 `docs/WHY.md` 참조)
- git blame/log보다 **문서 레벨** 맥락이 필요할 때

## 미완료 계획서 (이 폴더에 없음 — 활성 상태)

아래 계획서는 완료되지 않아 `docs/superpowers/plans/`에 그대로 있다:

- `2026-04-06-pending-items-inventory.md` — 잔여 미완료 항목 목록
- `2026-04-07-neo4j-integration-plan.md` — Neo4j E2E 검증 대기
- `2026-04-07-pinecone-vector-db-integration.md` — BedrockEmbeddingClient 미구현

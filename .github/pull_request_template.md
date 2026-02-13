## 변경 사항

<!-- 이 PR에서 변경한 내용을 간략히 설명해주세요 -->

## 관련 에이전트

<!-- 이 PR이 영향을 미치는 에이전트를 선택해주세요 -->
- [ ] Intent Classifier
- [ ] Safety Agent
- [ ] Emotion Agent
- [ ] Context Agent
- [ ] Memory Agent
- [ ] Knowledge Agent
- [ ] Reasoning Agent
- [ ] Synthesis Agent
- [ ] Validator Agent
- [ ] Personalization Agent
- [ ] Visualization Agent
- [ ] Telemetry Agent
- [ ] Learning Agent
- [ ] Content Analyzer (팟캐스트)
- [ ] Episode Memory (팟캐스트)
- [ ] Podcast Reasoning (팟캐스트)
- [ ] Script Generator (팟캐스트)
- [ ] Batch Validator (팟캐스트)
- [ ] Script Personalizer (팟캐스트)

## 담당 개발자

<!-- 자신의 브랜치 접두사를 선택해주세요 -->
- [ ] 개발자1 (feature/analysis-*)
- [ ] 개발자2 (feature/reasoning-*)
- [ ] 개발자3 (feature/validation-*)

## Protected Files 변경 여부

<!-- 아래 파일 수정이 포함된 경우 3인 전원 리뷰가 필요합니다 -->
- [ ] `src/models/agent_state.py`
- [ ] `src/models/message.py`
- [ ] `src/api/contracts.py`
- [ ] `src/graph/workflow.py`

## 체크리스트

- [ ] 자기 도메인 파일만 수정했는가?
- [ ] 타입 힌팅을 모두 작성했는가?
- [ ] `black .` 포맷팅을 적용했는가?
- [ ] `ruff check .` 린트를 통과했는가?
- [ ] 단위 테스트를 작성/업데이트했는가?
- [ ] `pytest tests/ -v` 테스트를 통과했는가?
- [ ] AgentState 필드 접근 규칙을 준수했는가? (자기 필드만 쓰기)
- [ ] 에이전트 노드 시그니처를 준수했는가? (`async def {name}_node(state) -> state`)

## 테스트 결과

<!-- pytest 실행 결과를 붙여넣어주세요 -->
```
pytest output here
```

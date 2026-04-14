# S3 Public-Read ACL 추가 Implementation Plan

> **상태**: ✅ 완료 (PR #117, 2026-04-14 MERGED)

**Goal:** Visualization Agent가 S3에 업로드하는 이미지에 `ACL="public-read"`를 추가하여 브라우저에서 직접 URL로 접근 가능하게 한다.

**Architecture:** `visualization.py`의 `put_object` 호출에 `ACL="public-read"` 파라미터 한 줄 추가. S3Client(`src/db/s3_client.py`)는 건드리지 않는다 — Visualization Agent는 자체 boto3 client를 직접 사용하고 있어 S3Client와 무관하다.

**Tech Stack:** boto3, pytest, pytest-asyncio

> **브랜치 주의:** Visualization Agent는 개발자2 담당(`feature/reasoning-*`). 현재 `feature/validation-*` 브랜치에서 작업 중이라면, 작업 전 `feature/reasoning-s3-public-read` 브랜치를 새로 생성한다.

---

### Task 1: ACL 파라미터 추가 및 테스트 검증

**Files:**
- Modify: `src/agents/podcast/visualization.py:108-113`
- Test: `tests/agents/podcast/test_visualization_agent.py`

---

- [x] **Step 1: 브랜치 생성**

```bash
git checkout main
git pull
git checkout -b feature/reasoning-s3-public-read
```

---

- [x] **Step 2: 기존 테스트 실행 — 현재 통과 확인**

```bash
pytest tests/agents/podcast/test_visualization_agent.py -v
```

Expected: 모든 테스트 PASS (기준선 확인)

---

- [x] **Step 3: ACL 검증 테스트 추가**

`tests/agents/podcast/test_visualization_agent.py` 파일 하단(line 312 이후)에 아래 테스트를 추가한다:

```python
@pytest.mark.asyncio
async def test_put_object_called_with_public_read_acl(agent: VisualizationAgent) -> None:
    """S3 업로드 시 ACL='public-read'가 포함되어야 한다."""
    llm_response = {
        "image_prompt": "test prompt",
        "style_type": "organic",
        "interpretation": "테스트",
    }
    image_gen_response = {"image_binary": b"\x89PNG\r\n\x1a\n"}
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={},
        content_analysis={},
    )

    mock_s3 = MagicMock()
    agent.s3_client = mock_s3

    with (
        patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
        patch.object(
            agent, "call_image_gen", new_callable=AsyncMock, return_value=image_gen_response
        ),
    ):
        await agent.process(state)

    call_kwargs = mock_s3.put_object.call_args.kwargs
    assert call_kwargs.get("ACL") == "public-read", (
        f"put_object에 ACL='public-read'가 없음. 실제 kwargs: {call_kwargs}"
    )
```

---

- [x] **Step 4: 새 테스트 실행 — FAIL 확인**

```bash
pytest tests/agents/podcast/test_visualization_agent.py::test_put_object_called_with_public_read_acl -v
```

Expected: FAIL — `AssertionError: put_object에 ACL='public-read'가 없음`

---

- [x] **Step 5: `visualization.py` 수정 — ACL 추가**

`src/agents/podcast/visualization.py`의 `put_object` 호출 블록(line 108-113)을 아래와 같이 수정한다:

```python
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=raw_res["image_binary"],
                ContentType="image/png",
                ACL="public-read",
            )
```

---

- [x] **Step 6: 전체 테스트 실행 — 모두 PASS 확인**

```bash
pytest tests/agents/podcast/test_visualization_agent.py -v
```

Expected: 모든 테스트 PASS (신규 테스트 포함)

---

- [x] **Step 7: 전체 테스트 스위트 이상 없음 확인**

```bash
pytest tests/ -v --timeout=60 -x
```

Expected: 583 passed (기존 582 + 신규 1)

---

- [x] **Step 8: 커밋**

```bash
git add src/agents/podcast/visualization.py tests/agents/podcast/test_visualization_agent.py
git commit -m "fix: S3 업로드 시 ACL=public-read 추가 — 브라우저 직접 접근 허용"
```

---

## 완료 기준

- `put_object` 호출에 `ACL="public-read"` 포함
- 기존 테스트 전부 통과
- 신규 ACL 검증 테스트 통과
- `https://{bucket}.s3.amazonaws.com/{key}` URL로 브라우저 접근 가능 (AWS 버킷의 Block Public Access 설정이 off인 경우)

> **AWS 콘솔 확인 필요:** 코드 수정만으로는 부족할 수 있다. S3 버킷 `t7-mindlog-ai-assets`의
> **Block Public Access** 설정에서 "Block all public access"가 **비활성화**되어 있어야 한다.
> 콘솔 경로: S3 → 버킷 선택 → Permissions → Block public access → Edit

*작성일: 2026-04-14*
*완료일: 2026-04-14 (PR #117 → develop MERGED)*

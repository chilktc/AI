"""
Script Generator Agent
팟캐스트 스크립트를 생성합니다 (세그먼트별 배치 생성).

TIER 2 에이전트: Podcast Reasoning에서 넘어온 기획안을 바탕으로 완전한 스크립트를 작성합니다.
"""

import uuid
from datetime import datetime
from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


class ScriptGeneratorAgent(BaseAgent):
    """
    팟캐스트 스크립트 생성 에이전트
    세그먼트별로 순차적으로 스크립트를 생성합니다.
    """

    # 한국어 기준 평균 발화 속도 (KBS 아나운서 기준 ~150 WPM). 팟캐스트 시간 추정에 사용.
    WORDS_PER_MINUTE = 150

    def __init__(self):
        super().__init__(name="script_generator", tier=2)

    async def process(self, state: AgentState) -> dict:
        """
        LangGraph 노드 함수 (비동기)

        Args:
            state: 팟캐스트 상태

        Returns:
            업데이트된 상태 (script_draft 등)
        """
        start_time = datetime.now()

        self.logger.info("[ScriptGenerator] 스크립트 생성 프로세스 시작")

        # 입력 데이터 추출 (content_analysis 등 이전 단계 결과 반영)
        content_analysis = state.get(
            "content_analysis", state
        )  # state 최상단에 병합됐을 수도 있고 dict 형태일 수도 있음
        main_theme = content_analysis.get("main_theme", state.get("main_theme", "Mental Health"))
        sub_themes = content_analysis.get("sub_themes", state.get("sub_themes", []))
        emotional_journey = content_analysis.get(
            "emotional_journey", state.get("emotional_journey", {})
        )

        target_duration = content_analysis.get(
            "target_duration", state.get("target_duration", 5)
        )  # 전체 목표 시간

        # Reasoning에서 생성된 segment_plan (또는 episode_structure) 추출
        reasoning_result = state.get("reasoning_result", {})
        segment_plan = state.get("segment_plan", [])
        if not segment_plan and "episode_structure" in reasoning_result:
            episode_structure = reasoning_result["episode_structure"]
            num_sections = max(len(episode_structure), 1)
            default_ratio = round(1.0 / num_sections, 2)

            for idx, sec in enumerate(episode_structure):
                # sec가 str인 경우 (프롬프트가 문자열 배열을 반환한 경우) dict로 변환
                if isinstance(sec, str):
                    sec = {"section": sec}

                duration_ratio = float(sec.get("duration_ratio", default_ratio))
                calc_duration = max(1, int(target_duration * duration_ratio))

                segment_plan.append(
                    {
                        "segment_id": f"seg_{idx+1}_{uuid.uuid4().hex[:4]}",
                        "segment_type": sec.get("section", f"part_{idx+1}"),
                        "duration_minutes": calc_duration,
                        "key_points": [sec.get("content_direction", "")],
                        "emotional_tone": sec.get("emotional_tone", "차분함"),
                        "transition_hint": sec.get("transition", ""),
                    }
                )

        # 그래도 플랜이 없다면 임시 플랜 생성
        if not segment_plan:
            start_emotion = emotional_journey.get(
                "opening", emotional_journey.get("start_emotion", "차분함")
            )
            segment_plan = [
                {
                    "segment_id": f"seg_{uuid.uuid4().hex[:6]}",
                    "segment_type": "intro",
                    "duration_minutes": 2,
                    "key_points": [main_theme + "에 대한 공감"],
                    "emotional_tone": start_emotion,
                    "transition_hint": "자연스럽게 본론으로 넘어가기",
                }
            ]

        knowledge_context = state.get("knowledge_context", {})

        try:
            # 1. 에피소드 제목 생성
            episode_title = await self._generate_title(main_theme, sub_themes, emotional_journey)
            self.logger.info("[ScriptGenerator] 제목 생성 완료: %s", episode_title)

            # 2. 세그먼트별 스크립트 생성
            generated_segments = []
            for idx, segment in enumerate(segment_plan):
                self.logger.info(
                    f"[ScriptGenerator] 세그먼트 {idx + 1}/{len(segment_plan)} 생성 중..."
                )

                prev_context = self._get_previous_context(generated_segments, idx)
                segment_script = await self._generate_segment_script(
                    segment=segment,
                    episode_title=episode_title,
                    main_theme=main_theme,
                    emotional_journey=emotional_journey,
                    previous_context=prev_context,
                    knowledge_context=knowledge_context,
                )
                generated_segments.append(segment_script)

            # 3. 핵심 인사이트 추출
            key_insights = await self._extract_insights(generated_segments)

            # 4. 최종 스크립트 (Draft) 구조화
            total_duration = sum(seg.get("duration_minutes", 0) for seg in generated_segments)
            total_words = sum(seg.get("word_count", 0) for seg in generated_segments)

            script_draft = {
                "episode_title": episode_title,
                "total_duration": total_duration,
                "segments": generated_segments,
                "key_insights": key_insights,
                "themes": [main_theme] + sub_themes,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "main_theme": main_theme,
                    "total_words": total_words,
                    "segment_count": len(generated_segments),
                    "processing_time": (datetime.now() - start_time).total_seconds(),
                },
            }

            self.logger.info(
                f"[ScriptGenerator] 전체 생성 완료. 총 {total_words}단어, 예상 시간 {total_duration}분"
            )

            return {"script_draft": script_draft}

        except Exception as e:
            self.logger.error("[ScriptGenerator] 스크립트 작성 중 에러 발생: %s", e)
            return {"script_draft": {}, "error": str(e)}

    async def _generate_title(
        self, main_theme: str, sub_themes: list[str], emotional_journey: dict
    ) -> str:
        """에피소드 제목을 LLM으로 생성한다.

        Args:
            main_theme: 에피소드 메인 테마
            sub_themes: 서브 테마 목록
            emotional_journey: 감정 여정 dict (opening, resolution 등)

        Returns:
            생성된 에피소드 제목 문자열
        """
        start_emotion = emotional_journey.get(
            "opening", emotional_journey.get("start_emotion", "None")
        )
        resolution_emotion = emotional_journey.get(
            "resolution", emotional_journey.get("resolution_emotion", "None")
        )

        # yaml 내에 user_prompt 도 정의해 두었거나, 기존처럼 코드 내에 유지하되 yaml의 system_prompt 만 사용할 수도 있습니다.
        # 코드 변경사항을 최소화하기 위해 user_message는 기존 형식을 유지하고, system_prompt만 로더에서 가져옵니다.
        # 혹은 yaml에서 가져온 user_prompt도 format하여 사용할 수 있습니다. 여기서는 yaml도 고려하여 두 가지 모두 가져옵니다.
        
        prompts = self._prompt_loader.load_all("podcast", "script_generator")
        
        user_prompt = self._prompt_loader.load_user_prompt("podcast", "script_generator", "generate_title")
        prompt = user_prompt.format(
            main_theme=main_theme,
            sub_themes=", ".join(sub_themes),
            start_emotion=start_emotion,
            resolution_emotion=resolution_emotion
        )

        try:
            # generate 메서드는 일반 텍스트를 반환합니다.
            response_text = await self.call_llm(
                system_prompt=self.get_prompt("generate_title"),
                user_message=prompt,
            )
            title = response_text.strip().replace('"', "").replace("'", "")
            return title if len(title) <= 30 else title[:30] + "..."
        except Exception:
            return f"당실을 위한 마음 이야기: {main_theme}"

    async def _generate_segment_script(
        self,
        segment: dict,
        episode_title: str,
        main_theme: str,
        emotional_journey: dict,
        previous_context: str,
        knowledge_context: dict,
    ) -> dict:
        """개별 세그먼트의 스크립트 텍스트를 LLM으로 생성한다.

        Args:
            segment: 세그먼트 메타 (segment_type, duration_minutes, key_points 등)
            episode_title: 에피소드 제목
            main_theme: 메인 테마
            emotional_journey: 감정 여정 dict
            previous_context: 이전 세그먼트 맥락 요약
            knowledge_context: Knowledge Agent 검색 결과

        Returns:
            스크립트 텍스트가 포함된 세그먼트 dict
        """
        duration_minutes = segment.get("duration_minutes", 2)
        word_count_target = duration_minutes * self.WORDS_PER_MINUTE

        # 지식 요약
        knowledge_summary = "사용 가능한 전문 지식이 없습니다."
        if knowledge_context and isinstance(knowledge_context, dict):
            synthesis = knowledge_context.get("knowledge_results", {}).get("synthesis")
            if synthesis:
                knowledge_summary = synthesis

        key_points_text = "\n".join([f"- {kp}" for kp in segment.get("key_points", [])])

        user_prompt = self._prompt_loader.load_user_prompt("podcast", "script_generator", "generate_segment")
        prompt = user_prompt.format(
            episode_title=episode_title,
            main_theme=main_theme,
            duration_minutes=duration_minutes,
            word_count_target=word_count_target,
            key_points_text=key_points_text,
            emotional_tone=segment.get("emotional_tone", "neutral"),
            transition_hint=segment.get("transition_hint", "natural transition"),
            previous_context=previous_context or "This is the opening segment.",
            knowledge_summary=knowledge_summary
        )

        try:
            script_text = await self.call_llm(
                system_prompt=self.get_prompt("generate_segment"),
                user_message=prompt,
            )

            word_count = len(script_text.split())

            return {
                "segment_id": segment.get("segment_id", "unknown_seg"),
                "segment_type": segment.get("segment_type", "body"),
                "duration_minutes": duration_minutes,
                "script_text": script_text.strip(),
                "word_count": word_count,
                "emotional_tone": segment.get("emotional_tone", "neutral"),
                "tts_markers": [],
            }
        except Exception as e:
            self.logger.error("세그먼트 스크립트 작성 실패: %s", e)
            return {
                "segment_id": segment.get("segment_id", f"error_seg_{uuid.uuid4().hex[:4]}"),
                "segment_type": segment.get("segment_type", "body"),
                "duration_minutes": duration_minutes,
                "script_text": f"(스크립트 작성 실패: {main_theme} 관련 내용을 논의하는 부분입니다.)",
                "word_count": 10,
                "emotional_tone": "neutral",
                "tts_markers": [],
            }

    def _get_previous_context(self, generated_segments: list[dict], current_index: int) -> str:
        """이전 세그먼트를 기준으로 짧은 요약 컨텍스트를 제공"""
        if current_index == 0 or not generated_segments:
            return ""

        prev_seg = generated_segments[-1]
        text_preview = prev_seg.get("script_text", "")[-150:]
        return f"이전 세그먼트는 이렇게 끝났습니다: '...{text_preview}'"

    async def _extract_insights(self, generated_segments: list[dict]) -> list[str]:
        """생성된 스크립트들에서 핵심 인사이트 추출 (JSON 배열 형식 반환)"""
        if not generated_segments:
            return []

        full_script = "\n\n".join([s.get("script_text", "") for s in generated_segments])
        # 스크립트가 너무 길면 잘라냄
        if len(full_script) > 5000:
            full_script = full_script[:5000] + "..."

        system_prompt = self.get_prompt("extract_insights")
        user_prompt = self._prompt_loader.load_user_prompt("podcast", "script_generator", "extract_insights")
        user_message = user_prompt.format(
            full_script=full_script
        )

        try:
            insights = await self.call_llm_json(
                system_prompt=system_prompt,
                user_message=user_message,
            )
            # 만약 dict로 오면 values 추출, list면 그대로
            if isinstance(insights, dict) and "insights" in insights:
                return insights["insights"]
            if isinstance(insights, list):
                return insights[:5]
            return []
        except Exception:
            return ["감정 수용하기", "스스로에게 친절하게 대하기"]


async def create_script_generator_node() -> Any:
    """LangGraph에서 호출 가능한 노드 팩토리 생성"""
    agent = ScriptGeneratorAgent()

    async def _node(state: AgentState) -> dict:
        return await agent.process(state)

    return _node

"""
라이브 LLM 테스트 패키지 — 개별 에이전트 실제 LLM 호출 스모크 테스트.

이 패키지는 dev/ 폴더에 위치하며 .gitignore에 의해 git push에서 제외된다.
Ollama(로컬), Anthropic API, AWS Bedrock 모든 프로바이더를 지원한다.

사용법:
    python3 -m dev.live_tests.run_live --agent content_analyzer
    python3 -m dev.live_tests.run_live --all --provider anthropic
    python3 -m dev.live_tests.run_live --pipeline
"""

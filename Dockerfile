# Mind-Log AI Docker Image
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 필요한 디렉토리 생성
RUN mkdir -p logs data/cache data/outputs

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 포트 노출 (API 서버용)
EXPOSE 8000

# 기본 명령어 — uvicorn으로 FastAPI 서버 시작
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

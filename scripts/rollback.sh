#!/bin/bash
# scripts/rollback.sh
# 직전 배포 이미지로 AI 서버를 롤백한다.
#
# EC2에서 직접 실행:
#   sudo bash /home/ubuntu/app/scripts/rollback.sh
#
# 전제 조건:
#   - /home/ubuntu/app/.prev_image 파일이 존재해야 한다 (deploy.yml이 자동 생성)
#   - Docker Compose 환경이 /home/ubuntu/app에 구성되어 있어야 한다

set -euo pipefail

APP_DIR="/home/ubuntu/app"
PREV_IMAGE_FILE="$APP_DIR/.prev_image"

if [ ! -f "$PREV_IMAGE_FILE" ]; then
    echo "ERROR: .prev_image 파일 없음 — 롤백 대상 이미지를 알 수 없습니다."
    exit 1
fi

PREV_IMAGE=$(cat "$PREV_IMAGE_FILE")

if [ -z "$PREV_IMAGE" ]; then
    echo "ERROR: .prev_image 파일이 비어 있습니다 — 이전 배포 이미지 정보가 없습니다."
    exit 1
fi

echo "롤백 대상 이미지: $PREV_IMAGE"

cd "$APP_DIR"

# .env의 AI_SERVER_IMAGE를 이전 이미지로 교체
sed -i "s|AI_SERVER_IMAGE=.*|AI_SERVER_IMAGE=$PREV_IMAGE|" .env
echo ".env 업데이트 완료"

# 현재 컨테이너 정지 (graceful)
docker compose stop --timeout 30 ai-server 2>/dev/null || true

# 이전 이미지로 기동
docker compose up -d --no-deps ai-server

echo "롤백 완료: $PREV_IMAGE"

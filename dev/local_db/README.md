# 로컬 DB 개발 환경 (dev/local_db)

개발 전용 로컬 DB 환경. 기존 코드를 수정하지 않으며, 언제든 완전 삭제 가능.

## 빠른 시작

```bash
# 1. DB 컨테이너 시작
docker compose -f dev/local_db/docker-compose.db.yml up -d

# 2. 헬스체크 대기 (약 30초)
docker compose -f dev/local_db/docker-compose.db.yml ps

# 3. 환경변수 로드
export $(cat dev/local_db/.env.db | xargs)

# 4. 시드 데이터 로드
python -m dev.local_db.seed

# 5. 전체 검증
python -m dev.local_db.verify
```

## 구성 요소

| 파일 | 설명 |
|------|------|
| `docker-compose.db.yml` | MySQL 8.0 + Neo4j 5 Docker 서비스 |
| `.env.db` | DB 접속 환경변수 |
| `mysql/init.sql` | MySQL 7개 테이블 DDL (자동 실행) |
| `neo4j/init.cypher` | Neo4j 제약조건/인덱스 (verify.py에서 실행) |
| `fixtures/seed_data.json` | e2e 호환 시드 데이터 (JSON) |
| `seed.py` | JSON → DB 로드 스크립트 |
| `pinecone_mock.py` | 인메모리 Pinecone Mock 클라이언트 |
| `verify.py` | 연결/스키마/CRUD/에이전트쿼리 검증 |

## 명령어

### 시드 데이터

```bash
python -m dev.local_db.seed              # 전체 시드
python -m dev.local_db.seed --mysql      # MySQL만
python -m dev.local_db.seed --neo4j      # Neo4j만
python -m dev.local_db.seed --clean      # 시드 데이터 삭제
```

### 검증

```bash
python -m dev.local_db.verify            # 전체 검증 (9개 항목)
python -m dev.local_db.verify --mysql    # MySQL만
python -m dev.local_db.verify --neo4j    # Neo4j만
python -m dev.local_db.verify --pinecone # Pinecone Mock만
python -m dev.local_db.verify --factory  # Factory 패턴만
```

### Docker 생명주기

```bash
# 시작
docker compose -f dev/local_db/docker-compose.db.yml up -d

# 종료 (데이터 유지)
docker compose -f dev/local_db/docker-compose.db.yml down

# 완전 삭제 (볼륨 포함)
docker compose -f dev/local_db/docker-compose.db.yml down -v
```

## 완전 삭제

```bash
# DB 컨테이너 + 볼륨 제거
docker compose -f dev/local_db/docker-compose.db.yml down -v

# 파일까지 완전 삭제
rm -rf dev/local_db/
```

## 접속 정보

| DB | URL | 사용자 | 비밀번호 |
|----|-----|--------|---------|
| MySQL | `localhost:3306/mindlog` | `mindlog_user` | `.env.db` 참조 |
| Neo4j Browser | `http://localhost:7474` | `neo4j` | `.env.db` 참조 |
| Neo4j Bolt | `bolt://localhost:7687` | `neo4j` | `.env.db` 참조 |

> 비밀번호는 `dev/local_db/.env.db`에서 관리합니다. `.env.db.example`을 복사하여 설정하세요.

## 트러블슈팅

### 포트 충돌
로컬에 MySQL/Neo4j가 이미 실행 중이면 포트 충돌 발생:
```bash
# 기존 서비스 확인
lsof -i :3306
lsof -i :7687

# Homebrew 서비스 중지
brew services stop mysql
brew services stop neo4j
```

### MySQL 초기화 실패
볼륨에 이전 데이터가 있으면 init.sql이 건너뛰어짐:
```bash
docker compose -f dev/local_db/docker-compose.db.yml down -v
docker compose -f dev/local_db/docker-compose.db.yml up -d
```

### Neo4j 메모리 부족
Docker Desktop 메모리 할당 확인 (최소 2GB 권장).

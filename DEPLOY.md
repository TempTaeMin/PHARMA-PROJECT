# MediSync 배포 흐름

베타 운영: **medisync.co.kr** / 가비아 Gen2 (Ubuntu) / Docker Compose v2 / Caddy 자동 HTTPS.

서버: `139.150.81.16` — SSH 키 `medisync-key.pem`.

`docker-compose.yml` 4개 서비스: `db` (postgres) / `api` (FastAPI) / `frontend` (Vite build) / `caddy` (reverse proxy + TLS).
Celery worker/beat/redis 는 미가동 — 자동 크롤링 없음, 수동 트리거(`POST /api/crawl/sync/{code}`) 만 사용.

---

## 1) 일반 코드 변경 배포

로컬 작업 → 커밋 → push → 서버에서 pull + rebuild.

```bash
# 1. 로컬
git add -p
git commit -m "..."
git push origin main

# 2. 서버
ssh -i medisync-key.pem ubuntu@139.150.81.16
cd ~/medisync
git pull origin main

# 3. 변경된 서비스만 빌드/재시작
docker compose build api          # 백엔드만 바뀌었을 때
docker compose up -d api

docker compose build frontend     # 프런트만 바뀌었을 때
docker compose up -d frontend

# 4. 검증
curl -o /dev/null -w "%{http_code}\n" https://medisync.co.kr/health
docker compose logs api --tail=30
```

api 재시작은 5~15초. 그 동안 502 잠깐 뜨는 건 정상.

---

## 2) DB 스키마 변경 (alembic 마이그레이션)

새 마이그레이션 파일이 `backend/alembic/versions/` 에 추가됐을 때만.

```bash
# 서버, api 컨테이너 살아있는 상태에서
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current   # head 표시되는지 확인
```

**금지:** `alembic stamp head` 만 돌리고 실제 ALTER 안 하는 것. 5/6 시점에 visit_logs 4컬럼 + visits_memo 가 운영에서 깨졌던 사고. stamp 는 "버전만 마킹" 이라 진짜 컬럼은 안 만든다 — 비어있는 DB 에 한 번만 쓸 수 있는 안전장치.

---

## 3) Caddyfile / 환경변수 변경

```bash
# Caddyfile 변경
docker compose restart caddy
# (reload 가 "config unchanged" 거부 시 restart 로)

# .env.production 변경
docker compose up -d api   # env_file 다시 읽힘
```

---

## 4) 운영 데이터 작업 (백필 / 마이그레이션 스크립트)

`scripts/` 안의 일회성 Python 스크립트는 컨테이너 내부에서 실행.

```bash
# 예: EUMC 스케줄 백필
docker compose exec api python scripts/backfill_schedules.py EUMCMK EUMCSL

# 예: 대학병원 26개 일괄 (HTTP 우회, timeout 안 걸림)
docker compose exec api python scripts/backfill_schedules.py --preset universities
```

`DATABASE_URL` 환경변수가 컨테이너 내부에 이미 PG 로 설정돼 있어 로컬 SQLite 가 아니라 운영 PG 로 쓴다.

---

## 5) 검증 / 트러블슈팅

```bash
# 컨테이너 상태
docker compose ps

# 로그
docker compose logs api --tail=100
docker compose logs api -f          # follow
docker compose logs caddy --tail=50

# PG 직접 쿼리
docker compose exec db psql -U medisync -d medisync -c "SELECT code, COUNT(*) FROM hospitals JOIN doctors ON doctors.hospital_id=hospitals.id GROUP BY code;"

# 헬스체크
curl -o /dev/null -w "%{http_code}\n" https://medisync.co.kr/health

# 컨테이너 안 들어가서 디버깅
docker compose exec api bash
docker compose exec db bash
```

---

## 6) 백업

`pg_data` 볼륨이 호스트에 있어 PG 데이터는 컨테이너 재시작/재빌드에 안 날아간다. cron 등 정기 dump 는 아직 미설정 (TODO).

긴급 dump:
```bash
docker compose exec -T db pg_dump -U medisync medisync > backup-$(date +%F).sql
```

---

## 7) 자주 헷갈리는 것

- **로컬 `pharma_scheduler.db` (SQLite) ≠ 운영 DB**. 로컬은 dev 용. 운영 진단 시 절대 로컬 DB 쿼리로 결론 내지 말 것. 운영은 컨테이너 안 `psql` 또는 운영 API 호출.
- **`docker compose` (v2) vs `docker-compose` (v1)**. 가비아 서버는 v2 — 띄어쓰기 형식만 사용.
- **`init_db()` 가 더 이상 schema 자동 생성 안 함**. 새 모델 추가 시 반드시 alembic 마이그 작성 + 운영에서 upgrade.
- **api 재시작 도중 502** 는 5~15초 정상. 길어지면 `docker compose logs api` 확인.
- **프런트 빌드 결과는 컨테이너 내부**. 로컬 `npm run build` → scp 흐름은 옛 비-Docker 방식 (`deploy/README.md`). 지금은 `docker compose build frontend` 가 컨테이너 내부에서 빌드.

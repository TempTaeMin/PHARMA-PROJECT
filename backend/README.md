# PharmScheduler Backend v0.4.0

제약 영업사원(MR)을 위한 교수 진료일정 크롤링 & 스케줄 관리 API

## 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | Python FastAPI 0.115 + asyncio |
| **DB** | SQLAlchemy 2.0 + SQLite (MVP) → PostgreSQL (운영) |
| **크롤링** | httpx + BeautifulSoup + Playwright 1.47 |
| **태스크 큐** | Celery 5.4 + Redis |
| **실시간 알림** | WebSocket (FastAPI 내장) |
| **설정 관리** | pydantic-settings (.env 지원) |
| **Frontend** | React 19 + Vite (별도 디렉토리) |

## 프로젝트 구조

```
pharma-project/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 앱 엔트리포인트
│   │   ├── config.py                # 설정 관리 (pydantic-settings)
│   │   ├── api/
│   │   │   ├── crawl.py             # 크롤링 API
│   │   │   ├── doctors.py           # 의료진 관리 API
│   │   │   ├── hospitals.py         # 병원 관리 API
│   │   │   ├── scheduler.py         # Celery 스케줄러 API
│   │   │   └── notifications.py     # 알림 API + WebSocket
│   │   ├── crawlers/
│   │   │   ├── factory.py           # 크롤러 팩토리 (병원 코드 → 크롤러 매핑)
│   │   │   ├── playwright_engine.py # Playwright 범용 크롤러
│   │   │   ├── cmc_base.py          # 가톨릭중앙의료원 그룹 베이스
│   │   │   ├── kumc_base.py         # 고려대의료원 그룹 베이스
│   │   │   └── *_crawler.py         # 병원별 전용 크롤러 (29개)
│   │   ├── models/
│   │   │   ├── database.py          # SQLAlchemy 모델 (7개 테이블)
│   │   │   ├── connection.py        # DB 연결 설정
│   │   │   └── seed.py             # 시드 데이터 (29개 병원 + 샘플)
│   │   ├── schemas/
│   │   │   └── schemas.py           # Pydantic 스키마
│   │   ├── services/
│   │   │   └── crawl_service.py     # 크롤링 결과 DB 저장 로직
│   │   ├── tasks/
│   │   │   ├── celery_app.py        # Celery 앱 + Beat 스케줄
│   │   │   ├── crawl_tasks.py       # 크롤링 태스크
│   │   │   └── notification_tasks.py # 알림 태스크
│   │   └── notifications/
│   │       └── manager.py           # WebSocket 연결 관리
│   ├── run.py                       # Windows 호환 서버 실행 스크립트
│   ├── tests/
│   │   ├── test_integration.py      # Mock 기반 통합 테스트
│   │   ├── test_poc_crawl.py        # 실제 크롤링 PoC 테스트
│   │   └── test_v2_integration.py   # v2 통합 테스트
│   └── requirements.txt
├── frontend/                        # React 19 + Vite
│   └── src/
│       ├── pages/                   # Dashboard, MyDoctors, BrowseDoctors, CrawlStatus
│       ├── components/              # NotificationPanel 등
│       ├── hooks/                   # useApi, useCachedApi
│       └── api/                     # HTTP 클라이언트
└── pharma_scheduler.db              # SQLite DB 파일
```

## 빠른 시작

### Backend (기본)

```bash
cd backend
pip install -r requirements.txt
python run.py
# 또는: uvicorn app.main:app --port 8000
```

### Celery + Redis 포함 (전체 기능)

```bash
# 터미널 1: Redis
redis-server

# 터미널 2: Celery Worker + Beat (개발용)
celery -A app.tasks.celery_app worker --beat --loglevel=info

# 터미널 3: FastAPI
python run.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### API 문서

```
http://localhost:8000/docs
```

## 지원 병원 (29개)

### 서울 (18개)

| 코드 | 병원명 | 코드 | 병원명 |
|------|--------|------|--------|
| AMC | 서울아산병원 | SNUH | 서울대학교병원 |
| SMC | 삼성서울병원 | SEVERANCE | 세브란스병원 |
| CMCSEOUL | 서울성모병원 | CMCEP | 은평성모병원 |
| CMCYD | 여의도성모병원 | GANSEV | 강남세브란스병원 |
| EUMCMK | 이대목동병원 | EUMCSL | 이대서울병원 |
| KUANAM | 고대안암병원 | KUGURO | 고대구로병원 |
| KCCH | 한국원자력의학원 | KUH | 건국대학교병원 |
| HYUMC | 한양대병원 | KHU | 경희대병원 |
| KBSMC | 강북삼성병원 | CAU | 중앙대병원 |

### 경기 (8개)

| 코드 | 병원명 | 코드 | 병원명 |
|------|--------|------|--------|
| KUANSAN | 고대안산병원 | NCC | 국립암센터 |
| DUIH | 동국대일산병원 | SNUBH | 분당서울대병원 |
| CMCSV | 성빈센트병원 | SCHBC | 부천순천향병원 |
| AJOUMC | 아주대병원 | HALLYM | 한림성심병원 |

### 인천 (3개)

| 코드 | 병원명 |
|------|--------|
| GIL | 길병원 |
| CMCIC | 인천성모병원 |
| INHA | 인하대병원 |

## API 엔드포인트

### 크롤링 (`/api/crawl`)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/hospitals` | 지원 병원 목록 (지역 포함) |
| GET | `/departments/{hospital_code}` | 진료과 목록 |
| GET | `/browse/{hospital_code}` | 교수 탐색 (DB 조회, 이름/진료과 검색) |
| POST | `/sync/{hospital_code}` | 병원 교수 목록 크롤링 → DB 저장 |
| POST | `/my-doctors` | 내 교수 일정 크롤링 |
| GET | `/doctor/{hospital_code}/{staff_id}` | 의료진 개별 진료시간 크롤링 |
| POST | `/register-doctor` | 내 교수로 등록 (visit_grade=B) |

### 의료진 관리 (`/api/doctors`)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 의료진 목록 (hospital_id, department, visit_grade, my_only 필터) |
| GET | `/{doctor_id}` | 의료진 상세 (일정 포함) |
| POST | `/` | 의료진 등록 |
| PATCH | `/{doctor_id}` | 의료진 정보 수정 (방문등급, 메모 등) |
| POST | `/{doctor_id}/visits` | 방문 기록 등록 |
| GET | `/{doctor_id}/visits` | 방문 기록 조회 |

### 병원 관리 (`/api/hospitals`)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 병원 목록 |
| GET | `/{hospital_id}` | 병원 상세 |
| POST | `/` | 병원 등록 |

### 스케줄러 (`/api/scheduler`)

| Method | Path | 설명 |
|--------|------|------|
| POST | `/run/{hospital_code}` | 수동 크롤링 실행 (Celery 태스크) |
| POST | `/run-all` | 전체 병원 크롤링 실행 |
| GET | `/task/{task_id}` | 태스크 상태 조회 |
| GET | `/status` | 스케줄러 상태 + 워커 현황 |

### 알림 (`/api/notifications`)

| Method | Path | 설명 |
|--------|------|------|
| WebSocket | `/ws` | 실시간 알림 (`?user_id=mr_001`) |
| GET | `/` | 알림 목록 조회 |
| POST | `/{notification_id}/read` | 알림 읽음 처리 |
| POST | `/read-all` | 전체 알림 읽음 |
| GET | `/status` | 알림 시스템 상태 |
| POST | `/test` | 테스트 알림 발송 |

### 헬스체크

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 서비스 상태 + WebSocket 연결 수 |
| GET | `/health` | 헬스체크 |

## DB 모델

| 모델 | 설명 |
|------|------|
| **Hospital** | 병원 정보 (코드, 주소, 연락처, 크롤러 타입) |
| **Doctor** | 의료진 (소속 병원, 진료과, 직책, 전문분야, visit_grade) |
| **DoctorSchedule** | 요일별 진료 일정 (월~일, 오전/오후/저녁) |
| **DoctorDateSchedule** | 날짜별 진료 일정 (진료/휴진/대진 상태) |
| **ScheduleChange** | 일정 변경 이력 (변경 유형, 이전/이후 일정) |
| **VisitLog** | 방문 기록 (성공/부재/거절/예정, 제품, 메모) |
| **CrawlLog** | 크롤링 실행 로그 (성공/실패, 소요 시간) |

### 방문 등급 (visit_grade)

| 등급 | 주기 | 설명 |
|------|------|------|
| **A** | 주 1회 | 핵심 교수 |
| **B** | 격주 | 등록된 교수 (내 교수로 등록 시 기본값) |
| **C** | 월 1회 | 관심 교수 |
| **None** | - | 탐색용 (크롤링으로 발견된 교수) |

## 자동 스케줄러 (Celery Beat)

| 스케줄 | 주기 | 태스크 |
|--------|------|--------|
| `crawl-all-hospitals-daily` | 매일 03:00 KST | 전체 29개 병원 크롤링 |
| `check-schedule-changes` | 30분 간격 | 등록된 교수 일정 변경 감지 |

큐 라우팅: `crawl` 큐 (크롤링), `notify` 큐 (알림)

> Celery/Redis 미연결 시 스케줄러 API는 동기 방식으로 폴백 실행됩니다.

## 설정

`app/config.py`에서 관리하며 `.env` 파일을 지원합니다.

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./pharma_scheduler.db` | DB 연결 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 연결 |
| `CRAWL_INTERVAL_HOURS` | `24` | 크롤링 주기 (시간) |
| `CRAWL_TIME` | `03:00` | 자동 크롤링 시각 (KST) |
| `CRAWL_REQUEST_DELAY` | `1.0` | 요청 간 딜레이 (초) |
| `CRAWL_MAX_RETRIES` | `3` | 실패 시 재시도 횟수 |
| `CRAWL_TIMEOUT` | `30` | 요청 타임아웃 (초) |
| `WEBSOCKET_HEARTBEAT` | `30` | WebSocket 하트비트 (초) |

## 새 병원 크롤러 추가 방법

1. `app/crawlers/`에 `{hospital}_crawler.py` 생성
2. 그룹이 있으면 base 상속 (`cmc_base.py`, `kumc_base.py`)
3. `crawl_doctor_list()`, `crawl_doctor_schedule()` 메서드 구현
4. `factory.py`의 `_DEDICATED_CRAWLERS`에 등록
5. `seed.py`의 `SEED_HOSPITALS`에 병원 정보 추가
6. `factory.py`의 `_HOSPITAL_REGION`에 지역 정보 추가

## 테스트

```bash
# Mock 기반 통합 테스트
python tests/test_integration.py

# 실제 크롤링 PoC (네트워크 필요)
python tests/test_poc_crawl.py

# v2 통합 테스트
python tests/test_v2_integration.py
```

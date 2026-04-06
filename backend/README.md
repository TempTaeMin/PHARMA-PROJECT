# 💊 PharmScheduler - Backend MVP

제약 영업사원(MR)을 위한 교수 진료일정 크롤링 & 스케줄 관리 API

## 기술 스택
- **Backend**: Python FastAPI
- **크롤링**: httpx + BeautifulSoup (+ Playwright 확장 예정)
- **DB**: SQLAlchemy + SQLite (MVP) → PostgreSQL (운영)
- **비동기**: Python asyncio

## 프로젝트 구조
```
pharma-scheduler/
├── app/
│   ├── main.py              # FastAPI 앱 엔트리포인트
│   ├── api/
│   │   ├── crawl.py          # 크롤링 API 라우터
│   │   └── doctors.py        # 의료진 관리 API 라우터
│   ├── crawlers/
│   │   ├── base.py           # 크롤러 기본 인터페이스
│   │   ├── factory.py        # 크롤러 팩토리 (병원별 매핑)
│   │   └── asan_medical.py   # 서울아산병원 크롤러
│   ├── models/
│   │   ├── database.py       # SQLAlchemy 모델
│   │   └── connection.py     # DB 연결 설정
│   └── schemas/
│       └── schemas.py        # Pydantic 스키마
├── tests/
│   ├── test_poc_crawl.py     # 실제 크롤링 PoC 테스트
│   └── test_integration.py   # Mock 기반 통합 테스트
└── requirements.txt
```

## 빠른 시작

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn app.main:app --reload --port 8000

# API 문서 확인
open http://localhost:8000/docs
```

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/crawl/hospitals` | 지원 병원 목록 |
| GET | `/api/crawl/departments/{code}` | 진료과 목록 |
| POST | `/api/crawl/run/{code}` | 크롤링 실행 |
| GET | `/api/crawl/doctor/{code}/{staffId}` | 의료진 개별 크롤링 |
| GET | `/api/doctors/` | 의료진 목록 |
| POST | `/api/doctors/` | 의료진 등록 |
| GET | `/api/doctors/{id}` | 의료진 상세 |
| POST | `/api/doctors/{id}/visits` | 방문 기록 등록 |

## 새 병원 크롤러 추가 방법

1. `app/crawlers/` 에 `{hospital}_crawler.py` 생성
2. `BaseCrawler` 상속 후 3개 메서드 구현
3. `factory.py`의 `CRAWLER_REGISTRY`에 등록

## 테스트

```bash
# 통합 테스트
python tests/test_integration.py

# 실제 크롤링 PoC (네트워크 필요)
python tests/test_poc_crawl.py
```

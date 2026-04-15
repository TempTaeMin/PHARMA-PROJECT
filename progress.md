# PharmScheduler — 진행 현황

> MR 방문 스케줄링 & 교수 크롤러 플랫폼. 이 문서는 세션 간 컨텍스트 복구용이다.
> 최초 진입 시 이 파일 → `backend/README.md` → 관련 코드 순으로 읽는다.

---

## 프로젝트 개요

- **Frontend**: React + Vite (`frontend/`), state 기반 페이지 전환 (React Router 미사용)
- **Backend**: FastAPI + SQLAlchemy async (`backend/app/`), SQLite (`pharma_scheduler.db`)
- **주요 기능 영역**
  1. 대시보드 — 월간 방문 캘린더, 일정 추가/완료/AI 정리
  2. 교수 탐색/내 교수 — 병원/진료과별 교수 그레이딩(A/B/C)
  3. 메모/회의록 — Claude Haiku 기반 AI 정리(`services/ai_memo.py`)
  4. 학회 일정 — Academic crawlers
  5. 병원 크롤러 — 30+ 병원별 playwright/HTTP 크롤러 (`crawlers/`)
- **네비게이션**: `App.jsx` 의 `page` state (`setPage`) 로 조건부 렌더. 대시보드는 페이지 진입 시마다 **unmount→mount** 된다.
- **캐시**: `frontend/src/api/cache.js` SWR 패턴, TTL 2분. `useCachedApi` 로 래핑.

---

## 2026-04-15 세션 — 완료된 수정

### UX 버그 픽스 (dashboard/memo)
1. **대시보드 + 버튼 날짜 기본값** — `PersonalEventEditor.jsx`, `SelectMeetingTime.jsx` 에 `open` 이 `true` 가 될 때 `initialDate` / 시간 / 메모 필드를 리셋하는 `useEffect` 추가. 이전엔 `useState(initialDate)` 가 마운트 시에만 실행되어 state 가 잔존 → 오늘 날짜가 남아 있었음.
2. **메모 상세 탭 기본값** — `MemoDetail.jsx:26` 초기값을 `'raw'` 로 변경, `useEffect([memo?.id, hasAi])` 로 `hasAi ? 'ai' : 'raw'` 동기화. AI 정리 없으면 원본 우선, 생성되면 자동 AI 탭.
3. **대시보드 즉시 반영** — `Dashboard.jsx` 에 `useEffect(() => refresh(), [])` 추가. `App.jsx` 가 `page === 'dashboard'` 분기로 조건부 렌더하므로 페이지 복귀 시 재마운트 → `useMonthCalendar` 캐시 무효화 → 최신 `visit.ai_summary` 반영.
4. **메모 필터 기본 ON** — `Memos.jsx:53` `showFilters = useState(true)`.
5. **메모 기간 필터 기본 = 오늘** — `todayYMD()` 헬퍼 추가, `fromDate`/`toDate` 초기값으로 사용.
6. **완료 방문 클릭 시 AI 정리 우선 노출** — `VisitDetailModal.jsx` 에 `AI 정리 / 원본` 탭 UI 추가. `visit.ai_summary` 파싱, 완료 상태(`!isPlanned`) + `hasAi` 조건에서만 탭 노출. AI 탭은 `title` + `summary` 필드별 구조화 렌더, 원본 탭은 기존 `notes` textarea 유지.

### 학회 일정 개선 — 동기화 실패 + 인앱 상세 뷰
7. **동기화 실패 원인 & 픽스** — `/api/academic-events/sync` 가 `crawl_academic_events.delay()` (Celery) 를 호출하던 것이 문제. 로컬에서 Redis/worker 가 안 떠 있으면 `.delay()` 자체가 ConnectionRefused → 500 → 프론트 "실패". **해결**: 엔드포인트를 FastAPI `BackgroundTasks` 로 인라인 실행하게 변경 (`api/academic.py`). Celery 와 무관하게 `_crawl_events_async()` 를 직접 호출. Beat 스케줄은 유지.
8. **AcademicEvent 컬럼 4개 추가** — KMA 크롤러가 이미 추출하지만 버려지던 필드를 저장:
   - `sub_organizer` (주관)
   - `region` (지역)
   - `event_code` (교육코드)
   - `detail_url_external` (비고의 외부 URL — 학회 자체 페이지)
   - `models/database.py`, `tasks/academic_tasks.py` (sync 저장), `api/academic.py` (`_event_to_dict`) 모두 반영.
   - 마이그레이션: `backend/scripts/add_academic_detail_columns.py` 한 번 실행.
9. **인앱 상세 모달** — `components/AcademicEventModal.jsx` 신규. 카드 클릭 시 외부 이동 대신 모달 열기. 필드 행: 일정 / 장소+지역 / 주최 / 주관 / 분야 / 교육코드 / 비고. 맨 아래 "원본 사이트에서 자세히 보기" 버튼 1개 — `detail_url_external` 우선, 없으면 KMA `url` fallback. `pages/Conferences.jsx` 의 카드 `<a href>` 제거, `onClick={setSelectedEvent}` + `ChevronRight` 아이콘으로 교체. 사용자 원칙: "모든 정보 조회는 앱 안에서" 준수.
10. **단건 조회 엔드포인트** — `GET /api/academic-events/{id}` 추가 (상세 모달용 fallback, 현재는 리스트 응답으로 충분하지만 미래 확장 대비).

### 관련 플랜
- `C:\Users\ParkNam\.claude\plans\wiggly-waddling-knuth.md` — 1~5번 픽스 + 학회 모달 강사진 매칭 플랜 (이미 적용됨)

### 학회 동기화 실패 재발 — Pydantic Settings `.env` 충돌 (2차 픽스)
17. **증상**: 7번에서 Celery→BackgroundTasks 로 전환했는데도 동기화 버튼이 다시 "실패" 표시. 엔드포인트 자체는 `{"status": "dispatched"}` 만 리턴하는 구조라 500 이 날 수 없어야 정상.
   - **원인**: 핸들러 첫 줄의 lazy import `from app.tasks.academic_tasks import _crawl_events_async` 가 체인 로드 시 `celery_app.py` → `settings = get_settings()` → `Settings()` 생성자까지 타고 들어감. pydantic-settings v2 는 `.env` 파일을 읽는데 `.env` 에 `ANTHROPIC_API_KEY` 가 있고, `Settings` 클래스엔 해당 필드가 없음. v2 기본값이 `extra="forbid"` 라서 `ValidationError: Extra inputs are not permitted` 발생 → FastAPI 500 → 프론트 "실패".
   - 왜 이전에 못 잡았나: 7번에서 BackgroundTasks 전환만 했고 end-to-end 검증은 안 했음. 이후 `ai_memo.py` + `.env` 에 `ANTHROPIC_API_KEY` 가 추가되면서 표면화.
   - **픽스**: `backend/app/config.py:32-35` 의 inner `Config` 에 `extra = "ignore"` 한 줄 추가. `ANTHROPIC_API_KEY` 는 `services/ai_memo.py` 가 `os.getenv()` 로 직접 읽으므로 Settings 필드가 될 필요 없음. 향후 외부 툴이 `.env` 에 키를 더 추가해도 안전.
   - **검증**: `cd backend && python -c "from app.tasks.academic_tasks import _crawl_events_async; print('ok')"` → `ok` 출력 확인됨. 백엔드 재시작 후 동기화 버튼 테스트 필요.

### 학회 모달 강사진 필터 — 내 교수만
19. **매칭된 내 교수 강사만 노출** — `AcademicEventModal.jsx` 의 강사진 섹션이 전체 강사를 다 뿌리던 것을 `matched_doctor_id` 가 있는 항목으로 필터. 섹션 타이틀도 `"강사진"` → `"내 교수 강사진"` 으로 변경. 원본에 강사가 있지만 매칭이 하나도 없을 땐 `"내 교수로 등록된 강사가 없습니다"` 안내. 원본 강사가 아예 없거나 로딩 전이면 섹션 숨김. 백엔드 enrich 로직(`api/academic.py:_enrich_lectures_with_doctors`) 은 그대로 사용.

### 교수 탐색 통합 검색 (BrowseDoctors)
18. **병원 선택 전에 교수 이름 검색 가능** — 기존엔 병원을 먼저 클릭해야 그 병원 내에서만 교수 검색이 되던 구조. 병원 목록 화면의 검색 입력이 이제 병원명과 교수명을 동시 매칭.
    - **Backend**: `api/crawl.py` 에 `GET /api/crawl/search-doctors?q=...` 신규. `Doctor ⨝ Hospital` 조인, `Doctor.name.contains(q)` 로 활성 교수만 최대 50명 반환. 응답에 `hospital_code`/`hospital_name` 포함.
    - **Frontend**: `api/client.js` 에 `crawlApi.searchDoctors(q)` 추가. `pages/BrowseDoctors.jsx` 의 병원 목록 화면에서 `hospitalSearchQ` 변화에 debounce(250ms) `useEffect` 로 전역 교수 검색 실행. 검색 모드일 때 "병원" / "교수" 두 섹션을 상하로 표시. 교수 카드 클릭 시 `openDoctorFromGlobal()` 이 해당 병원을 선택한 뒤 미리보기 패널을 자동 오픈 → 바로 "진료시간 가져오기" / "내 교수로 등록" 가능.
    - 플레이스홀더도 `"병원명 검색"` → `"병원명 또는 교수 이름 검색"` 으로 변경.

### 학회 모달 추가 개선 (같은 세션 후속)
11. **비고 블록 제거** — `AcademicEventModal.jsx` 에서 `event.description` 비고 박스 삭제. 참가비/결제 안내라 MR 이 볼 가치 없음.
12. **지역 독립 행** — 기존 `장소` 행에 inline 으로 붙던 region 을 `<MapPin/> 지역` 독립 Row 로 분리. `장소` 가 없어도 `지역` 만 단독 노출.
13. **KMA 강의 프로그램 크롤링** — `kma_edu_crawler._parse_lectures()` 신규. `table.scheduleList` 에서 {time, title, lecturer, affiliation} 추출, 강사 비어 있으면 skip (개회사/폐회사 행). probe 스크립트 `backend/scripts/probe_kma_program.py` 로 HTML 구조 확인 완료 (6열: 구분/월·일/시간/강의제목/강사/소속).
14. **`lectures_json` 컬럼** — `AcademicEvent.lectures_json = Column(Text)` 추가, JSON 배열 저장. 정규화 대신 JSON 컬럼 선택 (이벤트 종속, 필터/검색 필요 없음, 렌더용). 마이그레이션: `backend/scripts/add_academic_lectures_column.py`. `academic_tasks._crawl_events_async` 의 create/update 분기 둘 다 `json.dumps(e["lectures"] or [], ensure_ascii=False)` 저장.
15. **강사 ↔ 내 교수 매칭 (읽기 시점)** — `api/academic.py` 에 `_normalize_name`(직위 suffix 제거 regex) + `_enrich_lectures_with_doctors()` 추가. `GET /academic-events/{id}` 단건 응답에서만 enrich, 리스트 응답은 skip(성능). 로직: visit_grade in (A,B,C) 범위에서 정규화 이름 완전일치 조회 → 단일 후보면 매칭, 다수면 `affiliation` 문자열에 병원 별칭 최장매치로 좁힘, 여전히 모호하면 매칭 포기.
    - **`HOSPITAL_ALIASES` 테이블** (28개 병원): "울산의대" → `서울아산병원`, "고려의대" → `고대안암병원`(flagship), "연세의대" → `세브란스병원`(flagship), "서울의대" → `서울대학교병원`, "가톨릭의대" → `서울성모병원`(flagship), "성균관의대" → `삼성서울병원` 등. 여러 병원을 가진 학교의 school-level 약칭은 본원에만 배정.
    - **`_alias_match()` 최장매치 로직**: affiliation 안에서 alias list 를 모두 시도, 가장 긴 매치(동점은 더 앞쪽 pos) 를 반환. 글로벌 최장매치로 승자 결정 → `분당서울대병원` 은 `서울대병원`(5자) vs `분당서울대`(5자) tie 에서 earlier pos 인 SNUBH 가 이김, `강남세브란스병원` 은 `세브란스병원`(6자) vs `강남세브란스병원`(8자) 에서 GANSEV 가 이김.
16. **모달 강사진 섹션 + 네비게이션** — `AcademicEventModal` 이 `open` 될 때 `academicApi.getById(id)` 호출해 enriched 이벤트 fetch (`client.js:academicApi.getById` 신규). 강사진 리스트 렌더, 매칭된 강사는 그레이드별 색상 뱃지(A 빨강 / B 주황 / C 파랑) + 전체 행 클릭 시 `onNavigateDoctor(doctor_id)` → `Conferences` 가 `onNavigate('my-doctors', { doctorId })` 호출. `App.jsx` 에서 `<Conferences onNavigate={navTo}/>` + `<MyDoctors initialDoctorId={pageProps.doctorId}/>`. `MyDoctors` 에 `useEffect(() => { if (initialDoctorId) openDetail({id: initialDoctorId}) }, [initialDoctorId])` 추가.

### 사용자가 해야 할 액션
- **DB 마이그레이션 2개 실행** (둘 다 idempotent):
  ```bash
  cd backend
  python scripts/add_academic_detail_columns.py   # 1차 세션용 (sub_organizer/region/event_code/detail_url_external)
  python scripts/add_academic_lectures_column.py  # 2차 세션용 (lectures_json)
  ```
- **동기화 버튼 클릭** → 신규 컬럼들과 `lectures_json` 이 채워짐. 기존 레코드는 `external_key` 로 update 되며 `lectures_json` 도 보강됨. KMA 역순 스캔 1500건 + 강사 크롤링이라 수 분 소요 가능.
- **확인**: 학회 카드 클릭 → 비고 안 보임, 지역 독립 행, 강사진 섹션에 시간/제목/강사/소속 표시. visit_grade A/B/C 교수가 강사진에 있으면 뱃지 + 클릭 시 MyDoctors 해당 교수 상세로 이동.

---

## 진행 중 / 미반영 작업 (`git status` 기반)

### 새 파일 (untracked, 커밋 전)
- **Backend**
  - `backend/.env.example` — 환경변수 템플릿
  - `backend/app/api/memos.py` — 메모 CRUD + AI summarize 엔드포인트
  - `backend/app/api/visits.py` — 방문 로그 CRUD
  - `backend/app/services/ai_memo.py` — Claude Haiku 호출 (`organize_memo()`), 동기 블로킹
  - `backend/scripts/fix_visit_tz.py` — 방문 타임존 보정 스크립트
- **Frontend**
  - `frontend/src/components/MemoDetail.jsx`, `MemoEditor.jsx`, `TemplateSettings.jsx`
  - `frontend/src/components/PersonalEventEditor.jsx`, `VisitDetailModal.jsx`
  - `frontend/src/pages/Memos.jsx`
- **기타**
  - `.gitignore` — 루트 gitignore 최초 추가

### 수정된 파일 (unstaged)
- Backend: `app/main.py`, `api/dashboard.py`, `models/*`, `schemas/schemas.py`, `tasks/*`, `pharma_scheduler.db`, `requirements.txt`
- Frontend: `App.jsx`, `api/client.js`, `components/{AddEventBottomSheet,DailySchedule,DoctorScheduleHintPopup,SelectMeetingTime}.jsx`, `hooks/useMonthCalendar.js`, `pages/{Conferences,Dashboard,MyDoctors}.jsx`, `package.json`

### 삭제된 파일
- `backend/app/crawlers/academic/healthmedia_event_crawler.py`

**다음 세션에서 해야 할 것**: 이 변경분들을 논리 단위로 묶어 커밋 — AI 메모 시스템 도입 / 대시보드 UX 픽스 / 크롤러 정리 등으로 분리하는 것이 자연스럽다.

---

## 알려진 이슈 / 백로그

- **병원 로고 보완** — 교수 탐색에서 로고 14곳이 저해상도, SCHBC 1곳 누락. 향후 교체 예정.
- **KBSMC 월간 전환** — 강북삼성병원 주간→월간 스케줄 전환 완료(2026-04-10). 유사 전환을 다른 병원에 적용할 수 있는지 재검토 가능.
- **AI 메모 동기 블로킹** — `/api/memos/{id}/summarize` 가 Claude Haiku 응답을 기다리며 request 를 블록. 길어지면 FastAPI worker 고갈 위험. 백그라운드 태스크(Celery 이미 있음 `tasks/celery_app.py`) 로 이전 검토.
- **캐시 TTL 2분** — 대시보드는 mount 시 refresh 로 해결했지만 Memos/Conferences 등은 stale 데이터가 남을 수 있음. 필요 시 페이지별 동일 패턴 적용.
- **학회 동기화 진행 상황 미노출** — sync 가 BackgroundTasks 로 비동기 실행되므로 완료 시점을 프론트가 알 수 없음. 현재는 2초 후 refresh 로 대충 잡지만, KMA 크롤링이 실제로 수십 초~수 분 걸릴 수 있음. 추후 task_id 기반 polling 엔드포인트 필요.
- **기존 academic_events 행의 신규 필드 백필** — 마이그레이션으로 컬럼만 추가되고 값은 NULL. 동기화 재실행해야 기존 행도 업데이트됨 (sync 로직이 external_key 로 기존 행 업데이트함).

---

## 핵심 파일 맵

### 데이터 흐름 (방문 + 메모)
```
VisitLog (visits.py)
  └─ notes            ← 자유 입력, DailySchedule 카드/VisitDetailModal 원본 탭
  └─ status           ← 예정/성공/부재/거절
VisitMemo (memos.py)
  ├─ raw_memo         ← 방문 완료 시점 입력
  └─ ai_summary       ← JSON { title, summary: { 논의내용, 결과, ... } }
    └─ services/ai_memo.py:organize_memo() 가 Claude Haiku 로 생성
```
`GET /api/dashboard/my-visits` 가 `VisitLog ⟕ VisitMemo` outer join 으로 양쪽을 한 번에 내려준다 (`dashboard.py:162~205`).

### 프론트 컴포넌트 연결
- `pages/Dashboard.jsx` — 대시보드 전체 컨테이너. 완료 모달(`completing` state) 은 여기 있음.
- `components/DailySchedule.jsx` — 일자별 카드 렌더. 399~419 에서 AI 정리 뱃지 표시.
- `components/VisitDetailModal.jsx` — 카드 클릭 시 열리는 상세/수정 모달. 완료 + AI 있으면 AI/원본 탭.
- `components/MemoDetail.jsx` — 메모 페이지 내 상세. 동일한 AI/원본 패턴 + `resummarize` 액션.
- `hooks/useMonthCalendar.js` — `useCachedApi` 로 dashboard summary + my-visits 페칭, `refresh()` 반환.

### 크롤러
- `backend/app/crawlers/factory.py` — 병원별 크롤러 매핑
- `cmc_base.py`, `kumc_base.py` — CMC/KUMC 공용 base
- `playwright_engine.py` — playwright 공유 셋업
- 병원 크롤러 추가/수정 시 `.claude/skills/hospital-crawler` 스킬 참조

---

## 로컬 실행 (참고)

- Backend: `cd backend && python run.py` (또는 `uvicorn app.main:app --reload`)
- Frontend: `cd frontend && npm run dev`
- DB: SQLite 파일 `backend/pharma_scheduler.db` (백업 `*.backup-*.db` 자동 생성)
- 크롤러 단독 실행: `backend/tests/` 아래 개별 테스트 스크립트 참고

---

## 이 문서 사용법

- 새 세션 시작 시 **이 파일부터 읽는다.** "지금 뭐 하고 있었지?" 의 진입점.
- 의미 있는 진행/수정 단위마다 이 파일을 갱신한다 — 특히 "완료된 수정" / "진행 중" / "백로그" 섹션.
- 상세 플랜은 별도 파일(`.claude/plans/*.md`) 에 두고 여기서는 포인터만 유지.
- 긴 히스토리가 쌓이면 날짜별 세션 섹션으로 분리, 오래된 완료 항목은 요약해서 압축.

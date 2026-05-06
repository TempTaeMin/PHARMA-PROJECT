# MediSync — 진행 현황

> MR 방문 스케줄링 + 교수 크롤러 플랫폼. 이 문서는 세션 간 컨텍스트 복구용.
> 최초 진입 시 이 파일 → `backend/README.md` → 관련 코드 순으로 읽는다.
> 압축 정책: 최근 3개 세션은 verbatim, 1주 이상 된 세션은 한 줄 요약. 상세는 `git log` / `git blame`.

---

## 프로젝트 개요

- **Frontend**: React + Vite (`frontend/`), state 기반 페이지 전환 (React Router 미사용 — `App.jsx` 의 `page` state)
- **Backend**: FastAPI + SQLAlchemy async (`backend/app/`), 운영 Postgres 16 / 로컬 SQLite (`pharma_scheduler.db`)
- **인증**: Google OAuth (1.0). 가입 시 1인 팀 자동 생성
- **주요 기능 영역**
  1. 대시보드 — 월간 방문 캘린더, 일정 추가/완료/AI 정리
  2. 교수 탐색 / 내 교수 — 병원·진료과별 교수 그레이딩(A/B/C, 사용자별)
  3. 메모 / 회의록 — `services/ai_memo.py` Gemini Flash 기반 정리
  4. 학회 일정 — academic crawler + 강사 ↔ 내 교수 매칭
  5. 병원 크롤러 — 80+ 병원, `crawlers/factory.py` 매핑
- **캐시**: `frontend/src/api/cache.js` SWR 패턴, TTL 2분, `useCachedApi` 로 래핑
- **PWA**: manifest + sw.js + icons 완비, 모바일 베타 테스터에게 `PwaInstallHint` 로 설치 안내
- **베타 배포**: `medisync.co.kr` (가비아 Gen2 / Docker Compose v2 / Caddy 자동 HTTPS)

---

## 운영 인프라 정보

| 항목 | 값 |
|---|---|
| 서버 | 가비아 Gen2 Standard 2vCore/2GB, IP `139.150.81.16` |
| OS | Ubuntu 22.04 LTS |
| 도메인 | `medisync.co.kr` (apex + `www` 둘 다 정상, www→apex 301) |
| SSH 키 | `medisync-key.pem` (프로젝트 루트, gitignore) |
| 코드 위치 | `~/medisync/` (ubuntu 유저) |
| Docker Compose | v2.30.3 plugin |
| Swap | `/swapfile` 2GB (영구) |
| HTTPS 인증서 | Caddy 자동 갱신 (Let's Encrypt) |
| 백업 | `~/medisync/pre-*-backup-*.sql.gz` (수시 추가) |
| Admin 이메일 | `ADMIN_EMAILS=namgiggo1@gmail.com` (env, 피드백 admin 가드) |

---

## 2026-05-06 — 베타 사이클 보강 4종 + DB 스키마 복구 (verbatim)

### 1) 베타 테스터 피드백 채널

- 백엔드: `Feedback` 모델 (id, user_id nullable FK, category bug|suggestion|other, message, page_path, user_agent, handled, created_at) + alembic `e7a2c5b9d1f0_add_feedback_table.py` + `app/api/feedback.py` (POST 누구나, GET/PATCH/DELETE admin)
- admin 가드: env `ADMIN_EMAILS` (쉼표 구분) 와 `current_user.email.lower()` 비교. env 비어있으면 모든 admin 엔드포인트 403 (안전한 default)
- 프론트: `FeedbackModal.jsx` 카테고리 라디오+textarea, 헤더 프로필 dropdown 에 "피드백 보내기" 항목 추가 (App.jsx)
- admin 페이지: `pages/AdminFeedback.jsx` — 필터(미처리/전체/카테고리별), 카드 리스트(작성자/페이지/UA), 처리 토글 + 삭제, summary 뱃지
- 사이드바: `isAdminEmail(currentUser.email)` 일 때만 "피드백 관리" 메뉴 노출, 미처리 카운트 빨간 뱃지 (60초 폴링)

### 2) PWA 설치 안내

- `components/PwaInstallHint.jsx` — 모바일 + 미설치(`display-mode: standalone` 체크) + `localStorage 'medisync-pwa-hint-dismissed' !== '1'` 일 때만 노출. 1.5s 지연
- iOS Safari: 매뉴얼 안내 (공유 → 홈 화면에 추가)
- Android Chrome: `beforeinstallprompt` 캡처 → "지금 설치" 버튼이 직접 prompt 호출. 이벤트 미수신 시 메뉴 안내
- "다시 보지 않기" / "나중에" / X 버튼 — 영구 dismiss 는 localStorage stamp

### 3) 변경사항 안내 모달

- `frontend/public/changelog.json` — `{latest, entries: [{version, date, title, items: [...]}]}`. 배포 때 갱신
- `components/ChangelogModal.jsx` — fetch (`?v=Date.now()` cache-bust) → localStorage `medisync-changelog-last-version` 비교
  - 일치 → no-op
  - last-version 없음 (첫 방문) → silent stamp (변경의 의미 없으므로 모달 안 띄움)
  - 다름 → last-version 보다 새로운 entry 만 모아 모달 표시
- App.jsx 마운트 시 `<ChangelogModal />` 자동 동작, 마우트당 1회

### 4) progress.md 압축 정책

- ~2400 줄 → ~400 줄. 1주 이상 된 세션은 한 줄 요약, 최근 3개만 verbatim
- 거짓 "진행 중 / 미반영 작업" 섹션(4-29 시점 정보) 삭제

### 5) DB 스키마 복구 (★ 중요)

- 증상: 운영에서 의료진 패치 / 메모 관련 엔드포인트가 SQL 단계에서 깨짐 — `column visit_logs.notes_author_id does not exist`
- 원인: 5/6 데이터 마이그 작업 시 누가 `alembic stamp head` 만 돌리고 실제 ALTER 미실행. `b1f3a92d4e6c` (visit_logs 4컬럼) + `c2a8d31f7b9e` (visits_memo UNIQUE) 둘 다 미적용 상태에서 alembic 만 head 표시
- 처리: 백업 → `alembic stamp a0db4d78f885` → `alembic upgrade head` 정상 실행. visit_logs 4컬럼 + visits_memo UNIQUE 적용 확인
- 교훈: 운영 데이터 마이그 시 **stamp 가 아니라 진짜 upgrade** 실행 + 마지막에 `\d <table>` 로 실제 컬럼 확인

### 6) CMC 계열 6개 크롤러 SSL 핸드셰이크 + legacy prefix

- 증상: 서울/은평/여의도/성빈센트/의정부/부천 성모 의료진 진료시간 안 뜸
- 원인 1 (SSL): CMC 서버가 weak RSA signature 만 받는 구형 TLS — Python OpenSSL 기본 SECLEVEL=2 가 WRONG_SIGNATURE_TYPE 으로 끊음. `cmc_base.py` 에 module-level `_SSL_CONTEXT = ssl.create_default_context(); set_ciphers("DEFAULT@SECLEVEL=1")` 만들어 모든 `httpx.AsyncClient` 에 `verify=` 주입
- 원인 2 (legacy prefix): DB 의 옛 external_id 가 `CMC-D...` (CMCSEOUL 도 마찬가지) — `crawl_doctor_schedule` 의 prefix 분리가 `CMCSEOUL-` 만 인식해서 `CMC-` 통째로 dr_no 에 포함 → API 200 OK 지만 빈 배열. fix: `staff_id.split("-", 1)[1]` 로 prefix 무시 + 캐시 룩업도 양쪽 포맷 매칭
- 운영 DB 정규화 SQL: `UPDATE doctors SET external_id = REPLACE(external_id, 'CMC-', h.code || '-') ... WHERE h.code IN (CMC*)` — 574개 정규화

### 7) 5월 6일 사용 중 발견 이슈 6건 일괄 수정

- `_doctor_to_response_dict` 가 async 에서 `doctor.hospital` lazy access 시 MissingGreenlet — try/except 보호 + create/update 응답 직전 selectinload(hospital, linked_doctor.hospital, visit_logs) 로 fresh row 사용. 이직/퇴직/오인등록 + 수동 등록 + 의료진 해제 (visit_grade=null) 셋 다 같은 root cause
- 수동 등록 6명 중복 → 위 fix 의 부산물 (commit 후 응답 500 → 사용자 재시도 → INSERT 누적). 이번 수정으로 차단됨. 운영 DB 의 박유미 6명 + 신도림현대 6개 병원 직접 삭제 완료
- NotificationPanel: width 380 + maxWidth 100vw → 모바일 풀스크린 → `min(380px, 92vw)` 로 변경
- Conferences 카드: 진료과 태그 4개 초과 시 `+N` expandable (DeptChips sub-component)
- ManualDoctorModal: 시간 박스 가로 넘침 → `flex-wrap` + `flex 1 1 220px` + input `minWidth 0` 으로 좁은 폰에서 세로 스택
- Caddyfile: `www.{$DOMAIN}` site block 추가 → apex 301 redirect. Caddy reload "config unchanged" 거부 → restart 로 강제 재파싱

### 8) Samsung 크롤러 공휴일 override + verify_crawler 품질 체크

- `samsung_crawler.SMC_CLOSED_DATES` 오버라이드 — 주간 패턴이 공휴일에 새는 문제 차단
- `verify_crawler.py` C10/C11 추가: 공휴일 열린 일정 / 일정 없고 설명도 없는 의사

### 9) 백엔드 댓글 메타 + 메모 직렬화

- 방문 코멘트 메타(작성자명/개수), 메모 직렬화에 `author_name`/`is_mine`/`is_root` 노출, `raw_memo` 본인만 노출

---

## 2026-05-05 ~ 05-06 — 베타 배포 (가비아 Gen2 + Docker Compose + Caddy HTTPS) + 운영 데이터 마이그 + 모바일 뒤로가기 + PWA (verbatim)

### 인프라 / 도메인 / DNS
- 가비아 클라우드 Gen2 Standard 2vCore/2GB/50GB SSD, Ubuntu 22.04, IP `139.150.81.16`
- 도메인 `medisync.co.kr` (가비아). DNS A `@` + `www` → IP, TTL 600
- 가비아 보안그룹: 22 / 80 / 443. Google OAuth Console 에 운영 redirect URI 추가

### Docker Compose 4서비스
- `db` (postgres:16-alpine) / `api` (FastAPI Playwright) / `frontend` (nginx) / `caddy` (자동 LE)
- Celery 미가동 (수동 `POST /api/scheduler/run/{HOSP}`)
- `Caddyfile` — `/api/*`, `/auth/*`, `/health` → backend, 그 외 → frontend SPA
- `.env.production` (gitignore, scp 업로드) — DB 비번 / SESSION_SECRET 자동 생성

### 빌드 단계 호환성 이슈
- `playwright install --with-deps chromium` 실패 → 베이스 이미지 `mcr.microsoft.com/playwright/python:v1.47.0-jammy` 로 교체
- 프론트 Dockerfile heredoc → `frontend/nginx.conf` 별도 파일
- apt `docker-compose` v1 깨짐 → 공식 v2 plugin 설치 (`/usr/local/lib/docker/cli-plugins/`)
- vite/rolldown OOM → `/swapfile` 2GB

### Seed / Alembic
- `ENABLE_SEED` env 분기 (default true)
- `seed_memo_templates` 가 user_id=1 없으면 skip (OAuth 첫 로그인 전 빈 DB FK 위반 방지)

### dev SQLite → 운영 Postgres 데이터 마이그 (★)
- `backend/scripts/migrate_dev_to_prod.py` — sync SQLAlchemy reflect → ID 보존 INSERT → SEQUENCE 재설정
- 옮긴 마스터: hospitals 146 / doctors 12,599 / doctor_schedules 15,776 / doctor_date_schedules 39,956 / academic_organizers 199 / academic_events 714 / academic_event_departments 1,788 ≈ 71k row
- 옮기지 않음: users / teams / team_members / user_doctor_grades / user_doctor_memos / user_academic_pins / visit_logs / visits_memo / memo_templates / reports / schedule_changes / crawl_logs

### 모바일 뒤로가기 (App.jsx)
- `navTo` 가 `history.pushState` 동기화. URL pathname 도 변경
- popstate 로 page 복원, 사이드바/notif/profile 자동 닫힘
- `pageFromPath()` — 직접 URL / 새로고침 시 첫 segment 로 페이지 결정 (`PAGE_IDS` whitelist)

### PWA
- `manifest.json` (name/standalone/icons 192·512·maskable-512/theme `#0040a1`)
- `sw.js` 최소 PWA 자격 (네트워크 우선, 캐싱 없음 — 베타 단계 새 버전 즉시)
- `frontend/public/icons/` PIL 자동 생성 'M' 로고
- `main.jsx` — `import.meta.env.PROD` 일 때만 SW 등록

### 후속 / 백로그
- API 키 회전 (현재 dev 키 운영 사용)
- pg_dump cron 등록 (`0 2 * * *`)
- Celery 자동 크롤링 도입 결정
- PWA 캐싱 (오프라인 지원)

---

## 2026-05-04 ~ 05-05 — 결과 메모 "댓글" 모델 + raw 누출 fix + 보고서/UX (verbatim)

### 결과 메모 "댓글" 모델 (메인)
배경: 사수+부사수 동행 visit 에서 각자 raw 메모 + AI 정리 보유, AI 는 visit 관계자 전원 노출, raw 는 본인만. 기존 `visit_logs.post_notes` 단일 컬럼 공유로 raw 누출 발생.

| 데이터 | 저장 | 노출 | 쓰기 |
|---|---|---|---|
| raw 결과 메모 | `VisitMemo.raw_memo` (사용자별 row) | 본인만 | 본인만 |
| AI 정리본 | `VisitMemo.ai_summary` | visit 관계자 전원 | 본인만 |

- 마이그: `b1f3a92d4e6c` (visit_logs.notes_author_id 등 4컬럼), `c2a8d31f7b9e` (visits_memo UNIQUE)
- `apply_memo_authorship` / `upsert_my_raw_memo` helper (visits.py)
- VisitDetailModal/MemoDetail/Memos 페이지 댓글형 UI

### Critical 버그 fix
- `_doctor_to_response_dict` 의 lazy-load (5/6 에 다시 발견되어 강화)
- 메모 페이지 페이징 / 카드 다중선택 race
- Dialog 컴포넌트 + 전역 alert/confirm 일관

### 일일 보고서 — 동료 메모 추가 가능
- `Report.source_memo_ids` 가 본인 외 메모도 가능 (visit 관계자 한정)

### 보고서 탭 일일/주간 필터, 기타 작은 변경
- Memos 페이지 sticky 필터 보강

---

## 2026-04-29 — MR 일일/주간 보고서 시스템 + AI 백본 교체 + 메모 UX (verbatim)

### 보고서 시스템 신규 (메인)
- 모델: `Report` (report_type daily|weekly, period_start/end, source_memo_ids JSON, source_report_ids JSON, raw_combined, ai_summary, template_id)
- 라우터: `app/api/reports.py` — CRUD + regenerate + docx 다운로드
- 서비스: `services/ai_memo.summarize_report()` — 메모 합본을 AI 가 일일/주간 보고서로 종합
- 프론트: `pages/Memos.jsx` 보고서 탭, `components/ReportGenerator.jsx` 생성 모달, `components/ReportDetail.jsx` 상세/편집/재정리/docx/삭제

### AI 백본 Claude Haiku → Gemini Flash
- `services/ai_memo._get_gemini_client()` — `gemini-2.5-flash-lite`. Anthropic 키 사용 안 함 (비용 정책)
- 메모 단건 정리 + 보고서 종합 둘 다 Gemini

### 메모 페이지 UX
- 7일 기본 / 다중선택 / sticky filter

---

## 2026-04-20 ~ 2026-04-28 — 한 줄 요약 (압축됨)

### 의료진 라이프사이클 + 캘린더 통일 + 학회 매칭
- **이직·퇴직·오인등록 처리** (4-26): `Doctor.is_active/deactivated_at/deactivated_reason/linked_doctor_id`. is_active=False 시 자동 deactivate. linked_doctor 양방향. 비활성 보기 + 복원 버튼
- **수동 병원/의사 등록** (4-26): `Hospital.source='manual'`, `Doctor.source='manual'`, `external_id='MANUAL-{uuid8}'`. ManualDoctorModal 3단계
- **진료 시간표 캘린더 통일** (4-28): 모든 화면 `ScheduleCalendar` 단일 컴포넌트로 통일
- **의료진 상세 화면 정리** (4-28): 헤더 specialty 제거, 방문 이력·메모 통합 timeline
- **학회 매칭 alias 보강** (4-27): `HOSPITAL_ALIASES` 28개 병원, school-level 약칭 flagship 매핑, `_alias_match()` 글로벌 최장매치
- **학회 진료과 세분화 작업 → 롤백** (4-27): 학회명 키워드 우선 + 데이터 기반 보강 했다가 부작용 커서 롤백. 향후 재시도 시 키워드 + 학회 ID 화이트리스트 병용 필요
- **학회 캐시 무효화 + 내 일정 학회 표시** (4-27): 의료진 변경 시 academic 캐시 invalidate, 카드 뱃지 위치 고정
- **학회 일정 추가 흐름 두 갈래** (4-27): 직접 입력 / 학회 목록에서 선택 (pickMode)
- **사이드바 메뉴 라벨 + "교수→의료진" 통일** (4-27)
- **UX 보강 일괄** (4-26): 일정 흐름 / 학회 필터 / 비활성·복원 / 이직 매칭 / 탐색 수리

### 25개 대학병원 크롤러 1차 (4-23 ~ 4-25)
- Phase 1 정찰 25개 → Phase 2 (PAIKBS + 4개 신규 + SPA/playwright 분류 3개) → 1차 마무리 (재확인 3개 + sandbox 차단 우회)
- sub-agent sandbox DNS 차단 우회 패턴: 메인이 먼저 정찰해 패키지로 넘김
- JNUH/JNUHHS 크롤러 (4-23)

### 학회/메모/일정 시스템 (4-22 ~ 4-23)
- **AI 정리 + 사전/사후 메모 분리** (4-23): `VisitMemo.raw_memo`/`ai_summary` 분리, `services/ai_memo.organize_memo()`
- **학회 일정 재설계** (4-23): 내 교수 매칭 + 모바일 터치 + 내 일정 핀 (`user_academic_pins`/`team_academic_pins`). KMA 강의 프로그램 크롤링 (`lectures_json` JSON 컬럼)
- **업무공지 등록** (4-23): VisitLog 의 announcement 카테고리
- **월간 일정(Schedule) 아젠다 전면 개편 + 학회 수동 추가** (4-22): Schedule.jsx rewrite, 카테고리 라벨 재정비, 학회 수동 추가 플로우
- **학회 일정 데이터 정리 + 기간 필터** (4-22)

### 크롤러 추가 / 수정 (4-20 ~ 4-22)
- **경기/인천 8개 크롤러 추가** (4-22): 엑셀 92~99
- **서울/경기/인천 크롤러 1차 전수 검증 + 버그 픽스** (4-22): 9종 체크, HYUMC 타임아웃 최적화
- **경기 7개 크롤러 일괄 추가** (4-21): 등록 + 1차 검증
- **일산백병원(ISPAIK) 크롤러** (4-20)
- **부천성모병원(CMCBC) 크롤러** (4-20)
- **HYUMC/HYUGR 개별 교수 조회 규칙 #7 위반 수정** (4-20 심야)
- **스케줄 셀 판정 규칙 SKILL.md 반영** (4-20 심야): `_schedule_rules.is_clinic_cell()` 공통화

### 병원 로고 작업 (4-21)
- 17개 → 18개 → 18개 추가 / 고해상도 교체 (3 세션). 17곳 SVG/PNG, 1곳(CMCYD) 구 도메인 cmcsungmo.or.kr 로 대체
- 14곳 저해상도 + SCHBC 1곳 누락은 추후 교체 backlog

---

## 알려진 이슈 / 백로그

- **병원 로고 보완** — 14곳 저해상도, SCHBC 1곳 누락
- **AI 메모 동기 블로킹** — `/api/memos/{id}/summarize` + `/api/reports` 가 Gemini 응답 동기 대기. 보고서가 더 길어 worker 고갈 위험. 백그라운드 태스크(Celery 이미 있음) 이전 검토
- **캐시 TTL 2분** — 대시보드 외 페이지에서 stale 가능. 페이지별 mount-refresh 적용 검토
- **학회 동기화 진행 상황 미노출** — task_id 기반 polling 엔드포인트 필요
- **API 키 회전** — 운영 키와 dev 키 분리 + 회전
- **pg_dump 백업 cron** — 운영 서버에 등록 안 됨
- **Celery 자동 크롤링** — 베타 안정화 후 도입 결정
- **PWA 캐싱** — 현재 네트워크 패스스루. 진짜 오프라인 지원
- **모바일 모달 뒤로가기** — Notif/Sidebar/Profile 도 뒤로가기로 닫히게

---

## 핵심 파일 맵

### 데이터 흐름 (방문 + 메모)
```
VisitLog (visits.py)
  ├─ notes            ← 자유 입력
  ├─ post_notes       ← legacy, 사용 안 함 (VisitMemo 로 이전)
  ├─ notes_author_id  / notes_updated_at         ← 작성자 추적 (5/4 추가)
  ├─ post_notes_author_id / post_notes_updated_at ← (5/4 추가)
  └─ status           ← 예정/성공/부재/거절

VisitMemo (memos.py)
  ├─ raw_memo         ← 본인만 노출
  └─ ai_summary       ← visit 관계자 전원 노출. JSON {title, summary: {...}}
    └─ services/ai_memo.organize_memo() / Gemini Flash (gemini-2.5-flash-lite)
  UNIQUE (visit_log_id, user_id) — 사람당 1개

Report (reports.py) — 일일/주간 종합
  ├─ source_memo_ids / source_report_ids  ← 묶을 원본
  ├─ raw_combined     ← 합본 평문 (감사용)
  └─ ai_summary       ← services/ai_memo.summarize_report()
    └─ /api/reports/{id}/docx — python-docx 워드 다운로드

Feedback (feedback.py) — 5/6 추가
  ├─ user_id (nullable, FK SET NULL)
  ├─ category bug|suggestion|other
  ├─ message + page_path + user_agent
  └─ handled  ← admin 처리 토글
```

### 프론트 컴포넌트 연결
- `pages/Dashboard.jsx` — 대시보드 컨테이너. 완료 모달(`completing` state) 여기
- `pages/AdminFeedback.jsx` — 5/6 추가, admin 전용
- `components/DailySchedule.jsx` — 일자별 카드. AI 정리 뱃지
- `components/VisitDetailModal.jsx` — 카드 상세/수정. AI/원본 탭 + 댓글
- `components/MemoDetail.jsx` — 메모 페이지 상세. AI/원본 + resummarize
- `components/FeedbackModal.jsx` / `PwaInstallHint.jsx` / `ChangelogModal.jsx` — 5/6 추가
- `hooks/useMonthCalendar.js` — `useCachedApi` 로 dashboard summary + my-visits

### 크롤러
- `backend/app/crawlers/factory.py` — 병원별 크롤러 매핑
- `cmc_base.py` (CMC 6병원 공유, SECLEVEL=1 SSL context), `kumc_base.py` (고대 3병원), `eumc_crawler.py` (이대 2병원)
- `_schedule_rules.py` — 셀 판정 (`is_clinic_cell`) 공통
- `playwright_engine.py` — playwright 공유 셋업
- 크롤러 추가/수정 시 `.claude/skills/hospital-crawler` 스킬 참조

### Auth / Admin
- `backend/app/auth/deps.py` — `get_current_user`, `get_my_team_id`
- `backend/app/api/feedback.py` — `_admin_emails()` env 기반 가드
- `frontend/src/App.jsx` — `ADMIN_EMAILS` 상수 (백엔드 env 와 동기화)

---

## 로컬 실행

- Backend: `cd backend && python run.py` (또는 `uvicorn app.main:app --reload`)
- Frontend: `cd frontend && npm run dev`
- DB: 로컬 SQLite `backend/pharma_scheduler.db`. 운영 Postgres 는 `~/medisync/.env.production` 의 DATABASE_URL
- 크롤러 단독 실행: `python backend/scripts/verify_crawler.py [HOSPITAL_CODE]`

---

## 운영 배포 절차 (체크리스트)

```bash
# 로컬에서 git push 후
ssh -i medisync-key.pem ubuntu@139.150.81.16
cd ~/medisync
git pull origin main
docker compose build api frontend         # 코드 변경 있을 때
docker compose up -d api frontend         # 재시작
# 마이그레이션 있을 때 ★ 반드시 진짜 upgrade
docker compose exec -T api alembic upgrade head
# Caddyfile 변경 있을 때
docker compose restart caddy              # reload 가 "config unchanged" 거부 시 restart
# 검증
curl -o /dev/null -w "%{http_code}\n" https://medisync.co.kr/health
docker compose logs api --tail=30
```

**금지**: `alembic stamp head` 만 돌리고 실제 ALTER 안 하는 건 절대 금지. 5/6 시점에서 이걸로 visit_logs 4컬럼 + visits_memo 가 운영에서 깨졌었다.

---

## 이 문서 사용법

- 새 세션 시작 시 **이 파일부터 읽는다** — "지금 뭐 하고 있었지?" 의 진입점
- 의미 있는 진행/수정 단위마다 갱신 — 특히 "최근 세션" / "백로그"
- 1주 이상 지난 세션은 한 줄 요약으로 압축, 상세는 git log/blame
- 새 세션 verbatim 추가 시 가장 위에. 4번째 verbatim 이 생기면 가장 오래된 verbatim 을 한 줄 요약으로 강등

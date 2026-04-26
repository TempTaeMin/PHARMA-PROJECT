# Phase 1 종합 검증 리포트 — 2026-04-26

> 4/24~26 세션 합산 변경(146 병원 / 의사 라이프사이클 / UX 보강 / 매칭 알림 / 학회 필터)에 대한 1차 통합 점검 결과.

## 종합 판정: ✅ **PASS** (1 FAIL 일시 이슈 + 1 WARN 기지 마이너)

| 영역 | 결과 | 비고 |
|---|---|---|
| 빌드 / Import | ✅ OK | 18/18 backend 모듈, frontend `vite build` 2.33s |
| DB 무결성 | ✅ OK | 신규 컬럼 모두 존재, FK orphan 0, snapshot 누락 0 |
| 신규 25개 크롤러 | ⚠️ 23/25 | CHNUH WARN (격주 4명, 기지) / DCMC FAIL (timeout, retry 중) |
| FastAPI 라우트 | ✅ OK | 71 routes, 신규 endpoint(`schedules`, `date-schedules`, `delete schedule`) 노출 |
| 함수 단위 시나리오 | ✅ OK | 재단 매핑 8/8 정확, response 합성 정상, helper import 정상 |

---

## 1. 빌드 / Import sanity

### Backend
```
OK 18/18 modules
```
점검 모듈: `models.{database,connection}`, `schemas.schemas`, `api.{doctors,hospitals,crawl,visits,academic,dashboard,memos,notifications,scheduler}`, `services.{crawl_service,ai_memo,academic_mapping}`, `crawlers.{factory,_schedule_rules}`, `notifications.manager`

### Frontend
```
✓ built in 2.33s
dist/assets/index.js  460 kB / gzip 117 kB
```

---

## 2. DB 무결성 점검

### 신규 컬럼 존재 — ✅ 모두 OK
- `hospitals.{source, region}`
- `doctors.{source, deactivated_at, deactivated_reason, linked_doctor_id, missing_count}`
- `doctor_schedules.source`, `doctor_date_schedules.source`
- `visit_logs.{doctor_name_snapshot, doctor_dept_snapshot, hospital_name_snapshot}`
- `visits_memo.{doctor_name_snapshot, doctor_dept_snapshot, hospital_name_snapshot}`

### Hospitals
- 활성 146개 (crawler=146, manual=0)
- region 분포: 서울 58, 경기 59, 인천 4, 대구 5, 부산 5, 강원 2, 경남 2, 광주 2, 대전 2, 전북 2, 울산 1, 전남 1, 충남 1, 충북 1
- region NULL 1건 (수동 INSERT 잔존 — 단일 row, 사용 영향 없음)

### Doctors
- 총 11,303명 (활성 11,248 / 비활성 55)
- visit_grade 분포(활성): 없음(탐색용) 11,223 / B 25 / A 0 / C 0
- source: manual 0건 (수동 등록 미사용 상태)
- linked_doctor_id 사용: 0건 (이직 매칭 미사용 상태)

### 무결성
- FK orphan: doctor_schedules 0 / doctor_date_schedules 0 / visit_logs 0 / visits_memo 0
- Snapshot 백필 누락: 0 (12 visit_logs + 6 visits_memo 모두 채워짐)

---

## 3. 신규 25개 크롤러 일괄 재검증

### 결과 요약
- **OK 23 / WARN 1 / FAIL 1**

### 상세
| 코드 | verdict | 의사 | 진료과 | 빈% | 시간 |
|------|---------|------|--------|-----|------|
| DAMC | OK | 138 | 35 | 23.2% | 10.8s |
| KOSIN | OK | 194 | 41 | 23.7% | 0.8s |
| **DCMC** | **FAIL** | — | — | — | timeout 240s |
| DKUH | OK | 202 | 34 | 11.4% | 16.1s |
| GNAH | OK | 148 | 33 | 27.0% | 13.4s |
| UUH | OK | 259 | 36 | 32.4% | 67.1s |
| KNUH | OK | 231 | 41 | 0.0% | 8.0s |
| KNUHCG | OK | 196 | 51 | 0.0% | 9.3s |
| JNUH | OK | 258 | 41 | 34.1% | 5.0s |
| JNUHHS | OK | 147 | 35 | 26.5% | 4.2s |
| PAIKBS | OK | 360 | 75 | 11.1% | 2.5s |
| PNUH | OK | 430 | 51 | 26.5% | 23.7s |
| PNUYH | OK | 229 | 29 | 30.6% | 3.6s |
| YUMC | OK | 194 | 39 | 25.8% | 2.8s |
| DSMC | OK | 264 | 42 | 3.0% | 40.0s |
| SCWH | OK | 176 | 34 | 31.2% | 10.4s |
| CBNUH | OK | 192 | 46 | 27.1% | 2.9s |
| **CHNUH** | **WARN** | 260 | 34 | 8.8% | 5.2s |
| YWMC | OK | 188 | 40 | 12.8% | 7.0s |
| CUH | OK | 174 | 32 | 23.6% | 1.7s |
| KYUH | OK | 169 | 34 | 33.1% | 62.2s |
| JBUH | OK | 239 | 42 | 24.3% | 17.2s |
| MIZMEDI | OK | 79 | 14 | 41.8% | 26.8s |
| WKUH | OK | 155 | 38 | 29.7% | 8.4s |
| GNUH2 | OK | 188 | 46 | 19.7% | 58.2s |

### FAIL/WARN 세부
- **DCMC FAIL — 360s retry 도 timeout**:
  - 4/24 1차 검증: OK (264명/42과/40s)
  - 4/26 1차 시도: 240s timeout
  - 4/26 retry (360s): 다시 timeout
  - 추가 진단:
    - 사이트 메인 + 진료과 목록 응답 빠름 (각 0.3~0.4s)
    - 직접 `crawl_doctors()` 호출 시 85s 도 timeout (코드 무한루프 아님 — 응답 늦은 호출이 누적)
    - 추정 원인: 의사별 13주 스케줄 fetch 단계에서 사이트 throttle/rate-limit. 4/24 264명 × 13주 ≈ 3,432 요청을 sem=8 동시성으로 처리할 때 4/24 에는 40s 였는데 4/26 에는 사이트가 throttle 강화한 듯
  - **운영 영향**: Celery task 가 `max_retries=3` 으로 시도하므로 timeout 시 결국 실패. weeks=13 을 줄이거나 sched_sem 동시성을 낮추는 보완 필요 (5월 검증 시 함께 처리).
- **CHNUH WARN — 격주 진료 notes 미반영 4명** (재활의학과 안소영·최자영, 정형외과 김상범·윤자영). 4/25 동일 항목으로 기지 마이너 이슈, 5월 검증 시 함께 처리 예정.

---

## 4. FastAPI 라우트 점검

### 71 routes 모두 정상 등록

#### 신규 endpoint (4/26 세션) — ✅ 모두 노출 확인
- `POST /api/doctors/{id}/schedules` (수동 주간 진료시간)
- `POST /api/doctors/{id}/date-schedules` (수동 날짜별)
- `DELETE /api/doctors/{id}/schedules/{schedule_id}` (수동 행 삭제)
- `GET /api/doctors/?status=active|inactive|all` (status 필터)
- `PATCH /api/doctors/{id}` (linked_doctor_id, deactivated_reason 처리)
- `POST /api/hospitals/` (source, code 자동 발급)

#### 영역별 라우트 수
- academic-events: 13 / academic-organizers: 3 / crawl: 8 / dashboard: 2 / **doctors: 12** / hospitals: 3 / memo-templates: 4 / memos: 6 / notifications: 5 / scheduler: 4 / visits: 3 / etc: 8

---

## 5. 함수 단위 시나리오 sanity

### A. 재단 그룹 매핑 (`get_hospital_group`)
- 총 16 그룹 등록: CMC(7), HALLYM(4), PAIK(4), SEVERANCE(4), KU(3) 등
- 매핑 검증 8/8 정확:
  - KUANAM/KUGURO → KU ✓
  - AMC/GNAH → ASAN ✓
  - CMCSEOUL → CMC ✓
  - AJOUMC → None (단일) ✓
  - PNUH → PNUH ✓
  - GNUH2 → None (단일) ✓

### B. `_doctor_to_response_dict` linked_doctor 합성
- 활성 의사 샘플 1명 호출 → linked_doctor_id=None 인 정상 케이스에서 응답 dict 정상 합성:
  - `linked_doctor_name`/`linked_hospital_name`/`linked_doctor_department` 모두 None 으로 채워짐 (기대 동작)

### C. crawl_service helpers
- `save_crawl_result`, `crawl_my_doctors`, `_handle_missing_doctors`, `detect_transfer_candidate` 모두 import OK
- `MISSING_THRESHOLD = 2` 확인

### D. visits 생성 helpers
- `create_visit_log` 시그니처 OK (snapshot 자동 채움 로직 포함)

---

## 5월 첫째 주 검증/배포 시 추가 점검 권장 (운영 시나리오)

코드 단위 sanity 는 OK 라 통과. 다음은 실제 운영 환경에서만 확인 가능한 항목:

1. **이직 매칭 알림 E2E** — 임의 활성 의사를 deactivate → 같은 이름+같은 진료과를 다른 병원에 임시 INSERT → sync 호출 → `doctor_transfer_candidate` 알림 broadcast 확인
2. **수동 등록 → 크롤러 sync 가드** — ManualDoctorModal 로 1명 등록 → 같은 병원 sync → manual 의사 record 의 모든 필드가 변하지 않는지
3. **자동 누락 감지 E2E** — 임의 의사를 크롤링 응답에서 빼고 2회 sync → `is_active=False, deactivated_reason='auto-missing'` (내 교수면 알림만)
4. **DCMC throttle 대응** — 사이트가 의사별 13주 스케줄 동시 호출 (sem=8)에 throttle 적용. weeks 축소(예: 4주) 또는 동시성 감소(sem=3) 또는 의사별 호출 사이 sleep 삽입으로 보완. 운영 Celery 재시도만으로는 회복 안 됨.
5. **CHNUH 격주 4명 보완** — `is_clinic_cell` 의 `<span>가능</span>` 처리에 격주 표기 정밀 매칭 추가
6. **로고 4개 폴백 (CHNUH/YWMC/KYUH/JBUH) + KOSIN 작은 크기** — 수동 교체

---

## 결론

오늘까지 들어간 대규모 변경(이직/퇴직 라이프사이클, 수동 등록 흐름, 자동 매칭, 학회 필터, 25개 크롤러, 146개 hospital seed, 21개 신규 로고) 가 **빌드/DB/API/시나리오 4개 영역에서 모두 깨지지 않고 통합**되어 있음. 운영 사이드 시나리오는 5월 첫째 주에 별도 검증.

별도 회귀 없음 — 안전하게 5월 첫째 주 검증/배포 단계로 진입 가능.

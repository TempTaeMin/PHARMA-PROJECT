"""미즈메디병원 (Mizmedi Hospital) 크롤러.

병원 공식명: 미즈메디병원 (의료법인 미즈메디의료재단)
홈페이지: https://mizmedi.com
기술: 정적 JSON API (httpx, async)
캠퍼스: 강서(wweb / locationType=2), 강남(sweb / locationType=1) — 단일 코드 MIZMEDI 로 통합 수집

API 구조 (사이트 alldoctors.js + reserve.js 분석):

  1) 의료진 목록
       POST /wweb/main/doctor/list
       body: {"deptCode":"", "locationType": <1|2>}
       → {"list": [{doctorId, doctorName, deptCode, deptKorName, deptPkid,
                    usrId, briefHistory, society, specialCategory,
                    doctorPicture, doctorPictureName, reservable, ...}]}

  2) 의료진 상세 (이미 (1) 의 list 가 충분히 정보를 담고 있어 추가 호출 불필요)
       POST /intro/popup/doctor/info  body: {doctorId, locationType}
       (개별 단독 조회용 fallback 으로만 사용)

  3) 진료스케줄 (월별 1개월씩)
       POST /intro/other/reserve/able/popup/list
       body: {usrId, deptCode, year:"YYYY", month:"MM", day:"DD", locationType}
       → list[item], item 의 holiday=YYYYMMDD, ampmFlag=AM|PM, dayoff!=null 면 휴진,
         clncActFlag='1' 이면 활성 (이 날 진료)
       강남(loc=1) 측 응답이 ~60s 504 timeout 빈발 — 우호적 fallback (빈 일정) 처리.

캠퍼스 구분:
  list 호출에 사용된 locationType 값을 doctor dict 에 저장 → location 필드
    1 → "강남"
    2 → "강서"
  같은 doctorId 가 양쪽 list 에 모두 잡히는 경우는 거의 없으나, 발견 시 별도
  external_id 로 분리한다 (`MIZMEDI-{doctorId}-S` / `-W`).

external_id: `MIZMEDI-{doctorId}` (사이트 내 unique). 양 캠퍼스 중복 의사가 있으면
            `MIZMEDI-{doctorId}-W` 또는 `-S` 로 분리.

스케줄:
  - schedules: 3개월치 date_schedules 를 요일/오전·오후 패턴으로 집계
    (각 요일+슬롯이 1회 이상 활성 → 주간 패턴에 추가)
  - date_schedules: 월별 API 호출 결과를 그대로 매핑
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime
from typing import Optional

import httpx

from app.crawlers._schedule_rules import is_clinic_cell  # noqa: F401  (정책 일관성용)

logger = logging.getLogger(__name__)

BASE_URL = "https://mizmedi.com"
DOCTOR_LIST_URL = f"{BASE_URL}/wweb/main/doctor/list"
DOCTOR_INFO_URL = f"{BASE_URL}/intro/popup/doctor/info"
DOCTOR_SCHEDULE_URL = f"{BASE_URL}/intro/other/reserve/able/popup/list"
DOCTOR_DETAIL_PAGE = f"{BASE_URL}/{{root}}/alldoctors/doctordetail"
DOCTOR_PICTURE_URL = f"{BASE_URL}/upload/doctor/"  # ATM only used for placeholder

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# locationType → (라벨, root prefix)
CAMPUS_BY_LOC = {
    2: ("강서", "wweb"),
    1: ("강남", "sweb"),
}

# 사진 업로드 경로 — alldoctors.js 의 UPLOAD_PATH_*_DOCTOR 에 해당.
# 파일명 = doctorPicture(uuid) + "." + doctorPictureName 의 확장자
UPLOAD_PATH = {
    2: f"{BASE_URL}/upload/wweb/doctor/",
    1: f"{BASE_URL}/upload/sweb/doctor/",
}


class MizmediCrawler:
    """미즈메디병원 크롤러 — JSON API."""

    def __init__(self):
        self.hospital_code = "MIZMEDI"
        self.hospital_name = "미즈메디병원"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Content-Type": "application/json; charset=UTF-8",
            "Referer": f"{BASE_URL}/wweb/alldoctors",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data: Optional[list[dict]] = None

    # ─── httpx ─────────────────────────────────────────────────
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 공용 헬퍼 ─────────────────────────────────────────────
    @staticmethod
    def _strip_html(text: Optional[str]) -> str:
        if not text:
            return ""
        # <li>...</li> / <li/> / <br> 등 단순 정리
        t = re.sub(r"<\s*li\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
        t = re.sub(r"</\s*li\s*>", "", t, flags=re.IGNORECASE)
        t = re.sub(r"<\s*br\s*/?\s*>", "\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    @staticmethod
    def _photo_url(doctor: dict, location_type: int) -> str:
        pic = (doctor.get("doctorPicture") or "").strip()
        name = (doctor.get("doctorPictureName") or "").strip()
        if not pic or not name or "." not in name:
            return ""
        ext = name.rsplit(".", 1)[-1]
        base = UPLOAD_PATH.get(location_type, UPLOAD_PATH[2])
        return f"{base}{pic}.{ext}"

    @staticmethod
    def _profile_url(doctor: dict, location_type: int) -> str:
        root = CAMPUS_BY_LOC.get(location_type, ("강서", "wweb"))[1]
        did = doctor.get("doctorId")
        dpk = doctor.get("deptPkid")
        if not did:
            return ""
        url = f"{BASE_URL}/{root}/alldoctors/doctordetail?doctorId={did}"
        if dpk:
            url += f"&deptPkid={dpk}"
        return url

    @staticmethod
    def _extract_position(brief: str) -> str:
        """briefHistory 첫 줄에서 직책(과장/원장/교수 등) 추출 — 보수적."""
        if not brief:
            return ""
        head = brief.splitlines()[0].strip()[:80] if brief else ""
        # 우선 흔한 직책 키워드만 추출
        for kw in ("원장", "병원장", "부원장", "센터장", "과장", "교수", "전문의"):
            if kw in head:
                # 첫 등장 토큰부터 직책 키워드까지
                m = re.search(rf"([가-힣A-Za-z0-9 ]{{0,12}}{kw})", head)
                if m:
                    return m.group(1).strip()
        return ""

    # ─── 의료진 목록 ──────────────────────────────────────────
    async def _fetch_doctor_list(
        self, client: httpx.AsyncClient, location_type: int,
    ) -> list[dict]:
        try:
            resp = await client.post(
                DOCTOR_LIST_URL,
                json={"deptCode": "", "locationType": location_type},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[MIZMEDI] 의료진 목록 로드 실패 (loc={location_type}): {e}")
            return []
        return data.get("list", []) or []

    # ─── 월별 진료 스케줄 ─────────────────────────────────────
    async def _fetch_month_schedule(
        self,
        client: httpx.AsyncClient,
        usr_id: str,
        dept_code: str,
        location_type: int,
        year: int,
        month: int,
    ) -> list[dict]:
        """1 의사 1 월의 진료 가능 슬롯(AM/PM)을 (date,slot) 튜플로 반환.

        반환: [{"date": "YYYY-MM-DD", "slot": "morning"|"afternoon"}, ...]
        """
        body = {
            "usrId": usr_id,
            "deptCode": (dept_code or "").strip(),
            "year": f"{year:04d}",
            "month": f"{month:02d}",
            "day": "01",
            "locationType": location_type,
        }
        # 강남(loc=1) 측 서버가 504 timeout 빈발 → 짧게 잘라 폴백
        sched_timeout = 18 if location_type == 2 else 8
        try:
            resp = await client.post(DOCTOR_SCHEDULE_URL, json=body, timeout=sched_timeout)
        except (httpx.TimeoutException, httpx.ReadTimeout) as e:
            logger.warning(
                f"[MIZMEDI] schedule timeout {usr_id}/{dept_code} {year}-{month}: {e}"
            )
            return []
        except Exception as e:
            logger.warning(
                f"[MIZMEDI] schedule error {usr_id}/{dept_code} {year}-{month}: {e}"
            )
            return []
        if resp.status_code >= 400:
            # 504 등 — 빈 결과로 폴백
            return []
        try:
            data = resp.json()
        except Exception:
            return []

        out: list[dict] = []
        for item in data.get("list", []) or []:
            if (item.get("clncActFlag") or "") != "1":
                continue
            if item.get("dayoff"):
                continue
            holiday = (item.get("holiday") or "").strip()
            if len(holiday) != 8 or not holiday.isdigit():
                continue
            ampm = (item.get("ampmFlag") or "").strip().upper()
            slot = "morning" if ampm == "AM" else "afternoon" if ampm == "PM" else ""
            if not slot:
                continue
            iso = f"{holiday[0:4]}-{holiday[4:6]}-{holiday[6:8]}"
            out.append({"date": iso, "slot": slot})
        return out

    async def _fetch_three_months(
        self,
        client: httpx.AsyncClient,
        usr_id: str,
        dept_code: str,
        location_type: int,
    ) -> list[dict]:
        """오늘 기준 3개월치 (현재월 포함) 슬롯 수집."""
        if not usr_id or not dept_code:
            return []
        today = date.today()
        months: list[tuple[int, int]] = []
        y, m = today.year, today.month
        for _ in range(3):
            months.append((y, m))
            m += 1
            if m > 12:
                m = 1
                y += 1
        coros = [
            self._fetch_month_schedule(client, usr_id, dept_code, location_type, yy, mm)
            for (yy, mm) in months
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)
        out: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            out.extend(r)
        return out

    # ─── 의사 단위 어셈블 ─────────────────────────────────────
    def _build_doctor_record(
        self, raw: dict, location_type: int, schedule_slots: list[dict],
    ) -> dict:
        location_label, _ = CAMPUS_BY_LOC.get(location_type, ("", "wweb"))
        doctor_id = str(raw.get("doctorId") or "").strip()
        usr_id = (raw.get("usrId") or "").strip()
        dept_code = (raw.get("deptCode") or "").strip()
        dept_name = (raw.get("deptKorName") or "").strip()
        name = (raw.get("doctorName") or "").strip()
        specialty = (raw.get("specialCategory") or "").strip()
        title = (raw.get("title") or "").strip()
        brief = self._strip_html(raw.get("briefHistory"))
        society = self._strip_html(raw.get("society"))
        position = self._extract_position(brief)

        notes_parts: list[str] = []
        if location_label:
            notes_parts.append(f"[캠퍼스] {location_label}")
        if title:
            notes_parts.append(f"[소개] {title}")
        if brief:
            notes_parts.append(f"[약력]\n{brief}")
        if society:
            notes_parts.append(f"[학회/논문]\n{society}")
        notes = "\n\n".join(notes_parts)[:1500]

        # date_schedules
        date_schedules = []
        for s in schedule_slots:
            start, end = TIME_RANGES[s["slot"]]
            date_schedules.append({
                "schedule_date": s["date"],
                "time_slot": s["slot"],
                "start_time": start,
                "end_time": end,
                "location": location_label,
                "status": "진료",
            })

        # weekly schedules — 3개월치 슬롯 중 (요일,슬롯) 별 1회 이상 등장 시 패턴화
        seen: set[tuple[int, str]] = set()
        for s in schedule_slots:
            try:
                dt = date.fromisoformat(s["date"])
            except Exception:
                continue
            seen.add((dt.weekday(), s["slot"]))
        schedules = []
        for (dow, slot) in sorted(seen):
            start, end = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start,
                "end_time": end,
                "location": location_label,
            })

        ext_id = f"MIZMEDI-{doctor_id}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "doctor_id": doctor_id,
            "usr_id": usr_id,
            "dept_code": dept_code,
            "dept_pkid": str(raw.get("deptPkid") or "").strip(),
            "location_type": location_type,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": self._profile_url(raw, location_type),
            "photo_url": self._photo_url(raw, location_type),
            "notes": notes,
            "schedules": schedules,
            "date_schedules": date_schedules,
        }

    # ─── 전체 ──────────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            # 1) 양 캠퍼스 의사 목록
            list_results = await asyncio.gather(
                self._fetch_doctor_list(client, 2),  # 강서
                self._fetch_doctor_list(client, 1),  # 강남
                return_exceptions=True,
            )
            campus_lists: list[tuple[int, list[dict]]] = []
            for loc, r in zip([2, 1], list_results):
                if isinstance(r, Exception):
                    logger.error(f"[MIZMEDI] loc={loc} 목록 예외: {r}")
                    continue
                # 유효 의사만 (doctorId, usrId, deptCode 모두 있는 경우)
                valid = [
                    d for d in r
                    if str(d.get("doctorId") or "").strip()
                    and (d.get("usrId") or "").strip()
                ]
                campus_lists.append((loc, valid))
                logger.info(f"[MIZMEDI] loc={loc} 의사 {len(valid)}명")

            # 2) 의사별 3개월 스케줄 병렬 수집 (양 캠퍼스 합쳐 세마포어 제한)
            sem = asyncio.Semaphore(8)

            async def _enrich(loc: int, raw: dict) -> Optional[dict]:
                async with sem:
                    slots = await self._fetch_three_months(
                        client,
                        usr_id=(raw.get("usrId") or "").strip(),
                        dept_code=(raw.get("deptCode") or "").strip(),
                        location_type=loc,
                    )
                return self._build_doctor_record(raw, loc, slots)

            tasks = []
            for (loc, lst) in campus_lists:
                for raw in lst:
                    tasks.append(_enrich(loc, raw))
            built = await asyncio.gather(*tasks, return_exceptions=True)

        # 3) 중복 처리: 같은 doctorId 가 양 캠퍼스에 모두 잡히면 분리 ID 부여
        by_id: dict[str, list[dict]] = {}
        for r in built:
            if isinstance(r, Exception) or not r:
                continue
            by_id.setdefault(r["doctor_id"], []).append(r)

        out: list[dict] = []
        for did, recs in by_id.items():
            if len(recs) == 1:
                out.append(recs[0])
                continue
            # 충돌 — 캠퍼스 suffix 부여
            for rec in recs:
                suffix = "W" if rec["location_type"] == 2 else "S"
                ext_id = f"MIZMEDI-{did}-{suffix}"
                rec["staff_id"] = ext_id
                rec["external_id"] = ext_id
                out.append(rec)

        self._cached_data = out
        logger.info(f"[MIZMEDI] 총 {len(out)}명 수집 완료")
        return out

    # ─── 진료과 ────────────────────────────────────────────────
    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen: dict[str, str] = {}
        for d in data:
            code = d.get("dept_code", "")
            name = d.get("department", "")
            if code and name and code not in seen:
                seen[code] = name
        return [{"code": c, "name": n} for c, n in seen.items()]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "photo_url", "notes")
        return [{k: d.get(k, "") for k in keys} for d in data]

    # ─── 단독 조회 ────────────────────────────────────────────
    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 1명만 네트워크 요청 (skill 규칙 #7)."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {
                        "staff_id": staff_id,
                        "name": d.get("name", ""),
                        "department": d.get("department", ""),
                        "position": d.get("position", ""),
                        "specialty": d.get("specialty", ""),
                        "profile_url": d.get("profile_url", ""),
                        "photo_url": d.get("photo_url", ""),
                        "notes": d.get("notes", ""),
                        "schedules": d.get("schedules", []),
                        "date_schedules": d.get("date_schedules", []),
                    }
            return empty

        # external_id 파싱: MIZMEDI-{doctorId} 또는 MIZMEDI-{doctorId}-W/-S
        prefix = f"{self.hospital_code}-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        m = re.match(r"^(?P<did>\d+)(?:-(?P<suffix>[WS]))?$", raw)
        if not m:
            return empty
        doctor_id = m.group("did")
        suffix = m.group("suffix")
        candidate_locs: list[int]
        if suffix == "W":
            candidate_locs = [2]
        elif suffix == "S":
            candidate_locs = [1]
        else:
            candidate_locs = [2, 1]  # 강서 우선, 강남 폴백

        async with self._make_client() as client:
            # 1) list 에서 doctorId 매칭 — 양 캠퍼스 병렬 조회로 시간 단축
            target: Optional[dict] = None
            target_loc: Optional[int] = None
            list_results = await asyncio.gather(
                *[self._fetch_doctor_list(client, loc) for loc in candidate_locs],
                return_exceptions=True,
            )
            for loc, lst in zip(candidate_locs, list_results):
                if isinstance(lst, Exception):
                    continue
                for d in lst:
                    if str(d.get("doctorId") or "") == doctor_id:
                        target = d
                        target_loc = loc
                        break
                if target is not None:
                    break

            # 2) list 에 없으면 info popup 으로 폴백 (raw doctorId 만 알 때)
            if not target:
                for loc in candidate_locs:
                    try:
                        resp = await client.post(
                            DOCTOR_INFO_URL,
                            json={"doctorId": doctor_id, "locationType": loc},
                            timeout=10,
                        )
                        resp.raise_for_status()
                        info = resp.json()
                    except Exception as e:
                        logger.warning(
                            f"[MIZMEDI] info 호출 실패 {staff_id} loc={loc}: {e}"
                        )
                        continue
                    if info and info.get("usrId") and info.get("deptCode"):
                        target = info
                        target_loc = loc
                        break

            if not target or target_loc is None:
                logger.warning(f"[MIZMEDI] {staff_id} 정보 조회 실패")
                return empty

            if not target or target_loc is None:
                logger.warning(f"[MIZMEDI] {staff_id} 정보 조회 실패")
                return empty

            usr_id = (target.get("usrId") or "").strip()
            dept_code = (target.get("deptCode") or "").strip()

            slots = await self._fetch_three_months(
                client, usr_id=usr_id, dept_code=dept_code, location_type=target_loc,
            )

        rec = self._build_doctor_record(target, target_loc, slots)
        rec["staff_id"] = staff_id
        rec["external_id"] = staff_id
        return {
            "staff_id": staff_id,
            "name": rec["name"],
            "department": rec["department"],
            "position": rec["position"],
            "specialty": rec["specialty"],
            "profile_url": rec["profile_url"],
            "photo_url": rec["photo_url"],
            "notes": rec["notes"],
            "schedules": rec["schedules"],
            "date_schedules": rec["date_schedules"],
        }

    # ─── 공개 (Crawler 표준) ──────────────────────────────────
    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                photo_url=d.get("photo_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
                date_schedules=d.get("date_schedules", []),
            )
            for d in data
        ]

        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="success" if doctors else "partial",
            doctors=doctors,
            crawled_at=datetime.utcnow(),
        )

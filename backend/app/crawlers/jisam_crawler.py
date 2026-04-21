"""효산의료재단 지샘병원(JISAM) 군포 크롤러

gnuboard CMS. 진료과 목록은 홈페이지 상단 메뉴에 `/bbs/content.php?co_id={code}` 형태.
진료과 페이지 하단에 의사 카드가 있고, 각 의사 상세는
`/doctor/doc_info.php?doctor_no=N` 에 있다.

상세 페이지에는 3개월치 달력 뷰(swiper slides)가 포함되어 있으며 각 날짜 셀에
`<span class='skd_mark mark_1'></span>` (진료) / `mark_2` (축소진료) / `mark_7` (공휴일/휴진) /
빈 셀 (휴진/주말) 마커가 있다. mark_1 / mark_2 를 진료로 취급한다.

external_id: `JISAM-{doctor_no}`
"""
from __future__ import annotations

import re
import ssl
import logging
import asyncio
from datetime import datetime

import httpx
from bs4 import BeautifulSoup


def _build_ssl_context() -> ssl.SSLContext:
    """JISAM 서버는 DH key 가 1024 bit 로 OpenSSL 3 기본 거부. 보안수준 1 로 낮춰 호환."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return ctx

from app.schemas.schemas import CrawlResult, CrawledDoctor

logger = logging.getLogger(__name__)

BASE_URL = "https://www.gsamhospital.com"
HOME_URL = f"{BASE_URL}/"
DETAIL_URL = f"{BASE_URL}/doctor/doc_info.php"

TIME_RANGES = {"morning": ("08:30", "12:30"), "afternoon": ("13:30", "17:30")}

# 진료로 취급할 마커
ACTIVE_MARKS = {"mark_1", "mark_2"}


class JisamCrawler:
    def __init__(self):
        self.hospital_code = "JISAM"
        self.hospital_name = "효산의료재단 지샘병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def _fetch_departments(self, client: httpx.AsyncClient) -> list[tuple[str, str]]:
        """홈페이지 메뉴에서 진료과 co_id 와 이름 추출."""
        resp = await client.get(HOME_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        depts: list[tuple[str, str]] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/bbs/content.php?co_id="]'):
            href = a.get("href", "")
            m = re.search(r"co_id=([^&]+)", href)
            if not m:
                continue
            co_id = m.group(1)
            name = a.get_text(strip=True)
            # 진료과 관련 co_id만 (이름에 '과', '클리닉' 포함하는 것)
            if not name or co_id in seen:
                continue
            # 센터/소개 페이지 제외
            if name in ("진료과", "병원안내", "효산의료재단소개", "지샘병원소개"):
                continue
            if ("과" in name) or ("클리닉" in name) or ("센터" in name):
                seen.add(co_id)
                depts.append((co_id, name))
        return depts

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, co_id: str, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/bbs/content.php?co_id={co_id}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[JISAM] 진료과 {co_id} 조회 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        doctors = []
        seen_no: set[str] = set()
        for a in soup.select('a[href*="/doctor/doc_info.php?doctor_no="]'):
            href = a.get("href", "")
            m = re.search(r"doctor_no=(\d+)", href)
            if not m:
                continue
            doctor_no = m.group(1)
            if doctor_no in seen_no:
                continue
            seen_no.add(doctor_no)

            h2 = a.select_one("h2.name")
            name, position = "", ""
            if h2:
                span = h2.find("span")
                if span:
                    position = span.get_text(strip=True)
                    span.extract()
                name = h2.get_text(strip=True)
            if not name:
                continue

            doctors.append({
                "doctor_no": doctor_no,
                "name": name,
                "position": position,
                "department": dept_name,
                "external_id": f"JISAM-{doctor_no}",
                "profile_url": f"{DETAIL_URL}?doctor_no={doctor_no}",
            })
        return doctors

    async def _fetch_doctor_detail(self, client: httpx.AsyncClient, doctor_no: str) -> dict:
        url = f"{DETAIL_URL}?doctor_no={doctor_no}"
        info = {"specialty": "", "schedules": [], "date_schedules": []}
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[JISAM] 상세 실패 doctor_no={doctor_no}: {e}")
            return info

        soup = BeautifulSoup(resp.text, "html.parser")

        # 전문분야
        clinic_ul = soup.select_one("ul.doc_det_clinic")
        if clinic_ul:
            info["specialty"] = clinic_ul.get_text(" ", strip=True)

        # 달력 스케줄 — swiper-slide 안에 각각 월별 테이블
        date_schedules: list[dict] = []
        day_counts: dict[tuple[int, str], int] = {}
        day_active: dict[tuple[int, str], int] = {}

        for slide in soup.select(".doc_skd_table .swiper-slide"):
            table = slide.select_one("table")
            if not table:
                continue
            trs = table.find_all("tr")
            if len(trs) < 3:
                continue
            # trs[0] = 날짜 (월 N 형태), trs[1] = 오전, trs[2] = 오후
            for row_idx, slot in enumerate(("morning", "afternoon"), start=1):
                if row_idx >= len(trs):
                    continue
                tds = trs[row_idx].find_all("td")
                start, end = TIME_RANGES[slot]
                for td in tds[1:]:  # 첫 td 는 "오전"/"오후" 라벨
                    date_str = td.get("data-date")
                    if not date_str:
                        continue
                    mark_span = td.select_one("span.skd_mark")
                    if not mark_span:
                        continue
                    cls = mark_span.get("class") or []
                    mark = next((c for c in cls if c.startswith("mark_")), None)
                    if not mark:
                        continue

                    is_active = mark in ACTIVE_MARKS
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        continue
                    day_idx = dt.weekday()
                    key = (day_idx, slot)
                    day_counts[key] = day_counts.get(key, 0) + 1
                    if is_active:
                        day_active[key] = day_active.get(key, 0) + 1
                        date_schedules.append({
                            "schedule_date": date_str,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                            "status": "진료",
                        })

        # schedules (요일 패턴) 도출 — 해당 (day, slot) 에서 50% 이상 진료면 포함
        schedules: list[dict] = []
        for key, total in day_counts.items():
            active = day_active.get(key, 0)
            if total >= 2 and active * 2 >= total:
                day_idx, slot = key
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": day_idx,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        info["schedules"] = schedules
        info["date_schedules"] = date_schedules
        return info

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=_build_ssl_context()) as client:
            try:
                depts = await self._fetch_departments(client)
            except Exception as e:
                logger.error(f"[JISAM] 진료과 목록 실패: {e}")
                self._cached_data = []
                return []

            sem_list = asyncio.Semaphore(6)

            async def gather_dept(co_id: str, name: str):
                async with sem_list:
                    return await self._fetch_dept_doctors(client, co_id, name)

            dept_results = await asyncio.gather(*(gather_dept(c, n) for c, n in depts), return_exceptions=True)

            # 중복 제거 (한 의사가 여러 진료과에 노출되면 첫 번째만 유지)
            doctors_map: dict[str, dict] = {}
            for res in dept_results:
                if isinstance(res, Exception):
                    continue
                for d in res:
                    if d["external_id"] not in doctors_map:
                        doctors_map[d["external_id"]] = d
            doctors = list(doctors_map.values())

            sem_detail = asyncio.Semaphore(6)

            async def enrich(d: dict):
                async with sem_detail:
                    detail = await self._fetch_doctor_detail(client, d["doctor_no"])
                    d["specialty"] = detail["specialty"]
                    d["schedules"] = detail["schedules"]
                    d["date_schedules"] = detail["date_schedules"]
                    d["staff_id"] = d["external_id"]
                    d["notes"] = ""

            await asyncio.gather(*(enrich(d) for d in doctors), return_exceptions=True)

        self._cached_data = doctors
        logger.info(f"[JISAM] 크롤링 완료: {len(doctors)}명")
        return doctors

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen, depts = set(), []
        for d in data:
            key = d.get("department") or ""
            if key and key not in seen:
                seen.add(key)
                depts.append({"code": key, "name": key})
        return depts

    async def crawl_doctor_list(self, department: str | None = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d.get("department") == department]
        return [
            {k: v for k, v in d.items() if k not in ("schedules", "date_schedules")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — 상세 페이지 1회 GET (rule #7)."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return d
            return empty

        prefix = f"{self.hospital_code}-"
        doctor_no = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=_build_ssl_context()) as client:
            detail = await self._fetch_doctor_detail(client, doctor_no)
            # 상세 페이지에 이름/진료과/직책 도 있으므로 별도 파싱
            try:
                resp = await client.get(f"{DETAIL_URL}?doctor_no={doctor_no}")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                h2 = soup.select_one("h2.sub_section_title + div h2.name, .doctor_profile h2.name, h2.name")
                name, position, dept = "", "", ""
                if h2:
                    span = h2.find("span")
                    if span:
                        position = span.get_text(strip=True)
                        span.extract()
                    name = h2.get_text(strip=True)
                dept_el = soup.select_one(".doctor_profile .dept")
                if dept_el:
                    dept = dept_el.get_text(strip=True)
            except Exception:
                name, position, dept = "", "", ""

        return {
            "staff_id": staff_id,
            "external_id": staff_id,
            "name": name,
            "department": dept,
            "position": position,
            "specialty": detail["specialty"],
            "profile_url": f"{DETAIL_URL}?doctor_no={doctor_no}",
            "notes": "",
            "schedules": detail["schedules"],
            "date_schedules": detail["date_schedules"],
        }

    async def crawl_doctors(self, department: str | None = None) -> CrawlResult:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d.get("department") == department]

        doctors = [
            CrawledDoctor(
                name=d.get("name", ""),
                department=d.get("department", ""),
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d.get("schedules", []),
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

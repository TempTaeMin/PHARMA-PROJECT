"""성애병원(Sungae Hospital) 크롤러

병원 공식명: 성애병원 (성애의료재단 종합병원, 서울 영등포구 여의대방로53길 22)
홈페이지: h.sungae.co.kr
기술: Spring MVC 정적 HTML (httpx + BeautifulSoup)

구조:
  1) 진료과 목록: /info/timetable.do
       네비게이션 앵커 `a[href*="deptID=SH####"]` 26개.
  2) 진료과별 의사 + 스케줄: /info/timetable.do?deptID=SH####
       단일 테이블, 의사 1명당 2행:
         첫 행 (rowspan=2: 진료과/이름/전문분야/예약): 월~토 오전 셀
         둘째 행: "오후" 라벨 + 월~토 오후 셀
       진료 표시: <img src=".../icon_circle.png"> 존재 → 외래 진료
       빈 셀 → 휴진
       이름 셀 내부 `<a href="/reserve/profile.do?doctorID=DT####">` 에서 의사 ID 추출.
  3) 개별 프로필(선택): /reserve/profile.do?doctorID=DT####

external_id: SUNGAE-{deptID}-{doctorID}
  (deptID 내장으로 개별 조회 시 해당 진료과 페이지만 1회 GET)
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://h.sungae.co.kr"
TIMETABLE_URL = f"{BASE_URL}/info/timetable.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class SungaeCrawler:
    def __init__(self):
        self.hospital_code = "SUNGAE"
        self.hospital_name = "성애병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(TIMETABLE_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SUNGAE] 진료과 목록 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        depts: list[dict] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="deptID=SH"]'):
            href = a.get("href", "")
            m = re.search(r"deptID=(SH\d+)", href)
            if not m:
                continue
            code = m.group(1)
            name = a.get_text(" ", strip=True)
            if code in seen or not name or len(name) > 40:
                continue
            seen.add(code)
            depts.append({"code": code, "name": name})
        return depts

    def _parse_dept_page(self, html: str, dept_code: str, dept_name: str) -> list[dict]:
        """진료과 페이지 파싱 → 의사 리스트 (스케줄 포함)"""
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table")
        if table is None:
            return []

        rows = table.select("tbody tr") or table.select("tr")
        result: list[dict] = []
        i = 0
        while i < len(rows):
            row = rows[i]
            cells = row.select("td, th")
            # 의사 시작 행은 rowspan=2 td 가 맨 앞(진료과)에 있고, 전체 셀 수가 많음
            if not cells or not cells[0].has_attr("rowspan"):
                i += 1
                continue

            # 첫 행 (오전)
            # 셀 구성: [진료과(rs=2), 이름(rs=2), 전문분야(rs=2), 시간(오전), 월, 화, 수, 목, 금, 토, 예약(rs=2)]
            try:
                dept_cell = cells[0]
                name_cell = cells[1]
                specialty_cell = cells[2]
                morning_days = cells[4:10]  # 월~토
            except IndexError:
                i += 1
                continue

            # 이름 + doctorID
            a_tag = name_cell.select_one('a[href*="doctorID=DT"]')
            dr_id = ""
            if a_tag:
                m = re.search(r"doctorID=(DT\d+)", a_tag.get("href", ""))
                if m:
                    dr_id = m.group(1)
            # name 은 a 태그 텍스트 (직책 제외) — "박준식 소아청소년과" 같이 나올 수도 있으니 셀 전체 텍스트에서 이름만 추출
            raw_name = name_cell.get_text(" ", strip=True)
            # 한글 2~4자 이름 추출
            m_name = re.match(r"^([가-힣]{2,4})", raw_name)
            name = m_name.group(1) if m_name else raw_name.split()[0] if raw_name else ""
            # 직책(과장/원장/전문의 등) 추출
            position = ""
            m_pos = re.search(r"(주임과장|부과장|과장|부원장|원장|전문의|교수|진료부장|센터장)", raw_name)
            if m_pos:
                position = m_pos.group(1)

            specialty = specialty_cell.get_text(" ", strip=True)
            dept_display = dept_cell.get_text(" ", strip=True) or dept_name

            # 다음 행(오후) 확인
            afternoon_days: list = []
            if i + 1 < len(rows):
                r2 = rows[i + 1]
                r2_cells = r2.select("td, th")
                # 오후 행 셀: [시간(오후), 월, 화, 수, 목, 금, 토]
                if len(r2_cells) >= 7:
                    afternoon_days = r2_cells[1:7]

            schedules: list[dict] = []

            def mark(cell_list, slot):
                if len(cell_list) < 6:
                    return
                start, end = TIME_RANGES[slot]
                for dow, cell in enumerate(cell_list[:6]):
                    if cell.select_one('img[src*="circle"]'):
                        schedules.append({
                            "day_of_week": dow,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })

            mark(morning_days, "morning")
            mark(afternoon_days, "afternoon")

            if dr_id:
                ext_id = f"{self.hospital_code}-{dept_code}-{dr_id}"
                result.append({
                    "staff_id": ext_id,
                    "external_id": ext_id,
                    "name": name,
                    "department": dept_display,
                    "position": position,
                    "specialty": specialty,
                    "profile_url": f"{BASE_URL}/reserve/profile.do?doctorID={dr_id}",
                    "notes": "",
                    "schedules": schedules,
                    "date_schedules": [],
                    "_dept_code": dept_code,
                    "_dr_id": dr_id,
                })
            i += 2

        return result

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        try:
            resp = await client.get(TIMETABLE_URL, params={"deptID": dept_code})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SUNGAE] {dept_name} 의사 목록 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, dept_code, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            depts = await self._fetch_dept_list(client)
            sem = asyncio.Semaphore(5)

            async def one(dept):
                async with sem:
                    return await self._fetch_dept_doctors(client, dept["code"], dept["name"])

            results = await asyncio.gather(*[one(d) for d in depts], return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                continue
            for d in res:
                if d["external_id"] in all_doctors:
                    continue
                all_doctors[d["external_id"]] = d

        result = list(all_doctors.values())
        logger.info(f"[SUNGAE] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            depts = await self._fetch_dept_list(client)
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — external_id 에 내장된 deptID 로 해당 진료과 페이지만 1회 GET"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                            else d.get(k, [])
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        m = re.match(r"^SUNGAE-(SH\d+)-(DT\d+)$", staff_id)
        if not m:
            return empty
        dept_code, dr_id = m.group(1), m.group(2)

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            try:
                resp = await client.get(TIMETABLE_URL, params={"deptID": dept_code})
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[SUNGAE] 개별 조회 실패 {staff_id}: {e}")
                return empty

        doctors = self._parse_dept_page(resp.text, dept_code, "")
        for d in doctors:
            if d["_dr_id"] == dr_id:
                return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                        else d.get(k, [])
                        for k in ("staff_id", "name", "department", "position",
                                 "specialty", "profile_url", "notes",
                                 "schedules", "date_schedules")}
        return empty

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

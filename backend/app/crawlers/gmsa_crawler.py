"""광명성애병원(Gwangmyeong Sungae Hospital) 크롤러

병원 공식명: 광명성애병원 (성애의료재단 계열, 경기 광명시 디지털로 36)
홈페이지: h.ksungae.co.kr
기술: Spring MVC 정적 HTML (httpx + BeautifulSoup)

성애병원(sungae_crawler.py)과 동일한 사이트 템플릿이며
URL 경로/파라미터/테이블 구조가 그대로 이식되어 있다.

구조:
  1) 진료과 목록: /info/timetable.do
       네비게이션 앵커 `a[href*="deptID=SH####"]` 30여개.
  2) 진료과별 의사 + 스케줄: /info/timetable.do?deptID=SH####
       단일 테이블, 의사 1명당 2행:
         첫 행 (rowspan=2: 진료과/이름/전문분야/예약): 월~토 오전 셀
         둘째 행: "오후" 라벨 + 월~토 오후 셀
       진료 표시: <img src="/images/gm/icon/icon_circle.png"> 존재 → 외래 진료
       빈 셀 → 휴진
       이름 셀 내부 `<a href="/reserve/profile.do?doctorID=DT####">` 에서 의사 ID 추출.
  3) 개별 프로필(선택): /reserve/profile.do?doctorID=DT####

external_id: GMSA-{deptID}-{doctorID}
  (deptID 내장으로 개별 조회 시 해당 진료과 페이지만 1회 GET → SKILL.md 핵심 원칙 #7)
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://h.ksungae.co.kr"
TIMETABLE_URL = f"{BASE_URL}/info/timetable.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class GmsaCrawler:
    """광명성애병원 크롤러

    출처: https://h.ksungae.co.kr/info/timetable.do
    """

    def __init__(self):
        self.hospital_code = "GMSA"
        self.hospital_name = "광명성애병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None

    # ───────────────────────── 내부 헬퍼 ─────────────────────────

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(TIMETABLE_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[GMSA] 진료과 목록 실패: {e}")
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
            # 네비 상단에 "진료시간표" 같은 일반 링크가 deptID 와 함께 붙어있는 경우 필터
            if name in ("진료시간표", "진료안내", "의료진찾기"):
                continue
            seen.add(code)
            depts.append({"code": code, "name": name})
        return depts

    def _parse_dept_page(self, html: str, dept_code: str, dept_name: str) -> list[dict]:
        """진료과 페이지 파싱 → 의사 리스트 (스케줄 포함)"""
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.table_type_01") or soup.select_one("table")
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
                morning_days = cells[4:10]  # 월~토 6칸
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

            # name 은 셀 전체 텍스트 앞부분에서 한글 2~4자 이름만 추출
            raw_name = name_cell.get_text(" ", strip=True)
            m_name = re.match(r"^([가-힣]{2,4})", raw_name)
            if m_name:
                name = m_name.group(1)
            else:
                name = raw_name.split()[0] if raw_name else ""

            # 직책 추출 (선택)
            position = ""
            m_pos = re.search(
                r"(주임과장|부과장|과장|부원장|원장|전문의|교수|진료부장|센터장|진료과장)",
                raw_name,
            )
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
                    text = cell.get_text(" ", strip=True)
                    # 1) 비활성 키워드 우선
                    if any(kw in text for kw in ("휴진", "휴무", "공휴일", "부재", "출장", "학회")):
                        continue
                    # 2) 제외 키워드
                    if any(kw in text for kw in (
                        "수술", "내시경", "시술", "초음파", "조영",
                        "CT", "MRI", "PET", "회진", "실험", "연구",
                    )):
                        continue
                    # 3) 실제 GMSA 는 <img src=".../icon_circle.png"> 로 진료 표시
                    #    + 혹시 몰라 텍스트 마크/진료 키워드도 허용
                    has_circle_img = cell.select_one('img[src*="circle"]') is not None
                    has_clinic_kw = any(kw in text for kw in (
                        "진료", "외래", "예약", "격주", "순환", "왕진",
                        "클리닉", "상담", "투석", "검진",
                    ))
                    has_clinic_mark = any(mk in text for mk in (
                        "●", "○", "◎", "◯", "★", "ㅇ", "◆", "■", "✓",
                    ))
                    if not (has_circle_img or has_clinic_kw or has_clinic_mark):
                        continue
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
            logger.warning(f"[GMSA] {dept_name}({dept_code}) 페이지 실패: {e}")
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
            logger.info(f"[GMSA] 진료과 {len(depts)}개")
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
        logger.info(f"[GMSA] 총 {len(result)}명")
        self._cached_data = result
        return result

    @staticmethod
    def _to_public_dict(d: dict) -> dict:
        """내부 캐시 dict → 공개 응답 dict (언더스코어 prefix 필드 제외)"""
        return {
            k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
            for k in (
                "staff_id", "name", "department", "position",
                "specialty", "profile_url", "notes",
                "schedules", "date_schedules",
            )
        }

    # ───────────────────────── 공개 인터페이스 ─────────────────────────

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
            {k: d[k] for k in (
                "staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "notes",
            )}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — external_id 에 내장된 deptID 로 해당 진료과 페이지만 1회 GET.

        SKILL.md 핵심 원칙 #7 준수: `_fetch_all()` 호출 금지.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 내 캐시가 있으면 그대로 사용 (crawl_doctors 흐름)
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_public_dict(d)
            return empty

        m = re.match(r"^GMSA-(SH\d+)-(DT\d+)$", staff_id)
        if not m:
            logger.warning(f"[GMSA] external_id 파싱 실패: {staff_id}")
            return empty
        dept_code, dr_id = m.group(1), m.group(2)

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            try:
                resp = await client.get(TIMETABLE_URL, params={"deptID": dept_code})
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[GMSA] 개별 조회 실패 {staff_id}: {e}")
                return empty

        doctors = self._parse_dept_page(resp.text, dept_code, "")
        for d in doctors:
            if d["_dr_id"] == dr_id:
                return self._to_public_dict(d)
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

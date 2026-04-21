"""국립중앙의료원(National Medical Center) 크롤러

병원 공식명: 국립중앙의료원
홈페이지: www.nmc.or.kr
기술: 정적 HTML (httpx + BeautifulSoup)

구조:
  1) 진료과 목록: /nmc/medicalDept/deptList → fn_detail('{deptCd}', '{deptNm}')
  2) 진료과별 스케줄: /nmc/fixed/docSchedule/list?deptCd={X}&cntrCd={X}
     - 각 의사는 ul.schedule_info_list > li(또는 동급 li) 단위
     - h3 안에 이름 + <strong>{부서}</strong>
     - a[href*="viewType="] → dcSeq
     - a[onclick*="goReserve('{deptCd}', '{profEmpCd}')"] → profEmpCd
     - table.ver_04 의 tbody td 11개 (월오전, 월오후, ..., 금오후, 토오전)
     - td > div.schedule_resv_box.on → 진료, 없으면 휴진

external_id: NMC-{profEmpCd}  (6자리 숫자)
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.nmc.or.kr"
DEPT_LIST_URL = f"{BASE_URL}/nmc/fixed/docSchedule/list"
SCHEDULE_URL = f"{BASE_URL}/nmc/fixed/docSchedule/list?deptCd={{code}}&cntrCd={{code}}"
DETAIL_URL = f"{BASE_URL}/nmc/medicalDept/deptDetail?typeCd=A&deptCd={{dept}}&cntrCd={{dept}}&viewType={{seq}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# table.ver_04 tbody tr > td 11개 순서
SLOT_MAP_11 = [
    (0, "morning"), (0, "afternoon"),
    (1, "morning"), (1, "afternoon"),
    (2, "morning"), (2, "afternoon"),
    (3, "morning"), (3, "afternoon"),
    (4, "morning"), (4, "afternoon"),
    (5, "morning"),
]

FN_DETAIL_RE = re.compile(r"fn_detail\(\s*'(\d{6,})'\s*,\s*'([^']+)'\s*\)")
GO_RESERVE_RE = re.compile(r"goReserve\(\s*'(\d+)'\s*,\s*'(\d+)'\s*\)")


class NmcCrawler:
    """국립중앙의료원 크롤러 — 진료과별 스케줄 HTML 파싱"""

    def __init__(self):
        self.hospital_code = "NMC"
        self.hospital_name = "국립중앙의료원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data: list[dict] | None = None
        self._cached_depts: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_departments(self, client: httpx.AsyncClient) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[NMC] 진료과 목록 실패: {e}")
            self._cached_depts = []
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        depts: dict[str, str] = {}
        for a in soup.find_all("a", href=re.compile(r"deptCd=\d+")):
            href = a.get("href", "")
            m = re.search(r"deptCd=(\d+)", href)
            if not m:
                continue
            code = m.group(1)
            name = a.get_text(" ", strip=True)
            if code and name and len(name) < 25 and code not in depts:
                depts[code] = name
        result = [{"code": c, "name": n} for c, n in depts.items()]
        logger.info(f"[NMC] 진료과 {len(result)}개")
        self._cached_depts = result
        return result

    def _parse_schedule_table(self, table) -> list[dict]:
        if table is None:
            return []
        tbody = table.find("tbody") or table
        tds = tbody.find_all("td", recursive=True)
        # 첫 번째 tr 의 11개 td 만 취함
        # (일부 페이지는 tbody 안에 tr 1개 이므로 순서대로 처리)
        schedules = []
        for i, td in enumerate(tds[:11]):
            box = td.find("div", class_=re.compile(r"schedule_resv_box"))
            if box is None:
                continue
            classes = box.get("class") or []
            if "on" not in classes:
                continue
            dow, slot = SLOT_MAP_11[i]
            start, end = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start,
                "end_time": end,
                "location": "",
            })
        return schedules

    def _parse_doctor_block(self, li, dept_code: str, dept_name: str) -> dict | None:
        # 이름 + 진료과: schedule_info_txt > p 안
        info_txt = li.find("div", class_=re.compile(r"schedule_info_txt"))
        name_tag = None
        if info_txt:
            name_tag = info_txt.find("p")
        if name_tag is None:
            name_tag = li.find("h3") or li.find("p")
        if name_tag is None:
            return None
        strong = name_tag.find("strong")
        sub_dept = strong.get_text(strip=True) if strong else ""
        if strong:
            strong.extract()
        name = name_tag.get_text(" ", strip=True)
        if not name:
            return None

        # goReserve → profEmpCd
        prof_emp_cd = ""
        for a in li.find_all("a"):
            onclick = a.get("href", "") + " " + (a.get("onclick") or "")
            m = GO_RESERVE_RE.search(onclick)
            if m:
                prof_emp_cd = m.group(2)
                break
        if not prof_emp_cd:
            return None

        # viewType → dcSeq (상세 페이지 URL)
        dc_seq = ""
        detail_link = li.find("a", href=re.compile(r"viewType=\d+"))
        if detail_link:
            m = re.search(r"viewType=(\d+)", detail_link["href"])
            if m:
                dc_seq = m.group(1)

        # 전문분야 — ul 안에 li.schedule_info_subtit "진료분야" 다음 li
        specialty = ""
        if info_txt:
            ul = info_txt.find("ul")
            if ul:
                items = ul.find_all("li", recursive=False)
                for idx, item in enumerate(items):
                    classes = item.get("class") or []
                    if "schedule_info_subtit" in classes and idx + 1 < len(items):
                        specialty = items[idx + 1].get_text(" ", strip=True)
                        break

        table = li.find("table", class_=re.compile(r"ver_04"))
        schedules = self._parse_schedule_table(table)

        ext_id = f"NMC-{prof_emp_cd}"
        profile_url = DETAIL_URL.format(dept=dept_code, seq=dc_seq) if dc_seq else SCHEDULE_URL.format(code=dept_code)

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": sub_dept or dept_name,
            "position": "",
            "specialty": specialty,
            "profile_url": profile_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
            "_dept_code": dept_code,
            "_prof_emp_cd": prof_emp_cd,
            "_dc_seq": dc_seq,
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        try:
            resp = await client.get(SCHEDULE_URL.format(code=dept_code))
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[NMC] {dept_name}({dept_code}) 스케줄 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        doctors: list[dict] = []
        # 의사 블록: div.schedule_resv_box.on 을 가진 li 또는 div.schedule_resv_box 래퍼
        # 페이지 구조상 의사 1명 = 상위 <li> 하나
        seen: set[str] = set()
        for li in soup.find_all("li"):
            # 의사 블록 판별: 안에 goReserve 또는 table.ver_04 존재
            if not li.find("table", class_=re.compile(r"ver_04")):
                continue
            doc = self._parse_doctor_block(li, dept_code, dept_name)
            if not doc:
                continue
            if doc["external_id"] in seen:
                continue
            seen.add(doc["external_id"])
            doctors.append(doc)

        logger.info(f"[NMC] {dept_name}: {len(doctors)}명")
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
            if not depts:
                self._cached_data = []
                return []

            tasks = [
                asyncio.create_task(self._fetch_dept_doctors(client, d["code"], d["name"]))
                for d in depts
            ]
            all_doctors: dict[str, dict] = {}
            for coro in asyncio.as_completed(tasks):
                docs = await coro
                for d in docs:
                    if d["external_id"] not in all_doctors:
                        all_doctors[d["external_id"]] = d

        result = list(all_doctors.values())
        logger.info(f"[NMC] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            return await self._fetch_departments(client)

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
        """개별 교수 조회 — 전 진료과 1회씩 조회해 매칭 (진료과가 미리 특정 불가)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, []) if k in ("schedules", "date_schedules") else d.get(k, "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        # external_id 에 진료과 정보가 없어 전체 진료과를 순회해야 하나,
        # 진료과 페이지 단위 조회로 제한 → 의사별 개별 페이지는 호출하지 않음
        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
            for dept in depts:
                docs = await self._fetch_dept_doctors(client, dept["code"], dept["name"])
                for d in docs:
                    if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                        return {k: d.get(k, []) if k in ("schedules", "date_schedules") else d.get(k, "")
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

"""의정부을지대학교병원(UEMC) 크롤러

홈페이지: www.uemc.ac.kr
※ 노원을지대학교병원(EULJINW, eulji.or.kr)과 동일한 JSP 구조를 공유한다.
   URL/도메인만 다르고 템플릿은 완전히 동일하므로 같은 파싱 로직을 사용한다.

구조:
  진료과 목록: /clinic/clinic_pg04.jsp
  진료과 시간표: /clinic/clinic_pg04.jsp?dept={CODE}
    — `td.line_r` 안 `<a onclick="... doct={ID}">이름</a>`
    — `span > img[src*="bg_clinic_img03.gif"]` = 진료

external_id: UEMC-{deptCode}-{doctId}
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.uemc.ac.kr"
DEPT_LIST_URL = f"{BASE_URL}/clinic/clinic_pg04.jsp"
DEPT_URL_TMPL = f"{BASE_URL}/clinic/clinic_pg04.jsp?dept={{dept}}"
DOCTOR_DETAIL_URL_TMPL = f"{BASE_URL}/clinic/clinic_doc_view01_01.jsp?dept={{dept}}&doct={{doct}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

DOCT_RE = re.compile(r"doct=(\d+)")
DEPT_RE = re.compile(r"dept=([A-Z]+)")
SCHEDULE_IMG_NAME = "bg_clinic_img03.gif"


class UemcCrawler:
    """의정부을지대학교병원 크롤러 — JSP 정적 HTML"""

    def __init__(self):
        self.hospital_code = "UEMC"
        self.hospital_name = "의정부을지대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None
        self._cached_depts: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[UEMC] 진료과 목록 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        seen: dict[str, str] = {}
        for a in soup.select('a[href*="clinic_pg04.jsp?dept="]'):
            m = DEPT_RE.search(a.get("href", ""))
            if not m:
                continue
            code = m.group(1)
            name = a.get_text(strip=True)
            if not name or code in seen:
                continue
            seen[code] = name
        depts = [{"code": c, "name": n} for c, n in seen.items()]
        self._cached_depts = depts
        return depts

    def _parse_dept_table(self, soup: BeautifulSoup, dept_code: str, dept_name: str) -> list[dict]:
        doctors: list[dict] = []
        for table in soup.find_all("table"):
            header_row = table.find("thead")
            if header_row is None:
                continue
            ths = [th.get_text(strip=True) for th in header_row.find_all("th")]
            if not any(t in DAY_INDEX for t in ths):
                continue
            col_to_dow: dict[int, int] = {}
            for ci, t in enumerate(ths):
                if t in DAY_INDEX:
                    col_to_dow[ci] = DAY_INDEX[t]
            if not col_to_dow:
                continue

            tbody = table.find("tbody")
            if tbody is None:
                continue
            rows = tbody.find_all("tr", recursive=False)
            i = 0
            while i < len(rows):
                row = rows[i]
                name_td = row.find("td", class_="line_r")
                if name_td is None:
                    i += 1
                    continue
                anchor = name_td.find("a")
                name = ""
                doct_id = ""
                if anchor:
                    name = anchor.get_text(strip=True)
                    onclick = anchor.get("onclick", "") or ""
                    m = DOCT_RE.search(onclick)
                    if m:
                        doct_id = m.group(1)
                if not name:
                    name = name_td.get_text(" ", strip=True)
                if not name:
                    i += 1
                    continue

                tr_am = row
                tr_pm = rows[i + 1] if (i + 1) < len(rows) else None

                specialty = ""
                td_al = row.find("td", class_="td_al")
                if td_al:
                    for tag in td_al.find_all(["p", "br"]):
                        tag.extract()
                    specialty = td_al.get_text(" ", strip=True)

                schedules: list[dict] = []

                def _iter_slots(tr, slot: str):
                    if tr is None:
                        return
                    cells = tr.find_all("td", recursive=False)
                    info_cells = [td for td in cells if "d_info" in (td.get("class") or [])]
                    if len(info_cells) < 6:
                        return
                    start, end = TIME_RANGES[slot]
                    for di, cell in enumerate(info_cells[:6]):
                        img = cell.select_one(f'img[src*="{SCHEDULE_IMG_NAME}"]')
                        if img is None:
                            continue
                        schedules.append({
                            "day_of_week": di,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })

                _iter_slots(tr_am, "morning")
                _iter_slots(tr_pm, "afternoon")

                profile_url = ""
                if doct_id:
                    profile_url = DOCTOR_DETAIL_URL_TMPL.format(dept=dept_code, doct=doct_id)
                ext_key = f"{dept_code}-{doct_id}" if doct_id else f"{dept_code}-{name}"
                doctors.append({
                    "staff_id": f"UEMC-{ext_key}",
                    "external_id": f"UEMC-{ext_key}",
                    "doct_id": doct_id,
                    "dept_code": dept_code,
                    "name": name,
                    "department": dept_name,
                    "position": "",
                    "specialty": specialty,
                    "profile_url": profile_url,
                    "photo_url": "",
                    "notes": "",
                    "schedules": schedules,
                    "date_schedules": [],
                })

                i += 2 if tr_pm is not None else 1
        return doctors

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, dept: dict) -> list[dict]:
        url = DEPT_URL_TMPL.format(dept=dept["code"])
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[UEMC] {dept['code']} 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_dept_table(soup, dept["code"], dept["name"])

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(5)

            async def job(d):
                async with sem:
                    return await self._fetch_dept_doctors(client, d)

            tasks = [asyncio.create_task(job(d)) for d in depts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        seen: set[str] = set()
        all_docs: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            for d in r:
                if d["external_id"] in seen:
                    continue
                seen.add(d["external_id"])
                all_docs.append(d)

        logger.info(f"[UEMC] 총 {len(all_docs)}명")
        self._cached_data = all_docs
        return all_docs

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            return await self._fetch_dept_list(client)

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
        """개별 교수 조회 — 해당 진료과 페이지만 1회 GET (skill 규칙 #7)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules","date_schedules") else "")
                            for k in ("staff_id","name","department","position",
                                     "specialty","profile_url","notes",
                                     "schedules","date_schedules")}
            return empty

        prefix = "UEMC-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if "-" not in raw:
            return empty
        dept_code, doct_id = raw.split("-", 1)
        if not dept_code or not doct_id:
            return empty

        async with self._make_client() as client:
            dept_task = asyncio.create_task(self._fetch_dept_list(client))
            url = DEPT_URL_TMPL.format(dept=dept_code)
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[UEMC] 개별 조회 실패 {staff_id}: {e}")
                return empty
            depts = await dept_task
            dept_name = next((d["name"] for d in depts if d["code"] == dept_code), "")
            soup = BeautifulSoup(resp.text, "html.parser")
            doctors = self._parse_dept_table(soup, dept_code, dept_name)

        for d in doctors:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id \
                    or (d["doct_id"] == doct_id and d["dept_code"] == dept_code):
                return {k: d.get(k, [] if k in ("schedules","date_schedules") else "")
                        for k in ("staff_id","name","department","position",
                                 "specialty","profile_url","notes",
                                 "schedules","date_schedules")}
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

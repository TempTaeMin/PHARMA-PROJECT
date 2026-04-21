"""보라매병원(Seoul Metropolitan Government - Seoul National University Boramae Medical Center) 크롤러

병원 공식명: 서울특별시 보라매병원 (서울대학교병원 운영)
홈페이지: www.brmh.org
기술: 정적 HTML + XHR (httpx + BeautifulSoup)

구조:
  1) 진료과 목록 XHR: POST /mediteam_manage/comm/MediSelect.ajx
     body: {"code":"","pt_code":"001000000","info_chk":"N"}
     응답: URL-encoded JSON — SOSOK_OPTION 에 <option value='CODE|CODE'>진료과명</option>

  2) 진료과별 의사+스케줄 페이지: GET /custom/doctor_search.do?site=001&medi_type=001000000&medi_sosok={code}|{code}&doctor_order=A
     - 의사 카드: li.doctor_top_right > p.doctor_name — <span>{dept}</span>{이름}
       openDoctorView('{dt_no}', '{code}|{code}', 'view') → dt_no 고유
     - p.doctor_info — 전문분야
     - div.tb_calendar_wrap — 여러 개의 월간 테이블 (첫 번째만 사용)
         table.tb_calendar: thead + tbody
         tbody 안에 tr.amTr (오전) / tr.pmTr (오후) 각각 6개 td (월~토)
         td 안에 img[alt*="일반진료"] 또는 img[alt*="클리닉"] → 외래

external_id: BRMH-{dt_no}  (정수)
"""
import re
import json
import asyncio
import logging
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.brmh.org"
DEPT_AJAX = f"{BASE_URL}/mediteam_manage/comm/MediSelect.ajx"
SEARCH_URL = f"{BASE_URL}/custom/doctor_search.do"
DETAIL_URL = f"{BASE_URL}/custom/popup/layer_doctor_view.do?dt_no={{dt_no}}&medi_code={{code}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

OPEN_DOCTOR_RE = re.compile(r"openDoctorView\(\s*'(\d+)'\s*,\s*'([^']+)'")
OPTION_RE = re.compile(r"<option\s+value='(\d{9})\|(\d{9})'\s*>([^<]+)</option>")
OUTPATIENT_ALT_KEYWORDS = ("일반진료", "클리닉")


class BrmhCrawler:
    """보라매병원 크롤러 — XHR 진료과 목록 + 진료과별 doctor_search.do 파싱"""

    def __init__(self):
        self.hospital_code = "BRMH"
        self.hospital_name = "서울특별시 보라매병원"
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
            resp = await client.post(
                DEPT_AJAX,
                json={"code": "", "pt_code": "001000000", "info_chk": "N"},
                headers={"Content-Type": "application/json; charset=UTF-8"},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[BRMH] 진료과 목록 실패: {e}")
            self._cached_depts = []
            return []

        decoded = urllib.parse.unquote_plus(resp.text)
        try:
            payload = json.loads(decoded)
            options_html = payload.get("SOSOK_OPTION", "")
        except Exception:
            options_html = decoded
        depts: list[dict] = []
        seen: set[str] = set()
        for m in OPTION_RE.finditer(options_html):
            code = m.group(1)
            name = m.group(3).strip()
            if not code or code in seen:
                continue
            seen.add(code)
            depts.append({"code": code, "name": name})
        logger.info(f"[BRMH] 진료과 {len(depts)}개")
        self._cached_depts = depts
        return depts

    def _parse_one_calendar(self, table) -> list[dict]:
        """table.tb_calendar 1개에서 오전/오후 행을 찾아 스케줄 리스트 반환"""
        schedules: list[dict] = []
        if table is None:
            return schedules
        am = table.find("tr", class_=re.compile(r"\bamTr\b"))
        pm = table.find("tr", class_=re.compile(r"\bpmTr\b"))
        for tr, slot in ((am, "morning"), (pm, "afternoon")):
            if tr is None:
                continue
            tds = tr.find_all("td", recursive=False)
            # 6개 요일 셀
            day_tds = tds[:6]
            start, end = TIME_RANGES[slot]
            for i, td in enumerate(day_tds):
                img = td.find("img")
                if img is None:
                    continue
                alt = (img.get("alt") or "").strip()
                if not any(kw in alt for kw in OUTPATIENT_ALT_KEYWORDS):
                    continue
                schedules.append({
                    "day_of_week": i,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _parse_doctor_wrap(self, wrap, dept_code: str, dept_name: str) -> dict | None:
        name_tag = wrap.find("p", class_="doctor_name")
        if name_tag is None:
            return None
        # <p class="doctor_name"><span>{sub_dept}</span>{name}<a onclick="openDoctorView('dt_no', 'code|code', 'view')">자세히 보기</a></p>
        sub_dept = ""
        sub_span = name_tag.find("span")
        if sub_span:
            sub_dept = sub_span.get_text(" ", strip=True)
            sub_span.extract()
        # a 태그 제거 후 남은 텍스트 = 이름
        a_detail = name_tag.find("a")
        if a_detail:
            a_detail.extract()
        name = name_tag.get_text(" ", strip=True)
        if not name:
            return None

        # dt_no 찾기 — wrap 전체에서 openDoctorView 콜
        dt_no = ""
        medi_code = dept_code
        for a in wrap.find_all("a", onclick=True):
            m = OPEN_DOCTOR_RE.search(a.get("onclick", ""))
            if m:
                dt_no = m.group(1)
                medi_code = m.group(2).split("|")[0] or dept_code
                break
        if not dt_no:
            return None

        # 전문분야
        specialty = ""
        info_p = wrap.find("p", class_="doctor_info")
        if info_p:
            specialty = info_p.get_text(" ", strip=True)

        # 스케줄 — 첫 table.tb_calendar
        cal_wrap = wrap.find("div", class_=re.compile(r"tb_calendar_wrap"))
        first_table = None
        if cal_wrap:
            first_table = cal_wrap.find("table", class_=re.compile(r"tb_calendar"))
        schedules = self._parse_one_calendar(first_table)

        ext_id = f"BRMH-{dt_no}"
        profile_url = DETAIL_URL.format(dt_no=dt_no, code=f"{medi_code}|{medi_code}")
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
            "_dt_no": dt_no,
            "_medi_code": medi_code,
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, code: str, name: str
    ) -> list[dict]:
        params = {
            "site": "001",
            "medi_type": "001000000",
            "medi_sosok": f"{code}|{code}",
            "doctor_order": "A",
        }
        try:
            resp = await client.get(SEARCH_URL, params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[BRMH] {name}({code}) 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        doctors: list[dict] = []
        seen: set[str] = set()
        # 의사 카드: doctor_top_right 를 포함하는 상위 컨테이너 — <li class="doctor_top_right"> 의 부모 ul,
        # 그리고 같은 부모 안에 tb_calendar_wrap 이 붙음. 상위 래퍼 탐색.
        for top_right in soup.find_all("li", class_="doctor_top_right"):
            # 적절한 wrap — 가장 가까운 공통 부모(doctor_info_wrap 또는 동급 div)
            wrap = top_right
            for _ in range(8):
                wrap = wrap.parent
                if wrap is None:
                    break
                if wrap.find("div", class_=re.compile(r"tb_calendar_wrap")):
                    break
            if wrap is None:
                continue
            doc = self._parse_doctor_wrap(wrap, code, name)
            if not doc:
                continue
            if doc["external_id"] in seen:
                continue
            seen.add(doc["external_id"])
            doctors.append(doc)

        logger.info(f"[BRMH] {name}({code}): {len(doctors)}명")
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
            if not depts:
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(6)

            async def _one(d: dict) -> list[dict]:
                async with sem:
                    return await self._fetch_dept_doctors(client, d["code"], d["name"])

            tasks = [asyncio.create_task(_one(d)) for d in depts]
            all_doctors: dict[str, dict] = {}
            for coro in asyncio.as_completed(tasks):
                docs = await coro
                for d in docs:
                    if d["external_id"] not in all_doctors:
                        all_doctors[d["external_id"]] = d

        result = list(all_doctors.values())
        logger.info(f"[BRMH] 총 {len(result)}명")
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
        """개별 교수 조회 — 진료과 전체 순회(최대 1회씩) 후 dt_no 매칭

        보라매병원은 external_id(dt_no) 에서 진료과 코드를 역추출할 방법이 없고,
        의사별 단일 상세 페이지는 layer_doctor_view.do 로 스케줄을 포함하지 않으므로
        각 진료과 페이지를 순차 조회한다. (전체 순회이되 매 호출마다 전체 캐시는 남기지 않는다)
        """
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

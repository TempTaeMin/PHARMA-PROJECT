"""강동경희대학교병원 크롤러

구조:
  1) 진료과 목록 JSON API: /api/department/deptCdList.do?instNo=1&deptClsf=A
     → [{deptCd, deptNm, ...}] (31개, 의과대학병원)
  2) 진료과별 시간표 HTML: /kr/treatment/department/{deptCd}/timetable.do
     → li.profile_outer 안에 의사 카드 + 주간 스케줄 테이블

의사 카드 구조:
  li.profile_outer
    div.profile_box
      img[src*='drNo=']          → drNo 추출
      p.doctor_name              → "{이름} {직책}"
      p.doctor_info              → 소속/전문분야/초진·재진일 등
    div.table_type01 table
      tbody tr[0]: <td>오전</td> + 월~토 (6 cells)
      tbody tr[1]: <td>오후</td> + 월~토 (6 cells)
    각 요일 셀에:
      em.dat.blue   → 진료과
      em.dat.red    → 센터
      em.dat.star   → 협진진료처

external_id: KHNMC-{deptCd}-{drNo}
  개별 교수 조회 시 staff_id 에서 deptCd/drNo 파싱 → 해당 진료과 1곳만 조회
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.khnmc.or.kr"
DEPT_LIST_URL = f"{BASE_URL}/api/department/deptCdList.do"
DEPT_TIMETABLE_URL = f"{BASE_URL}/kr/treatment/department/{{dept_cd}}/timetable.do"
DOCTOR_PROFILE_URL = f"{BASE_URL}/kr/treatment/doctor/{{dr_no}}/profile.do"
MAIN_URL = f"{BASE_URL}/kr/main.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:30", "17:00")}


class KhnmcCrawler:
    """강동경희대학교병원 크롤러 — JSON API + 진료과별 timetable HTML"""

    def __init__(self):
        self.hospital_code = "KHNMC"
        self.hospital_name = "강동경희대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": MAIN_URL,
        }
        self._cached_data: list[dict] | None = None
        self._cached_depts: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _bootstrap_session(self, client: httpx.AsyncClient) -> None:
        """메인 페이지 한 번 열어 세션 쿠키 확보 (WAF 우회)"""
        try:
            await client.get(MAIN_URL)
        except Exception as e:
            logger.warning(f"[KHNMC] 세션 초기화 실패 (무시): {e}")

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        """진료과 목록 JSON"""
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.get(
                DEPT_LIST_URL,
                params={"instNo": "1", "deptClsf": "A"},
                headers={**self.headers, "X-Requested-With": "XMLHttpRequest"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[KHNMC] 진료과 목록 실패: {e}")
            return []
        depts = [
            {"code": d["deptCd"], "name": d["deptNm"]}
            for d in data.get("deptList", [])
            if d.get("deptCd") and d.get("deptNm")
        ]
        self._cached_depts = depts
        return depts

    def _parse_timetable_page(self, html: str, dept_name: str) -> list[dict]:
        """진료과 timetable HTML 파싱 → 의사 리스트"""
        soup = BeautifulSoup(html, "html.parser")
        doctors = []
        for li in soup.select("li.profile_outer"):
            doc = self._parse_profile_outer(li, dept_name)
            if doc:
                doctors.append(doc)
        return doctors

    def _parse_profile_outer(self, li, dept_name: str) -> dict | None:
        # drNo 추출
        img = li.select_one("img[src*='drNo=']")
        if not img:
            return None
        m = re.search(r"drNo=(\w+)", img.get("src", ""))
        if not m:
            return None
        dr_no = m.group(1)

        # 이름 + 직책
        name_el = li.select_one("p.doctor_name")
        if not name_el:
            return None
        spans = [s.get_text(strip=True) for s in name_el.select("span")]
        name = spans[0] if spans else ""
        position = spans[1] if len(spans) > 1 else ""
        if not name:
            return None

        # 전문분야
        specialty = ""
        info = li.select_one("p.doctor_info")
        if info:
            info_text = info.get_text("\n", strip=True)
            m2 = re.search(r"전문분야\s*[:：]\s*([^\n]+)", info_text)
            if m2:
                specialty = m2.group(1).strip()

        # 스케줄 파싱
        schedules = self._parse_schedule_table(li)

        return {
            "dr_no": dr_no,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "schedules": schedules,
        }

    def _parse_schedule_table(self, container) -> list[dict]:
        table = container.select_one("div.table_type01 table") or container.select_one("table")
        if not table:
            return []
        rows = table.select("tbody tr")
        schedules = []
        seen = set()
        for row in rows:
            cells = row.select("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            # 월~토 6 cells
            for dow, cell in enumerate(cells[1:7]):
                has_dept = cell.select_one("em.dat.blue") is not None
                has_center = cell.select_one("em.dat.red") is not None
                has_coop = cell.select_one("em.dat.star") is not None
                if not (has_dept or has_center or has_coop):
                    continue
                key = (dow, slot)
                if key in seen:
                    continue
                seen.add(key)
                # 위치: 단일 캠퍼스라 센터/협진만 구분
                if has_center:
                    location = "센터"
                elif has_coop:
                    location = "협진"
                else:
                    location = ""
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": location,
                })
        return schedules

    async def _fetch_dept(
        self, client: httpx.AsyncClient, dept_cd: str, dept_name: str,
    ) -> list[dict]:
        try:
            resp = await client.get(DEPT_TIMETABLE_URL.format(dept_cd=dept_cd))
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[KHNMC] {dept_name}({dept_cd}) 실패: {e}")
            return []
        return self._parse_timetable_page(resp.text, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            await self._bootstrap_session(client)
            depts = await self._fetch_dept_list(client)
            if not depts:
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(5)

            async def guarded(dept):
                async with sem:
                    return await self._fetch_dept(client, dept["code"], dept["name"])

            tasks = [asyncio.create_task(guarded(d)) for d in depts]
            all_doctors: list[dict] = []
            seen_ids: set[str] = set()
            for coro in asyncio.as_completed(tasks):
                docs = await coro
                dept_name = docs[0]["department"] if docs else ""
                for d in docs:
                    ext_id = f"KHNMC-{self._dept_cd_of(dept_name, depts)}-{d['dr_no']}"
                    if ext_id in seen_ids:
                        continue
                    seen_ids.add(ext_id)
                    dr_no = d["dr_no"]
                    all_doctors.append({
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": d["name"],
                        "department": d["department"],
                        "position": d["position"],
                        "specialty": d["specialty"],
                        "profile_url": DOCTOR_PROFILE_URL.format(dr_no=dr_no),
                        "notes": "",
                        "schedules": d["schedules"],
                    })

        logger.info(f"[KHNMC] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    @staticmethod
    def _dept_cd_of(dept_name: str, depts: list[dict]) -> str:
        for d in depts:
            if d["name"] == dept_name:
                return d["code"]
        return ""

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            await self._bootstrap_session(client)
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
        """개별 교수 조회 — external_id에서 deptCd/drNo 파싱, 해당 진료과 1곳만 조회"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in
                            ("staff_id", "name", "department", "position",
                             "specialty", "profile_url", "notes", "schedules")}
            return empty

        # KHNMC-{deptCd}-{drNo} 파싱
        m = re.match(r"^KHNMC-([0-9A-Za-z]+)-(\w+)$", staff_id)
        if not m:
            logger.warning(f"[KHNMC] staff_id 형식 오류: {staff_id}")
            return empty
        dept_cd, dr_no = m.group(1), m.group(2)

        async with self._make_client() as client:
            await self._bootstrap_session(client)
            depts = await self._fetch_dept_list(client)
            dept_name = next((d["name"] for d in depts if d["code"] == dept_cd), "")
            if not dept_name:
                return empty
            docs = await self._fetch_dept(client, dept_cd, dept_name)

        for d in docs:
            if d["dr_no"] == dr_no:
                return {
                    "staff_id": staff_id,
                    "name": d["name"],
                    "department": d["department"],
                    "position": d["position"],
                    "specialty": d["specialty"],
                    "profile_url": DOCTOR_PROFILE_URL.format(dr_no=dr_no),
                    "notes": "",
                    "schedules": d["schedules"],
                }
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

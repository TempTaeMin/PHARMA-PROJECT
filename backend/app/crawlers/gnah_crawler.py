"""강릉아산병원(Gangneung Asan Hospital) 크롤러

홈페이지: https://www.gnah.co.kr
기술: 정적 HTML (httpx + BeautifulSoup), POST 기반 검색

구조:
  1) 의료진 목록 페이지 (초기 GET 시 비어 있음)
     /kor/CMS/DoctorMgr/list.do?mCode=MN092
     - `select[name=dept_code]` 에 진료과 코드 목록
  2) 진료과별 의사 목록 (POST)
     action=/kor/CMS/DoctorMgr/list.do
     data={mCode: MN092, searchID: sch001, searchYn: Y,
           schGubun: D, dept_code: {CODE}, doctorKeyword: ''}
     - `div.doctorLstBox ul li a` → view.do?doctor_seq={N}&sch_depart_code={CODE}
     - 카드에 deptName, doctName 텍스트
  3) 의사 상세 페이지 (진료시간표 포함)
     /kor/CMS/DoctorMgr/view.do?mCode=MN092&doctor_seq={N}&sch_depart_code={CODE}&docMode=viewMode
     - `table.doctTime` : thead 에 요일(월~토), tbody 2행 (오전/오후)
     - 셀 텍스트 "진료" = 외래, "-" = 없음
     - `div.doctBaseInfo span.deptName/doctName/doctPosi`
     - `dl.doctSect dd` = 전문분야

external_id: GNAH-{doctor_seq}  (sch_depart_code 는 포함하지 않음)
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.gnah.co.kr"
LIST_URL = f"{BASE_URL}/kor/CMS/DoctorMgr/list.do"
VIEW_URL = f"{BASE_URL}/kor/CMS/DoctorMgr/view.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_HEADERS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
SLOT_HEADERS = {"오전": "morning", "오후": "afternoon"}

# 사이트 검색 폼의 dept_code 옵션을 그대로 채집
GNAH_DEPARTMENTS: dict[str, str] = {
    "FM": "가정의학과",
    "INF": "감염내과",
    "END": "내분비내과",
    "RH": "류마티스내과",
    "ANS": "마취통증의학과",
    "RO": "방사선종양학과",
    "DP": "병리과",
    "URO": "비뇨의학과",
    "OBY": "산부인과",
    "PS": "성형외과",
    "PED": "소아청소년과",
    "GI": "소화기내과",
    "NR": "신경과",
    "NS": "신경외과",
    "NPH": "신장내과",
    "CV": "심장내과",
    "CS": "심장혈관흉부외과",
    "OPH": "안과",
    "ALG": "알레르기내과",
    "DR": "영상의학과",
    "GS": "외과",
    "EM": "응급의학과",
    "ENT": "이비인후과",
    "GIM": "일반내과",
    "RM": "재활의학과",
    "PSY": "정신건강의학과",
    "OS": "정형외과",
    "LM": "진단검사의학과",
    "DNT": "치과",
    "DER": "피부과",
    "NM": "핵의학과",
    "ONC": "혈액종양내과",
    "PLM": "호흡기내과",
}


class GnahCrawler:
    """강릉아산병원 크롤러 — 정적 HTML + POST 검색 기반"""

    def __init__(self):
        self.hospital_code = "GNAH"
        self.hospital_name = "강릉아산병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/kor/CMS/DoctorMgr/list.do?mCode=MN092",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    # ─── 진료과별 목록 ───

    async def _fetch_dept_list(self, client: httpx.AsyncClient,
                                dept_code: str, dept_name: str) -> list[dict]:
        """진료과 1개의 의사 카드 목록을 가져옴."""
        data = {
            "mCode": "MN092",
            "searchID": "sch001",
            "searchYn": "Y",
            "schGubun": "D",
            "dept_code": dept_code,
            "sch_cntr_id": "",
            "doctorKeyword": "",
        }
        try:
            resp = await client.post(LIST_URL, data=data)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[GNAH] dept {dept_code}({dept_name}) 목록 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        box = soup.select_one("div.doctorLstBox")
        if not box:
            return []

        doctors: list[dict] = []
        for a in box.select("ul li a[href*='view.do']"):
            href = a.get("href", "")
            m = re.search(r"doctor_seq=(\d+)", href)
            if not m:
                continue
            doctor_seq = m.group(1)

            # 카드 내부의 txtBox 텍스트에서 이름/부서 추출
            name_el = a.select_one(".txtBox .doctName") or a.select_one(".doctName")
            name = self._clean(name_el.get_text(" ", strip=True)) if name_el else ""
            if not name:
                continue

            dept_el = a.select_one(".txtBox .deptName") or a.select_one(".deptName")
            card_dept = self._clean(dept_el.get_text(" ", strip=True)) if dept_el else dept_name

            pos_el = a.select_one(".txtBox .doctPosi") or a.select_one(".doctPosi")
            position = self._clean(pos_el.get_text(" ", strip=True)) if pos_el else ""

            img = a.select_one("img")
            photo_url = ""
            if img:
                src = (img.get("src") or "").strip()
                if src:
                    photo_url = src if src.startswith("http") else f"{BASE_URL}{src if src.startswith('/') else '/' + src}"

            ext_id = f"GNAH-{doctor_seq}"
            profile_url = (
                f"{VIEW_URL}?mCode=MN092&doctor_seq={doctor_seq}"
                f"&sch_depart_code={dept_code}&docMode=viewMode"
            )
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "doctor_seq": doctor_seq,
                "dept_code": dept_code,
                "name": name,
                "department": card_dept or dept_name,
                "position": position,
                "specialty": "",
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": [],
                "date_schedules": [],
            })
        return doctors

    # ─── 개별 의사 상세 + 스케줄 ───

    def _parse_schedule_table(self, soup: BeautifulSoup) -> list[dict]:
        """`table.doctTime` 에서 요일×슬롯 매트릭스 파싱."""
        table = soup.select_one("table.doctTime")
        if not table:
            return []

        # thead 에서 요일 컬럼 순서 결정
        head_cells = table.select("thead tr th")
        day_order: list[int | None] = []
        for th in head_cells:
            txt = self._clean(th.get_text(" ", strip=True))
            if not txt:
                day_order.append(None)  # 좌상단 빈칸 (첫 컬럼)
                continue
            day_order.append(DAY_HEADERS.get(txt))

        rows = table.select("tbody tr")
        schedules: list[dict] = []
        seen: set[tuple[int, str]] = set()

        for tr in rows:
            slot_th = tr.find("th")
            if not slot_th:
                continue
            slot_label = self._clean(slot_th.get_text(" ", strip=True))
            slot = SLOT_HEADERS.get(slot_label)
            if not slot:
                continue

            tds = tr.find_all("td")
            # 첫번째 day_order 항목이 좌상단(빈칸)이면 td 인덱스는 day_order[1:] 와 정렬됨
            day_cols = [d for d in day_order if d is not None]
            for idx, td in enumerate(tds):
                if idx >= len(day_cols):
                    break
                dow = day_cols[idx]
                if dow is None:
                    continue
                cell_text = self._clean(td.get_text(" ", strip=True))
                if not is_clinic_cell(cell_text):
                    continue
                key = (dow, slot)
                if key in seen:
                    continue
                seen.add(key)
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        schedules.sort(key=lambda s: (s["day_of_week"], s["time_slot"]))
        return schedules

    def _parse_doctor_detail(self, html: str) -> dict:
        """상세 페이지 → 이름/진료과/직책/전문분야/스케줄"""
        soup = BeautifulSoup(html, "html.parser")

        info: dict = {
            "name": "",
            "department": "",
            "position": "",
            "specialty": "",
            "photo_url": "",
            "schedules": [],
        }

        base = soup.select_one("div.doctBaseInfo") or soup
        dept_el = base.select_one(".deptName")
        if dept_el:
            info["department"] = self._clean(dept_el.get_text(" ", strip=True))
        name_el = base.select_one(".doctName")
        if name_el:
            info["name"] = self._clean(name_el.get_text(" ", strip=True))
        pos_el = base.select_one(".doctPosi")
        if pos_el:
            info["position"] = self._clean(pos_el.get_text(" ", strip=True))

        spec_el = soup.select_one("div.doctBaseInfo dl.doctSect dd")
        if spec_el:
            info["specialty"] = self._clean(spec_el.get_text(" ", strip=True))

        main_shot = soup.select_one("div.dv-mainShot div.dvImg img")
        if main_shot:
            src = (main_shot.get("src") or "").strip()
            if src:
                info["photo_url"] = src if src.startswith("http") else f"{BASE_URL}{src if src.startswith('/') else '/' + src}"

        info["schedules"] = self._parse_schedule_table(soup)
        return info

    async def _fetch_doctor_detail(self, client: httpx.AsyncClient,
                                    doctor_seq: str, dept_code: str) -> dict:
        url = f"{VIEW_URL}?mCode=MN092&doctor_seq={doctor_seq}&sch_depart_code={dept_code}&docMode=viewMode"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[GNAH] detail doctor_seq={doctor_seq} 실패: {e}")
            return {"name": "", "department": "", "position": "",
                    "specialty": "", "photo_url": "", "schedules": []}
        return self._parse_doctor_detail(resp.text)

    # ─── 전체 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            dept_results = await asyncio.gather(
                *[self._fetch_dept_list(client, code, name)
                  for code, name in GNAH_DEPARTMENTS.items()],
                return_exceptions=True,
            )
            # doctor_seq 기준 dedup (여러 진료과 중복 소속)
            seen: dict[str, dict] = {}
            extra_depts: dict[str, list[str]] = {}
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                for d in r:
                    seq = d["doctor_seq"]
                    if seq in seen:
                        ex = d["department"]
                        if ex and ex != seen[seq]["department"] and ex not in extra_depts[seq]:
                            extra_depts[seq].append(ex)
                        continue
                    seen[seq] = d
                    extra_depts[seq] = []

            unique = list(seen.values())
            logger.info(f"[GNAH] 진료과 합산 {len(unique)}명")

            # 상세 페이지 병렬 수집 (Semaphore 로 부하 제어)
            sem = asyncio.Semaphore(8)

            async def fill(doc: dict):
                async with sem:
                    detail = await self._fetch_doctor_detail(
                        client, doc["doctor_seq"], doc["dept_code"]
                    )
                # 상세 페이지 값 우선 (단 목록에서만 나오는 photo 는 목록 것 유지 가능)
                if detail.get("name"):
                    doc["name"] = detail["name"]
                if detail.get("department"):
                    doc["department"] = detail["department"]
                if detail.get("position"):
                    doc["position"] = detail["position"]
                if detail.get("specialty"):
                    doc["specialty"] = detail["specialty"]
                if detail.get("photo_url") and not doc.get("photo_url"):
                    doc["photo_url"] = detail["photo_url"]
                doc["schedules"] = detail.get("schedules", [])
                # date_schedules 미지원 (사이트가 월별 달력 제공 안 함)
                doc["date_schedules"] = []

                extras = extra_depts.get(doc["doctor_seq"], [])
                if extras:
                    doc["notes"] = f"복수 진료과: {', '.join(extras)}"

            await asyncio.gather(*[fill(d) for d in unique], return_exceptions=True)

        self._cached_data = unique
        return unique

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in GNAH_DEPARTMENTS.items()]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department or d["dept_code"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 해당 교수 1명만 네트워크 요청 (skill 규칙 #7)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

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
                        "notes": d.get("notes", ""),
                        "schedules": d.get("schedules", []),
                        "date_schedules": d.get("date_schedules", []),
                    }
            return empty

        prefix = "GNAH-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id.isdigit():
            return empty

        # view.do 는 doctor_seq 만으로 정상 응답한다 (sch_depart_code 는 탐색용 힌트).
        # 상세 페이지에서 department 가 채워지므로 진료과 파라미터 없이 조회 가능.
        async with self._make_client() as client:
            url = f"{VIEW_URL}?mCode=MN092&doctor_seq={raw_id}&docMode=viewMode"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[GNAH] 개별 조회 실패 {staff_id}: {e}")
                return empty
            detail = self._parse_doctor_detail(resp.text)

        return {
            "staff_id": staff_id,
            "name": detail.get("name", ""),
            "department": detail.get("department", ""),
            "position": detail.get("position", ""),
            "specialty": detail.get("specialty", ""),
            "profile_url": f"{VIEW_URL}?mCode=MN092&doctor_seq={raw_id}&docMode=viewMode",
            "notes": "",
            "schedules": detail.get("schedules", []),
            "date_schedules": [],
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department or d["dept_code"] == department]

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

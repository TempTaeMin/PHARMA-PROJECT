"""세란병원(Seran Hospital) 크롤러

병원 공식명: 세란병원 (서울 종로구)
홈페이지: www.seran.co.kr
기술: 정적 HTML + AJAX (httpx + BeautifulSoup)

구조:
  1) 의료진 목록: /index.php/html/153
     - div.dr_list 반복
       - li.img > img (프로필)
       - li.dr_link onclick="view_(id,num)"  — id 가 고유
       - li.name — 의사 이름

  2) 의사 프로필 상세 (AJAX POST): /xmldata/doctor/profile_load.php?id={id}
     - p.name > "이름<span> 직책</span>"
     - div.clinic .c_con — 전문분야
     - ul.contents — 학력/약력

  3) 당직 스케줄 (정형외과 2명만): /index.php/html/57
     - table.table_con2 안에 이름 + 오전/오후 × 월~토 (6열)
     - td.select_01 "진료" → 외래
     - td.select_02 "휴진" → 제외
     - td.select_03 "내시경/문의/심초" → 제외

external_id: SERAN-{id}  (view_(id,num) 의 id)
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.seran.co.kr"
MEDTEAM_URL = f"{BASE_URL}/index.php/html/153"
PROFILE_URL = f"{BASE_URL}/xmldata/doctor/profile_load.php"
SCHEDULE_URL = f"{BASE_URL}/index.php/html/57"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("14:00", "17:30")}

VIEW_RE = re.compile(r"view_\(\s*(\d+)\s*,\s*(\d+)\s*\)")

NOTE_NO_SCHEDULE = (
    "※ 세란병원 홈페이지에는 정형외과 당직 외에 교수별 주간 진료시간표가 공개되어 "
    "있지 않습니다. 외래 진료 가능 시간은 대표번호 1577-0075 또는 병원에 직접 "
    "문의해 주세요."
)


class SeranCrawler:
    """세란병원 크롤러 — 의료진 목록 + AJAX 프로필 + 당직 스케줄"""

    def __init__(self):
        self.hospital_code = "SERAN"
        self.hospital_name = "세란병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_profile(
        self, client: httpx.AsyncClient, doctor_id: str
    ) -> tuple[str, str, str, str]:
        """(position, specialty, notes, detail_html) 반환"""
        try:
            resp = await client.post(PROFILE_URL, data={"id": doctor_id})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SERAN] 프로필 로드 실패 id={doctor_id}: {e}")
            return "", "", "", ""
        soup = BeautifulSoup(resp.text, "html.parser")

        position = ""
        name_tag = soup.find("p", class_="name")
        if name_tag:
            span = name_tag.find("span")
            if span:
                position = span.get_text(" ", strip=True)

        specialty = ""
        clinic = soup.find("div", class_="clinic")
        if clinic:
            c_con = clinic.find("div", class_="c_con")
            if c_con:
                specialty = c_con.get_text(" ", strip=True)

        notes_lines: list[str] = []
        for ul in soup.find_all("ul", class_="contents"):
            title_li = ul.find("li", class_="title")
            title = title_li.get_text(" ", strip=True) if title_li else ""
            con_li = ul.find("li", class_="con")
            if con_li:
                body = con_li.get_text("\n", strip=True)
                if title:
                    notes_lines.append(f"[{title}]\n{body}")
                else:
                    notes_lines.append(body)
        notes = "\n\n".join(notes_lines)

        return position, specialty, notes, resp.text

    async def _fetch_oncall_schedules(self, client: httpx.AsyncClient) -> dict[str, list[dict]]:
        """당직의사 시간표(/html/57) 에서 이름→스케줄 매핑"""
        try:
            resp = await client.get(SCHEDULE_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SERAN] 당직 시간표 실패: {e}")
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")

        result: dict[str, list[dict]] = {}
        for table in soup.find_all("table", class_=re.compile(r"table_con")):
            rows = table.find_all("tr")
            # 첫 행은 헤더(전문의/시간/월~토), 이후 이름 rowspan=2 + 오전/오후
            current_name: str | None = None
            morning_cells: list | None = None
            for row in rows[1:]:
                cells = row.find_all("td")
                if not cells:
                    continue
                name_td = row.find("td", class_="name")
                if name_td is not None:
                    current_name = name_td.get_text(" ", strip=True)
                    result.setdefault(current_name, [])
                    # cells 첫 요소가 이름 td (rowspan), 다음이 "오전", 이후 6개가 요일
                    day_cells = cells[2:8] if len(cells) >= 8 else cells[-6:]
                    slot = "morning"
                else:
                    # 오후 행 — 첫 td 가 "오후", 이후 6개
                    day_cells = cells[1:7] if len(cells) >= 7 else cells[-6:]
                    slot = "afternoon"
                start, end = TIME_RANGES[slot]
                for i, td in enumerate(day_cells):
                    classes = td.get("class") or []
                    if "select_01" not in classes:
                        continue
                    if current_name is None:
                        continue
                    result[current_name].append({
                        "day_of_week": i,
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })
        return result

    @staticmethod
    def _guess_department(position: str, specialty: str) -> str:
        """직책/전문분야 텍스트에서 진료과를 추정."""
        text = f"{position} {specialty}"
        DEPT_KEYWORDS = (
            "내과", "외과", "정형외과", "신경외과", "신경과", "정신건강의학과",
            "재활의학과", "마취통증의학과", "영상의학과", "진단검사의학과",
            "이비인후과", "안과", "피부과", "비뇨의학과", "산부인과",
            "소아청소년과", "가정의학과", "응급의학과", "흉부외과", "성형외과",
            "병리과", "치과", "한방", "방사선종양학과",
        )
        for kw in DEPT_KEYWORDS:
            if kw in text:
                return kw
        return ""

    async def _parse_medteam(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(MEDTEAM_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SERAN] 의료진 목록 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        entries: list[dict] = []
        for card in soup.find_all("div", class_="dr_list"):
            name_li = card.find("li", class_="name")
            link_li = card.find("li", class_="dr_link")
            if name_li is None or link_li is None:
                continue
            name = name_li.get_text(" ", strip=True)
            onclick = link_li.get("onclick", "")
            m = VIEW_RE.search(onclick)
            if not m:
                continue
            doctor_id = m.group(1)
            img_tag = card.find("img")
            img_src = img_tag.get("src", "") if img_tag else ""
            entries.append({
                "id": doctor_id,
                "name": name,
                "img_src": f"{BASE_URL}{img_src}" if img_src.startswith("/") else img_src,
            })
        return entries

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            entries = await self._parse_medteam(client)
            oncall_map = await self._fetch_oncall_schedules(client)

            profile_tasks = [
                asyncio.create_task(self._fetch_profile(client, e["id"]))
                for e in entries
            ]
            profiles = await asyncio.gather(*profile_tasks, return_exceptions=True)

        result: list[dict] = []
        seen: set[str] = set()
        for entry, prof in zip(entries, profiles):
            if isinstance(prof, Exception):
                position, specialty, notes = "", "", ""
            else:
                position, specialty, notes, _ = prof
            ext_id = f"SERAN-{entry['id']}"
            if ext_id in seen:
                continue
            seen.add(ext_id)
            schedules = oncall_map.get(entry["name"], [])
            # 부서는 position(직책) 또는 specialty 첫 토큰에서 추정
            department = self._guess_department(position, specialty)
            final_notes = notes
            if not schedules:
                final_notes = (notes + "\n\n" + NOTE_NO_SCHEDULE).strip() if notes else NOTE_NO_SCHEDULE
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": entry["name"],
                "department": department,
                "position": position,
                "specialty": specialty,
                "profile_url": MEDTEAM_URL,
                "notes": final_notes,
                "schedules": schedules,
                "date_schedules": [],
            })

        logger.info(f"[SERAN] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen: list[str] = []
        for d in data:
            dept = d.get("department", "")
            if dept and dept not in seen:
                seen.append(dept)
        if not seen:
            return [{"code": "ALL", "name": "전체"}]
        return [{"code": dept, "name": dept} for dept in seen]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department and department != "ALL":
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 프로필 AJAX + 당직 시간표 매칭"""
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

        prefix = "SERAN-"
        doctor_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not doctor_id:
            return empty

        async with self._make_client() as client:
            # 의료진 목록에서 이름 찾기
            entries = await self._parse_medteam(client)
            matched = next((e for e in entries if e["id"] == doctor_id), None)
            if matched is None:
                return empty
            position, specialty, notes, _ = await self._fetch_profile(client, doctor_id)
            oncall_map = await self._fetch_oncall_schedules(client)

        return {
            "staff_id": staff_id,
            "name": matched["name"],
            "department": "",
            "position": position,
            "specialty": specialty,
            "profile_url": MEDTEAM_URL,
            "notes": notes,
            "schedules": oncall_map.get(matched["name"], []),
            "date_schedules": [],
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department and department != "ALL":
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

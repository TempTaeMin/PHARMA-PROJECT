"""전북대학교병원(JBUH) 크롤러

전라북도 전주시 덕진구 건지로 20 / www.jbuh.co.kr

구조 (정적 HTML, httpx 가능):
  1) 진료과 목록 페이지
       /prog/mdcl/main/sub01_01_01/list.do
     → 사이드 메뉴/리스트의 mdclCd={진료과코드}로 42개 진료과 추출
  2) 진료과별 의료진 + 시간표 페이지 (의사 카드가 인라인 시간표 포함)
       /prog/mdcl/main/sub01_01_01/viewStf.do?mdclCd={dept}
     → div.dl-item 내부에 이름/sub-dept/전문분야/시간표/상세링크 모두 들어 있음
  3) 의사 개별 상세 페이지(개별 조회 시)
       /prog/mdclStf/main/sub01_01/view.do?mdclCd={dept}&mdclStfEmplNo={empNo}
     → Title-box(이름·진료과), 전문분야, 진료일정 테이블 동일 구조

스케줄:
  - 주간 패턴: <table> 안에 location 그룹(th rowspan=2) + 오전/오후 행 + 월~토 열
  - 진료 셀 = <div class="ov"><span class="sr-only">진료가능</span></div>
  - 빈 td 는 비활성. 텍스트 키워드 없이 OV 마크만 사용.
  - location 은 본관/노인센터/암센터/응급센터/어린이병원/강내치료 등.
    여러 장소 진료 시 schedule.location 에 기록하고 notes 에 요약을 남긴다 (SNUH 패턴).
  - 날짜별 스케줄 미제공 → date_schedules = []

external_id 포맷: JBUH-{mdclCd}-{mdclStfEmplNo}
  (mdclCd 는 단독 조회 URL 에 필수)
"""
import re
import asyncio
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jbuh.co.kr"
DEPT_LIST_URL = f"{BASE_URL}/prog/mdcl/main/sub01_01_01/list.do"
DEPT_VIEW_URL = f"{BASE_URL}/prog/mdcl/main/sub01_01_01/viewStf.do"
STAFF_VIEW_URL = f"{BASE_URL}/prog/mdclStf/main/sub01_01/view.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_KO = ("월", "화", "수", "목", "금", "토", "일")
DAY_INDEX = {ko: i for i, ko in enumerate(DAY_KO)}


class JbuhCrawler:
    """전북대학교병원 (전북) 크롤러."""

    def __init__(self):
        self.hospital_code = "JBUH"
        self.hospital_name = "전북대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        self._cached_data: list[dict] | None = None
        self._dept_map: dict[str, str] | None = None  # mdclCd → 진료과명

    # ───────────────────── 공용 ─────────────────────

    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_dept_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        """진료과 목록 페이지에서 {mdclCd: 진료과명} 추출."""
        if self._dept_map is not None:
            return self._dept_map

        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[JBUH] 진료과 목록 로드 실패: {e}")
            self._dept_map = {}
            return self._dept_map

        soup = BeautifulSoup(resp.text, "html.parser")
        result: dict[str, str] = {}
        seen_codes: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"mdclCd=([A-Za-z0-9_]+)", href)
            if not m:
                continue
            code = m.group(1)
            name = self._clean(a.get_text(" ", strip=True))
            if not name or len(name) < 2:
                continue
            if code in seen_codes:
                continue
            seen_codes.add(code)
            # 잡 메뉴(전체보기 등) 필터
            if name in ("전체보기", "더보기", "바로가기", "자세히 보기"):
                continue
            result[code] = name

        self._dept_map = result
        logger.info(f"[JBUH] 진료과 {len(result)}개 추출")
        return result

    # ───────────────────── 표 파싱 ─────────────────────

    @staticmethod
    def _is_active_cell(td) -> bool:
        """<td> 가 진료 활성 셀인지 — <div class="ov"> 마크 우선, 텍스트 fallback."""
        if td is None:
            return False
        if td.find("div", class_="ov") is not None:
            return True
        text = td.get_text(" ", strip=True)
        if not text:
            return False
        return is_clinic_cell(text)

    def _parse_schedule_table(self, table) -> list[dict]:
        """JBUH 시간표 테이블 파싱.

        구조:
          thead: th[colspan=2] '구분' + th 월/화/수/목/금/토(/일)
          tbody: 각 location 그룹마다 2행
            row1: th[rowspan=2] '본관/노인센터/...' + td '오전' + td×7
            row2: td '오후' + td×7
        """
        if table is None:
            return []
        thead = table.find("thead")
        if thead is None:
            return []
        head_ths = thead.find_all("th")
        # 첫 th 는 colspan=2 '구분', 그 다음부터가 요일
        days: list[int] = []
        for th in head_ths:
            t = self._clean(th.get_text())
            if t in DAY_INDEX:
                days.append(DAY_INDEX[t])
        if not days:
            return []

        result: list[dict] = []
        tbody = table.find("tbody")
        if tbody is None:
            return result

        current_loc = ""
        rows = tbody.find_all("tr")
        for tr in rows:
            tds = tr.find_all(["th", "td"], recursive=False)
            if not tds:
                continue
            idx = 0
            # location 셀(th rowspan=2) 처리
            first = tds[0]
            if first.name == "th" and first.get("rowspan"):
                current_loc = self._clean(first.get_text())
                idx = 1
            # 시간 슬롯 라벨 (오전/오후) — th 또는 td
            slot_cell = tds[idx] if idx < len(tds) else None
            if slot_cell is None:
                continue
            slot_label = self._clean(slot_cell.get_text())
            if "오전" in slot_label:
                slot = "morning"
            elif "오후" in slot_label:
                slot = "afternoon"
            else:
                continue
            start_t, end_t = TIME_RANGES[slot]
            day_cells = tds[idx + 1:]
            for di, td in enumerate(day_cells):
                if di >= len(days):
                    break
                day_idx = days[di]
                if day_idx is None:
                    continue
                if not self._is_active_cell(td):
                    continue
                result.append({
                    "day_of_week": day_idx,
                    "time_slot": slot,
                    "start_time": start_t,
                    "end_time": end_t,
                    "location": current_loc,
                })
        return result

    @staticmethod
    def _summarize_locations(schedules: list[dict]) -> str:
        """여러 location 진료 시 notes 에 들어갈 요약 문자열 생성 (SNUH 패턴)."""
        locs: list[str] = []
        for s in schedules:
            loc = s.get("location") or ""
            if loc and loc not in locs:
                locs.append(loc)
        if len(locs) <= 1:
            return ""
        lines = []
        for loc in locs:
            loc_sched = [s for s in schedules if s.get("location") == loc]
            if not loc_sched:
                continue
            day_slots = []
            for s in loc_sched:
                day_idx = s["day_of_week"]
                if 0 <= day_idx < len(DAY_KO):
                    day_ko = DAY_KO[day_idx]
                else:
                    continue
                slot_ko = "오전" if s["time_slot"] == "morning" else "오후"
                day_slots.append(f"{day_ko} {slot_ko}")
            if day_slots:
                lines.append(f"{loc}: {', '.join(day_slots)}")
        return "\n".join(lines)

    # ───────────────────── 카드 파싱 ─────────────────────

    def _parse_doctor_card(self, card, mdcl_cd: str, dept_name: str) -> dict | None:
        """진료과 viewStf 페이지의 div.dl-item 카드 1개 파싱."""
        # 이름 + sub-dept(실제 분과)
        name_el = card.find("strong", class_="dl-name")
        if name_el is None:
            return None
        name = self._clean(name_el.get_text())
        if not name:
            return None

        sub_el = card.find("span", class_="dl-sub-name")
        sub_dept = self._clean(sub_el.get_text()) if sub_el else ""
        # sub-dept 가 더 구체적이면 그걸 department 로 사용
        department = sub_dept or dept_name

        # 전문분야
        field_el = card.find("span", class_="dl-field-text")
        specialty = self._clean(field_el.get_text(" ", strip=True)) if field_el else ""

        # 사진
        photo_url = ""
        img = card.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("/"):
                src = BASE_URL + src
            photo_url = src

        # 상세 링크에서 mdclStfEmplNo 추출
        empl_no = ""
        for a in card.find_all("a", href=True):
            m = re.search(r"mdclStfEmplNo=(\d+)", a["href"])
            if m:
                empl_no = m.group(1)
                break
        if not empl_no:
            return None

        # 시간표
        table = card.find("table")
        schedules = self._parse_schedule_table(table)

        # 진료특이사항(notes)
        check_el = card.find("div", class_="dl-checkBox")
        check_note = ""
        if check_el:
            # 예외 메시지 제외
            exc = check_el.find("span", class_="dlc-exception")
            if exc is None:
                contents = check_el.find("span", class_="dlc-contents")
                if contents:
                    check_note = self._clean(contents.get_text(" ", strip=True))

        loc_summary = self._summarize_locations(schedules)
        notes = "\n".join(x for x in (loc_summary, check_note) if x)

        external_id = f"{self.hospital_code}-{mdcl_cd}-{empl_no}"
        profile_url = (f"{STAFF_VIEW_URL}?mdclCd={mdcl_cd}&mdclStfEmplNo={empl_no}")

        return {
            "staff_id": external_id,
            "external_id": external_id,
            "name": name,
            "department": department,
            "position": "",
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
            "_mdclCd": mdcl_cd,
            "_emplNo": empl_no,
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, mdcl_cd: str, dept_name: str
    ) -> list[dict]:
        """한 진료과의 의료진 목록 + 시간표를 가져온다."""
        try:
            resp = await client.get(DEPT_VIEW_URL, params={"mdclCd": mdcl_cd})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[JBUH] {dept_name}({mdcl_cd}) 의료진 페이지 로드 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []
        for card in soup.find_all("div", class_="dl-item"):
            try:
                doc = self._parse_doctor_card(card, mdcl_cd, dept_name)
                if doc:
                    results.append(doc)
            except Exception as e:
                logger.debug(f"[JBUH] {dept_name} 카드 파싱 오류: {e}")
                continue
        return results

    # ───────────────────── 전체 크롤링 ─────────────────────

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with self._make_client() as client:
            dept_map = await self._fetch_dept_map(client)
            if not dept_map:
                self._cached_data = []
                return self._cached_data

            sem = asyncio.Semaphore(5)

            async def _job(code: str, name: str):
                async with sem:
                    return await self._fetch_dept_doctors(client, code, name)

            tasks = [_job(code, name) for code, name in dept_map.items()]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    logger.warning(f"[JBUH] 진료과 크롤링 예외: {res}")
                    continue
                for doc in res:
                    eid = doc["external_id"]
                    if eid not in all_doctors:
                        all_doctors[eid] = doc

        result_list = list(all_doctors.values())
        self._cached_data = result_list
        logger.info(f"[JBUH] 총 의사 {len(result_list)}명 수집")
        return result_list

    # ───────────────────── 표준 인터페이스 ─────────────────────

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            dept_map = await self._fetch_dept_map(client)
        return [{"code": c, "name": n} for c, n in dept_map.items()]

    async def crawl_doctor_list(self, department: str | None = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "position": d.get("position", ""),
                "specialty": d.get("specialty", ""),
                "profile_url": d.get("profile_url", ""),
                "photo_url": d.get("photo_url", ""),
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 1명만 네트워크 조회. _fetch_all 절대 호출하지 않음.

        external_id 포맷: JBUH-{mdclCd}-{mdclStfEmplNo}
        조회 URL: STAFF_VIEW_URL 에 mdclCd / mdclStfEmplNo 동시 전달.
        """
        empty = {
            "staff_id": staff_id,
            "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "photo_url": "",
            "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시 우선
        if self._cached_data is not None:
            for d in self._cached_data:
                if d.get("staff_id") == staff_id or d.get("external_id") == staff_id:
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

        # external_id 파싱 — "JBUH-{mdclCd}-{mdclStfEmplNo}"
        prefix = f"{self.hospital_code}-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.rsplit("-", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            logger.warning(f"[JBUH] external_id 형식 오류: {staff_id}")
            return empty
        mdcl_cd, empl_no = parts[0], parts[1]

        async with self._make_client() as client:
            try:
                resp = await client.get(
                    STAFF_VIEW_URL, params={"mdclCd": mdcl_cd, "mdclStfEmplNo": empl_no}
                )
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[JBUH] 개별 조회 실패 {staff_id}: {e}")
                return empty

            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # 이름/진료과(상단 Title-box)
            tb = soup.find("div", class_="Title-box")
            name = ""
            department = ""
            if tb:
                n_el = tb.find("strong", class_="mtName")
                if n_el:
                    name = self._clean(n_el.get_text())
                p_el = tb.find("span", class_="mtPart")
                if p_el:
                    department = self._clean(p_el.get_text())

            # 전문분야 — '전문진료분야' 라벨 다음 conText
            specialty = ""
            for strong in soup.find_all("strong", class_="tit"):
                if "전문진료분야" in strong.get_text():
                    info_box = strong.find_parent("div", class_="infoBox") or strong.find_parent("div")
                    if info_box:
                        ct = info_box.find("p", class_="conText")
                        if ct:
                            specialty = self._clean(ct.get_text(" ", strip=True))
                    break

            # 사진
            photo_url = ""
            if tb:
                img = tb.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    if src.startswith("/"):
                        src = BASE_URL + src
                    photo_url = src

            # 시간표 — 외래진료일정 tab-panel 내 table
            schedules: list[dict] = []
            for table in soup.find_all("table", class_="table"):
                cap = table.find("caption")
                cap_text = cap.get_text(" ", strip=True) if cap else ""
                if "진료일정" not in cap_text and "외래진료" not in cap_text:
                    # caption 없으면 그냥 시도
                    if cap_text:
                        continue
                schedules = self._parse_schedule_table(table)
                if schedules:
                    break

            # 진료특이사항(notes)
            check_note = ""
            for strong in soup.find_all("strong", class_="dl-sub-title"):
                if "진료특이사항" in strong.get_text():
                    parent = strong.find_parent("div", class_="dl-checkBox")
                    if parent:
                        exc = parent.find("span", class_="dlc-exception")
                        if exc is None:
                            contents = parent.find("span", class_="dlc-contents")
                            if contents:
                                check_note = self._clean(contents.get_text(" ", strip=True))
                    break

            loc_summary = self._summarize_locations(schedules)
            notes = "\n".join(x for x in (loc_summary, check_note) if x)

            profile_url = f"{STAFF_VIEW_URL}?mdclCd={mdcl_cd}&mdclStfEmplNo={empl_no}"

            return {
                "staff_id": staff_id,
                "name": name,
                "department": department,
                "position": "",
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
            }

    async def crawl_doctors(self, department: str | None = None):
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

"""조선대학교병원(CUH) 크롤러

광주광역시 동구 필문대로 365 / hosp.chosun.ac.kr

구조 (정적 HTML, httpx 가능):
  1) 진료과 목록 페이지
       /medi_depart/?type=lists&site=hospital&mn=112&cate=A
     → 각 진료과의 mn 코드 + catename(한글) 추출
  2) 진료과별 의료진 페이지
       /medi_depart/?site=hospital&mn={mn}&type=doctor&catename={URL인코딩 진료과명}
     → <li> 내 actionImg2 카드, 이름/직책/전문분야/주간 진료시간표 + 비고(time_p)
        상세보기 href 에서 dt_idx 추출
  3) 의사 상세 페이지(개별 조회)
       /medi_depart/?site=hospital&mn={mn}&type=doctor_view&catename={진료과명}&dt_idx={id}
     → 동일 정보 + 경력. catename 누락 시 "선택된 진료과가 존재하지 않습니다" 알림.

스케줄:
  - 주간 패턴(<table>): 월~토 × 오전/오후, 진료 셀 = <span class="work2">…</span>
  - 셀 텍스트 비어있어도 <span class="work2"> 가 있으면 진료
  - 비고 <p class="time_p"> 에 격주/내시경 등 부가 텍스트 (예: "금(오전)-내시경")
    → EXCLUDE 키워드(내시경/검사 등) 포함 시 해당 슬롯 제외
  - 날짜별 스케줄 미제공 → date_schedules = []

external_id 포맷: CUH-{mn}-{dt_idx}
  (mn 만으론 진료과 식별 충분, 슬래시 금지)
"""
import re
import asyncio
import logging
import urllib.parse
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)

BASE_URL = "https://hosp.chosun.ac.kr"
DEPT_LIST_URL = f"{BASE_URL}/medi_depart/?type=lists&site=hospital&mn=112&cate=A"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_KO = ("월", "화", "수", "목", "금", "토", "일")
DAY_INDEX = {ko: i for i, ko in enumerate(DAY_KO)}

# 비고에서 EXCLUDE 슬롯 추출 (예: "금(오전)-내시경", "월(오후) 수술", "목요일 오후")
_NOTE_EXCLUDE_RE = re.compile(
    r"([월화수목금토일])(?:요일)?\s*[\(\s]*\s*(오전|오후)\s*\)?"
)


class CuhCrawler:
    """조선대학교병원 (광주) 크롤러."""

    def __init__(self):
        self.hospital_code = "CUH"
        self.hospital_name = "조선대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        self._cached_data: list[dict] | None = None
        self._dept_map: dict[str, str] | None = None  # mn → catename(진료과명)

    # ───────────────────── 공용 ─────────────────────

    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_dept_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        """진료과 목록 페이지에서 {mn: 진료과명} 추출. cate=A(진료과)만."""
        if self._dept_map is not None:
            return self._dept_map

        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[CUH] 진료과 목록 로드 실패: {e}")
            self._dept_map = {}
            return self._dept_map

        soup = BeautifulSoup(resp.text, "html.parser")
        result: dict[str, str] = {}

        # link_zone 의 "진료과 바로가기" 영역(list2) — cate=A 진료과만 모아두는 곳
        # href="/medi_depart/?site=hospital&mn=NNN&type=view&catename=가나다과"
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m_mn = re.search(r"mn=(\d+)", href)
            m_cate = re.search(r"catename=([^&]+)", href)
            if not (m_mn and m_cate and "type=view" in href):
                continue
            mn = m_mn.group(1)
            try:
                catename = urllib.parse.unquote(m_cate.group(1))
            except Exception:
                continue
            # 진료과만(끝이 '과'/'센터' 가 아닌 부서/지원실 제외)
            # cate=A 기준: 진료과는 mn 117~139, 467~475 범위 + 추후 추가 가능.
            # 텍스트(`<span>`) 가 명확히 한글 진료과명일 때만 포함.
            text = self._clean(a.get_text(" ", strip=True))
            if not text or text != catename:
                continue
            # 진료지원부서/전문진료센터/직원게시판 등 제외
            if any(skip in catename for skip in
                   ("부서", "행정", "수련부", "총무", "간호부", "약제부",
                    "은행", "IRB", "사회사업", "센터", "팀", "실")):
                continue
            # 진료과만 (이름이 '과' 또는 '의학' 으로 끝나거나 일반 진료과)
            result[mn] = catename

        self._dept_map = result
        logger.info(f"[CUH] 진료과 {len(result)}개 추출")
        return result

    # ───────────────────── 표 파싱 ─────────────────────

    @staticmethod
    def _is_active_slot(cell) -> bool:
        """<td> 셀이 활성(진료) 인지.

        구조: <td><span class="work2"></span></td> 가 활성.
        텍스트 ○/● 등이 직접 있어도 인정.
        """
        if cell is None:
            return False
        # span class 확인
        for cls in ("work2", "work1", "work3"):
            if cell.find("span", class_=cls):
                return True
        text = cell.get_text(" ", strip=True)
        if not text:
            return False
        return is_clinic_cell(text)

    @staticmethod
    def _excluded_slots_from_note(note: str) -> set[tuple[int, str]]:
        """비고 텍스트에서 (요일,슬롯) 제외 셋을 만든다.

        규칙:
          - 한 문장(슬래시 `/` 로 구분되는 큰 조각) 안에 EXCLUDE 키워드(내시경/수술/시술/CT 등)
            가 등장하면, 그 문장에 적힌 모든 day(slot) 표기를 제외 처리한다.
          - 예: "* 금(오전)-내시경 ..."          → {(4,'morning')}
          - 예: "※수(오후), 금(오후) - 재진환자시술" → {(2,'afternoon'),(4,'afternoon')}
          - 예: "오전 - (중재시술)월,수,목,금 (초음파)화" — day(slot) 표기 없는 키워드는
                 무시 (이런 케이스는 표 자체에 진료 셀이 없을 가능성이 높음).
        """
        if not note:
            return set()
        result: set[tuple[int, str]] = set()
        # 문장 단위로 분리 (`/`, `·` 등 큰 구분자만 사용해 짧게 끊지 않는다)
        chunks = re.split(r"[/／·]", note)
        for chunk in chunks:
            if not any(kw in chunk for kw in EXCLUDE_KEYWORDS):
                continue
            for m in _NOTE_EXCLUDE_RE.finditer(chunk):
                day_ko, slot_ko = m.group(1), m.group(2)
                day_idx = DAY_INDEX.get(day_ko)
                if day_idx is None:
                    continue
                slot = "morning" if slot_ko == "오전" else "afternoon"
                result.add((day_idx, slot))
        return result

    def _parse_schedule_table(self, table, note_text: str = "") -> list[dict]:
        """주간 시간표 <table> 파싱.

        헤더(thead) 의 th 중 첫 번째(구분) 제외한 나머지 열이 요일.
        tbody 의 각 tr 첫 th 가 '오전'/'오후', 나머지 td 가 요일별 셀.
        """
        if table is None:
            return []
        # 헤더 요일
        thead = table.find("thead")
        if thead is None:
            return []
        head_ths = thead.find_all("th")
        days: list[int] = []
        for th in head_ths[1:]:
            t = self._clean(th.get_text())
            day_idx = DAY_INDEX.get(t)
            days.append(day_idx if day_idx is not None else -1)
        if not days:
            return []

        excluded = self._excluded_slots_from_note(note_text)

        result: list[dict] = []
        tbody = table.find("tbody")
        if tbody is None:
            return result
        for tr in tbody.find_all("tr"):
            row_th = tr.find("th")
            if row_th is None:
                continue
            slot_label = self._clean(row_th.get_text())
            if "오전" in slot_label:
                slot = "morning"
            elif "오후" in slot_label:
                slot = "afternoon"
            else:
                continue
            start_t, end_t = TIME_RANGES[slot]
            tds = tr.find_all("td")
            for i, td in enumerate(tds):
                if i >= len(days):
                    break
                day_idx = days[i]
                if day_idx is None or day_idx < 0:
                    continue
                if not self._is_active_slot(td):
                    continue
                if (day_idx, slot) in excluded:
                    continue
                result.append({
                    "day_of_week": day_idx,
                    "time_slot": slot,
                    "start_time": start_t,
                    "end_time": end_t,
                    "location": "",
                })
        return result

    # ───────────────────── 카드/리스트 파싱 ─────────────────────

    def _parse_doctor_card(self, li_or_root, mn: str, dept_name: str) -> dict | None:
        """진료과 의료진 페이지의 1명 카드 파싱.

        li_or_root: BeautifulSoup element. <li> 안 .actionImg2 / .box.
        반환: dict (raw fields) 또는 None.
        """
        # 이름 + 직책
        h4 = li_or_root.find("h4")
        if h4 is None:
            return None
        # 첫 h4: "이름 <span>직책</span>"
        position_span = h4.find("span")
        position = self._clean(position_span.get_text()) if position_span else ""
        # 이름은 h4 텍스트 - position 부분
        full_text = self._clean(h4.get_text(" ", strip=True))
        if position and full_text.endswith(position):
            name = self._clean(full_text[: -len(position)])
        else:
            name = full_text
        if not name:
            return None

        # 사진
        photo_url = ""
        img = li_or_root.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("/"):
                src = BASE_URL + src
            photo_url = src

        # 전문분야
        subj = li_or_root.find("p", class_="subject")
        specialty = self._clean(subj.get_text()) if subj else ""

        # dt_idx (상세보기 링크)
        dt_idx = ""
        for a in li_or_root.find_all("a", href=True):
            m = re.search(r"dt_idx=(\d+)", a["href"])
            if m:
                dt_idx = m.group(1)
                break
        if not dt_idx:
            return None

        # 진료시간표
        table = li_or_root.find("table")
        # 비고 (time_p)
        time_p = li_or_root.find("p", class_="time_p")
        note_text = self._clean(time_p.get_text(" ", strip=True)) if time_p else ""
        schedules = self._parse_schedule_table(table, note_text)

        external_id = f"CUH-{mn}-{dt_idx}"
        # profile_url 은 catename 인코딩하여 상세 URL 생성
        catename_enc = urllib.parse.quote(dept_name)
        profile_url = (f"{BASE_URL}/medi_depart/?site=hospital&mn={mn}"
                       f"&type=doctor_view&catename={catename_enc}&dt_idx={dt_idx}")

        return {
            "staff_id": external_id,
            "external_id": external_id,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": note_text,
            "schedules": schedules,
            "date_schedules": [],
            "_mn": mn,
            "_dt_idx": dt_idx,
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, mn: str, dept_name: str
    ) -> list[dict]:
        """한 진료과의 의료진 목록 + 시간표를 가져온다."""
        catename_enc = urllib.parse.quote(dept_name)
        url = (f"{BASE_URL}/medi_depart/?site=hospital&mn={mn}"
               f"&type=doctor&catename={catename_enc}")
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CUH] {dept_name} 의료진 페이지 로드 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        # 의료진은 ul.dep_li > li > div.box.actionImg2 구조
        results: list[dict] = []
        ul = soup.find("ul", class_="dep_li")
        if ul is None:
            return results
        for li in ul.find_all("li", recursive=False):
            try:
                doc = self._parse_doctor_card(li, mn, dept_name)
                if doc:
                    results.append(doc)
            except Exception as e:
                logger.debug(f"[CUH] {dept_name} 카드 파싱 오류: {e}")
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

            # 동시 요청 적당히 제한
            sem = asyncio.Semaphore(5)

            async def _job(mn: str, name: str):
                async with sem:
                    return await self._fetch_dept_doctors(client, mn, name)

            tasks = [_job(mn, name) for mn, name in dept_map.items()]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    logger.warning(f"[CUH] 진료과 크롤링 예외: {res}")
                    continue
                for doc in res:
                    eid = doc["external_id"]
                    if eid not in all_doctors:
                        all_doctors[eid] = doc

        result_list = list(all_doctors.values())
        self._cached_data = result_list
        logger.info(f"[CUH] 총 의사 {len(result_list)}명 수집")
        return result_list

    # ───────────────────── 표준 인터페이스 ─────────────────────

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            dept_map = await self._fetch_dept_map(client)
        return [{"code": mn, "name": name} for mn, name in dept_map.items()]

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
        """개별 교수 1명만 네트워크 조회. _fetch_all 절대 호출하지 않음."""
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

        # external_id 파싱 — "CUH-{mn}-{dt_idx}"
        prefix = f"{self.hospital_code}-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-")
        if len(parts) < 2:
            logger.warning(f"[CUH] external_id 형식 오류: {staff_id}")
            return empty
        mn, dt_idx = parts[0], parts[1]

        async with self._make_client() as client:
            # mn → catename 매핑 가져오기
            dept_map = await self._fetch_dept_map(client)
            dept_name = dept_map.get(mn, "")
            if not dept_name:
                logger.warning(f"[CUH] mn={mn} 진료과 매핑 없음 (staff_id={staff_id})")
                return empty

            catename_enc = urllib.parse.quote(dept_name)
            url = (f"{BASE_URL}/medi_depart/?site=hospital&mn={mn}"
                   f"&type=doctor_view&catename={catename_enc}&dt_idx={dt_idx}")
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[CUH] 개별 조회 실패 {staff_id}: {e}")
                return empty

            html = resp.text
            # 알림 페이지(작은 응답) 인지 확인
            if len(html) < 2000 and "선택된 진료과가 존재하지 않습니다" in html:
                logger.warning(f"[CUH] 개별 조회 알림 페이지: {staff_id}")
                return empty

            soup = BeautifulSoup(html, "html.parser")
            wrap = soup.find("div", class_="profile_wrap")
            if wrap is None:
                logger.warning(f"[CUH] profile_wrap 없음: {staff_id}")
                return empty

            # 이름/직책
            name_p = wrap.find("p", class_="pro_name")
            name = ""
            position = ""
            if name_p:
                pos_span = name_p.find("span")
                position = self._clean(pos_span.get_text()) if pos_span else ""
                full = self._clean(name_p.get_text(" ", strip=True))
                if position and full.endswith(position):
                    name = self._clean(full[: -len(position)])
                else:
                    name = full

            # 진료과
            dep_p = wrap.find("p", class_="pro_dep")
            department = self._clean(dep_p.get_text()) if dep_p else dept_name

            # 전문분야
            sub_p = wrap.find("p", class_="pro_subject")
            specialty = self._clean(sub_p.get_text()) if sub_p else ""

            # 사진
            photo_url = ""
            img = wrap.find("img")
            if img and img.get("src"):
                src = img["src"]
                if src.startswith("/"):
                    src = BASE_URL + src
                photo_url = src

            # 진료시간표
            table = wrap.find("table")
            time_p = wrap.find("p", class_="time_p")
            note_text = self._clean(time_p.get_text(" ", strip=True)) if time_p else ""
            schedules = self._parse_schedule_table(table, note_text)

            return {
                "staff_id": staff_id,
                "name": name,
                "department": department,
                "position": position,
                "specialty": specialty,
                "profile_url": url,
                "photo_url": photo_url,
                "notes": note_text,
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

"""인천성모병원 크롤러

HTML 파싱 기반 크롤러. cmcism.or.kr 도메인 사용.
이전 CMC JSON API가 아닌 서버사이드 렌더링 HTML 파싱 방식.

API:
  진료과 목록: GET /treatment/treatment_list → <a href="/treatment/treatment_info?deptSeq={seq}"> 파싱
  의료진 목록: GET /treatment/doctor_list?schType=dprtmnt&keyword={deptSeq} → 의사 카드 파싱
  의료진 상세: GET /treatment/doctor_list 페이지 내 layer_pop_{seq} 모달에서 스케줄 파싱

스케줄 테이블 구조 (모달 내):
  <table>
    <tr><td>월</td><td>화</td>...<td>토</td></tr>
    <tr><td colspan="6">오전</td></tr>
    <tr><td colspan="6">오후</td></tr>
  </table>
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cmcism.or.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class CmcincheonCrawler:
    """인천성모병원 크롤러"""

    def __init__(self):
        self.hospital_code = "CMCIC"
        self.hospital_name = "인천성모병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL,
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 (HTML 파싱)"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{BASE_URL}/treatment/treatment_list")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts = []
                seen = set()

                # 방법 1: deptSeq 파라미터가 있는 링크 파싱
                for link in soup.select("a[href*='deptSeq=']"):
                    href = link.get("href", "")
                    name = link.get_text(strip=True)
                    m = re.search(r"deptSeq=(\d+)", href)
                    if m and name:
                        code = m.group(1)
                        if code not in seen:
                            depts.append({"code": code, "name": name})
                            seen.add(code)

                # 방법 2: select option에서 파싱
                if not depts:
                    for option in soup.select("select option"):
                        code = option.get("value", "").strip()
                        name = option.get_text(strip=True)
                        if code and name and code not in seen and code not in ("", "0"):
                            depts.append({"code": code, "name": name})
                            seen.add(code)

                logger.info(f"[CMCIC] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[CMCIC] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 의료진 목록 (전체 페이지 순회) ───

    async def _fetch_all_doctors_page(
        self, client: httpx.AsyncClient, page: int = 1,
        sch_type: str = "", keyword: str = "",
    ) -> tuple[list[dict], int]:
        """의료진 목록 한 페이지 파싱, (doctors, total_pages) 반환"""
        params = {
            "page": str(page),
            "limit": "10",
            "schType": sch_type,
            "keyword": keyword,
        }
        try:
            resp = await client.get(
                f"{BASE_URL}/treatment/doctor_list", params=params,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[CMCIC] 의료진 목록 페이지 {page} 실패: {e}")
            return [], 0

        soup = BeautifulSoup(resp.text, "html.parser")
        doctors = self._parse_doctor_cards(soup)

        # 페이지네이션에서 마지막 페이지 추출
        total_pages = page
        for a in soup.select("a[href*='page=']"):
            href = a.get("href", "")
            m = re.search(r"page=(\d+)", href)
            if m:
                p = int(m.group(1))
                if p > total_pages:
                    total_pages = p

        return doctors, total_pages

    def _parse_doctor_cards(self, soup: BeautifulSoup) -> list[dict]:
        """HTML에서 의사 카드 파싱

        실제 HTML 구조 (div.team_dv):
          <div class="team_dv">
            <a class="btn_open img" id="btn_open_599"><img.../></a>
            <div class="right_view">
              <p class="p_h">
                <a class="btn_open" id="btn_open_599">황선욱</a>
                <span class="ok">과장</span>
                [소속:가정의학과]
              </p>
              <p class="job"><b>전문분야</b> 만성질환, ...</p>
              <a class="btn_open btn01" id="btn_open_599">자세히 보기</a>
            </div>
          </div>
        """
        doctors = []
        seen_seqs = set()

        # div.team_dv 카드 파싱
        cards = soup.select("div.team_dv")
        if not cards:
            # 폴백: right_view 직접 탐색
            cards = soup.select("div.right_view")

        for card in cards:
            # seq 추출: btn_open_{seq} ID에서
            seq = ""
            for a_tag in card.select("a[id^='btn_open_']"):
                seq = a_tag.get("id", "").replace("btn_open_", "")
                if seq:
                    break
            if not seq or seq in seen_seqs:
                continue
            seen_seqs.add(seq)

            # 이름 추출: p.p_h 내 a.btn_open 텍스트 (이미지가 아닌 텍스트 링크)
            name = ""
            p_h = card.select_one("p.p_h")
            if p_h:
                for a_tag in p_h.select("a.btn_open"):
                    txt = a_tag.get_text(strip=True)
                    if txt and txt != "자세히 보기" and not a_tag.select_one("img"):
                        if re.search(r'[가-힣]{2,}', txt):
                            name = txt
                            break

            # 폴백: img alt
            if not name:
                img = card.select_one("img[alt]")
                if img:
                    alt = img.get("alt", "").strip()
                    alt_clean = re.sub(r'\s*(이미지|교수|전문의|과장|원장|프로필)\s*$', '', alt).strip()
                    if alt_clean and re.fullmatch(r'[가-힣]{2,5}', alt_clean):
                        name = alt_clean

            if not name or len(name) < 2:
                continue

            # 직위: span.ok
            position = ""
            pos_el = card.select_one("span.ok, span.position")
            if pos_el:
                position = pos_el.get_text(strip=True)

            # 진료과: [소속:XXX] 텍스트
            department = ""
            if p_h:
                p_h_text = p_h.get_text(strip=True)
                m = re.search(r'\[소속\s*:\s*([^\]]+)\]', p_h_text)
                if m:
                    department = m.group(1).strip()

            # 전문분야: p.job 텍스트에서 "전문분야" 제거
            specialty = ""
            job_el = card.select_one("p.job")
            if job_el:
                job_text = job_el.get_text(strip=True)
                specialty = re.sub(r'^전문분야\s*:?\s*', '', job_text).strip()

            # 스케줄: 모달(layer_pop_{seq})에서 파싱
            schedules = []
            modal = soup.select_one(f"#layer_pop_{seq}")
            if modal:
                schedules = self._parse_schedule_table(modal)
                # 스케줄 테이블이 비어있으면 ul.day_icon 텍스트에서 파싱
                if not schedules:
                    schedules = self._parse_schedule_from_text(modal)

            ext_id = f"CMCIC-{seq}"
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": department,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/treatment/doctor_list",
                "notes": "",
                "schedules": schedules,
                "_seq": seq,
            })

        return doctors

    def _parse_schedule_from_text(self, container) -> list[dict]:
        """ul.day_icon 등 텍스트에서 스케줄 파싱

        예: "수(오후) 자문형호스피스 진료", "월(오전) 가정의학과"
        """
        schedules = []
        seen = set()
        text_els = container.select("ul.day_icon li, p, span")
        for el in text_els:
            text = el.get_text(strip=True)
            for day_char, dow in DAY_MAP.items():
                # "월(오전)", "수(오후)" 패턴
                m = re.search(rf'{day_char}\s*\(\s*(오전|오후)\s*\)', text)
                if m:
                    slot = "morning" if m.group(1) == "오전" else "afternoon"
                    key = (dow, slot)
                    if key not in seen:
                        seen.add(key)
                        start, end = TIME_RANGES[slot]
                        schedules.append({
                            "day_of_week": dow,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })
        return schedules

    def _parse_schedule_table(self, container) -> list[dict]:
        """컨테이너(모달 등) 내 스케줄 테이블 파싱"""
        schedules = []
        seen = set()

        tables = container.select("table")
        for table in tables:
            rows = table.select("tr")
            if not rows:
                continue

            # 헤더에서 요일 칼럼 매핑
            col_to_dow = {}
            header_row = rows[0]
            header_cells = header_row.select("th, td")
            for ci, cell in enumerate(header_cells):
                text = cell.get_text(strip=True)
                for day_char, dow in DAY_MAP.items():
                    if day_char in text:
                        col_to_dow[ci] = dow
                        break

            if not col_to_dow:
                continue

            # 오전/오후 행 파싱
            for row in rows[1:]:
                cells = row.select("th, td")
                if not cells:
                    continue

                first_text = cells[0].get_text(strip=True)
                if "오전" in first_text:
                    slot = "morning"
                elif "오후" in first_text:
                    slot = "afternoon"
                else:
                    continue

                for ci, cell in enumerate(cells):
                    if ci not in col_to_dow:
                        continue
                    dow = col_to_dow[ci]

                    text = cell.get_text(strip=True)
                    classes = cell.get("class", [])

                    has_schedule = False
                    if any(c in classes for c in ("on", "active", "check", "Y")):
                        has_schedule = True
                    elif text and text not in ("", "-", "X", "x", "휴진", "휴"):
                        has_schedule = True
                    elif cell.select("i, img, span.on, span.check"):
                        has_schedule = True

                    if has_schedule:
                        key = (dow, slot)
                        if key not in seen:
                            seen.add(key)
                            start, end = TIME_RANGES[slot]
                            schedules.append({
                                "day_of_week": dow,
                                "time_slot": slot,
                                "start_time": start,
                                "end_time": end,
                                "location": "",
                            })

        return schedules

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 의료진 크롤링 (전체 목록 페이지네이션) 후 캐시

        진료과별 검색(`schType=dprtmnt`)은 서버가 빈 결과를 반환하므로,
        전체 목록을 페이지네이션으로 순회합니다. 각 카드에 [소속:진료과] 정보가 포함됨.
        302 rate limiting 방지를 위해 요청 간 딜레이 추가.
        """
        if self._cached_data is not None:
            return self._cached_data

        import asyncio
        all_doctors = {}  # ext_id → doctor dict

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            page = 1
            while True:
                doctors, total_pages = await self._fetch_all_doctors_page(
                    client, page=page,
                )
                for doc in doctors:
                    ext_id = doc["external_id"]
                    if ext_id not in all_doctors:
                        all_doctors[ext_id] = doc
                if page >= total_pages or not doctors:
                    break
                page += 1
                await asyncio.sleep(1)  # rate limiting 방지

        result = list(all_doctors.values())
        logger.info(f"[CMCIC] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환"""
        depts = await self._fetch_departments()
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """교수 목록 (스케줄 제외)"""
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "position": d["position"],
                "specialty": d["specialty"],
                "profile_url": d["profile_url"],
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        # 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            return empty

        # 전체 크롤링 후 조회
        data = await self._fetch_all()
        for d in data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return self._to_schedule_dict(d)

        return empty

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d["name"],
            "department": d["department"],
            "position": d.get("position", ""),
            "specialty": d["specialty"],
            "profile_url": d["profile_url"],
            "notes": d.get("notes", ""),
            "schedules": d["schedules"],
        }

    async def crawl_doctors(self, department: str = None):
        """전체 크롤링 (CrawlResult 반환)"""
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d.get("position", ""),
                specialty=d["specialty"],
                profile_url=d["profile_url"],
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

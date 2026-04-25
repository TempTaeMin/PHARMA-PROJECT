"""부천세종병원(Bucheon Sejong Hospital) 크롤러

공식명: 부천세종병원
홈페이지: https://bucheon.sejongh.co.kr
기술: 정적 HTML + AJAX POST (httpx + BeautifulSoup)

구조:
  1) 진료과 목록 HTML: /medical_part/part?cate1=214&cate2=216&html_mode=text&Depth=2
     → a[href*="/medical_part/part_01?"] 에서 depthngnm=이름 & orddeptcd=코드 추출
  2) 진료과별 의료진 목록 (AJAX POST):
     POST /adm/adm_boardProc.php
       board_id=doctors_team, mode=2, orddeptcd={진료과코드}, idx={임의값}
     → div.item 블록, h3>b=이름, /data/doctor/..=사진, p(첫번째 f_16)=진료과,
        진료분야 텍스트, href="…orddrid={원내코드}…"
  3) 의료진 상세 + 월간 스케줄 HTML:
     GET /medical_part/part_01_detail?orddeptcd={코드}&orddrid={원내코드}
     → section.doctor_schedule_area 안 div.ds_slider > div.item 반복
       표 구조: 1행=헤더(th에 "월<br>06" 형식),
               2행=오전(td), 3행=오후(td)
       각 td에 <span>O</span> 있으면 진료, 빈칸이면 휴무

external_id: BCSEJONG-{orddeptcd}-{orddrid}
  — 동일 의사가 여러 진료과에 노출될 수 있으므로 진료과 코드도 포함
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, date
from urllib.parse import unquote

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://bucheon.sejongh.co.kr"
DEPT_LIST_URL = f"{BASE_URL}/medical_part/part?cate1=214&cate2=216&html_mode=text&Depth=2"
TEAM_PAGE_URL = f"{BASE_URL}/medical_part/team?cate1=214&cate2=255&html_mode=text&Depth=2"
DOCTOR_LIST_AJAX_URL = f"{BASE_URL}/adm/adm_boardProc.php"
DETAIL_URL = f"{BASE_URL}/medical_part/part_01_detail"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

# orddrid=XXXX, orddeptcd=XXXX 패턴
ORDDRID_RE = re.compile(r"orddrid=(\d+)")
ORDDEPTCD_RE = re.compile(r"orddeptcd=(\d+)")
# 진료과 목록: depthngnm={이름}&orddeptcd={코드}
DEPT_LINK_RE = re.compile(r"depthngnm=([^&]+)&orddeptcd=(\d+)")
# 월간 스케줄 헤더: "목<br>02" / "목02"
HEADER_DAY_RE = re.compile(r"^([월화수목금토일])\s*0*(\d{1,2})")


class BcsejongCrawler:
    """부천세종병원 크롤러"""

    def __init__(self):
        self.hospital_code = "BCSEJONG"
        self.hospital_name = "부천세종병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL + "/",
        }
        self._cached_data: list[dict] | None = None
        self._cached_depts: list[dict] | None = None

    # ─────────────────────────── client helpers ───────────────────────────
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─────────────────────────── 진료과 ───────────────────────────
    async def _fetch_departments(self, client: httpx.AsyncClient) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[BCSEJONG] 진료과 목록 로드 실패: {e}")
            return []

        html = resp.text
        depts: list[dict] = []
        seen: set[str] = set()
        for m in DEPT_LINK_RE.finditer(html):
            raw_name = unquote(m.group(1))
            code = m.group(2)
            name = raw_name.strip()
            if not name or not code or code in seen:
                continue
            seen.add(code)
            depts.append({"code": code, "name": name})

        self._cached_depts = depts
        logger.info(f"[BCSEJONG] 진료과 {len(depts)}개")
        return depts

    # ─────────────────────────── 진료과별 의료진 ───────────────────────────
    async def _fetch_doctors_by_dept(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """AJAX POST → 의료진 목록 HTML fragment 파싱."""
        headers = {
            **self.headers,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": TEAM_PAGE_URL,
            "Origin": BASE_URL,
        }
        data = {
            "board_id": "doctors_team",
            "idx": "1",           # 탭 인덱스 — 진료과는 사용되지 않지만 원 스크립트 호환
            "orddeptcd": dept_code,
            "mode": "2",
        }
        try:
            resp = await client.post(DOCTOR_LIST_AJAX_URL, headers=headers, data=data)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[BCSEJONG] {dept_name}({dept_code}) 의사목록 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        doctors: list[dict] = []
        for item in soup.select("div.item"):
            info = item.select_one("div.doctor_info")
            if info is None:
                continue
            name_el = info.select_one("h3 b") or info.select_one("h3")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue

            # 첫번째 <p class="f_16 txc_bk pdt_15"> 가 진료과 (목록상)
            dept_el = info.find("p", class_=lambda c: c and "f_16" in c and "txc_bk" in c)
            shown_dept = dept_el.get_text(strip=True) if dept_el else dept_name

            # 진료분야 — "진료분야" 라벨 다음 p
            specialty = ""
            p_tags = info.find_all("p")
            for idx, p in enumerate(p_tags):
                if p.get_text(strip=True) == "진료분야" and idx + 1 < len(p_tags):
                    specialty = p_tags[idx + 1].get_text(" ", strip=True)
                    break

            # 상세 링크에서 orddrid 추출
            detail_a = item.select_one('a[href*="part_01_detail"]')
            href = detail_a.get("href", "") if detail_a else ""
            m_drid = ORDDRID_RE.search(href)
            orddrid = m_drid.group(1) if m_drid else ""
            if not orddrid:
                # 진료예약 링크로 폴백
                res_a = item.select_one('a[href*="orddrid="]')
                if res_a:
                    m_drid2 = ORDDRID_RE.search(res_a.get("href", ""))
                    if m_drid2:
                        orddrid = m_drid2.group(1)
            if not orddrid:
                continue

            # 사진
            photo_url = ""
            img = item.select_one("div.profile img")
            if img and img.get("src"):
                src = img["src"]
                photo_url = src if src.startswith("http") else BASE_URL + src

            profile_url = (
                f"{DETAIL_URL}?orddeptcd={dept_code}&orddrid={orddrid}"
                f"&cate1=214&cate2=216"
            )

            ext_id = f"{self.hospital_code}-{dept_code}-{orddrid}"
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": shown_dept or dept_name,
                "position": "",           # 목록에서 직책 미노출
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "orddrid": orddrid,
                "orddeptcd": dept_code,
            })
        return doctors

    # ─────────────────────────── 개별 교수 스케줄 파싱 ───────────────────────────
    def _parse_schedule_html(self, html: str) -> tuple[list[dict], list[dict], dict]:
        """
        상세 페이지 HTML에서:
          - schedules (주간 패턴, 요일별 오전/오후)
          - date_schedules (날짜별, 금월 이후 3개월치)
          - meta: {name, department, specialty, notes}
        """
        soup = BeautifulSoup(html, "html.parser")

        # 메타: 상단 h2 구조 "<span>{과}</span><br><strong>{이름}</strong>"
        meta = {"name": "", "department": "", "specialty": "", "notes": ""}
        h2 = soup.select_one("section.doctor_area h2")
        if h2 is None:
            h2 = soup.select_one("div.doctor_info h2") or soup.select_one("h2")
        if h2:
            strong = h2.find("strong")
            if strong:
                meta["name"] = strong.get_text(strip=True)
            sp = h2.find("span")
            if sp:
                meta["department"] = sp.get_text(strip=True)

        # 전문분야 — "전문분야" 라벨 다음 p
        for p in soup.select("div.d_subject p"):
            if p.get_text(strip=True) == "전문분야":
                nxt = p.find_next_sibling("p")
                if nxt:
                    meta["specialty"] = nxt.get_text(" ", strip=True)
                    break

        # 월간 스케줄 테이블들 수집
        today = date.today()
        date_schedules: list[dict] = []
        weekly_seen: set[tuple[int, str]] = set()
        schedules: list[dict] = []

        slider = soup.select_one("section.doctor_schedule_area div.ds_slider")
        if slider is None:
            return schedules, date_schedules, meta

        items = slider.select("div.item")
        if not items:
            return schedules, date_schedules, meta

        # 현재 보이는 월: id="slick_month" (e.g. "4월")
        cur_month_el = soup.select_one("#slick_month")
        start_month = today.month
        if cur_month_el:
            cur_txt = cur_month_el.get_text(strip=True)
            mm = re.search(r"(\d{1,2})\s*월", cur_txt)
            if mm:
                start_month = int(mm.group(1))

        # 연도 산출: 첫 item이 current month, 이후 item들은 다음달(년도 넘어가면 증가)
        # 슬라이더에 표시된 월 순서대로 연·월 부여
        months_context: list[tuple[int, int]] = []   # [(year, month), ...]
        year = today.year if start_month >= today.month else today.year + 1
        cur_m = start_month
        cur_y = year
        for _ in items:
            months_context.append((cur_y, cur_m))
            cur_m += 1
            if cur_m > 12:
                cur_m = 1
                cur_y += 1

        horizon_end_month = (today.month + 2)  # 3개월: 오늘 월 포함 +2
        horizon_end_year = today.year
        while horizon_end_month > 12:
            horizon_end_month -= 12
            horizon_end_year += 1

        def _within_horizon(y: int, m: int) -> bool:
            if y < today.year:
                return False
            if y == today.year and m < today.month:
                return False
            if y > horizon_end_year:
                return False
            if y == horizon_end_year and m > horizon_end_month:
                return False
            return True

        for (y, m), item in zip(months_context, items):
            table = item.find("table")
            if table is None:
                continue
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # 헤더 파싱 — th들 각각 "{요일}\n{일자}"
            header_cells = rows[0].find_all(["th", "td"])
            # 첫 번째 th 는 라벨 공백 → skip
            day_infos: list[tuple[int, int] | None] = [None]
            for th in header_cells[1:]:
                raw = th.get_text(" ", strip=True).replace("\n", " ")
                raw = re.sub(r"\s+", "", raw)
                hmatch = HEADER_DAY_RE.match(raw)
                if hmatch:
                    dow = DAY_MAP.get(hmatch.group(1))
                    dd = int(hmatch.group(2))
                    if dow is not None and 1 <= dd <= 31:
                        day_infos.append((dow, dd))
                        continue
                day_infos.append(None)

            for slot_name, row_idx in (("morning", 1), ("afternoon", 2)):
                if row_idx >= len(rows):
                    continue
                slot_cells = rows[row_idx].find_all("td")
                # 첫 칸은 "오전"/"오후" 라벨
                for col_idx, cell in enumerate(slot_cells[1:], start=1):
                    if col_idx >= len(day_infos):
                        break
                    info = day_infos[col_idx]
                    if info is None:
                        continue
                    dow, dd = info
                    cell_text = cell.get_text(" ", strip=True)
                    has_mark = cell.find("span") is not None and bool(
                        cell.find("span").get_text(strip=True)
                    )
                    active = has_mark or is_clinic_cell(cell_text)
                    if not active:
                        continue

                    start, end = TIME_RANGES[slot_name]

                    # 날짜별
                    try:
                        d_obj = date(y, m, dd)
                    except ValueError:
                        d_obj = None

                    if d_obj is not None and _within_horizon(y, m) and d_obj >= today:
                        date_schedules.append({
                            "schedule_date": d_obj.isoformat(),
                            "time_slot": slot_name,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                            "status": "진료",
                        })

                    # 주간 패턴 (중복 제거)
                    key = (dow, slot_name)
                    if dow < 6 and key not in weekly_seen:   # 월~토만 의미 있음
                        weekly_seen.add(key)
                        schedules.append({
                            "day_of_week": dow,
                            "time_slot": slot_name,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })

        # 주간 정렬
        schedules.sort(key=lambda s: (s["day_of_week"], 0 if s["time_slot"] == "morning" else 1))
        return schedules, date_schedules, meta

    async def _fetch_doctor_detail(
        self, client: httpx.AsyncClient, orddeptcd: str, orddrid: str
    ) -> tuple[list[dict], list[dict], dict]:
        url = (
            f"{DETAIL_URL}?orddeptcd={orddeptcd}&orddrid={orddrid}"
            f"&cate1=214&cate2=216"
        )
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[BCSEJONG] 상세 로드 실패 {orddeptcd}/{orddrid}: {e}")
            return [], [], {"name": "", "department": "", "specialty": "", "notes": ""}
        return self._parse_schedule_html(resp.text)

    # ─────────────────────────── 전체 크롤링 ───────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
            if not depts:
                self._cached_data = []
                return []

            # 1) 각 진료과별 의사 목록 수집
            sem_list = asyncio.Semaphore(5)

            async def _load_dept(d):
                async with sem_list:
                    return await self._fetch_doctors_by_dept(client, d["code"], d["name"])

            dept_doctors = await asyncio.gather(
                *[_load_dept(d) for d in depts], return_exceptions=True
            )

            by_ext: dict[str, dict] = {}
            for dd in dept_doctors:
                if isinstance(dd, Exception):
                    logger.warning(f"[BCSEJONG] 진료과 처리 예외: {dd}")
                    continue
                for doc in dd:
                    ext = doc["external_id"]
                    if ext not in by_ext:
                        by_ext[ext] = doc

            # 2) 상세 페이지에서 스케줄 수집 — 의사별 1회
            sem_detail = asyncio.Semaphore(6)

            async def _load_detail(doc):
                async with sem_detail:
                    schedules, date_schedules, meta = await self._fetch_doctor_detail(
                        client, doc["orddeptcd"], doc["orddrid"]
                    )
                    doc["schedules"] = schedules
                    doc["date_schedules"] = date_schedules
                    # 상세에서 더 정확한 이름/과 있으면 덮어쓰기
                    if meta.get("name"):
                        doc["name"] = meta["name"]
                    if meta.get("department"):
                        doc["department"] = meta["department"]
                    if meta.get("specialty") and not doc.get("specialty"):
                        doc["specialty"] = meta["specialty"]
                    return doc

            await asyncio.gather(
                *[_load_detail(doc) for doc in by_ext.values()], return_exceptions=True
            )

            # 스케줄 로딩 실패한 경우 빈 리스트 보장
            for doc in by_ext.values():
                doc.setdefault("schedules", [])
                doc.setdefault("date_schedules", [])

        result = list(by_ext.values())
        logger.info(f"[BCSEJONG] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─────────────────────────── 공개 인터페이스 ───────────────────────────
    async def get_departments(self) -> list[dict]:
        """진료과 목록 (code=orddeptcd, name=진료과명)."""
        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
        return depts

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """경량 의사 목록 (스케줄 제외)."""
        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
            targets = depts
            if department:
                targets = [d for d in depts if d["name"] == department or d["code"] == department]
                if not targets:
                    return []

            sem = asyncio.Semaphore(5)

            async def _load(d):
                async with sem:
                    return await self._fetch_doctors_by_dept(client, d["code"], d["name"])

            results = await asyncio.gather(*[_load(d) for d in targets], return_exceptions=True)

        merged: dict[str, dict] = {}
        for r in results:
            if isinstance(r, Exception):
                continue
            for doc in r:
                merged.setdefault(doc["external_id"], doc)

        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "position": d.get("position", ""),
                "specialty": d.get("specialty", ""),
                "profile_url": d.get("profile_url", ""),
                "notes": d.get("notes", ""),
            }
            for d in merged.values()
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 상세 — 해당 1명만 조회 (skill 규칙 #7 준수)."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 내 캐시 재사용
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

        # external_id 포맷: BCSEJONG-{orddeptcd}-{orddrid}
        prefix = f"{self.hospital_code}-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-")
        if len(parts) < 2:
            return empty
        orddeptcd, orddrid = parts[0], parts[1]

        async with self._make_client() as client:
            schedules, date_schedules, meta = await self._fetch_doctor_detail(
                client, orddeptcd, orddrid
            )

        if not meta.get("name") and not schedules and not date_schedules:
            return empty

        profile_url = (
            f"{DETAIL_URL}?orddeptcd={orddeptcd}&orddrid={orddrid}"
            f"&cate1=214&cate2=216"
        )
        return {
            "staff_id": staff_id,
            "name": meta.get("name", ""),
            "department": meta.get("department", ""),
            "position": "",
            "specialty": meta.get("specialty", ""),
            "profile_url": profile_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": date_schedules,
        }

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
                schedules=d.get("schedules", []),
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

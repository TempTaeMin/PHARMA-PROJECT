"""청구성심병원(CGSS) 크롤러

병원 공식명: 의료법인 청구성심병원 (서울 은평구 갈현동)
홈페이지: www.cgss.co.kr  (PHP 정적 HTML, UTF-8)

구조:
  1) 진료과 인덱스: /page.php?pageIndex=130101 — 서브메뉴에 13XXXX 코드 14개
  2) 진료과별 의사 목록: /page.php?pageIndex=130XXX
     - `div.doctor-section .doctor-list` 반복. 각 카드:
       - `.img img src="./data/file/doctor/{docid_hash}_{slug}.jpg"` — 사진
       - `.info strong` — 직책 상위 수식어 ("주임 과장")
       - `.info h4` — "홍길동 <em>원장</em>"  (이름 + 직책)
       - `.info .doctor-txt` — specialty
       - `.info .more a href="/page/doctor_v.php?doctor_id={N}"` — 상세
  3) 의사 상세 + 월간 스케줄: /page/doctor_v.php?doctor_id={N}&year=YYYY&month=MM
     - `article#mDoctor h5` — 예: "내과 전문의"
     - `h4` — 이름 + span 직책
     - `.doctor-txt` — specialty
     - `.calendar table` — 4행: [라벨, 날짜들, 요일들, 오전/오후]
        - 오전/오후 셀 span.i1 = 진료, i2 = 수술/검사, i3 = 휴진, (빈 class) = 해당없음

external_id: CGSS-{doctor_id}  (doctor_v.php 의 doctor_id 숫자. 전역 유일)
"""
import re
import logging
import asyncio
import calendar as _cal
from datetime import datetime, date
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "http://www.cgss.co.kr"

# (pageIndex, dept_name)  — 공식 진료과 14개 (130101 index 제외)
DEPT_PAGES = [
    (130102, "내분비/다질환내과"),
    (130103, "소화기내과"),
    (130104, "호흡기내과"),
    (130105, "심장내과"),
    (130106, "정형외과"),
    (130107, "외과"),
    (130108, "신경과"),
    (130110, "비뇨의학과"),
    (130112, "소아청소년과"),
    (130113, "응급의학과"),
    (130114, "마취통증의학과"),
    (130115, "영상의학과"),
    (130116, "진단검사의학과"),
    (130119, "신장내과"),
]

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}
_DOCTOR_ID_RE = re.compile(r"doctor_id=(\d+)")
_WEEKDAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


class CgssCrawler:
    def __init__(self):
        self.hospital_code = "CGSS"
        self.hospital_name = "청구성심병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None

    # ─── 파싱 유틸 ───

    @staticmethod
    def _decode(resp: httpx.Response) -> str:
        """응답 본문을 UTF-8 로 디코드 (헤더 선언 우선, 폴백 euc-kr)"""
        try:
            return resp.content.decode("utf-8")
        except UnicodeDecodeError:
            return resp.content.decode("euc-kr", errors="replace")

    @staticmethod
    def _parse_name_position_from_h4(h4) -> tuple[str, str]:
        if h4 is None:
            return "", ""
        em = h4.find(["em", "span"])
        position = em.get_text(strip=True) if em else ""
        # h4 전체 텍스트에서 em 영역 제거
        text = h4.get_text(" ", strip=True)
        if position:
            text = text.replace(position, "").strip()
        m = re.search(r"([가-힣]{2,4})", text)
        name = m.group(1) if m else text
        return name, position

    def _parse_calendar_table(self, table, year: int, month: int) -> tuple[list[dict], list[dict]]:
        """달력 테이블 → (weekly_pattern, date_schedules)

        달력 4행: [헤더셀] / [날짜들] / [요일들] / [오전] / [오후] — 첫 셀은 rowspan 라벨,
        두 번째 행부터 td.td_0~6 반복. td 내 span.i1=진료 i2=수술/검사 i3=휴진.
        """
        date_schedules: list[dict] = []
        if table is None:
            return [], []
        trs = table.find_all("tr")
        if len(trs) < 4:
            return [], []

        # tr[0]: 라벨 + 날짜 행, tr[1]: 요일 행, tr[2]: 오전, tr[3]: 오후
        def _collect_dates(tr):
            # td.td_0~td_6 이 날짜. 첫 tr 은 rowspan label td 를 먼저 걸러냄.
            cells = []
            for td in tr.find_all("td"):
                cls = td.get("class") or []
                if any(re.fullmatch(r"td_[0-6]", c) for c in cls):
                    cells.append(td)
            return cells

        date_cells = _collect_dates(trs[0])
        morning_cells = _collect_dates(trs[2])
        afternoon_cells = _collect_dates(trs[3])

        # 날짜 텍스트 → int. 빈 셀은 skip (월초/월말 패딩)
        date_nums: list[int | None] = []
        for td in date_cells:
            t = td.get_text(strip=True)
            date_nums.append(int(t) if t.isdigit() else None)

        def _slot_from_span(td):
            sp = td.find("span")
            if sp is None:
                return None
            cls = sp.get("class") or []
            if "i1" in cls:
                return "진료"
            if "i2" in cls:
                return "수술/검사"
            if "i3" in cls:
                return "휴진"
            return None

        # 날짜별: 해당 날짜에 오전/오후 슬롯 상태
        _, last_day = _cal.monthrange(year, month)
        # dow_counter: weekday 별 working count 집계 → weekly pattern 도출
        weekly_count = {(dow, slot): {"work": 0, "total": 0} for dow in range(7) for slot in ("morning", "afternoon")}

        for idx, day in enumerate(date_nums):
            if day is None or day < 1 or day > last_day:
                continue
            try:
                d = date(year, month, day)
            except ValueError:
                continue
            dow = d.weekday()  # 0=월 ~ 6=일
            for slot_key, cells in (("morning", morning_cells), ("afternoon", afternoon_cells)):
                if idx >= len(cells):
                    continue
                status = _slot_from_span(cells[idx])
                weekly_count[(dow, slot_key)]["total"] += 1
                if status in ("진료", "수술/검사"):
                    weekly_count[(dow, slot_key)]["work"] += 1
                    s, e = TIME_RANGES[slot_key]
                    date_schedules.append({
                        "schedule_date": d.isoformat(),
                        "time_slot": slot_key,
                        "start_time": s,
                        "end_time": e,
                        "location": "",
                        "status": "진료" if status == "진료" else "수술/검사",
                    })

        # weekly pattern: 특정 요일 슬롯에서 과반 이상 진료하면 schedules 에 포함 (월~토만)
        schedules: list[dict] = []
        for (dow, slot_key), cnt in weekly_count.items():
            if dow == 6:  # 일요일 제외
                continue
            if cnt["total"] == 0:
                continue
            if cnt["work"] / cnt["total"] >= 0.5:
                s, e = TIME_RANGES[slot_key]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot_key,
                    "start_time": s,
                    "end_time": e,
                    "location": "",
                })
        schedules.sort(key=lambda x: (x["day_of_week"], x["time_slot"]))
        return schedules, date_schedules

    def _parse_dept_page_for_doctors(self, html: str, dept_name: str) -> list[dict]:
        """진료과 페이지에서 의사 카드 기본 정보만 추출 (스케줄 제외)"""
        soup = BeautifulSoup(html, "html.parser")
        result: list[dict] = []
        for dl in soup.select(".doctor-section .doctor-list"):
            info = dl.select_one(".info")
            if not info:
                continue
            more = info.select_one(".more a")
            href = more.get("href", "") if more else ""
            m = _DOCTOR_ID_RE.search(href)
            if not m:
                continue
            doctor_id = m.group(1)

            name, position = self._parse_name_position_from_h4(info.select_one("h4"))
            if not name:
                continue
            # strong 은 "내과 전문의" 같은 전공 라벨이므로 position 에 합치지 않음

            spec_el = info.select_one(".doctor-txt")
            specialty = spec_el.get_text(" ", strip=True) if spec_el else ""

            img = dl.select_one(".img img")
            img_src = img.get("src", "") if img else ""
            if img_src.startswith("./"):
                img_src = img_src[1:]
            photo_url = f"{BASE_URL}{img_src}" if img_src.startswith("/") else img_src

            ext_id = f"{self.hospital_code}-{doctor_id}"
            profile_url = f"{BASE_URL}/page/doctor_v.php?doctor_id={doctor_id}"
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "_doctor_id": doctor_id,
            })
        return result

    def _parse_doctor_v_meta(self, html: str) -> dict:
        """doctor_v.php 페이지의 이름/직책/전문분야/진료과 메타 정보 추출"""
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one("article#mDoctor") or soup
        h5 = root.find("h5")
        dept = h5.get_text(" ", strip=True) if h5 else ""
        # h5 가 "내과 전문의" 형태면 "전문의" 제거
        dept = re.sub(r"\s*전문의\s*$", "", dept).strip()

        h4 = root.find("h4")
        name, position = self._parse_name_position_from_h4(h4)

        spec_el = root.select_one(".doctor-txt")
        specialty = spec_el.get_text(" ", strip=True) if spec_el else ""

        return {
            "name": name,
            "department": dept,
            "position": position,
            "specialty": specialty,
        }

    # ─── 네트워크 ───

    async def _fetch_dept(
        self, client: httpx.AsyncClient, page_id: int, dept_name: str
    ) -> list[dict]:
        url = f"{BASE_URL}/page.php?pageIndex={page_id}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CGSS] dept {page_id}({dept_name}) 실패: {e}")
            return []
        return self._parse_dept_page_for_doctors(self._decode(resp), dept_name)

    async def _fetch_doctor_schedule(
        self, client: httpx.AsyncClient, doctor_id: str, months: int = 3,
    ) -> tuple[list[dict], list[dict], dict]:
        """의사의 스케줄을 현재 월 ~ months 개월 fetch. (weekly, date_schedules, meta) 반환"""
        today = datetime.now()
        all_schedules: dict[tuple[int, str], dict] = {}
        all_dates: list[dict] = []
        meta: dict = {}
        year, month = today.year, today.month
        for i in range(months):
            url = (f"{BASE_URL}/page/doctor_v.php?doctor_id={doctor_id}"
                   f"&year={year}&month={month:02d}")
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[CGSS] doctor {doctor_id} {year}-{month:02d} 실패: {e}")
                month = month + 1 if month < 12 else 1
                year = year + 1 if month == 1 else year
                continue
            html = self._decode(resp)
            if i == 0:
                meta = self._parse_doctor_v_meta(html)
            soup = BeautifulSoup(html, "html.parser")
            table = soup.select_one(".calendar table")
            weekly, dates = self._parse_calendar_table(table, year, month)
            for s in weekly:
                all_schedules[(s["day_of_week"], s["time_slot"])] = s
            all_dates.extend(dates)
            month = month + 1 if month < 12 else 1
            if month == 1:
                year += 1
        weekly_list = sorted(all_schedules.values(), key=lambda x: (x["day_of_week"], x["time_slot"]))
        return weekly_list, all_dates, meta

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            dept_results = await asyncio.gather(
                *[self._fetch_dept(client, pid, dn) for pid, dn in DEPT_PAGES],
                return_exceptions=True,
            )
            basic_list: list[dict] = []
            for res in dept_results:
                if isinstance(res, Exception):
                    continue
                for d in res:
                    key = d["external_id"]
                    if key in all_doctors:
                        continue
                    all_doctors[key] = d
                    basic_list.append(d)

            # 의사별 스케줄 병렬 fetch (동시성 8 제한)
            sem = asyncio.Semaphore(8)

            async def _fill(doc):
                async with sem:
                    try:
                        weekly, dates, meta = await self._fetch_doctor_schedule(
                            client, doc["_doctor_id"], months=3,
                        )
                    except Exception as e:
                        logger.warning(f"[CGSS] schedule {doc['_doctor_id']} 실패: {e}")
                        weekly, dates, meta = [], [], {}
                doc["schedules"] = weekly
                doc["date_schedules"] = dates
                # meta 로 필드 보강 (진료과는 이미 페이지 컨텍스트가 있으므로 기존 우선)
                if meta.get("position") and not doc.get("position"):
                    doc["position"] = meta["position"]
                if meta.get("specialty") and not doc.get("specialty"):
                    doc["specialty"] = meta["specialty"]

            await asyncio.gather(*[_fill(d) for d in basic_list])

        result = list(all_doctors.values())
        logger.info(f"[CGSS] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        return [{"code": dn, "name": dn} for _, dn in DEPT_PAGES]

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
        """개별 조회 — doctor_id 하나로 doctor_v.php 3개월치만 직접 fetch"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                            else d.get(k, [])
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        prefix = f"{self.hospital_code}-"
        doctor_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        if not doctor_id.isdigit():
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                weekly, dates, meta = await self._fetch_doctor_schedule(
                    client, doctor_id, months=3,
                )
            except Exception as e:
                logger.error(f"[CGSS] 개별 조회 실패 {staff_id}: {e}")
                return empty

        return {
            "staff_id": staff_id,
            "name": meta.get("name", ""),
            "department": meta.get("department", ""),
            "position": meta.get("position", ""),
            "specialty": meta.get("specialty", ""),
            "profile_url": f"{BASE_URL}/page/doctor_v.php?doctor_id={doctor_id}",
            "notes": "",
            "schedules": weekly,
            "date_schedules": dates,
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

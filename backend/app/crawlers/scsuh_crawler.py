"""신천연합병원(Shincheon United Hospital) 크롤러

병원 공식명: 신천연합병원
홈페이지: suh.or.kr
기술: 정적 HTML + AJAX JSON (httpx + BeautifulSoup)
인코딩: EUC-KR

구조:
  1) 진료과 페이지: /hospital_01_{N}.html (N=1..16)
     - 각 페이지에 `div.doc_infobox` 가 0..N개 (대부분 1명, 응급의학과는 5명)
     - doctor_pic, doc_tit(p > text + span=이름), doc_stit1(전문분야), doc_stit2(주요경력)
     - `div[class^="calendar_"]` 에서 doc_idx 추출
  2) 스케줄 AJAX: POST /modules/doctor/doctor_schedule_ajax.php
     - data: doc_idx, sch_year, sch_mon
     - 응답: 월간 달력 HTML (EUC-KR), `ul.days > li.day` 각각 1일
       * first `li.day.type` = 헤더 (`time_1` 오전, `time_2` 오후)
       * `p.r_doctor` = 진료
       * `p.r_closed` = 휴무
       * `p.r_holiday` = 휴일
       * 첫 `<p>` = 오전, 둘째 `<p>` = 오후

external_id: SCSUH-{doc_idx}
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://suh.or.kr"
SCHEDULE_URL = f"{BASE_URL}/modules/doctor/doctor_schedule_ajax.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 진료과 페이지 번호 → 이름 (사이트 nav 기준)
DEPT_PAGES = {
    1: "내과",
    2: "외과",
    3: "신경과",
    4: "신경외과",
    5: "부인과",
    6: "소아청소년과",
    7: "치과",
    8: "영상의학과",
    9: "마취통증의학과",
    10: "진단검사의학과",
    11: "응급의학과",
    12: "가정의학과",
    13: "정신건강의학과",
    14: "성인환자지원과",
    15: "신경외과(세부)",
    16: "통증의료센터",
}

CAL_CLASS_RE = re.compile(r"calendar_(\d+)")


class ScsuhCrawler:
    """신천연합병원 크롤러 — EUC-KR 정적 HTML + JSON AJAX"""

    def __init__(self):
        self.hospital_code = "SCSUH"
        self.hospital_name = "신천연합병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 헬퍼 ───

    @staticmethod
    def _decode(resp: httpx.Response) -> str:
        """EUC-KR 우선, UTF-8 폴백"""
        try:
            return resp.content.decode("euc-kr")
        except UnicodeDecodeError:
            return resp.content.decode("utf-8", errors="replace")

    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    def _parse_dept_page(self, html: str, dept_code: int, dept_name: str) -> list[dict]:
        """1개 진료과 페이지 → 의사 리스트"""
        soup = BeautifulSoup(html, "html.parser")
        doctors: list[dict] = []
        # 각 doc_infobox 를 순회. 바로 뒤 doc_hospi_time 안에 calendar_{doc_idx} 가 있음.
        boxes = soup.select("div.doc_infobox")
        for box in boxes:
            tit = box.select_one("div.doc_tit p")
            if not tit:
                continue
            span = tit.find("span")
            name = self._clean(span.get_text(" ", strip=True)) if span else ""
            if not name:
                continue
            # span 앞 텍스트 = 직책 (예: "전문의", "전문의/과장")
            position = ""
            parts = []
            for node in tit.children:
                if node is span:
                    break
                if isinstance(node, str):
                    parts.append(node)
            position = self._clean(" ".join(parts))

            # 전문분야
            specialty = ""
            stit = box.find("p", class_="doc_stit1")
            if stit is not None:
                nxt = stit.find_next_sibling("p")
                if nxt:
                    specialty = self._clean(nxt.get_text(" ", strip=True))

            # 경력 (notes)
            notes_parts = []
            for cls in ("doc_stit2", "doc_stit4"):
                lbl = box.find("p", class_=cls)
                if lbl is None:
                    continue
                ul = lbl.find_next_sibling("ul")
                if ul is None:
                    continue
                li = ul.find("li")
                if li is None:
                    continue
                txt = li.get_text("\n", strip=True)
                if txt:
                    notes_parts.append(txt)
            notes = "\n\n".join(notes_parts)[:500]

            # 사진
            photo_url = ""
            img = box.select_one("div.doctor_pic img")
            if img:
                src = (img.get("src") or "").strip()
                if src:
                    photo_url = src if src.startswith("http") else f"{BASE_URL}/{src.lstrip('/')}"

            # doc_idx 찾기 — 같은 페이지의 doc_infobox 와 짝지어지는 calendar_ 클래스
            # 각 의사 섹션마다 바로 뒤 doc_hospi_time 이 있고 그 안에 calendar_{N} 이 있음
            doc_idx = ""
            # box 의 부모 컨테이너에서 바로 뒤 doc_hospi_time 탐색
            cursor = box
            for _ in range(6):
                cursor = cursor.find_next_sibling() if cursor else None
                if cursor is None:
                    break
                if cursor.name == "div" and cursor.get("class") and \
                        ("doc_hospi_time" in cursor.get("class")):
                    cal_div = cursor.find(class_=CAL_CLASS_RE)
                    if cal_div:
                        for cls in cal_div.get("class", []):
                            m = CAL_CLASS_RE.match(cls)
                            if m:
                                doc_idx = m.group(1)
                                break
                    break
                # 다음 doc_infobox 를 만나면 중단
                if cursor.name == "div" and cursor.get("class") and \
                        ("doc_infobox" in cursor.get("class")):
                    break

            if not doc_idx:
                # 폴백: 페이지 전체에서 첫 calendar_{N}
                for el in soup.select('[class*="calendar_"]'):
                    for cls in el.get("class", []):
                        m = CAL_CLASS_RE.match(cls)
                        if m:
                            doc_idx = m.group(1)
                            break
                    if doc_idx:
                        break

            if not doc_idx:
                continue

            ext_id = f"SCSUH-{doc_idx}"
            profile_url = f"{BASE_URL}/hospital_01_{dept_code}.html"
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "doc_idx": doc_idx,
                "dept_code": dept_code,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": notes,
                "schedules": [],
                "date_schedules": [],
            })
        return doctors

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_code: int, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/hospital_01_{dept_code}.html"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SCSUH] dept {dept_code}({dept_name}) 로드 실패: {e}")
            return []
        html = self._decode(resp)
        return self._parse_dept_page(html, dept_code, dept_name)

    async def _fetch_month_schedule(self, client: httpx.AsyncClient, doc_idx: str,
                                     year: int, month: int) -> tuple[list[dict], list[dict]]:
        """월간 달력 AJAX → (schedules 요일패턴, date_schedules)"""
        try:
            resp = await client.post(SCHEDULE_URL, data={
                "doc_idx": doc_idx, "sch_year": str(year), "sch_mon": f"{month:02d}",
            })
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SCSUH] 달력 로드 실패 doc={doc_idx} {year}-{month}: {e}")
            return [], []

        html = self._decode(resp)
        soup = BeautifulSoup(html, "html.parser")
        weekly_pattern: set[tuple[int, str]] = set()  # (day_of_week, slot)
        date_sched: list[dict] = []
        today = date.today()

        for li in soup.select("ul.days li.day"):
            classes = li.get("class", [])
            # 헤더 type 행 스킵
            if "type" in classes:
                continue
            if "other-month" in classes:
                continue
            date_el = li.select_one("div.date")
            if not date_el:
                continue
            day_str = date_el.get_text(strip=True)
            if not day_str.isdigit():
                continue
            day = int(day_str)
            try:
                the_date = date(year, month, day)
            except ValueError:
                continue

            dow = the_date.weekday()  # 0=월 ~ 6=일
            event = li.select_one("div.event_wrap")
            if not event:
                continue
            ps = event.find_all("p", recursive=False)
            if not ps:
                continue

            for idx, p in enumerate(ps[:2]):
                cls = p.get("class", [])
                if "r_doctor" not in cls:
                    continue  # closed/holiday/etc → skip
                slot = "morning" if idx == 0 else "afternoon"
                start, end = TIME_RANGES[slot]
                weekly_pattern.add((dow, slot))
                if the_date >= today:
                    date_sched.append({
                        "schedule_date": the_date.isoformat(),
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                        "status": "진료",
                    })

        schedules = [
            {
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": TIME_RANGES[slot][0],
                "end_time": TIME_RANGES[slot][1],
                "location": "",
            }
            for dow, slot in sorted(weekly_pattern)
        ]
        return schedules, date_sched

    async def _fetch_3month_schedule(self, client: httpx.AsyncClient, doc_idx: str) -> tuple[list[dict], list[dict]]:
        """오늘부터 3개월치 달력 수집"""
        today = date.today()
        months: list[tuple[int, int]] = []
        y, m = today.year, today.month
        for _ in range(3):
            months.append((y, m))
            m += 1
            if m > 12:
                m = 1
                y += 1

        results = await asyncio.gather(
            *[self._fetch_month_schedule(client, doc_idx, yy, mm) for yy, mm in months],
            return_exceptions=True,
        )

        weekly_set: set[tuple[int, str]] = set()
        all_dates: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            wk, ds = r
            for s in wk:
                weekly_set.add((s["day_of_week"], s["time_slot"]))
            all_dates.extend(ds)

        schedules = [
            {
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": TIME_RANGES[slot][0],
                "end_time": TIME_RANGES[slot][1],
                "location": "",
            }
            for dow, slot in sorted(weekly_set)
        ]
        # 중복 제거 (같은 날짜+slot)
        seen = set()
        uniq_dates = []
        for d in all_dates:
            k = (d["schedule_date"], d["time_slot"])
            if k in seen:
                continue
            seen.add(k)
            uniq_dates.append(d)
        uniq_dates.sort(key=lambda d: (d["schedule_date"], d["time_slot"]))
        return schedules, uniq_dates

    # ─── 전체 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            dept_results = await asyncio.gather(
                *[self._fetch_dept(client, code, name) for code, name in DEPT_PAGES.items()],
                return_exceptions=True,
            )
            all_doctors: list[dict] = []
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                all_doctors.extend(r)

            # 중복 제거 (같은 doc_idx)
            seen: set[str] = set()
            uniq: list[dict] = []
            for d in all_doctors:
                if d["doc_idx"] in seen:
                    continue
                seen.add(d["doc_idx"])
                uniq.append(d)

            # 각 의사 스케줄 병렬 수집
            async def fill(doc: dict):
                sch, date_sch = await self._fetch_3month_schedule(client, doc["doc_idx"])
                doc["schedules"] = sch
                doc["date_schedules"] = date_sch

            await asyncio.gather(*[fill(d) for d in uniq], return_exceptions=True)

        logger.info(f"[SCSUH] 총 {len(uniq)}명")
        self._cached_data = uniq
        return uniq

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        # 사이트의 모든 진료과 nav 를 고정 맵으로 제공
        return [{"code": str(code), "name": name} for code, name in DEPT_PAGES.items()]

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
        """개별 교수 조회 — doc_idx 만으로 달력 AJAX 직접 호출 (skill 규칙 #7)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        prefix = "SCSUH-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id.isdigit():
            return empty

        # 이름/진료과 등 메타는 이 doc_idx 를 소유한 dept 페이지 1곳에서만 얻음.
        # 모든 dept 페이지를 탐색하지 않도록, doc_idx 만으로 스케줄을 먼저 가져오고
        # 메타 정보는 발견되는 첫 dept 페이지만 fetch.
        async with self._make_client() as client:
            # 스케줄은 doc_idx 만으로 가능
            sched, date_sched = await self._fetch_3month_schedule(client, raw_id)

            # 메타: dept 페이지를 병렬로 훑되 발견 즉시 중단할 수 없으므로 모두 훑는다.
            # dept 페이지는 가벼우므로 허용 범위.
            dept_htmls = await asyncio.gather(
                *[client.get(f"{BASE_URL}/hospital_01_{code}.html")
                  for code in DEPT_PAGES.keys()],
                return_exceptions=True,
            )
            meta = None
            for (code, name), resp in zip(DEPT_PAGES.items(), dept_htmls):
                if isinstance(resp, Exception):
                    continue
                try:
                    html = self._decode(resp)
                except Exception:
                    continue
                for d in self._parse_dept_page(html, code, name):
                    if d["doc_idx"] == raw_id:
                        meta = d
                        break
                if meta:
                    break

        if meta is None:
            # 스케줄은 있는데 메타 없음 — 그래도 스케줄만 반환
            return {
                "staff_id": staff_id, "name": "", "department": "",
                "position": "", "specialty": "",
                "profile_url": f"{BASE_URL}/hospital_01.html",
                "notes": "", "schedules": sched, "date_schedules": date_sched,
            }

        return {
            "staff_id": staff_id,
            "name": meta["name"],
            "department": meta["department"],
            "position": meta["position"],
            "specialty": meta["specialty"],
            "profile_url": meta["profile_url"],
            "notes": meta["notes"],
            "schedules": sched,
            "date_schedules": date_sched,
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

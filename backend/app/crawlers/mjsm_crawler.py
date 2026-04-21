"""명지성모병원(MJSM / Myongji Sungmo Hospital) 크롤러

병원 공식명: 명지성모병원 (서울 영등포구 대림동, 뇌혈관질환 전문병원)
홈페이지: www.myongji-sm.co.kr  (PHP 정적 HTML, UTF-8)

구조:
  1) 진료과/센터 페이지: /index.php/html/{50..65}
     50~62: 14개 기본 진료과
     63: 뇌혈관센터 (50 신경외과 doctors + 추가 혈관중재 전문의)
     64: 통합재활치료센터 (PT 포함 37명 → 중복/비의사 多. **제외**)
     65: 척추관절통증센터 (63/64 doctors 중복)
  2) 각 페이지에 `div.drbox` 의사 카드 반복. 카드:
     - `.drimgs img src="/filedata/md_medical_team/{DT}_{HASH}_{slug}.jpg"` — HASH 가 의사 고유 ID
     - `.drname .t1` (진료과+전문의), `.t2` (이름), `.t3` (직책 회장/원장/과장 등)
     - `.drtxt1 span=이름 + 진료과` (중복)
     - `.drtxt2 span=진료분야 + 전문분야 text`
     - `table.subtable5` — 월~토 × 오전/오후. `<span class="subject_1">진료</span>` = 외래 / `class="subject_"` = 휴진
     - `td.tdtitle2 + td.tdcon2 colspan=6` — 진료 공지 (notes)

external_id: MJSM-{img_hash}  (이미지 파일명의 8자 영숫자 해시 — 전역 유일)
"""
import re
import hashlib
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.myongji-sm.co.kr"

# (page_id, dept_name)
DEPT_PAGES = [
    (50, "신경외과"),
    (51, "신경과"),
    (52, "재활의학과"),
    (53, "응급의학과"),
    (54, "내과"),
    (55, "심장내과"),
    (56, "외과"),
    (57, "정형외과"),
    (58, "산부인과"),
    (59, "가정의학과"),
    (60, "영상의학과"),
    (61, "마취통증의학과"),
    (62, "진단검사의학과"),
    (63, "뇌혈관센터"),
    (65, "척추관절통증센터"),
]

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}

# 이미지 파일명 포맷: /filedata/md_medical_team/{YYYYMMDDhhmmss}_{HASH8}_{slug}.jpg
# HASH 는 timestamp 와 slug 사이의 고유 식별자
_IMG_HASH_RE = re.compile(r"/\d{14}_([a-zA-Z0-9]{6,12})_")


class MjsmCrawler:
    def __init__(self):
        self.hospital_code = "MJSM"
        self.hospital_name = "명지성모병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _extract_hash(src: str) -> str:
        m = _IMG_HASH_RE.search(src or "")
        return m.group(1) if m else ""

    @staticmethod
    def _fallback_hash(dept: str, name: str) -> str:
        return hashlib.md5(f"{dept}|{name}".encode("utf-8")).hexdigest()[:10]

    def _parse_schedule_table(self, table) -> tuple[list[dict], str]:
        """(schedules, notes) — notes 는 tdcon2 (진료 공지 셀) 텍스트"""
        if table is None:
            return [], ""
        tbody = table.find("tbody") or table
        trs = tbody.find_all("tr", recursive=False) or tbody.find_all("tr")
        schedules: list[dict] = []
        notes = ""
        for tr in trs:
            first = tr.find(["td", "th"])
            if not first:
                continue
            first_cls = first.get("class") or []
            label = first.get_text(strip=True)

            # 공지 행: tdtitle2 + tdcon2 colspan=6
            if "tdtitle2" in first_cls:
                con = tr.find("td", class_="tdcon2")
                if con:
                    notes = con.get_text(" ", strip=True)
                continue

            slot = None
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            if slot is None:
                continue

            tds = tr.find_all("td")
            # 첫 td 가 라벨(tdtitle) → dow 셀은 [1:]
            day_cells = tds[1:] if tds and "tdtitle" in (tds[0].get("class") or []) else tds
            for dow, td in enumerate(day_cells[:6]):
                span = td.find("span")
                span_cls = (span.get("class") or []) if span else []
                span_text = span.get_text(strip=True) if span else ""
                # subject_1 = 진료, subject_ / 빈 span = 휴진
                is_working = False
                if any(c in {"subject_1", "subject_2", "subject_3"} for c in span_cls):
                    is_working = True
                elif span_text and span_text not in ("-", "―"):
                    is_working = True
                if not is_working:
                    continue
                s, e = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": s, "end_time": e, "location": "",
                })
        return schedules, notes

    def _parse_dept_page(self, html: str, dept_name: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        boxes = soup.select("div.drbox")
        result: list[dict] = []
        for b in boxes:
            name_el = b.select_one(".drname .t2")
            name = name_el.get_text(" ", strip=True).replace(" ", "") if name_el else ""
            if not name:
                continue

            position_el = b.select_one(".drname .t3")
            position = position_el.get_text(strip=True) if position_el else ""

            # 진료과: .t1 (e.g. "신경외과 전문의") 에서 "전문의" 제거
            t1_el = b.select_one(".drname .t1")
            t1_text = t1_el.get_text(" ", strip=True) if t1_el else ""
            dept = re.sub(r"전문의$", "", t1_text).strip() or dept_name

            # specialty: .drtxt2 span("진료분야") 이후 텍스트
            spec_el = b.select_one(".drtxt2")
            specialty = ""
            if spec_el:
                spec_copy = BeautifulSoup(str(spec_el), "html.parser")
                # remove leading label span
                label_span = spec_copy.find("span")
                if label_span:
                    label_span.decompose()
                specialty = spec_copy.get_text(" ", strip=True)

            img_el = b.select_one(".drimgs img")
            img_src = img_el.get("src", "") if img_el else ""
            img_hash = self._extract_hash(img_src) or self._fallback_hash(dept, name)
            photo_url = f"{BASE_URL}{img_src}" if img_src.startswith("/") else img_src

            table = b.find("table", class_="subtable5") or b.find("table")
            schedules, table_notes = self._parse_schedule_table(table)

            ext_id = f"{self.hospital_code}-{img_hash}"
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/index.php/html/{DEPT_PAGES[0][0]}",  # overwritten per-dept
                "photo_url": photo_url,
                "notes": table_notes,
                "schedules": schedules,
                "date_schedules": [],
                "_hash": img_hash,
                "_dept_page": 0,
            })
        return result

    async def _fetch_dept(
        self, client: httpx.AsyncClient, page_id: int, dept_name: str
    ) -> list[dict]:
        url = f"{BASE_URL}/index.php/html/{page_id}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[MJSM] page {page_id}({dept_name}) 실패: {e}")
            return []
        doctors = self._parse_dept_page(resp.text, dept_name)
        for d in doctors:
            d["profile_url"] = url
            d["_dept_page"] = page_id
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            results = await asyncio.gather(
                *[self._fetch_dept(client, pid, dn) for pid, dn in DEPT_PAGES],
                return_exceptions=True,
            )

        for res in results:
            if isinstance(res, Exception):
                continue
            for d in res:
                key = d["external_id"]
                # 기본 진료과(50~62) 우선 — 센터(63/65) 에서 중복되면 skip
                if key in all_doctors:
                    continue
                all_doctors[key] = d

        result = list(all_doctors.values())
        logger.info(f"[MJSM] 총 {len(result)}명")
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
        """개별 조회 — img_hash 로 모든 진료과 페이지 순차 검색 후 첫 매칭 반환.

        의사 고유 ID(img_hash)에 진료과 정보가 없으므로 순차 검색이 불가피함.
        첫 매칭에서 break 하므로 worst case 15 페이지지만, 대부분은 평균적으로 수개 페이지 내 매칭.
        """
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
        target_hash = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        if not target_hash:
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            for pid, dn in DEPT_PAGES:
                doctors = await self._fetch_dept(client, pid, dn)
                for d in doctors:
                    if d["_hash"] == target_hash:
                        return {
                            "staff_id": staff_id,
                            "name": d["name"], "department": d["department"],
                            "position": d["position"], "specialty": d["specialty"],
                            "profile_url": d["profile_url"], "notes": d["notes"],
                            "schedules": d["schedules"],
                            "date_schedules": d["date_schedules"],
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

"""구로성심병원(GSS / Guro Sungsim Hospital) 크롤러

병원 공식명: 구로성심병원 (서울 구로구 고척동)
홈페이지: gurosungsim.co.kr  (imweb 호스팅, 정적 HTML, UTF-8)

특이사항:
- imweb 템플릿 — 전체 의료진/진료시간표가 단일 페이지 `/doctor` 에 서버사이드 렌더.
- 의사별 개별 URL 이 없음 → 개별 조회도 동일 페이지 1회 GET 후 필터.
- 단일 페이지 (~4.7 MB) 이지만 한 번 GET 으로 전체 커버되어 rule #7 준수 가능.

구조:
  `<h5>홍길동 <span>{진료과} 전문의</span></h5>` — 의사 이름 카드
  이후 같은 imweb grid 내부 `<table>` 에 주간 진료시간표:
    - 첫 행: 헤더 [진료, 월, 화, 수, 목, 금, 토]
    - 둘째 행: [오전, cells...] — 각 셀에 `●` (font-size 20px) 포함 시 진료, 빈 셀 = 휴진
    - 셋째 행: [오후, cells...]
  일부 의사는 스케줄 테이블이 없음 (비활성/사진만) → schedules=[]

external_id: GSS-{md5(dept|name)[:10]}  (사이트에 숫자 ID 부재)
"""
import re
import hashlib
import logging
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://gurosungsim.co.kr"
DOCTOR_URL = f"{BASE_URL}/doctor"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}

_H5_PAT = re.compile(r"^\s*([가-힣]{2,4})\s*(.*)$")
_DEPT_PAT = re.compile(r"(.+?)\s*전문의\s*$")


class GssCrawler:
    def __init__(self):
        self.hospital_code = "GSS"
        self.hospital_name = "구로성심병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _mk_id(dept: str, name: str) -> str:
        raw = f"{dept}|{name}".encode("utf-8")
        return hashlib.md5(raw).hexdigest()[:10]

    @staticmethod
    def _find_schedule_table(h5) -> "BeautifulSoup|None":
        """h5 의 조상 grid 에서 주간 스케줄 테이블을 찾음 (첫 행에 월/화/수/목/금/토 포함)"""
        anc = h5
        for _ in range(10):
            anc = anc.parent
            if anc is None:
                return None
            if getattr(anc, "name", None) == "div" and anc.get("doz_type") in ("grid", "row", "widget", "inside"):
                for tbl in anc.find_all("table"):
                    first_row = tbl.find("tr")
                    if not first_row:
                        continue
                    cells_text = " ".join(td.get_text(" ", strip=True) for td in first_row.find_all(["td", "th"]))
                    if all(d in cells_text for d in ["월", "화", "수", "목", "금"]):
                        return tbl
        return None

    def _parse_schedule_table(self, table) -> list[dict]:
        """imweb 주간 테이블 → schedules. 진료 셀은 `●` 포함, 휴진 셀은 비어있음."""
        if table is None:
            return []
        tbody = table.find("tbody") or table
        trs = tbody.find_all("tr", recursive=False) or tbody.find_all("tr")
        schedules: list[dict] = []
        for tr in trs:
            tds = tr.find_all("td")
            if len(tds) < 7:
                continue
            # 라벨 셀은 "오 &nbsp; 전" (U+00A0 non-breaking space 포함) → 모든 공백/제어문자 제거
            label_raw = tds[0].get_text(" ", strip=True)
            label = re.sub(r"\s+", "", label_raw)
            slot = None
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            if slot is None:
                continue
            # 날짜 컬럼 6개 (월~토)
            for dow, td in enumerate(tds[1:7]):
                text = td.get_text(" ", strip=True)
                # "●" 있거나 "진료" 키워드 존재 → 진료, 빈 셀/휴진 → 제외
                if "●" not in text and "진료" not in text:
                    continue
                if "휴진" in text or "휴무" in text:
                    continue
                s, e = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": s, "end_time": e, "location": "",
                })
        return schedules

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        result: list[dict] = []
        seen_keys: set[str] = set()

        for h5 in soup.find_all("h5"):
            text = h5.get_text(" ", strip=True)
            span = h5.find("span")
            if not span:
                continue
            span_text = span.get_text(" ", strip=True)
            m_dept = _DEPT_PAT.search(span_text)
            if not m_dept:
                continue
            dept = m_dept.group(1).strip()
            if not dept:
                continue
            # h5 전체 텍스트에서 span 부분 제거하면 이름 영역
            name_part = text.replace(span_text, "").strip()
            m_name = re.search(r"([가-힣]{2,4})", name_part)
            if not m_name:
                continue
            name = m_name.group(1)

            key = f"{dept}|{name}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            tbl = self._find_schedule_table(h5)
            schedules = self._parse_schedule_table(tbl) if tbl else []

            # 근처 이미지 추출
            anc = h5
            photo_url = ""
            for _ in range(10):
                anc = anc.parent
                if anc is None:
                    break
                img = anc.find("img") if anc else None
                if img and img.get("src"):
                    src = img.get("src")
                    if "/doctor" in src or "profile" in src.lower() or "portrait" in src.lower():
                        photo_url = src if src.startswith("http") else f"{BASE_URL}{src}"
                        break

            ext_id = f"{self.hospital_code}-{self._mk_id(dept, name)}"
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept,
                "position": "전문의",
                "specialty": "",
                "profile_url": DOCTOR_URL,
                "photo_url": photo_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
            })
        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data
        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(DOCTOR_URL)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[GSS] /doctor fetch 실패: {e}")
                return []
        html = resp.content.decode("utf-8", errors="replace")
        result = self._parse_page(html)
        logger.info(f"[GSS] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        depts = sorted({d["department"] for d in data})
        return [{"code": dn, "name": dn} for dn in depts]

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
        """개별 조회 — /doctor 페이지 1회 GET 후 external_id 로 필터.

        imweb 구조상 의사 개별 URL 이 없으므로 단일 페이지 전체를 받아 필터링.
        페이지 크기는 크지만 한 번의 GET 으로 끝나므로 rule #7 의 취지(여러 페이지 스캔 금지) 에 부합.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        data = await self._fetch_all()
        for d in data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                        else d.get(k, [])
                        for k in ("staff_id", "name", "department", "position",
                                 "specialty", "profile_url", "notes",
                                 "schedules", "date_schedules")}
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

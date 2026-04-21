"""에이치플러스 양지병원(H+ Yangji Hospital) 크롤러

병원 공식명: 에이치플러스 양지병원 (서울 관악구)
홈페이지: www.newyjh.com
기술: 단일 정적 HTML (httpx + BeautifulSoup)

구조:
  통합 페이지 1개 /reservation/reservation-010000.html 에 전 진료과(29개) × 전 의사(96명) 인라인.
  의사 블록: <div class="mt_10 reservation01-conternt">
    - div.clearfix.docinfo > div.left > p (이름 + 직책)
    - div.clearfix.docinfo > div.right > a.reser-btn-01 (href?Idx_Fkey={ID})
    - div.mt_20.docimg > table.table.table-bordered
        thead: 진료(colspan=2) / 월 / 화 / 수 / 목 / 금 / 토  (8개 셀, 첫 2개는 '진료')
        tbody: 2 행 (오전/오후), 첫 td 는 'th row' 라벨, 다음 6개는 요일 셀
          td.check-red-01 (비어있음) → 외래 진료
          빈 td → 휴진
    - div.mt_30.docpartinfo > div.left > p "진료과 : {dept}"
    - div.docpartinfo > div.clear > p "전공분야 : {specialty}"
    - div.dochistory > div.left.ml_70 → 약력(notes)

external_id: HYJH-{Idx_Fkey}  (정수)
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.newyjh.com"
DOCTORS_URL = f"{BASE_URL}/reservation/reservation-010000.html"
DETAIL_URL = f"{BASE_URL}/reservation/reservation-010000_ins.html?Idx_Fkey={{id}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("14:00", "17:30")}

IDX_RE = re.compile(r"Idx_Fkey=(\d+)")


class HyjhCrawler:
    """에이치플러스 양지병원 크롤러 — 단일 통합 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "HYJH"
        self.hospital_name = "에이치플러스 양지병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data: list[dict] | None = None
        self._cached_soup: BeautifulSoup | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_page(self, client: httpx.AsyncClient) -> BeautifulSoup | None:
        if self._cached_soup is not None:
            return self._cached_soup
        try:
            resp = await client.get(DOCTORS_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[HYJH] 페이지 로드 실패: {e}")
            return None
        try:
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception:
            soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    def _parse_schedule(self, table) -> list[dict]:
        if table is None:
            return []
        tbody = table.find("tbody") or table
        schedules: list[dict] = []
        for row in tbody.find_all("tr"):
            ths = row.find_all("th")
            label = " ".join(th.get_text(" ", strip=True) for th in ths)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            start, end = TIME_RANGES[slot]
            tds = row.find_all("td")
            # 마지막 6개 td 가 월~토
            day_tds = tds[-6:] if len(tds) >= 6 else tds
            for i, td in enumerate(day_tds):
                classes = td.get("class") or []
                if "check-red-01" not in classes:
                    continue
                schedules.append({
                    "day_of_week": i,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    @staticmethod
    def _extract_name_position(raw: str) -> tuple[str, str]:
        """'김철수 이사장' → ('김철수', '이사장')"""
        raw = re.sub(r"\s+", " ", raw).strip()
        parts = raw.split(" ", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return raw, ""

    def _parse_block(self, block) -> dict | None:
        # docinfo > left > p (이름 + 직책)
        docinfo = block.find("div", class_="docinfo")
        if docinfo is None:
            return None
        left = docinfo.find("div", class_="left")
        if left is None:
            return None
        name_p = left.find("p")
        if name_p is None:
            return None
        name, position = self._extract_name_position(name_p.get_text(" ", strip=True))
        if not name:
            return None

        # docinfo > right > a.reser-btn-01 → Idx_Fkey
        right = docinfo.find("div", class_="right")
        idx = ""
        if right:
            a = right.find("a", href=IDX_RE)
            if a:
                m = IDX_RE.search(a.get("href", ""))
                if m:
                    idx = m.group(1)
        if not idx:
            # fallback — 블록 내 아무 곳에서나 Idx_Fkey 추출
            for a in block.find_all("a", href=IDX_RE):
                m = IDX_RE.search(a.get("href", ""))
                if m:
                    idx = m.group(1)
                    break
        if not idx:
            return None

        # docimg > table
        docimg = block.find("div", class_="docimg")
        table = docimg.find("table") if docimg else None
        schedules = self._parse_schedule(table)

        # docpartinfo > p "진료과 :" , "전공분야 :"
        department = ""
        specialty = ""
        part = block.find("div", class_="docpartinfo")
        if part:
            for p in part.find_all("p"):
                text = p.get_text(" ", strip=True)
                if text.startswith("진료과"):
                    sp = p.find("span")
                    if sp:
                        department = sp.get_text(" ", strip=True)
                elif text.startswith("전공분야"):
                    sp = p.find("span")
                    if sp:
                        specialty = sp.get_text(" ", strip=True)

        # 약력 → notes
        notes = ""
        hist = block.find("div", class_="dochistory")
        if hist:
            ml = hist.find_all("div", class_="left")
            for d in ml:
                classes = d.get("class") or []
                if "ml_70" in classes:
                    notes = d.get_text("\n", strip=True)
                    break

        ext_id = f"HYJH-{idx}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "profile_url": DETAIL_URL.format(id=idx),
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
        }

    def _parse_all_doctors(self, soup: BeautifulSoup) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        # 의사 블록: mt_10 + reservation01-conternt 두 클래스를 모두 가진 div
        for block in soup.find_all("div", class_="reservation01-conternt"):
            # docinfo 를 포함한 블록만 진료 블록으로 간주
            if not block.find("div", class_="docinfo"):
                continue
            doc = self._parse_block(block)
            if not doc:
                continue
            if doc["external_id"] in seen:
                continue
            seen.add(doc["external_id"])
            result.append(doc)
        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            soup = await self._fetch_page(client)

        if soup is None:
            self._cached_data = []
            return []

        result = self._parse_all_doctors(soup)
        logger.info(f"[HYJH] 총 {len(result)}명")
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
        return [{"code": dept, "name": dept} for dept in seen]

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
        """개별 교수 조회 — 통합 페이지 1회 GET 후 해당 Idx_Fkey 매칭"""
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

        prefix = "HYJH-"
        idx = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not idx:
            return empty

        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            return empty

        # 특정 Idx_Fkey 가진 a 를 포함한 블록 찾기
        for block in soup.find_all("div", class_="reservation01-conternt"):
            if not block.find("a", href=re.compile(rf"Idx_Fkey={idx}\b")):
                continue
            doc = self._parse_block(block)
            if not doc:
                continue
            return {k: doc.get(k, []) if k in ("schedules", "date_schedules") else doc.get(k, "")
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

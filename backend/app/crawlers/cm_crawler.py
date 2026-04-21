"""씨엠병원(CM Hospital) 크롤러

병원 공식명: CM병원 (보건복지부 지정 관절전문병원, 서울 영등포구 영등포로36길)
홈페이지: www.cmhospital.co.kr  (PHP 정적 HTML, UTF-8)

**특이사항**: SSL DH 키가 약해서 기본 httpx 컨텍스트로는 접근 불가.
`ssl.SSLContext.set_ciphers('DEFAULT@SECLEVEL=0')` 로 레거시 설정 적용.

구조:
  1) 진료과 페이지: /cmhospital/sub_02_{1..9}.php (정형/내과/신경/일반외/산부/마취통증/영상/진단/건강검진)
  2) 각 페이지에 `div.doctor_box` 의사 카드들. 카드:
     - `div.doc_img > img` — 프로필 사진
     - `p.don_name` — 이름 + `<span>직책 / 진료과</span>`
     - `p.don_part > span` — 진료분야(specialty)
     - `table` — 월~토 × 오전/오후, `<td><span>진료</span></td>` 존재 = 외래 / 빈 span = 휴진
     - `a[href*="doc_pop/doc_##"]` — 의사 고유 코드(두자리 숫자) 추출
  3) 의사 팝업: /cmhospital/doc_pop/doc_##.php (bio 만, 스케줄은 진료과 페이지에 있음)

external_id: CM-{doc_##}  (두자리 코드가 전체 병원 내 유일)
"""
import re
import ssl
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cmhospital.co.kr"

# sub_02_X → 기본 진료과명 (페이지 내 don_name 에서도 추출하지만 폴백용)
DEPT_PAGES = [
    (1, "정형외과"),
    (2, "내과"),
    (3, "신경과"),
    (4, "일반외과"),
    (5, "산부인과"),
    (6, "마취통증의학과"),
    (7, "영상의학과"),
    (8, "진단검사의학과"),
    (9, "가정의학과"),
]

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}


def _make_ssl_context() -> ssl.SSLContext:
    """CM 사이트의 약한 DH 파라미터 지원 컨텍스트"""
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class CmCrawler:
    def __init__(self):
        self.hospital_code = "CM"
        self.hospital_name = "CM병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _parse_don_name(text: str, fallback_dept: str) -> tuple[str, str, str]:
        """'장용준 부원장 / 내과' 또는 '장용준' + span('부원장 / 내과') 을 (name, position, dept) 로 분리"""
        name = ""
        position = ""
        dept = fallback_dept
        text = (text or "").strip()
        # 슬래시 분리: 왼쪽 = 이름+직책, 오른쪽 = 진료과
        if "/" in text:
            left, right = text.rsplit("/", 1)
            dept = right.strip() or fallback_dept
            left = left.strip()
        else:
            left = text
        # 이름(2~4 한글) + 직책(나머지)
        m = re.match(r"^([가-힣]{2,4})\s*(.*)$", left)
        if m:
            name = m.group(1)
            position = m.group(2).strip()
        else:
            name = left
        return name, position, dept

    def _parse_schedule_table(self, table) -> list[dict]:
        if table is None:
            return []
        tbody = table.find("tbody") or table
        trs = tbody.find_all("tr", recursive=False) or tbody.find_all("tr")
        schedules: list[dict] = []
        for tr in trs:
            label_el = tr.find("th")
            if not label_el:
                continue
            label = label_el.get_text(strip=True)
            slot = "morning" if "오전" in label else ("afternoon" if "오후" in label else None)
            if slot is None:
                continue
            tds = tr.find_all("td")
            for dow, td in enumerate(tds[:6]):
                # span 안 텍스트가 '진료' 또는 비어있지 않으면 진료
                text = td.get_text(" ", strip=True)
                if not text:
                    continue
                # "-" / "휴진" / "휴무" 는 휴진
                if text in {"-", "―"} or "휴" in text or "미진료" in text:
                    continue
                s, e = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": s, "end_time": e, "location": "",
                })
        return schedules

    def _parse_dept_page(self, html: str, default_dept: str, page_num: int) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        boxes = soup.select("div.doctor_box")
        result: list[dict] = []
        for b in boxes:
            link = b.select_one('a[href*="doc_pop/doc_"]')
            if not link:
                continue
            href = link.get("href", "")
            m = re.search(r"doc_(\d+)\.php", href)
            if not m:
                continue
            doc_code = m.group(1)

            name_el = b.select_one("p.don_name")
            raw_name = name_el.get_text(" ", strip=True) if name_el else ""
            name, position, dept = self._parse_don_name(raw_name, default_dept)

            spec_el = b.select_one("p.don_part span")
            specialty = spec_el.get_text(" ", strip=True) if spec_el else ""

            img_el = b.select_one("div.doc_img img")
            img_src = img_el.get("src", "") if img_el else ""
            photo_url = f"{BASE_URL}{img_src}" if img_src.startswith("/") else img_src

            table = b.find("table")
            schedules = self._parse_schedule_table(table)

            ext_id = f"{self.hospital_code}-{doc_code}"
            profile_url = f"{BASE_URL}{href}" if href.startswith("/") else href
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept,
                "position": position,
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
                "_doc_code": doc_code,
                "_page_num": page_num,
            })
        return result

    async def _fetch_dept(
        self, client: httpx.AsyncClient, page_num: int, dept_name: str
    ) -> list[dict]:
        url = f"{BASE_URL}/cmhospital/sub_02_{page_num}.php"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CM] sub_02_{page_num}({dept_name}) 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, dept_name, page_num)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        ssl_ctx = _make_ssl_context()
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=ssl_ctx,
        ) as client:
            results = await asyncio.gather(
                *[self._fetch_dept(client, pn, dn) for pn, dn in DEPT_PAGES],
                return_exceptions=True,
            )

        for res in results:
            if isinstance(res, Exception):
                continue
            for d in res:
                key = d["external_id"]
                if key not in all_doctors:
                    all_doctors[key] = d

        result = list(all_doctors.values())
        logger.info(f"[CM] 총 {len(result)}명")
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
        """개별 조회 — external_id 의 doc_code 를 모든 진료과 페이지에서 검색.

        의사 1명이 여러 진료과 페이지에 중복 노출될 수 있어, 첫 매칭 반환.
        진료과가 명시된 경우(향후 확장 시) 해당 페이지만 조회 가능.
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
        doc_code = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        if not doc_code.isdigit():
            return empty

        # 진료과 페이지를 순차 조회하며 doc_code 일치 첫 레코드 반환.
        ssl_ctx = _make_ssl_context()
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=ssl_ctx,
        ) as client:
            for pn, dn in DEPT_PAGES:
                doctors = await self._fetch_dept(client, pn, dn)
                for d in doctors:
                    if d["_doc_code"] == doc_code:
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

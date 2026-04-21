"""희명병원(Huimyung Hospital) 크롤러

병원 공식명: 희명병원 (서울 금천구 시흥)
홈페이지: hmhp.co.kr:41329  (euc-kr 인코딩 PHP 사이트)

제약사항:
- 주간/월간 진료시간표는 이미지 파일(JPG)로만 게시 → 구조화 파싱 불가
- 의료진 명단은 각 진료과 페이지의 `<img alt="{dept} {position} {name}">` 배너에서 추출
- 의사별 요일 스케줄은 제공되지 않음 → schedules=[], notes 에 안내 문구 기록

external_id: HUIMYUNG-{md5(dept+name)[:10]}
"""
import re
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://hmhp.co.kr:41329"

# 사이트맵에서 확인한 진료과목 페이지
DEPT_PAGES = [
    ("01", "가정의학과"),
    ("02", "신경외과"),
    ("03", "정형외과"),
    ("04", "외과"),
    ("05", "내과"),
    ("07", "산부인과"),
    ("08", "마취통증의학과"),
    ("09", "영상의학과"),
    ("10", "진단검사의학과"),
    ("11", "건강증진센터"),
    ("12", "응급센터"),
    ("13", "흉부외과"),
    ("14", "심장혈관흉부외과"),
]

_POSITION_RE = re.compile(
    r"(이사장|원장|병원장|부원장|진료부장|진료원장|부장|진료과장|주임과장|부과장|과장|센터장|소장|전문의)"
)

_NOTE_MSG = (
    "※ 희명병원은 월간 진료시간표를 이미지 파일(JPG)로만 게시하여 "
    "의사별 요일 스케줄 자동 수집이 불가합니다. "
    "현재 월 진료시간표는 공지사항(https://hmhp.co.kr:41329/new/sub/sub07-01.php)에서 "
    "'YYYY년 MM월 진료시간/진료일정표' 게시물로 확인하거나 병원(02-804-0002)에 직접 문의해 주세요."
)


class HuimyungCrawler:
    def __init__(self):
        self.hospital_code = "HUIMYUNG"
        self.hospital_name = "희명병원"
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

    def _parse_alt(self, alt: str, default_dept: str) -> tuple[str, str, str] | None:
        """'내과 5 진료과장 양우인' → (dept='내과', position='진료과장', name='양우인')"""
        alt = (alt or "").strip()
        if not alt:
            return None
        m = _POSITION_RE.search(alt)
        if m:
            position = m.group(1)
            before = alt[:m.start()].strip()
            after = alt[m.end():].strip()
        else:
            # 직책 없이 "영상의학과 박장미" 같은 형태
            position = ""
            toks = alt.split()
            if len(toks) < 2:
                return None
            before = " ".join(toks[:-1]).strip()
            after = toks[-1]
        dept_clean = re.sub(r"\s*\d+\s*$", "", before).strip()
        if not dept_clean:
            dept_clean = default_dept
        m_name = re.search(r"([가-힣]{2,4})", after)
        if not m_name:
            return None
        name = m_name.group(1)
        return dept_clean, position, name

    def _parse_dept_page(self, html: str, default_dept: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        imgs = soup.find_all(
            "img",
            src=lambda s: s and "name" in s and ".gif" in s and "sub03" in s,
        )
        result: list[dict] = []
        seen_names: set[str] = set()
        for img in imgs:
            alt = img.get("alt", "")
            parsed = self._parse_alt(alt, default_dept)
            if not parsed:
                continue
            dept, position, name = parsed
            if name in seen_names:
                continue
            seen_names.add(name)
            ext_id = f"{self.hospital_code}-{self._mk_id(dept, name)}"
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept,
                "position": position,
                "specialty": "",
                "profile_url": "",
                "notes": _NOTE_MSG,
                "schedules": [],
                "date_schedules": [],
            })
        return result

    async def _fetch_dept(self, client: httpx.AsyncClient, slug: str, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/new/sub/sub03-01-{slug}.php"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[HUIMYUNG] {dept_name} 실패: {e}")
            return []
        # euc-kr 명시
        html = resp.content.decode("euc-kr", errors="replace")
        doctors = self._parse_dept_page(html, dept_name)
        # profile_url 을 해당 진료과 페이지로 설정
        for d in doctors:
            d["profile_url"] = url
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        import asyncio
        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            results = await asyncio.gather(
                *[self._fetch_dept(client, slug, name) for slug, name in DEPT_PAGES],
                return_exceptions=True,
            )

        for res in results:
            if isinstance(res, Exception):
                continue
            for d in res:
                if d["external_id"] in all_doctors:
                    continue
                all_doctors[d["external_id"]] = d

        result = list(all_doctors.values())
        logger.info(f"[HUIMYUNG] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        return [{"code": name, "name": name} for _, name in DEPT_PAGES]

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
        """개별 조회 — 희명병원은 스케줄 미제공이므로 캐시 또는 전체 명단 조회 후 메타만 반환"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {
                        "staff_id": staff_id,
                        "name": d["name"], "department": d["department"],
                        "position": d["position"], "specialty": d["specialty"],
                        "profile_url": d["profile_url"], "notes": d["notes"],
                        "schedules": [], "date_schedules": [],
                    }
            return empty

        # 해시 기반 ID 라 역추적이 불가 → 진료과 페이지를 순차 조회하며 일치 확인
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            for slug, dept_name in DEPT_PAGES:
                doctors = await self._fetch_dept(client, slug, dept_name)
                for d in doctors:
                    if d["external_id"] == staff_id:
                        return {
                            "staff_id": staff_id,
                            "name": d["name"], "department": d["department"],
                            "position": d["position"], "specialty": d["specialty"],
                            "profile_url": d["profile_url"], "notes": d["notes"],
                            "schedules": [], "date_schedules": [],
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
                schedules=[],
                date_schedules=[],
            )
            for d in data
        ]
        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="partial" if doctors else "failed",
            doctors=doctors,
            crawled_at=datetime.utcnow(),
        )

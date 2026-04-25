"""화성유일병원(Hwaseong Yuil Hospital) 크롤러

병원 공식명: 화성유일병원
홈페이지: hsyuil.kr
기술: Creatorlink 빌더로 만든 단일 페이지 정적 HTML (httpx + regex)

사이트 구조:
  Creatorlink 로 만든 브로셔형 사이트로, 상세 진료과/일정 시스템이 없다.
  `SETTINGS.blocknameList` JSON 에 의사 이름이 블록으로 등록되어 있으며
  별도의 스케줄 페이지는 제공하지 않는다.

  따라서 이 크롤러는 의사 이름 5명만 반환하고 스케줄은 빈 리스트를 반환한다.
  (병원 전체 영업시간은 평일 08:30~17:30, 토 08:30~12:30 이지만 의사별로
   구분된 일정이 공개되지 않으므로 schedules 자체는 비워둔다.)

external_id: HSYUIL-{md5(이름)[:10]}
"""
import re
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://hsyuil.kr"
HOME_URL = f"{BASE_URL}/"

# blocknameList JSON 안에서 의사 이름을 추출 (순수 한글 이름만)
BLOCK_NAME_RE = re.compile(r'"blockname\d+":"([^"]+)"')
KOREAN_NAME_RE = re.compile(r"^[가-힣]{2,4}$")

# Creatorlink blocknameList 에 섞여 있는 non-이름 항목 필터
BLOCK_EXCLUDES = {
    "화성유일병원 소식", "동영상", "진료일정", "12월 진료일정",
    "이용안내", "언어치료", "감각통합치료", "인지치료",
    "시간표", "상담신청",
}


class HsyuilCrawler:
    """화성유일병원 크롤러 — Creatorlink 브로셔 사이트

    진료과 구분이나 스케줄 표가 제공되지 않아, 공식 홈 상단에 등재된 의료진
    이름만 추출하고 스케줄은 비워 반환한다. 등록 후 필요하면 수동 입력 가능.
    """

    def __init__(self):
        self.hospital_code = "HSYUIL"
        self.hospital_name = "화성유일병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_home(self, client: httpx.AsyncClient) -> str | None:
        try:
            resp = await client.get(HOME_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[HSYUIL] 홈 로드 실패: {e}")
            return None
        return resp.text

    @staticmethod
    def _extract_names(html: str) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for m in BLOCK_NAME_RE.finditer(html or ""):
            raw = m.group(1).strip()
            if raw in BLOCK_EXCLUDES:
                continue
            if KOREAN_NAME_RE.match(raw) and raw not in seen:
                seen.add(raw)
                names.append(raw)
        return names

    @staticmethod
    def _ext_id(name: str) -> str:
        h = hashlib.md5(name.encode("utf-8")).hexdigest()[:10]
        return f"HSYUIL-{h}"

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            html = await self._fetch_home(client)

        if not html:
            self._cached_data = []
            return []

        names = self._extract_names(html)
        result: list[dict] = []
        for n in names:
            ext_id = self._ext_id(n)
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": n,
                "department": "",
                "position": "",
                "specialty": "",
                "profile_url": BASE_URL,
                "notes": "",
                "schedules": [],
                "date_schedules": [],
            })

        logger.info(f"[HSYUIL] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        # 진료과 구분이 없으므로 전체 1개 그룹으로 반환
        return [{"code": "ALL", "name": "전체"}]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — 1회 GET 후 해당 이름만 매칭 (skill 규칙 #7)"""
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

        async with self._make_client() as client:
            html = await self._fetch_home(client)
        if not html:
            return empty

        for name in self._extract_names(html):
            if self._ext_id(name) == staff_id:
                return {
                    "staff_id": staff_id, "name": name, "department": "",
                    "position": "", "specialty": "", "profile_url": BASE_URL,
                    "notes": "", "schedules": [], "date_schedules": [],
                }
        return empty

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()

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

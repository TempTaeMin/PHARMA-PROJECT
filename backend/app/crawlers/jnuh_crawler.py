"""전남대학교병원(JNUH) / 화순전남대학교병원(JNUHHS) 크롤러

두 병원은 cs-server 계열 정적 사이트이며, 각각 독립 도메인을 갖는다.
  - JNUH   (광주 본원)   : https://www.cnuh.com
  - JNUHHS (화순분원)    : https://www.cnuhh.com

구조 (양 사이트 동일):
  1) 메인 페이지(/main.cs) 에서 진료과 코드 + 한글명 추출
     - nav 안 a[href*="dept.cs?act=view&deptCd="]
  2) 진료과별 의사 목록
     URL: /medical/info/dept.cs?act=view&mode=doctorList&deptCd={deptCd}
     - 각 div.doctorInfo 가 1명
       * dt → 이름 + 직책span
       * dd.img img → 사진
       * dd.txt → "전문분야 ..." 텍스트
       * a[href*=doctCd] → 원내 교수 코드
       * div.doctorCalendar table → 이번 주 주간 스케줄 5일
  3) 주간 달력 셀 텍스트는 "전대병원 진료" 또는 "화순 진료" 로 표기됨.
     같은 사이트 도메인에 같은 브랜치 의사만 노출되지만, 교차 셀이 섞인
     경우도 있어 브랜치별 cell 필터링을 추가 적용한다.
  4) 달력 스케줄은 주간 패턴만 제공 → date_schedules 미지원 (빈 리스트).
  5) 개별 교수 조회는 external_id 에 진료과 코드를 포함시켜 1 dept 페이지만 재요청.

external_id: {HOSPITAL_CODE}-{deptCd}-{doctCd}
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 요일 한글 → dayofweek (0=월 ~ 6=일)
DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

# 달력 셀 day_head 포맷: "20(월)" 또는 "20 (월)"
_DAY_HEAD_RE = re.compile(r"\(([월화수목금토일])\)")

# href 에서 doctCd/deptCd 추출
_DOCT_CD_RE = re.compile(r"doctCd=([A-Z0-9]+)")
_DEPT_CD_RE = re.compile(r"deptCd=([A-Z0-9]+)")


class _JnuhBaseCrawler:
    """JNUH/JNUHHS 공용 베이스.

    서브클래스에서 base_url, hospital_code, hospital_name, branch_markers 를 지정.
    branch_markers: 이 브랜치의 진료 셀로 인정할 키워드 튜플.
                     (예: JNUH → ("전대병원",), JNUHHS → ("화순",))
    """

    base_url: str = ""
    hospital_code: str = ""
    hospital_name: str = ""
    branch_markers: tuple[str, ...] = ()
    # 다른 브랜치 셀이면 건너뛰기 위한 키워드
    other_branch_markers: tuple[str, ...] = ()

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        self._cached_data: list[dict] | None = None
        self._dept_map: dict[str, str] | None = None  # deptCd → 한글명

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 공용 ───

    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    async def _fetch_departments(self, client: httpx.AsyncClient) -> dict[str, str]:
        """메인 페이지에서 진료과 코드 → 한글명 맵 수집."""
        if self._dept_map is not None:
            return self._dept_map
        try:
            resp = await client.get(f"{self.base_url}/main.cs")
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[{self.hospital_code}] main.cs 로드 실패: {e}")
            self._dept_map = {}
            return self._dept_map

        soup = BeautifulSoup(resp.text, "html.parser")
        codes: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "dept.cs?act=view&deptCd=" not in href or "mode=" in href:
                continue
            m = _DEPT_CD_RE.search(href)
            if not m:
                continue
            code = m.group(1)
            name = self._clean(a.get_text(strip=True))
            if name and code not in codes and len(name) < 30:
                codes[code] = name
        self._dept_map = codes
        logger.info(f"[{self.hospital_code}] 진료과 {len(codes)}개 수집")
        return codes

    # ─── 주간 달력 파싱 ───

    def _parse_calendar(self, table) -> list[dict]:
        """div.doctorCalendar > table → weekly pattern schedules.

        브랜치 필터 적용: cell text 에 self.branch_markers 중 하나가 있거나,
        명확히 다른 브랜치 마커가 없는 셀만 포함한다.
        """
        if table is None:
            return []
        head_cells = table.select("thead th")
        day_heads: list[str] = []
        for th in head_cells[1:]:
            t = th.get_text(" ", strip=True)
            m = _DAY_HEAD_RE.search(t)
            day_heads.append(m.group(1) if m else "")

        found: set[tuple[int, str]] = set()
        for tr in table.select("tbody tr"):
            tr_cls = tr.get("class", [])
            slot = "morning" if "timeAM" in tr_cls else (
                "afternoon" if "timePM" in tr_cls else ""
            )
            if not slot:
                # 저녁/야간 행은 무시
                continue
            tds = tr.find_all("td")
            for i, td in enumerate(tds):
                cell_text = self._clean(td.get_text(" ", strip=True))
                if not cell_text:
                    continue
                # 다른 브랜치 표기면 건너뜀
                if any(mk in cell_text for mk in self.other_branch_markers):
                    if not any(mk in cell_text for mk in self.branch_markers):
                        continue
                # 진료 여부 판정 (수술/내시경 등 제외)
                if not is_clinic_cell(cell_text):
                    continue
                if i >= len(day_heads):
                    continue
                korean_day = day_heads[i]
                dow = DAY_MAP.get(korean_day)
                if dow is None:
                    continue
                found.add((dow, slot))

        return [
            {
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": TIME_RANGES[slot][0],
                "end_time": TIME_RANGES[slot][1],
                "location": "",
            }
            for dow, slot in sorted(found)
        ]

    # ─── 진료과 페이지 파싱 ───

    def _parse_dept_page(self, html: str, dept_cd: str, dept_name: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        doctors: list[dict] = []
        for dinfo in soup.select("div.doctorInfo"):
            dt = dinfo.select_one("dt")
            if not dt:
                continue
            # 직책 span
            pos_span = dt.find("span")
            position = self._clean(pos_span.get_text(" ", strip=True)) if pos_span else ""
            # 이름 = span 앞 텍스트
            name_parts: list[str] = []
            for node in dt.children:
                if node is pos_span:
                    break
                if isinstance(node, str):
                    name_parts.append(node)
            name = self._clean(" ".join(name_parts))
            if not name:
                continue

            # doctCd 추출 (링크)
            a = dinfo.select_one("a[href*='doctCd']")
            if not a:
                continue
            m = _DOCT_CD_RE.search(a.get("href", ""))
            if not m:
                continue
            doct_cd = m.group(1)

            # 전문분야
            specialty = ""
            txt = dinfo.select_one("dd.txt")
            if txt:
                full = self._clean(txt.get_text(" ", strip=True))
                # "전문분야 ..." 접두 제거
                specialty = re.sub(r"^전문분야\s*[:\-]?\s*", "", full).strip()

            # 사진 URL
            photo_url = ""
            img = dinfo.select_one("dd.img img")
            if img:
                src = (img.get("src") or "").strip()
                if src:
                    photo_url = src if src.startswith("http") else f"{self.base_url}{src if src.startswith('/') else '/' + src}"

            # 주간 스케줄
            schedules = self._parse_calendar(dinfo.select_one("div.doctorCalendar table"))

            ext_id = f"{self.hospital_code}-{dept_cd}-{doct_cd}"
            profile_url = (
                f"{self.base_url}/medical/info/dept.cs"
                f"?act=view&mode=doctor&deptCd={dept_cd}&doctCd={doct_cd}"
            )
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "doct_cd": doct_cd,
                "dept_cd": dept_cd,
                "name": name,
                "department": dept_name,
                "position": position or dept_name,
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
            })
        return doctors

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_cd: str, dept_name: str) -> list[dict]:
        url = f"{self.base_url}/medical/info/dept.cs?act=view&mode=doctorList&deptCd={dept_cd}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[{self.hospital_code}] dept {dept_cd}({dept_name}) 로드 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, dept_cd, dept_name)

    # ─── 전체 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
            if not depts:
                self._cached_data = []
                return self._cached_data

            # 병원 부하 완화 위해 동시 요청 제한
            sem = asyncio.Semaphore(5)

            async def _one(code: str, name: str) -> list[dict]:
                async with sem:
                    return await self._fetch_dept(client, code, name)

            results = await asyncio.gather(
                *[_one(c, n) for c, n in depts.items()],
                return_exceptions=True,
            )

        all_docs: dict[str, dict] = {}
        for r in results:
            if isinstance(r, Exception):
                continue
            for d in r:
                # 브랜치 판정: schedules 가 비어 있고 이 브랜치에 속하지 않을 수도 있음
                # 그러나 도메인 분리상 기본적으로 이 사이트에 올라온 의사는
                # 이 브랜치 소속으로 간주. 중복 제거만 수행.
                all_docs.setdefault(d["external_id"], d)

        data = list(all_docs.values())
        logger.info(f"[{self.hospital_code}] 총 {len(data)}명")
        self._cached_data = data
        return data

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
        return [{"code": code, "name": name} for code, name in sorted(depts.items())]

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
        """개별 교수 조회 — external_id 에서 deptCd 파싱 후 해당 진료과 1곳만 요청."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 같은 인스턴스에서 _fetch_all() 결과가 있으면 사용
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        prefix = f"{self.hospital_code}-"
        if not staff_id.startswith(prefix):
            return empty
        raw = staff_id[len(prefix):]
        # 포맷: deptCd-doctCd
        if "-" not in raw:
            return empty
        dept_cd, doct_cd = raw.split("-", 1)
        if not dept_cd or not doct_cd:
            return empty

        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
            dept_name = depts.get(dept_cd, "")
            docs = await self._fetch_dept(client, dept_cd, dept_name)

        for d in docs:
            if d["doct_cd"] == doct_cd:
                return {
                    "staff_id": staff_id,
                    "name": d["name"],
                    "department": d["department"],
                    "position": d["position"],
                    "specialty": d["specialty"],
                    "profile_url": d["profile_url"],
                    "notes": d["notes"],
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


class JnuhCrawler(_JnuhBaseCrawler):
    """전남대학교병원 (광주 본원)"""
    base_url = "https://www.cnuh.com"
    hospital_code = "JNUH"
    hospital_name = "전남대학교병원"
    branch_markers = ("전대병원", "본원")
    other_branch_markers = ("화순",)


class JnuhhsCrawler(_JnuhBaseCrawler):
    """화순전남대학교병원 (화순분원)"""
    base_url = "https://www.cnuhh.com"
    hospital_code = "JNUHHS"
    hospital_name = "화순전남대학교병원"
    branch_markers = ("화순",)
    other_branch_markers = ("전대병원", "본원")

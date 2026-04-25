"""부산대학교병원(PNUH) / 양산부산대학교병원(PNUYH) 크롤러

두 병원은 부산대학교병원 의료원 계열이지만 서로 다른 Spring MVC 앱으로 운영되며,
HTML 구조/엔드포인트도 다르다. 하나의 베이스 클래스로 묶지 않고 개별 구현한다.

[PNUH – 부산대학교병원 본원(부산 서구)]
  - 기본 URL: https://www.pnuh.or.kr
  - 진료과 목록:     /pnuh/medical/department.do
      * 진료과 안내 링크에서 `tCode={코드}` 추출 (예: I1=소화기내과)
      * 메뉴 풋터의 "진료과 및 클리닉" <ul> 이 가장 깔끔한 소스
  - 의료진 소개:     /pnuh/medical/medical-team-info.do?tCode=<tCode>&type=2
      * li > div.team_doctor > img(`attach/image/{dno}_profilePhoto_...do`)
      * strong = "홍길동(English)"
      * dt "진료분야"
      * a[href*=doctor-info.do?...dno={dno}]
  - 진료 시간표:     /pnuh/medical/medical-schedule.do?tCode=<tCode>&type=3
      * table.lineTop_tb 에 <tr class="unit"> + 그 뒤 <tr>(오후) 쌍
      * 월~금 5개 칼럼 + 비고 — 셀에 "○" 또는 "○<br/><span>초예</span>" 있으면 진료

[PNUYH – 양산부산대학교병원(양산)]
  - 기본 URL: https://www.pnuyh.or.kr
  - 센터/진료과 목록: /pnuyh/medical/department.do
      * li.nlist 의 a[href*=department-team.do?treatCd=<treatCd>]
  - 의료진 + 스케줄: /pnuyh/medical/department/department-team.do?treatCd=<treatCd>
      * 한 페이지에 의료진 목록 + 각 의사별 주간 스케줄 테이블이 같이 렌더링됨
      * strong = 이름(한/영), dt "소속과" dd = 실제 진료과명
      * a[href*=department-teamIntro.do?doctorNo=<doctorNo>]
      * 주간 시간표 table 안 `td[data-schedule="진료"]` 로 판정

외래 진료만 수집. date_schedules 는 주간 패턴만 제공되어 빈 리스트로 둠.

external_id:
  - PNUH:  PNUH-{tCode}-{dno}
  - PNUYH: PNUYH-{treatCd}-{doctorNo}
  (단, 한 의사가 여러 tCode 에 걸치면 각 진료과 별로 별도 external_id 생성)
"""
from __future__ import annotations

import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 한글 요일 → dow (0=월)
_KDAY = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

_TCODE_RE = re.compile(r"tCode=([A-Za-z0-9]+)")
_DNO_RE = re.compile(r"dno=([A-Za-z0-9]+)")
_TREATCD_RE = re.compile(r"treatCd=([A-Za-z0-9]+)")
_DOCTORNO_RE = re.compile(r"doctorNo=([A-Za-z0-9]+)")
# 이미지 URL 에서 dno 추출 — .../image/{dno}_profilePhoto_...
_DNO_IMG_RE = re.compile(r"/image/([A-Za-z0-9]+)_profilePhoto")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _cell_is_clinic(td) -> bool:
    """PNUH 스케줄 셀: '○' 마크(옵션으로 <span>초예</span> 포함)면 진료."""
    text = td.get_text(" ", strip=True) if td is not None else ""
    # '○' 마크가 있거나 '예'/'초예' 같은 보조 표시 → is_clinic_cell 이 ○ 을 잡음
    return is_clinic_cell(text)


def _make_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }


# ──────────────────────────────────────────────────────────────────────────
# PNUH – 부산대학교병원(부산)
# ──────────────────────────────────────────────────────────────────────────

class PnuhCrawler:
    """부산대학교병원(부산 본원) 크롤러."""

    BASE_URL = "https://www.pnuh.or.kr"
    DEPT_URL = "/pnuh/medical/department.do"
    TEAM_URL = "/pnuh/medical/medical-team-info.do"
    SCHED_URL = "/pnuh/medical/medical-schedule.do"

    def __init__(self):
        self.hospital_code = "PNUH"
        self.hospital_name = "부산대학교병원"
        self.headers = _make_headers()
        self._cached_data: list[dict] | None = None
        self._dept_map: dict[str, str] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 진료과 ───

    async def _fetch_dept_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        """tCode → 진료과 한글명 맵."""
        if self._dept_map is not None:
            return self._dept_map
        try:
            resp = await client.get(f"{self.BASE_URL}{self.DEPT_URL}")
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[PNUH] department.do 로드 실패: {e}")
            self._dept_map = {}
            return self._dept_map

        soup = BeautifulSoup(resp.text, "html.parser")
        codes: dict[str, str] = {}

        # 1) 메인 본문: `<h4 class="sTit">소화기내과</h4>` 다음에 오는 링크 블록에서 tCode 추출.
        #    이게 가장 신뢰할 수 있음 — 진료과 이름과 코드가 1:1 매핑됨.
        for sTit in soup.select("h4.sTit"):
            name = _clean(sTit.get_text(" ", strip=True))
            if not name or len(name) > 30:
                continue
            # 같은 부모(li) 안 또는 바로 뒤 div.btn 에 tCode 링크가 있음
            container = sTit.parent
            if container is None:
                continue
            found_code = None
            for a in container.find_all("a", href=True):
                href = a["href"]
                m = _TCODE_RE.search(href)
                if m:
                    found_code = m.group(1)
                    break
            if not found_code:
                continue
            # 같은 코드가 이미 있으면 더 적절한 이름으로 덮어쓰지 않음
            codes.setdefault(found_code, name)

        # 2) 푸터의 "진료과 및 클리닉" 리스트 — title 속성에 이름, 덮어쓰지 않음
        for a in soup.select('a[href*="department-info.do"]'):
            if not a.get("title"):
                continue
            href = a.get("href", "")
            m = _TCODE_RE.search(href)
            if not m:
                continue
            code = m.group(1)
            name = _clean(a.get("title") or "")
            if not name or len(name) > 30:
                continue
            codes.setdefault(code, name)

        self._dept_map = codes
        logger.info(f"[PNUH] 진료과 {len(codes)}개 수집")
        return codes

    # ─── 의료진 + 스케줄 파싱 ───

    def _parse_team_page(self, html: str, t_code: str, dept_name: str) -> list[dict]:
        """medical-team-info.do 페이지 → 의사 리스트(스케줄 제외)."""
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        # team_ct > ul.team_list > li > div.team_doctor
        for box in soup.select("div.team_doctor"):
            strong = box.find("strong")
            if not strong:
                continue
            raw_name = _clean(strong.get_text(" ", strip=True))
            # 한글이름(영문) 형태. 괄호 앞부분만.
            m = re.match(r"^([^()]+?)(?:\s*\(.*)?$", raw_name)
            name = _clean(m.group(1)) if m else raw_name
            if not name:
                continue

            # 이미지에서 dno 추출 (최우선)
            dno = ""
            img = box.find("img")
            if img is not None:
                mm = _DNO_IMG_RE.search(img.get("src") or "")
                if mm:
                    dno = mm.group(1)

            # a[href] 의 dno 폴백 (상세소개 링크)
            if not dno:
                for a in box.select("a[href*='dno=']"):
                    mm = _DNO_RE.search(a.get("href", ""))
                    if mm:
                        dno = mm.group(1)
                        break

            if not dno:
                # 식별자가 없으면 스킵 (external_id 를 만들 수 없음)
                continue

            # 진료분야
            specialty = ""
            dl = box.find("dl")
            if dl:
                dd = dl.find("dd")
                if dd:
                    specialty = _clean(dd.get_text(" ", strip=True))

            # 사진 URL
            photo_url = ""
            if img is not None:
                src = (img.get("src") or "").strip()
                if src:
                    photo_url = src if src.startswith("http") else f"{self.BASE_URL}{src if src.startswith('/') else '/' + src}"

            ext_id = f"PNUH-{t_code}-{dno}"
            profile_url = f"{self.BASE_URL}/pnuh/medical/doctor-info.do?tCode={t_code}&dno={dno}"
            out.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "dno": dno,
                "tcode": t_code,
                "name": name,
                "department": dept_name,
                "position": "교수",  # 시간표 페이지에서 더 구체 정보 있으면 덮어씀
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": [],
                "date_schedules": [],
            })
        return out

    def _parse_schedule_page(self, html: str) -> dict[str, list[dict]]:
        """medical-schedule.do → {dno: [weekly schedules]}"""
        soup = BeautifulSoup(html, "html.parser")
        result: dict[str, list[dict]] = {}

        for table in soup.select("table.lineTop_tb"):
            # 헤더에서 요일 순서 추출 (의료진, (오전/오후), 월, 화, 수, 목, 금, 비고)
            head_cells = table.select("thead th")
            day_names: list[str] = []
            for th in head_cells:
                t = _clean(th.get_text(" ", strip=True))
                if t in _KDAY:
                    day_names.append(t)
            if not day_names:
                # 시간표 테이블이 아닐 수 있음 (휴진마감 안내 등)
                continue

            tbody = table.find("tbody")
            if not tbody:
                continue

            # 각 '의료진 블록' = 2행 쌍: <tr class="unit">(오전) + 바로 다음 <tr>(오후)
            rows = tbody.find_all("tr", recursive=False)
            i = 0
            while i < len(rows):
                row_am = rows[i]
                cls_am = row_am.get("class") or []
                if "unit" not in cls_am:
                    i += 1
                    continue
                row_pm = rows[i + 1] if (i + 1) < len(rows) else None

                # 의사 정보 추출 (rowspan=2 첫 td 안 div.team_doctor)
                doc_td = row_am.find("td")
                img = doc_td.find("img") if doc_td else None
                dno = ""
                if img is not None:
                    mm = _DNO_IMG_RE.search(img.get("src") or "")
                    if mm:
                        dno = mm.group(1)
                    if not dno:
                        # alt 에 "{dno}(English)" 형태
                        alt = (img.get("alt") or "").strip()
                        mm2 = re.match(r"^([0-9A-Za-z]+)", alt)
                        if mm2:
                            dno = mm2.group(1)

                # am row 셀 중, 의사 td(rowspan=2, 첫) + '오전' th 뒤의 요일 td 만 스캔
                # HTML 구조: <tr class="unit"> <td rowspan=2>의사</td> <td>오전</td> <td>월</td>...<td>금</td> <td rowspan=2>비고</td> </tr>
                # → td 중에서 의사 td / 오전 표지 td / 비고 td 를 제외한 중간 N개가 요일 셀
                found: set[tuple[int, str]] = set()

                def _process_row(tr, slot: str):
                    if tr is None or not dno:
                        return
                    tds = tr.find_all("td", recursive=False)
                    # 오전 행: 의사td + 오전td + ...요일td... + 비고td
                    # 오후 행: 오후td + ...요일td...
                    # 요일 셀만 뽑기 — 텍스트가 '오전'/'오후' 아닌 것들 중 비고 제외
                    day_tds = []
                    for td in tds:
                        text = _clean(td.get_text(" ", strip=True))
                        # 헤더 표지 제외
                        if text in ("오전", "오후"):
                            continue
                        # 의사 정보 td 는 img 있음 (오전 행 첫번째)
                        if td.find("img") is not None:
                            continue
                        day_tds.append(td)
                    # 마지막은 비고 — 다만 오전 행의 비고는 rowspan=2 로 오전 행에만 있음
                    # 그래서 오전 행 day_tds 개수가 오후 행보다 1개 많다.
                    # 요일 td 개수는 day_names 길이와 같아야 함.
                    if len(day_tds) > len(day_names):
                        # 맨 끝(비고) 제거
                        day_tds = day_tds[:len(day_names)]

                    for idx, td in enumerate(day_tds[:len(day_names)]):
                        if not _cell_is_clinic(td):
                            continue
                        dow = _KDAY.get(day_names[idx])
                        if dow is None:
                            continue
                        found.add((dow, slot))

                _process_row(row_am, "morning")
                _process_row(row_pm, "afternoon")

                if dno:
                    sched = [
                        {
                            "day_of_week": dow,
                            "time_slot": slot,
                            "start_time": TIME_RANGES[slot][0],
                            "end_time": TIME_RANGES[slot][1],
                            "location": "",
                        }
                        for dow, slot in sorted(found)
                    ]
                    result.setdefault(dno, []).extend(sched)

                # 다음 의사: 오후 행 이후로
                i += 2 if row_pm is not None and "unit" not in (row_pm.get("class") or []) else 1

        # 요일/슬롯 중복 제거
        for dno, lst in list(result.items()):
            dedup = { (s["day_of_week"], s["time_slot"]): s for s in lst }
            result[dno] = list(dedup.values())
        return result

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, t_code: str, dept_name: str) -> list[dict]:
        """1개 진료과의 의사 목록 + 스케줄."""
        team_url = f"{self.BASE_URL}{self.TEAM_URL}?tCode={t_code}&type=2"
        sched_url = f"{self.BASE_URL}{self.SCHED_URL}?tCode={t_code}&type=3"

        try:
            team_resp, sched_resp = await asyncio.gather(
                client.get(team_url), client.get(sched_url),
            )
        except Exception as e:
            logger.warning(f"[PNUH] 진료과 {t_code}({dept_name}) 로드 실패: {e}")
            return []

        doctors: list[dict] = []
        if team_resp.status_code == 200:
            doctors = self._parse_team_page(team_resp.text, t_code, dept_name)

        schedules: dict[str, list[dict]] = {}
        if sched_resp.status_code == 200:
            try:
                schedules = self._parse_schedule_page(sched_resp.text)
            except Exception as e:
                logger.warning(f"[PNUH] 스케줄 파싱 실패 {t_code}: {e}")

        for d in doctors:
            d["schedules"] = schedules.get(d["dno"], [])

        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_map(client)
            if not depts:
                self._cached_data = []
                return self._cached_data

            sem = asyncio.Semaphore(4)

            async def _one(code: str, name: str) -> list[dict]:
                async with sem:
                    return await self._fetch_dept_doctors(client, code, name)

            results = await asyncio.gather(
                *[_one(c, n) for c, n in depts.items()],
                return_exceptions=True,
            )

        merged: dict[str, dict] = {}
        for r in results:
            if isinstance(r, Exception):
                continue
            for d in r:
                # external_id 는 tCode 포함이라 고유. 다만 같은 tCode 안에서 중복이 있을 수 있음.
                merged.setdefault(d["external_id"], d)

        data = list(merged.values())
        logger.info(f"[PNUH] 총 {len(data)}명")
        self._cached_data = data
        return data

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_map(client)
        return [{"code": c, "name": n} for c, n in sorted(depts.items())]

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
        """개별 교수 조회 — external_id 에서 tCode 파싱 후 해당 진료과 1곳만 요청."""
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

        prefix = "PNUH-"
        if not staff_id.startswith(prefix):
            return empty
        raw = staff_id[len(prefix):]
        if "-" not in raw:
            return empty
        t_code, dno = raw.split("-", 1)
        if not t_code or not dno:
            return empty

        async with self._make_client() as client:
            depts = await self._fetch_dept_map(client)
            dept_name = depts.get(t_code, "")
            docs = await self._fetch_dept_doctors(client, t_code, dept_name)

        for d in docs:
            if d["dno"] == dno:
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


# ──────────────────────────────────────────────────────────────────────────
# PNUYH – 양산부산대학교병원(양산)
# ──────────────────────────────────────────────────────────────────────────

class PnuyhCrawler:
    """양산부산대학교병원 크롤러."""

    BASE_URL = "https://www.pnuyh.or.kr"
    DEPT_URL = "/pnuyh/medical/department.do"
    TEAM_URL = "/pnuyh/medical/department/department-team.do"

    def __init__(self):
        self.hospital_code = "PNUYH"
        self.hospital_name = "양산부산대학교병원"
        self.headers = _make_headers()
        self._cached_data: list[dict] | None = None
        self._dept_map: dict[str, str] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 진료과(+센터) ───

    async def _fetch_dept_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        if self._dept_map is not None:
            return self._dept_map
        try:
            resp = await client.get(f"{self.BASE_URL}{self.DEPT_URL}")
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[PNUYH] department.do 로드 실패: {e}")
            self._dept_map = {}
            return self._dept_map

        soup = BeautifulSoup(resp.text, "html.parser")
        codes: dict[str, str] = {}
        # li.nlist > h4.sTit > img alt 또는 span = 이름, 의료진 링크에서 treatCd
        for li in soup.select("li.nlist"):
            a = li.select_one("a[href*='department-team.do'], a[href*='transplant/team.do']")
            if not a:
                continue
            href = a.get("href", "")
            m = _TREATCD_RE.search(href)
            if not m:
                continue
            code = m.group(1)

            name = ""
            h4 = li.select_one("h4.sTit")
            if h4:
                span = h4.find("span")
                if span:
                    name = _clean(span.get_text(" ", strip=True))
                if not name:
                    img = h4.find("img")
                    if img is not None:
                        name = _clean(img.get("alt") or "")
                if not name:
                    name = _clean(h4.get_text(" ", strip=True))
            if not name or len(name) > 30:
                continue
            # 동일 treatCd 중복(동일 진료과가 여러 섹션에 노출)되면 첫 이름 유지
            codes.setdefault(code, name)

        self._dept_map = codes
        logger.info(f"[PNUYH] 진료과/센터 {len(codes)}개 수집")
        return codes

    # ─── 팀 페이지 파싱 ───

    def _parse_team_page(self, html: str, treat_cd: str, dept_group_name: str) -> list[dict]:
        """department-team.do → 의사 + 스케줄 (한 페이지에 모두 있음)."""
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []

        for li in soup.select("ul.team_list > li"):
            doc = li.select_one("div.team_doctor")
            if not doc:
                continue
            strong = doc.find("strong")
            if not strong:
                continue
            # strong 안 한글/영문이 줄바꿈으로 구분됨
            raw = _clean(strong.get_text(" ", strip=True))
            m = re.match(r"^([^()]+?)(?:\s*\(.*)?$", raw)
            name = _clean(m.group(1)) if m else raw
            if not name:
                continue

            # doctorNo 추출 — 상세소개 링크에 있음
            doctor_no = ""
            for a in doc.select("a[href*='doctorNo=']"):
                mm = _DOCTORNO_RE.search(a.get("href", ""))
                if mm:
                    doctor_no = mm.group(1)
                    break
            # 일부 의사 블록은 상세소개만 있고 예약 링크가 있을 수 있음 — teamIntro 우선
            if not doctor_no:
                a_intro = doc.select_one("a[href*='teamIntro']")
                if a_intro:
                    mm = _DOCTORNO_RE.search(a_intro.get("href", ""))
                    if mm:
                        doctor_no = mm.group(1)
            if not doctor_no:
                # 폴백: 이미지 파일명에 board attach id
                img = doc.find("img")
                if img is not None:
                    mm = re.search(r"/image/([0-9]+)_", img.get("src") or "")
                    if mm:
                        doctor_no = mm.group(1)
            if not doctor_no:
                continue

            # 실제 진료과 — 소속과 dd 값 (센터에 소속된 의사도 원래 진료과가 따로 존재)
            department = dept_group_name
            for dl in doc.find_all("dl"):
                dt = dl.find("dt")
                dd = dl.find("dd")
                if not dt or not dd:
                    continue
                if "소속" in dt.get_text():
                    val = _clean(dd.get_text(" ", strip=True))
                    if val:
                        department = val
                    break

            # 전문분야
            specialty = ""
            for dl in doc.find_all("dl"):
                dt = dl.find("dt")
                dd = dl.find("dd")
                if not dt or not dd:
                    continue
                if "진료분야" in dt.get_text():
                    specialty = _clean(dd.get_text(" ", strip=True))
                    break

            # 사진
            photo_url = ""
            img = doc.find("img")
            if img is not None:
                src = (img.get("src") or "").strip()
                if src and not src.startswith("data:"):
                    photo_url = src if src.startswith("http") else f"{self.BASE_URL}{src if src.startswith('/') else '/' + src}"

            # 주간 스케줄
            schedules = self._parse_team_table(li.select_one("div.team_table table"))

            ext_id = f"PNUYH-{treat_cd}-{doctor_no}"
            profile_url = (
                f"{self.BASE_URL}/pnuyh/medical/department/department-teamIntro.do"
                f"?doctorNo={doctor_no}&treatCd={treat_cd}"
            )
            out.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "doctor_no": doctor_no,
                "treat_cd": treat_cd,
                "name": name,
                "department": department,
                "position": "교수",
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
            })
        return out

    def _parse_team_table(self, table) -> list[dict]:
        """개별 의사 주간 시간표 테이블 → schedules."""
        if table is None:
            return []
        # thead: 진료시간 / 월 / 화 / 수 / 목 / 금 / 토
        headers = table.select("thead th")
        day_names: list[str] = []
        for th in headers[1:]:
            t = _clean(th.get_text(" ", strip=True))
            if t in _KDAY:
                day_names.append(t)
        if not day_names:
            return []

        found: set[tuple[int, str]] = set()
        for tr in table.select("tbody tr"):
            th = tr.find("th")
            slot_label = _clean(th.get_text(" ", strip=True)) if th else ""
            if "오전" in slot_label:
                slot = "morning"
            elif "오후" in slot_label:
                slot = "afternoon"
            else:
                continue
            tds = tr.find_all("td")
            for idx, td in enumerate(tds[:len(day_names)]):
                text = _clean((td.get("data-schedule") or "") + " " + td.get_text(" ", strip=True))
                if not is_clinic_cell(text):
                    continue
                dow = _KDAY.get(day_names[idx])
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

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, treat_cd: str, dept_name: str) -> list[dict]:
        url = f"{self.BASE_URL}{self.TEAM_URL}?treatCd={treat_cd}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[PNUYH] {treat_cd}({dept_name}) 로드 실패: {e}")
            return []
        return self._parse_team_page(resp.text, treat_cd, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_map(client)
            if not depts:
                self._cached_data = []
                return self._cached_data

            sem = asyncio.Semaphore(4)

            async def _one(code: str, name: str) -> list[dict]:
                async with sem:
                    return await self._fetch_dept_doctors(client, code, name)

            results = await asyncio.gather(
                *[_one(c, n) for c, n in depts.items()],
                return_exceptions=True,
            )

        merged: dict[str, dict] = {}
        for r in results:
            if isinstance(r, Exception):
                continue
            for d in r:
                merged.setdefault(d["external_id"], d)

        data = list(merged.values())
        logger.info(f"[PNUYH] 총 {len(data)}명")
        self._cached_data = data
        return data

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_map(client)
        return [{"code": c, "name": n} for c, n in sorted(depts.items())]

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
        """개별 교수 조회 — external_id 에서 treatCd 파싱 후 해당 진료과 1곳만 요청."""
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

        prefix = "PNUYH-"
        if not staff_id.startswith(prefix):
            return empty
        raw = staff_id[len(prefix):]
        if "-" not in raw:
            return empty
        treat_cd, doctor_no = raw.split("-", 1)
        if not treat_cd or not doctor_no:
            return empty

        async with self._make_client() as client:
            depts = await self._fetch_dept_map(client)
            dept_name = depts.get(treat_cd, "")
            docs = await self._fetch_dept_doctors(client, treat_cd, dept_name)

        for d in docs:
            if d["doctor_no"] == doctor_no:
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

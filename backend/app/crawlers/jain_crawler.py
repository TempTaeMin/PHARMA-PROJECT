"""더자인병원(The Jain Hospital) 크롤러

병원 공식명: 더자인병원 (경기 고양시 덕양구 중앙로 555)
홈페이지: www.the-jain.co.kr
기술: 단일 정적 HTML (httpx + BeautifulSoup)

구조:
  겉 페이지(`/bbs/content.php?co_id=jain_m1_4`)는 iframe 껍데기이며,
  실제 의료진 데이터는 iframe 대상인
  `/new_old/jain2020/01about/about03.php` 한 페이지에 전부 렌더링됨.

  페이지 구성:
    - `.docList ul li` = 의사 카드 (썸네일 + 진료과 + 이름 + 직책 + #docInfo_{id} 링크)
    - `#docInfo_{id}` 섹션 = 의사별 상세 (진료과, 전문분야, 진료시간표)
      - `.docInfo p` 내부의 `<strong>진료과</strong><span>...</span>` / `<strong>전문분야</strong><span>...</span>`
      - `.typeList table`: 오전/오후 × 월~토 6일 표
        - `span.iconStatus.statusOn`  = 진료 (외래)
        - `span.iconStatus.statusQ`   = 수술 (제외)
        - `span.iconStatus.statusOff` = 휴진 (제외)
        - 빈 td = 미진료

external_id: JAIN-{docid}
  docid = docList 링크의 #docInfo_{n} 숫자 부분 (사이트가 내부적으로 부여한 고유 ID).
  중복 엔트리(예: 고용 원장이 docInfo_99, docInfo_125 로 두 번 등장) 는 첫 번째만 채택.

건강검진 패키지(건강증진센터 하위 "검진") 카드는 이미지 파일명이 `checkup_*`/`n_checkup_*` 이므로
의사로 취급하지 않고 필터링.
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.the-jain.co.kr"
# iframe 실제 데이터 페이지
DOCTORS_URL = f"{BASE_URL}/new_old/jain2020/01about/about03.php"
# 사용자에게 노출할 프로필 URL (겉 페이지)
PROFILE_BASE_URL = f"{BASE_URL}/bbs/content.php?co_id=jain_m1_4"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DOC_ID_RE = re.compile(r"#docInfo_(\d+)")
CHECKUP_IMG_RE = re.compile(r"/(?:n_)?checkup_\d+\.", re.IGNORECASE)


class JainCrawler:
    """더자인병원 크롤러 — iframe 안의 단일 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "JAIN"
        self.hospital_name = "더자인병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": PROFILE_BASE_URL,
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
            logger.error(f"[JAIN] 페이지 로드 실패: {e}")
            return None
        # 이 페이지는 meta charset=utf-8
        soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    # ─── 카드 / 섹션 파싱 ───

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "")).strip()

    def _parse_card(self, li) -> dict | None:
        """.docList ul li → {docid, name, department, position, photo_url}"""
        a = li.find("a", href=True)
        if not a:
            return None
        m = DOC_ID_RE.search(a["href"])
        if not m:
            return None
        docid = m.group(1)

        img = a.find("img")
        img_src = (img.get("src", "") if img else "").strip()
        alt_name = self._clean(img.get("alt", "")) if img else ""

        # 건강검진 패키지(의사 아님) 필터링
        if img_src and CHECKUP_IMG_RE.search(img_src):
            return None

        span = a.find("span")
        if not span:
            return None
        strong = span.find("strong")
        # span 안 'strong' 바깥 텍스트 = 진료과
        dept = ""
        if strong is not None:
            # strong 앞쪽 텍스트만 추출
            dept_parts = []
            for node in span.children:
                if node is strong:
                    break
                if isinstance(node, str):
                    dept_parts.append(node)
            dept = self._clean(" ".join(dept_parts))
        else:
            dept = self._clean(span.get_text(" ", strip=True))

        # strong 내부 = "{이름} {직책}"
        name = ""
        position = ""
        if strong is not None:
            raw = self._clean(strong.get_text(" ", strip=True))
            # 이름(한글 2~4자)와 직책 분리
            m2 = re.match(r"^([가-힣]{2,4})\s+(.+)$", raw)
            if m2:
                name, position = m2.group(1), self._clean(m2.group(2))
            else:
                name = raw

        # 폴백: name 이 비면 img alt
        if not name:
            name = alt_name

        # 건강검진 카드의 position 은 보통 "검진" — 필터(이중 안전망)
        if position == "검진" and "검진" in dept:
            return None
        if not name:
            return None

        photo_url = img_src if (img_src.startswith("http") or not img_src) else f"{BASE_URL}{img_src}"

        return {
            "docid": docid,
            "name": name,
            "department": dept,
            "position": position,
            "photo_url": photo_url,
        }

    def _parse_section(self, sec) -> dict:
        """#docInfo_{id} docSection → {specialty, schedules}"""
        specialty = ""
        # docInfo 내부 p > strong:contains(전문분야) + span
        info = sec.select_one(".docInfo")
        if info is not None:
            for p in info.find_all("p"):
                st = p.find("strong")
                sp = p.find("span")
                if not st or not sp:
                    continue
                label = self._clean(st.get_text(" ", strip=True))
                if "전문분야" in label:
                    # <br> 를 개행으로 치환 → 한 줄 합치기
                    sp_copy = BeautifulSoup(str(sp), "html.parser")
                    for br in sp_copy.find_all("br"):
                        br.replace_with("\n")
                    txt = sp_copy.get_text("\n", strip=True)
                    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
                    specialty = ", ".join(lines)
                    break

        schedules = self._parse_schedule_table(sec)
        return {"specialty": specialty, "schedules": schedules}

    def _parse_schedule_table(self, sec) -> list[dict]:
        table = sec.select_one(".typeList table")
        if table is None:
            return []
        tbody = table.find("tbody") or table
        rows = tbody.find_all("tr", recursive=False) if tbody.name == "tbody" else tbody.find_all("tr")
        schedules: list[dict] = []
        for tr in rows:
            th = tr.find("th")
            if not th:
                continue
            label = self._clean(th.get_text(" ", strip=True))
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            tds = tr.find_all("td")
            # 월(0) ~ 토(5), 일요일은 아예 컬럼 없음
            for dow, td in enumerate(tds[:6]):
                cell_text = self._clean(td.get_text(" ", strip=True))
                if not cell_text:
                    continue
                # 셀 판정: "진료" 는 포함, "수술/휴진" 은 제외 (공용 유틸)
                if not is_clinic_cell(cell_text):
                    continue
                s, e = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": s,
                    "end_time": e,
                    "location": "",
                })
        return schedules

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            soup = await self._fetch_page(client)

        if soup is None:
            self._cached_data = []
            return []

        # 섹션 인덱스: docid → section element
        sections: dict[str, any] = {}
        for sec in soup.select("div.docSection.aboutDoc"):
            sec_id = sec.get("id", "")
            m = re.match(r"docInfo_(\d+)$", sec_id)
            if m:
                sections[m.group(1)] = sec

        result: list[dict] = []
        seen: set[str] = set()
        for li in soup.select(".docList ul li"):
            card = self._parse_card(li)
            if not card:
                continue
            docid = card["docid"]
            ext_id = f"JAIN-{docid}"
            if ext_id in seen:
                continue
            seen.add(ext_id)

            sec = sections.get(docid)
            extra = self._parse_section(sec) if sec is not None else {"specialty": "", "schedules": []}

            # profile_url: 겉 페이지 + 해시 (사용자가 해당 섹션 바로 볼 수 있게)
            profile_url = f"{PROFILE_BASE_URL}#docInfo_{docid}"

            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": card["name"],
                "department": card["department"],
                "position": card["position"],
                "specialty": extra["specialty"],
                "profile_url": profile_url,
                "photo_url": card["photo_url"],
                "notes": "",
                "schedules": extra["schedules"],
                "date_schedules": [],
                "_docid": docid,
            })

        logger.info(f"[JAIN] 총 {len(result)}명")
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
        """개별 교수 조회 — 단일 페이지 1회 GET 후 해당 섹션만 파싱 (skill 규칙 #7)"""
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

        prefix = "JAIN-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id or not raw_id.isdigit():
            return empty

        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            return empty

        # 해당 카드 + 섹션만 직접 타겟팅
        target_li = None
        for li in soup.select(".docList ul li"):
            a = li.find("a", href=True)
            if a and f"#docInfo_{raw_id}" in a["href"]:
                target_li = li
                break
        if target_li is None:
            return empty
        card = self._parse_card(target_li)
        if not card:
            return empty

        sec = soup.select_one(f"div.docSection.aboutDoc#docInfo_{raw_id}")
        extra = self._parse_section(sec) if sec is not None else {"specialty": "", "schedules": []}

        return {
            "staff_id": staff_id,
            "name": card["name"],
            "department": card["department"],
            "position": card["position"],
            "specialty": extra["specialty"],
            "profile_url": f"{PROFILE_BASE_URL}#docInfo_{raw_id}",
            "notes": "",
            "schedules": extra["schedules"],
            "date_schedules": [],
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

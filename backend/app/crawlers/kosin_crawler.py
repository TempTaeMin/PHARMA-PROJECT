"""고신대학교복음병원 (Kosin University Gospel Hospital) 크롤러

병원 공식명: 고신대학교복음병원
홈페이지: https://www.kosinmed.or.kr
기술: 정적 HTML (httpx + BeautifulSoup)
인코딩: UTF-8

구조 (중요 — 사이트 특성):
  - 단일 페이지 /depart/depart_11.php (쿼리스트링 없이) 가 전체 의료진 ~194명을
    하나의 HTML 로 렌더링한다. 각 교수는 `div.staff-wrap` 블록이며
    - 이름: `div.staff-wrap .name b.heading1`
    - 직책: 이름 `b` 태그 뒤 텍스트 (대부분 "교수")
    - 상세보기 링크: `a[href^="depart_1_detail.php?idx=..."]` → idx 가 교수 원내코드
    - 진료과: `dt:contains(진료과) + dd` (총 41개과)
    - 전문분야: `dt:contains(전문 진료 분야) + dd`
    - 사진: `div.img img[src]`
    - 스케줄 테이블: `table.time` (월~금 + 휴진안내 컬럼)
      · `<td class="primary">외래` → 외래 (MR 방문 가능)
      · `<td class="gray">시술|내시경|연구|약/서류|특수클리닉` → 제외
      · 빈 셀 (class 없음) → 휴진/비활성
  - 스케줄 셀은 오전/오후 2행 × 월~금 5열. 토요일 컬럼은 사이트 주석처럼 제거됨.
  - 휴진 정보(날짜별)는 AJAX `/module/board/ajax_staff_break_list.php?idx=N` 로 조회
    가능하지만, 본 크롤러는 주간 요일패턴(`schedules`)만 생산한다.
    → `date_schedules` 는 미지원 병원 규칙대로 빈 리스트.

external_id: KOSIN-{idx}
"""
import re
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.kosinmed.or.kr"
LIST_URL = f"{BASE_URL}/depart/depart_11.php"
DETAIL_URL = f"{BASE_URL}/depart/depart_1_detail.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 요일 헤더 → day_of_week (0=월)
DAY_HEADERS = ("월", "화", "수", "목", "금", "토")

# 사이트 주석에 따라 토요일 컬럼은 기본적으로 제거돼 있고 월~금 5열이 일반.
# 혹시 토요일이 추가되는 교수가 있을 가능성을 대비해 thead 헤더를 동적으로 파싱.


class KosinCrawler:
    """고신대학교복음병원 크롤러 — UTF-8 정적 HTML 단일 페이지.

    사이트 특성상 `/depart/depart_11.php` 한 번 호출로 전 교수 + 스케줄이
    모두 수집되므로 `_fetch_all()` 은 1 request 로 완료된다.
    """

    def __init__(self):
        self.hospital_code = "KOSIN"
        self.hospital_name = "고신대학교복음병원"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 파싱 헬퍼 ───

    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    def _parse_schedule_table(self, table) -> list[dict]:
        """`table.time` → 주간 요일패턴 리스트 반환.

        헤더: [구분, 월, 화, 수, 목, 금, (토?), 휴진안내]
        - 첫 열은 오전/오후 라벨
        - 마지막 "휴진안내" 컬럼은 rowspan=2 버튼이라 tbody 에서는
          첫 tr 에만 존재한다 (스케줄 대상 아님).
        - 활성 판정: `td.primary` 또는 셀 텍스트가 is_clinic_cell 통과.
        - 제외 판정: `td.gray` (예: 시술/내시경/연구/약/서류/특수클리닉).
        """
        # 헤더에서 요일 컬럼의 순서/범위 파악
        thead = table.find("thead")
        if not thead:
            return []
        header_cells = [self._clean(th.get_text(" ", strip=True))
                        for th in thead.find_all("th")]
        # 첫 th = 구분, 마지막 th = 휴진안내
        # 중간이 월~금 (혹은 월~토)
        day_labels = header_cells[1:]  # drop 구분
        # 휴진안내 컬럼 식별
        dayoff_idx = None
        for i, lbl in enumerate(day_labels):
            if "휴진" in lbl:
                dayoff_idx = i
                break
        if dayoff_idx is not None:
            day_labels = day_labels[:dayoff_idx]
        # day_labels → day_of_week 매핑
        dow_of_col: list[int] = []
        for lbl in day_labels:
            matched = -1
            for d, name in enumerate(DAY_HEADERS):
                if name in lbl:
                    matched = d
                    break
            dow_of_col.append(matched)

        tbody = table.find("tbody")
        if not tbody:
            return []
        rows = tbody.find_all("tr", recursive=False)

        schedules: list[dict] = []
        seen: set[tuple[int, str]] = set()

        for r_idx, tr in enumerate(rows[:2]):  # 오전(0), 오후(1)
            slot = "morning" if r_idx == 0 else "afternoon"
            start, end = TIME_RANGES[slot]
            tds = tr.find_all("td", recursive=False)
            if not tds:
                continue
            # 첫 td = 오전/오후 라벨. 2번째~부터 요일셀.
            body_cells = tds[1:]
            # 오전 행에는 휴진안내 rowspan 셀도 tds 마지막에 존재 → 제외
            # 오후 행에는 없음.
            # 따라서 body_cells 중 처음 len(dow_of_col) 개만 사용.
            body_cells = body_cells[:len(dow_of_col)]

            for col_idx, cell in enumerate(body_cells):
                if col_idx >= len(dow_of_col):
                    break
                dow = dow_of_col[col_idx]
                if dow < 0:
                    continue
                # class 우선 판정 — gray 는 명시적 제외
                classes = cell.get("class") or []
                text = self._clean(cell.get_text(" ", strip=True))
                if "gray" in classes:
                    continue
                active = False
                if "primary" in classes:
                    active = True
                elif text:
                    # 클래스 없지만 텍스트 있는 경우 공용 판정기 사용
                    active = is_clinic_cell(text)
                if not active:
                    continue
                key = (dow, slot)
                if key in seen:
                    continue
                seen.add(key)
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        schedules.sort(key=lambda s: (s["day_of_week"],
                                       0 if s["time_slot"] == "morning" else 1))
        return schedules

    def _parse_staff_block(self, block) -> dict | None:
        """`div.staff-wrap` 1개 → 의사 dict"""
        # 이름 + 직책
        name_p = block.select_one("p.name")
        if not name_p:
            return None
        b = name_p.find("b")
        if not b:
            return None
        name = self._clean(b.get_text(" ", strip=True))
        if not name:
            return None
        # b 뒤 텍스트 = 직책
        position_parts: list[str] = []
        for node in name_p.children:
            if node is b:
                continue
            if getattr(node, "name", None) == "b":
                continue
            if isinstance(node, str):
                position_parts.append(node)
            else:
                position_parts.append(node.get_text(" ", strip=True))
        position = self._clean(" ".join(position_parts))

        # idx
        link = block.select_one('a[href*="depart_1_detail.php"]')
        idx = ""
        profile_url = ""
        if link:
            href = link.get("href", "")
            m = re.search(r"idx=(\d+)", href)
            if m:
                idx = m.group(1)
                # 상대경로면 절대화
                if href.startswith("http"):
                    profile_url = href
                elif href.startswith("/"):
                    profile_url = f"{BASE_URL}{href}"
                else:
                    profile_url = f"{BASE_URL}/depart/{href}"
        if not idx:
            return None

        # 진료과 / 전문 진료 분야
        department = ""
        specialty = ""
        for dl in block.select("div.clinic dl"):
            dt = dl.find("dt")
            dd = dl.find("dd")
            if not dt or not dd:
                continue
            label = self._clean(dt.get_text(" ", strip=True))
            value = self._clean(dd.get_text(" ", strip=True))
            if "진료과" in label and "분야" not in label:
                department = value
            elif "전문" in label or "분야" in label:
                specialty = value

        # 사진
        photo_url = ""
        img = block.select_one("div.img img")
        if img is not None:
            src = (img.get("src") or "").strip()
            if src:
                photo_url = src if src.startswith("http") else f"{BASE_URL}{src if src.startswith('/') else '/' + src}"

        # 스케줄 테이블
        table = block.select_one("table.time")
        schedules = self._parse_schedule_table(table) if table else []

        ext_id = f"{self.hospital_code}-{idx}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "doc_idx": idx,
            "name": name,
            "department": department,
            "position": position or "교수",
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    def _parse_list_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        doctors: list[dict] = []
        seen_ids: set[str] = set()
        for block in soup.select("div.staff-wrap"):
            # "staff-wrap detail" 은 단독 상세페이지 구조이므로 스킵
            cls = block.get("class") or []
            if "detail" in cls:
                continue
            doc = self._parse_staff_block(block)
            if not doc:
                continue
            if doc["external_id"] in seen_ids:
                continue
            seen_ids.add(doc["external_id"])
            doctors.append(doc)
        return doctors

    # ─── 네트워크 ───

    async def _fetch_list_html(self, client: httpx.AsyncClient) -> str:
        try:
            resp = await client.get(LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[KOSIN] 목록 페이지 로드 실패: {e}")
            return ""
        try:
            return resp.content.decode("utf-8")
        except UnicodeDecodeError:
            return resp.content.decode("utf-8", errors="replace")

    async def _fetch_detail_html(self, client: httpx.AsyncClient, idx: str) -> str:
        try:
            resp = await client.get(DETAIL_URL, params={"idx": idx})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[KOSIN] 상세 페이지 로드 실패 idx={idx}: {e}")
            return ""
        try:
            return resp.content.decode("utf-8")
        except UnicodeDecodeError:
            return resp.content.decode("utf-8", errors="replace")

    def _parse_detail_html(self, html: str, idx: str) -> dict | None:
        """상세 페이지 1개 → 의사 dict (개별 조회 전용)"""
        soup = BeautifulSoup(html, "html.parser")
        block = soup.select_one("div.staff-wrap.detail") or soup.select_one("div.staff-wrap")
        if not block:
            return None

        name_p = block.select_one("p.name")
        b = name_p.find("b") if name_p else None
        if not (name_p and b):
            return None
        name = self._clean(b.get_text(" ", strip=True))
        if not name:
            return None
        position_parts = []
        for node in name_p.children:
            if node is b or getattr(node, "name", None) == "b":
                continue
            if isinstance(node, str):
                position_parts.append(node)
            else:
                position_parts.append(node.get_text(" ", strip=True))
        position = self._clean(" ".join(position_parts)) or "교수"

        # 진료과: 상세 페이지는 `span.depart` 에 표시
        department = ""
        dep_span = block.select_one("span.depart")
        if dep_span:
            department = self._clean(dep_span.get_text(" ", strip=True))

        # 전문분야
        specialty = ""
        for dl in block.select("div.clinic dl"):
            dt = dl.find("dt")
            dd = dl.find("dd")
            if dt and dd:
                label = self._clean(dt.get_text(" ", strip=True))
                value = self._clean(dd.get_text(" ", strip=True))
                if "전문" in label or "분야" in label:
                    specialty = value

        # 사진
        photo_url = ""
        img = block.select_one("div.img img")
        if img is not None:
            src = (img.get("src") or "").strip()
            if src:
                photo_url = src if src.startswith("http") else f"{BASE_URL}{src if src.startswith('/') else '/' + src}"

        # 스케줄
        table = block.select_one("table.time")
        schedules = self._parse_schedule_table(table) if table else []

        ext_id = f"{self.hospital_code}-{idx}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "doc_idx": idx,
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "profile_url": f"{DETAIL_URL}?idx={idx}",
            "photo_url": photo_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    # ─── 전체 수집 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            html = await self._fetch_list_html(client)
            if not html:
                self._cached_data = []
                return []
            doctors = self._parse_list_html(html)

        logger.info(f"[KOSIN] 총 {len(doctors)}명 수집")
        self._cached_data = doctors
        return doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        """진료과 목록 — 의료진 리스트에서 수집되는 unique 진료과 반환."""
        data = await self._fetch_all()
        dept_names: list[str] = []
        seen: set[str] = set()
        for d in data:
            name = d.get("department", "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            dept_names.append(name)
        dept_names.sort()
        # 사이트는 진료과별 숫자 코드를 외부에 노출하지 않으므로 이름을 code 로 사용.
        return [{"code": name, "name": name} for name in dept_names]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "notes")
        return [{k: d.get(k, "") for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 상세 페이지(`depart_1_detail.php?idx=N`) 1건만 호출.

        SKILL 규칙 #7 준수: `_fetch_all()` 호출 금지. 해당 교수의 상세 URL 만 fetch.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 같은 인스턴스에서 이미 _fetch_all() 돈 경우만 캐시 사용.
        if self._cached_data is not None:
            for d in self._cached_data:
                if d.get("staff_id") == staff_id or d.get("external_id") == staff_id:
                    return {
                        "staff_id": staff_id,
                        "name": d.get("name", ""),
                        "department": d.get("department", ""),
                        "position": d.get("position", ""),
                        "specialty": d.get("specialty", ""),
                        "profile_url": d.get("profile_url", ""),
                        "notes": d.get("notes", ""),
                        "schedules": d.get("schedules", []),
                        "date_schedules": d.get("date_schedules", []),
                    }
            return empty

        prefix = f"{self.hospital_code}-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id.isdigit():
            return empty

        async with self._make_client() as client:
            html = await self._fetch_detail_html(client, raw_id)
        if not html:
            return empty

        doc = self._parse_detail_html(html, raw_id)
        if not doc:
            return empty

        return {
            "staff_id": doc["staff_id"],
            "name": doc["name"],
            "department": doc["department"],
            "position": doc["position"],
            "specialty": doc["specialty"],
            "profile_url": doc["profile_url"],
            "notes": doc.get("notes", ""),
            "schedules": doc["schedules"],
            "date_schedules": doc["date_schedules"],
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
                photo_url=d.get("photo_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d.get("schedules", []),
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

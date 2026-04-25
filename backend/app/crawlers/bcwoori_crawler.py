"""부천우리병원(Bucheon Woori Hospital) 크롤러

병원 공식명: 부천우리병원
홈페이지: www.urimedi.com
기술: 단일 정적 HTML (httpx + BeautifulSoup)

구조:
  `/sub14.php` 한 페이지에 전체 진료과/의사 탭으로 렌더링.
    - `div.tab_con.doctor_tab_con` = 진료과 1개
        - `strong.sub_txt.fw_500` = 진료과 이름
        - `div.doctor_list` = 의사 1명
            - `strong.sub_txt2.fw_500` = "이름 직책" (예: "한상훤 병원장")
            - `div.doctor_history` → `li.doctor_pf_box` 내
                `strong.fw_500 > b` = 이름
                `div.doctor_pf_txt` = 진료분야/약력
                `div.doctor_time` = 진료시간표
                    `div.am_time dl dd.active` = 오전 활성 요일 (월~토 순)
                    `div.pm_time dl dd.active` = 오후 활성 요일
                    `dd.active.active_red`    = 휴진 (비활성 처리)
                    `dd.active.active_orange` = 내시경/수술 등 (외래 아님, 제외)
                    `dd.active.active_green`  = 수술 (외래 아님, 제외)
                    `dd.dummy`                = 빈 칸 (토요일 오후 등)
                    `dd.active` 만 단독이면 외래 진료로 판정

external_id: BCWOORI-{md5(dept|name)[:10]}
  — 동명이인이 같은 진료과에 없다는 전제(부천우리 규모상 안전).
  폴백 없음. 이미지 파일명 토큰은 재업로드 시 바뀔 수 있어 사용하지 않음.
"""
import re
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.urimedi.com"
DOCTORS_URL = f"{BASE_URL}/sub14.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 요일 헤더 순서 (사이트 고정: 월 화 수 목 금 토)
DAY_ORDER = ["월", "화", "수", "목", "금", "토"]
DAY_INDEX = {d: i for i, d in enumerate(DAY_ORDER)}

# 외래 진료 제외 표시 (오렌지=내시경/특수시술, 그린=수술, 레드=휴진)
EXCLUDE_CLASSES = {"active_red", "active_orange", "active_green"}

# "한상훤 병원장", "오유석 부장" 처럼 "이름 + 직책" 이 한 span 에 섞인 경우 분리용
POSITION_TOKENS = (
    "병원장", "부원장", "원장", "부장", "과장", "실장", "센터장",
    "교수", "전임의", "진료의", "명예원장",
)


class BcwooriCrawler:
    """부천우리병원 크롤러 — 단일 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "BCWOORI"
        self.hospital_name = "부천우리병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
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
            logger.error(f"[BCWOORI] sub14.php 로드 실패: {e}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    @staticmethod
    def _make_external_id(department: str, name: str) -> str:
        digest = hashlib.md5(f"{department}|{name}".encode("utf-8")).hexdigest()[:10]
        return f"BCWOORI-{digest}"

    @staticmethod
    def _split_name_position(raw: str) -> tuple[str, str]:
        """
        '한상훤 병원장' → ('한상훤', '병원장')
        '오유석 부장'  → ('오유석', '부장')
        직책 토큰이 없으면 전체를 이름으로 본다.
        """
        if not raw:
            return "", ""
        t = " ".join(raw.split())
        for tok in POSITION_TOKENS:
            if t.endswith(tok):
                name = t[: -len(tok)].strip()
                return name, tok
            # 중간에 직책이 있을 경우 (드묾) — 공백 기준 마지막 토큰이 직책이면
        parts = t.split()
        if len(parts) >= 2 and parts[-1] in POSITION_TOKENS:
            return " ".join(parts[:-1]), parts[-1]
        return t, ""

    def _parse_schedule(self, time_box) -> list[dict]:
        """`div.doctor_time` → schedules 리스트"""
        schedules: list[dict] = []
        if time_box is None:
            return schedules

        def _collect(row_selector: str, slot: str) -> None:
            row = time_box.select_one(row_selector)
            if row is None:
                return
            dds = row.select("dl > dd")
            # 첫 dd 가 라벨(오전진료/오후진료)이면 건너뜀 — 실제 HTML 은 <dt> 라벨이 따로 있어
            # 이 리스트는 월~토 6개(오전) / 월~금 5개+dummy(오후) 로 구성됨.
            day_cells = [c for c in dds]
            start, end = TIME_RANGES[slot]
            for di, cell in enumerate(day_cells):
                if di >= len(DAY_ORDER):
                    break
                classes = set(cell.get("class", []))
                if "dummy" in classes:
                    continue
                if "active" not in classes:
                    continue
                # 휴진/내시경/수술 등은 active_* 마커로 제외
                if classes & EXCLUDE_CLASSES:
                    continue
                schedules.append({
                    "day_of_week": di,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        _collect("div.am_time", "morning")
        _collect("div.pm_time", "afternoon")
        return schedules

    def _parse_doctor_block(self, block, department: str) -> dict | None:
        """`div.doctor_list` 1개 → 의사 dict"""
        name = ""
        position = ""

        # 1차: doctor_pf_box 안의 <b> 에 이름이 깔끔히 들어 있음
        pf_box = block.select_one("li.doctor_pf_box")
        if pf_box is not None:
            b_tag = pf_box.select_one("strong.fw_500 > b")
            if b_tag:
                name = b_tag.get_text(strip=True)
            strong_tag = pf_box.select_one("strong.fw_500")
            if strong_tag:
                full_text = strong_tag.get_text(" ", strip=True)
                # "한상훤 병원장" 에서 이름 제외 부분이 직책
                if name and full_text.startswith(name):
                    position = full_text[len(name):].strip()
                elif not name:
                    name, position = self._split_name_position(full_text)

        # 2차 폴백: 상단 카드의 sub_txt2
        if not name:
            top = block.select_one("strong.sub_txt2.fw_500")
            if top:
                name, position = self._split_name_position(top.get_text(strip=True))

        if not name:
            return None

        # 진료분야 (specialty)
        specialty = ""
        if pf_box is not None:
            for title in pf_box.select("p.doctor_pf_title"):
                if title.get_text(strip=True) == "진료분야":
                    dl = title.find_next_sibling("dl")
                    if dl:
                        specialty = dl.get_text(" ", strip=True)
                    break

        # 사진
        photo_url = ""
        img = block.select_one("li.doctor_pf_img img")
        if img is None:
            img = block.select_one("span.thum img")
        if img:
            src = img.get("src", "")
            photo_url = src if src.startswith("http") else f"{BASE_URL}{src}"

        # 스케줄
        time_box = block.select_one("div.doctor_time")
        schedules = self._parse_schedule(time_box)

        # 진료과 라벨 확인 (카드 내부 common_txt 가 진료과 탭과 다른 경우 — 응급실 탭에
        # 가정의학과 김재민 과장이 섞여 있는 케이스 처리)
        common_txt = block.select_one("span.common_txt")
        actual_dept = department
        if common_txt:
            ct = common_txt.get_text(strip=True)
            if ct and ct != department:
                actual_dept = ct

        return {
            "name": name,
            "department": actual_dept,
            "position": position,
            "specialty": specialty,
            "profile_url": DOCTORS_URL,
            "photo_url": photo_url,
            "schedules": schedules,
            "date_schedules": [],
            "notes": "",
        }

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            soup = await self._fetch_page(client)

        if soup is None:
            self._cached_data = []
            return []

        result: list[dict] = []
        seen: set[str] = set()

        for tab in soup.select("div.tab_con.doctor_tab_con"):
            title_el = tab.select_one("strong.sub_txt.fw_500")
            dept = title_el.get_text(strip=True) if title_el else ""
            for block in tab.select("div.doctor_list"):
                doc = self._parse_doctor_block(block, dept)
                if not doc:
                    continue
                ext_id = self._make_external_id(doc["department"], doc["name"])
                if ext_id in seen:
                    continue
                seen.add(ext_id)
                doc["staff_id"] = ext_id
                doc["external_id"] = ext_id
                result.append(doc)

        logger.info(f"[BCWOORI] 총 {len(result)}명 수집 (진료과 {len({d['department'] for d in result})}개)")
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
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "position": d.get("position", ""),
                "specialty": d.get("specialty", ""),
                "profile_url": d.get("profile_url", ""),
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회.

        sub14.php 는 전체 의료진을 한 페이지에 담는 단일 HTML 이라, 개별 URL 이 따로
        없다. 따라서 이 페이지만 1회 GET 후 해당 의사 블록만 골라 파싱한다
        (다른 의사 상세 페이지는 호출하지 않으므로 개별 조회 규칙 준수).
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 내 캐시 히트
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {
                        "staff_id": d["staff_id"],
                        "name": d["name"],
                        "department": d["department"],
                        "position": d.get("position", ""),
                        "specialty": d.get("specialty", ""),
                        "profile_url": d.get("profile_url", ""),
                        "notes": d.get("notes", ""),
                        "schedules": d.get("schedules", []),
                        "date_schedules": d.get("date_schedules", []),
                    }
            return empty

        # sub14.php 1회 GET 후 타겟 블록만 파싱
        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            return empty

        for tab in soup.select("div.tab_con.doctor_tab_con"):
            title_el = tab.select_one("strong.sub_txt.fw_500")
            dept = title_el.get_text(strip=True) if title_el else ""
            for block in tab.select("div.doctor_list"):
                doc = self._parse_doctor_block(block, dept)
                if not doc:
                    continue
                ext_id = self._make_external_id(doc["department"], doc["name"])
                if ext_id != staff_id:
                    continue
                return {
                    "staff_id": staff_id,
                    "name": doc["name"],
                    "department": doc["department"],
                    "position": doc.get("position", ""),
                    "specialty": doc.get("specialty", ""),
                    "profile_url": doc.get("profile_url", ""),
                    "notes": doc.get("notes", ""),
                    "schedules": doc.get("schedules", []),
                    "date_schedules": [],
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

"""녹색병원 크롤러

구조: 단일 진료시간표 페이지에 17개 진료과 테이블 나열.
URL: http://www.greenhospital.co.kr/sub01/sub02.php

각 테이블 앞에 진료과명 헤더(h2/h3/h4/p)가 있고,
테이블은 ['{직책}','진료','월','화','수','목','금','토'] 헤더 + 의사별 2행(오전/오후).
셀 텍스트에 '격주 진료', '1·3번 토 휴진 2·4번 토' 같은 변칙 표기가 있음.
"""
import re
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell, has_biweekly_mark

logger = logging.getLogger(__name__)

BASE_URL = "http://www.greenhospital.co.kr"
TIMETABLE_URL = f"{BASE_URL}/sub01/sub02.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
DEPT_HINTS = ("과", "센터", "클리닉")
# 진료과 헤더로 잘못 잡히지 않게 거를 단어들 — 페이지 안내문/특이사항 박스 제외용
DEPT_NAME_EXCLUDE = ("특이사항", "안내", "비고", "공지", "참고", "유의", "주의")


class GreenCrawler:
    """녹색병원 크롤러 — 단일 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "GREEN"
        self.hospital_name = "녹색병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data = None

    @staticmethod
    def _make_ext_id(department: str, name: str) -> str:
        digest = hashlib.md5(f"{department}|{name}".encode("utf-8")).hexdigest()[:10]
        return f"GREEN-{digest}"

    @staticmethod
    def _find_dept_name(table) -> str:
        """테이블 직전의 진료과명 헤더 탐색 — h1~h5 또는 일반 태그 중 '과/센터/클리닉' 포함"""
        prev = table.find_previous(["h1", "h2", "h3", "h4", "h5", "p", "div"])
        while prev is not None:
            text = prev.get_text(" ", strip=True)
            if text and len(text) < 25 and any(h in text for h in DEPT_HINTS):
                # "문의: 02-..." / 안내·특이사항 박스의 헤더는 진료과명이 아니므로 거른다
                if (
                    "문의" in text or "전화" in text
                    or any(e in text for e in DEPT_NAME_EXCLUDE)
                ):
                    prev = prev.find_previous(["h1", "h2", "h3", "h4", "h5", "p", "div"])
                    continue
                return text
            prev = prev.find_previous(["h1", "h2", "h3", "h4", "h5", "p", "div"])
        return ""

    def _parse_table(self, table, department: str) -> list[dict]:
        """진료과 테이블 1개에서 의사별 정보 추출.

        테이블 헤더: [직책, 진료, 월, 화, 수, 목, 금, 토]
        이후 행: 의사1 오전(8칸) / 의사1 오후(7칸, rowspan) / 의사2 오전... 순
        첫 칸이 이름이면 오전 행, 아니면 '오후' 행.
        """
        rows = table.select("tr")
        if not rows:
            return []

        # 헤더에서 요일 → 컬럼 인덱스 매핑
        header_cells = rows[0].select("th, td")
        col_to_dow = {}
        first_header_text = header_cells[0].get_text(strip=True) if header_cells else ""
        # 헤더 첫 칸 = 직책명 (예: "과장", "부원장"). 대부분 position 라벨로 사용
        position_label = first_header_text if len(first_header_text) < 10 else ""
        for ci, cell in enumerate(header_cells):
            t = cell.get_text(strip=True)
            for ch, dow in DAY_MAP.items():
                if ch in t and len(t) <= 3:
                    col_to_dow[ci] = dow
                    break

        if not col_to_dow:
            return []

        doctors = {}
        current_name = ""
        current_slot_map: dict = {}

        for row in rows[1:]:
            cells = row.select("th, td")
            if not cells:
                continue
            first_text = cells[0].get_text(" ", strip=True)

            # 첫 셀이 "오전"/"오후"이면 같은 의사의 오후 행 (rowspan 구조)
            if first_text == "오전":
                slot = "morning"
                schedule_cells = cells[1:]
            elif first_text == "오후":
                slot = "afternoon"
                schedule_cells = cells[1:]
            elif first_text:
                # 의사 이름 + (같은 행에 '오전' 셀)
                # 이름 정제: ★ 이후 제거, 괄호 제거, 앞쪽의 한글 이름만 추출
                raw = first_text.split("★")[0]
                raw = re.sub(r"\s*\(.*?\)\s*", "", raw).strip()
                m = re.match(r"^([가-힣]{2,4}(?:\s[가-힣]{1,3})?)", raw)
                current_name = m.group(1).strip() if m else raw[:6].strip()
                # cells[1]이 '오전' 레이블
                if len(cells) >= 2 and cells[1].get_text(strip=True) in ("오전", "오후"):
                    slot = "morning" if cells[1].get_text(strip=True) == "오전" else "afternoon"
                    schedule_cells = cells[2:]
                else:
                    continue
            else:
                continue

            if not current_name:
                continue

            # 이름 행을 만나면 스케줄 유무와 관계없이 의사 등록
            if current_name not in doctors:
                doctors[current_name] = {
                    "name": current_name,
                    "department": department,
                    "position": position_label,
                    "specialty": "",
                    "schedules": [],
                    "_seen": set(),
                }

            # 컬럼 인덱스 조정 — schedule_cells는 요일 컬럼에 1:1 대응
            # header col_to_dow는 전체 행 기준이므로 week 컬럼만 추출
            # 헤더에서 요일 첫 번째 컬럼 인덱스 계산
            min_dow_col = min(col_to_dow.keys())
            # schedule_cells는 min_dow_col 부터 시작했다고 가정
            for idx, cell in enumerate(schedule_cells):
                abs_col = min_dow_col + idx
                if abs_col not in col_to_dow:
                    continue
                dow = col_to_dow[abs_col]
                text = cell.get_text(" ", strip=True)

                # 녹색병원 시간표는 ○를 텍스트가 아닌 <span class="circle"></span>로 그린다.
                # bar 클래스는 휴진/없음 표시.
                has_circle = bool(cell.select_one(".circle"))
                has_bar = bool(cell.select_one(".bar"))

                if has_circle:
                    # 단순 ○ 셀 (텍스트 비어있어도 진료) — 그대로 인정
                    pass
                elif text:
                    # 격주 셀처럼 "1·3·5번 토 진료 / 2·4번 토 휴진" 양쪽 단어가 섞인 경우
                    # is_clinic_cell 은 "휴진"(INACTIVE) 만나는 순간 False 반환하므로
                    # 격주 표시 + "진료" 단어가 둘 다 있으면 진료로 인정한다.
                    if has_biweekly_mark(text) and "진료" in text:
                        pass
                    elif not is_clinic_cell(text):
                        continue
                else:
                    # 빈 셀 / bar (휴진)
                    continue

                key = (dow, slot)
                if key in doctors[current_name]["_seen"]:
                    continue
                doctors[current_name]["_seen"].add(key)

                start, end = TIME_RANGES[slot]
                location = ""
                # 특수 표기 요약 — 격주(다양한 표기) 또는 검진은 location 에 보존
                if has_biweekly_mark(text):
                    location = text  # 원문 그대로 보존 (격주/1·3주/홀수주 등)
                elif "검진" in text:
                    location = "검진"

                doctors[current_name]["schedules"].append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": location,
                })

        # _seen 제거 + 격주 notes 반영
        result = []
        for d in doctors.values():
            d.pop("_seen", None)
            if any(has_biweekly_mark(s.get("location") or "") for s in d.get("schedules", [])):
                if not has_biweekly_mark(d.get("notes") or ""):
                    d["notes"] = "격주 근무"
            result.append(d)
        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            try:
                resp = await client.get(TIMETABLE_URL)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                logger.error(f"[GREEN] 페이지 조회 실패: {e}")
                self._cached_data = []
                return []

        all_doctors = []
        seen_ids = set()

        for table in soup.select("table"):
            # 요일 헤더가 없는 테이블은 건너뜀.
            # 안내/특이사항 박스가 우연히 "월/화/수" 만 포함하는 경우를 거르려고
            # 평일 5요일 (월~금) 모두 등장해야 진료시간표 테이블로 인정한다.
            header_text = " ".join(c.get_text(strip=True) for c in table.select("tr")[0].select("th, td")) if table.select("tr") else ""
            if not all(d in header_text for d in ("월", "화", "수", "목", "금")):
                continue

            dept_name = self._find_dept_name(table)
            if not dept_name:
                continue

            for doc in self._parse_table(table, dept_name):
                if not doc["name"]:
                    continue
                ext_id = self._make_ext_id(doc["department"], doc["name"])
                if ext_id in seen_ids:
                    continue
                seen_ids.add(ext_id)
                doc["external_id"] = ext_id
                doc["staff_id"] = ext_id
                doc["profile_url"] = TIMETABLE_URL
                doc.setdefault("notes", "")
                all_doctors.append(doc)

        logger.info(f"[GREEN] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen = {}
        for d in data:
            dept = d.get("department") or ""
            if dept and dept not in seen:
                seen[dept] = {"code": dept, "name": dept}
        return list(seen.values())

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
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }
        data = await self._fetch_all()
        for d in data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {k: d.get(k, "") for k in
                        ("staff_id", "name", "department", "position",
                         "specialty", "profile_url", "notes", "schedules")}
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

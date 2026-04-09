"""인하대병원 크롤러

HTML 파싱 기반 크롤러.
API:
  진료과 목록: GET /page/department/medicine/dept → 진료과 링크 파싱
  의사 목록: GET /page/department/medicine/dept/{CODE}/staff → doc-box 카드 파싱
  스케줄: GET /page/department/medicine/dept/{CODE}/schedule → 주간 테이블 파싱
  의사 프로필: GET /page/department/medicine/doctor/{ID} → 개별 프로필+스케줄

스케줄 테이블 구조:
  의사별 행: 이름 | 전문분야 | 월~토(오전/오후) | 예약
  진료 표시: ★센터, ●진료과, 빈칸=없음
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.inha.com"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_CHAR_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class InhaCrawler:
    """인하대병원 크롤러"""

    def __init__(self):
        self.hospital_code = "INHA"
        self.hospital_name = "인하대병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL,
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 (HTML 링크 파싱)"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{BASE_URL}/page/department/medicine/dept")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts = []
                seen = set()

                # 방법 1: /page/department/medicine/dept/{CODE} 형식 링크 파싱
                for link in soup.select("a[href*='/page/department/medicine/dept/']"):
                    href = link.get("href", "")
                    name = link.get_text(strip=True)
                    if not name or len(name) > 20:
                        continue

                    # 진료과 코드 추출: /dept/{CODE} (서브 경로가 없는 것만)
                    m = re.search(r'/page/department/medicine/dept/([A-Za-z]+)$', href)
                    if m:
                        code = m.group(1)
                        if code not in seen:
                            depts.append({"code": code, "name": name})
                            seen.add(code)

                # 방법 2: select/option 파싱 (초성 검색 폼)
                if not depts:
                    for option in soup.select("select option"):
                        code = option.get("value", "").strip()
                        name = option.get_text(strip=True)
                        if code and name and code not in ("", "0", "all") and code not in seen:
                            depts.append({"code": code, "name": name})
                            seen.add(code)

                logger.info(f"[INHA] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[INHA] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 진료과별 의사 목록 ───

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """진료과별 의사 목록 HTML 파싱

        URL: /page/department/medicine/dept/{CODE}/staff
        각 의사는 li.doc-box 안에 표시되며 data-no 속성과
        /page/department/medicine/doctor/{ID} 링크를 갖는다.
        """
        try:
            resp = await client.get(
                f"{BASE_URL}/page/department/medicine/dept/{dept_code}/staff",
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[INHA] {dept_name} 의사 목록 실패: {e}")
            return []

        doctors = []
        seen = set()

        # 방법 1: doc-box 또는 doctor 링크 패턴 파싱
        cards = soup.select("li.doc-box, div.doc-box, li.doctor-item, div.doctor-card")

        for card in cards:
            doc_id = ""
            name = ""
            position = ""
            specialty = ""

            # data-no 속성에서 ID 추출
            data_no = card.get("data-no", "")
            # 자식 요소의 data-no
            if not data_no:
                el_with_data = card.select_one("[data-no]")
                if el_with_data:
                    data_no = el_with_data.get("data-no", "")

            # /page/department/medicine/doctor/{ID} 링크에서 ID 추출
            for link in card.select("a[href*='/doctor/']"):
                href = link.get("href", "")
                m = re.search(r'/doctor/(\d+)', href)
                if m:
                    doc_id = m.group(1)
                    link_text = link.get_text(strip=True)
                    if link_text and len(link_text) <= 10 and re.search(r'[가-힣]', link_text):
                        name = link_text
                    break

            if not doc_id and data_no:
                doc_id = data_no

            # 이미지 src에서 ID 추출
            if not doc_id:
                img = card.select_one("img[src*='/doctor/']")
                if img:
                    src = img.get("src", "")
                    m = re.search(r'/doctor/(\d+)', src)
                    if m:
                        doc_id = m.group(1)

            # 이름 추출
            if not name:
                name_el = card.select_one("p.name, h3, strong, span.name, h4")
                if name_el:
                    name = name_el.get_text(strip=True)

            if not name or not doc_id:
                continue
            if doc_id in seen:
                continue
            seen.add(doc_id)

            # 전문분야: p 태그 텍스트에서 추출
            for p in card.select("p"):
                text = p.get_text(strip=True)
                if text and text != name and len(text) > 3:
                    if not specialty:
                        specialty = text

            doctors.append({
                "doc_id": doc_id,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
            })

        # 방법 2: 일반 링크 패턴에서 추출
        if not cards:
            for link in soup.select("a[href*='/medicine/doctor/']"):
                href = link.get("href", "")
                m = re.search(r'/doctor/(\d+)', href)
                if not m:
                    continue
                doc_id = m.group(1)
                if doc_id in seen:
                    continue
                seen.add(doc_id)

                name = link.get_text(strip=True)
                if not name or len(name) > 10:
                    continue

                doctors.append({
                    "doc_id": doc_id,
                    "name": name,
                    "department": dept_name,
                    "position": "",
                    "specialty": "",
                })

        logger.info(f"[INHA] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 스케줄 파싱 ───

    async def _fetch_schedule(self, client: httpx.AsyncClient, doc_id: str) -> list[dict]:
        """개별 의사 프로필 페이지에서 스케줄 파싱

        URL: /page/department/medicine/doctor/{ID}
        스케줄은 테이블에서 ★센터, ●진료과 등으로 표시.
        """
        try:
            resp = await client.get(
                f"{BASE_URL}/page/department/medicine/doctor/{doc_id}",
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return []

        return self._parse_schedule_from_soup(soup)

    async def _fetch_dept_schedule(
        self, client: httpx.AsyncClient, dept_code: str
    ) -> dict[str, list[dict]]:
        """진료과 스케줄 페이지에서 의사별 스케줄 일괄 파싱

        URL: /page/department/medicine/dept/{CODE}/schedule
        반환: {doc_id: [schedule_list]}
        """
        try:
            resp = await client.get(
                f"{BASE_URL}/page/department/medicine/dept/{dept_code}/schedule",
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return {}

        result = {}

        # 스케줄 테이블에서 의사별 행 파싱
        tables = soup.select("table")
        for table in tables:
            rows = table.select("tr")
            if not rows:
                continue

            # 헤더에서 요일 칼럼 매핑
            header_row = rows[0]
            header_cells = header_row.select("th, td")
            col_to_dow = {}
            for ci, cell in enumerate(header_cells):
                text = cell.get_text(strip=True)
                for char, dow in DAY_CHAR_MAP.items():
                    if char in text:
                        col_to_dow[ci] = dow
                        break

            if not col_to_dow:
                continue

            # 의사별 행 파싱 (이미지/링크에서 ID 추출)
            for row in rows[1:]:
                # 의사 ID 추출
                doc_id = ""
                img = row.select_one("img[src*='/doctor/']")
                if img:
                    src = img.get("src", "")
                    m = re.search(r'/doctor/(\d+)', src)
                    if m:
                        doc_id = m.group(1)

                if not doc_id:
                    for link in row.select("a[href*='/doctor/']"):
                        href = link.get("href", "")
                        m = re.search(r'/doctor/(\d+)', href)
                        if m:
                            doc_id = m.group(1)
                            break

                if not doc_id:
                    data_el = row.select_one("[data-no]")
                    if data_el:
                        doc_id = data_el.get("data-no", "")

                if not doc_id:
                    continue

                # 각 셀에서 오전/오후 스케줄 파싱
                cells = row.select("td")
                schedules = []
                seen = set()

                for ci, cell in enumerate(cells):
                    if ci not in col_to_dow:
                        continue
                    dow = col_to_dow[ci]

                    cell_text = cell.get_text(strip=True)
                    # ★센터 또는 ●진료과 등 표시 확인
                    # 셀 안에 오전/오후 정보가 같이 들어있을 수 있음
                    if "★" in cell_text or "●" in cell_text or (cell_text and cell_text not in ("-", "", "X", "x", "휴진")):
                        location = ""
                        if "센터" in cell_text:
                            location = "센터"
                        elif "진료과" in cell_text:
                            location = "진료과"

                        # 오전/오후 모두 표시
                        for slot in ("morning", "afternoon"):
                            key = (dow, slot)
                            if key not in seen:
                                seen.add(key)
                                start, end = TIME_RANGES[slot]
                                schedules.append({
                                    "day_of_week": dow,
                                    "time_slot": slot,
                                    "start_time": start,
                                    "end_time": end,
                                    "location": location,
                                })

                if schedules:
                    result[doc_id] = schedules

        return result

    def _parse_schedule_from_soup(self, soup: BeautifulSoup) -> list[dict]:
        """HTML soup에서 스케줄 테이블 파싱 (개별 프로필 페이지용)"""
        schedules = []
        seen = set()

        tables = soup.select("table")
        for table in tables:
            # 헤더에서 요일 칼럼 매핑
            col_to_dow = {}
            header_row = table.select_one("thead tr") or table.select_one("tr")
            if not header_row:
                continue

            header_cells = header_row.select("th, td")
            for ci, cell in enumerate(header_cells):
                text = cell.get_text(strip=True)
                for char, dow in DAY_CHAR_MAP.items():
                    if char in text:
                        col_to_dow[ci] = dow
                        break

            if not col_to_dow:
                continue

            # 오전/오후 행 파싱
            rows = table.select("tbody tr") or table.select("tr")[1:]
            for row in rows:
                cells = row.select("th, td")
                if not cells:
                    continue

                first_text = cells[0].get_text(strip=True)
                if "오전" in first_text:
                    slot = "morning"
                elif "오후" in first_text:
                    slot = "afternoon"
                else:
                    continue

                for ci, cell in enumerate(cells):
                    if ci not in col_to_dow:
                        continue
                    dow = col_to_dow[ci]

                    cell_text = cell.get_text(strip=True)
                    cell_classes = " ".join(cell.get("class", []))

                    # 진료 여부: ★센터, ●진료과, 텍스트, 클래스
                    has_schedule = False
                    location = ""

                    if "★" in cell_text or "●" in cell_text:
                        has_schedule = True
                        if "센터" in cell_text:
                            location = "센터"
                        elif "진료과" in cell_text:
                            location = "진료과"
                    elif cell_text and cell_text not in ("-", "X", "x", "휴진", ""):
                        has_schedule = True
                    elif "on" in cell_classes or "active" in cell_classes or "check" in cell_classes:
                        has_schedule = True
                    elif cell.select("i, span.on, img, span.active, em"):
                        has_schedule = True

                    if has_schedule:
                        key = (dow, slot)
                        if key not in seen:
                            seen.add(key)
                            start, end = TIME_RANGES[slot]
                            schedules.append({
                                "day_of_week": dow,
                                "time_slot": slot,
                                "start_time": start,
                                "end_time": end,
                                "location": location,
                            })

            # 유효한 스케줄을 찾았으면 종료
            if schedules:
                break

        return schedules

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 의료진 크롤링 후 캐시"""
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}  # doc_id → doctor dict

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept in depts:
                docs = await self._fetch_dept_doctors(client, dept["code"], dept["name"])

                # 진료과 스케줄 페이지에서 일괄 조회 시도 (개별 조회보다 효율적)
                dept_schedules = await self._fetch_dept_schedule(client, dept["code"])

                for doc in docs:
                    doc_id = doc["doc_id"]
                    if doc_id in all_doctors:
                        # 이미 있는 교수 → 전문분야 병합
                        existing = all_doctors[doc_id]
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing["specialty"] else doc["specialty"]
                            )
                        continue

                    # 진료과 스케줄 페이지에서 가져온 데이터 우선 사용
                    schedules = dept_schedules.get(doc_id, [])

                    # 없으면 개별 프로필 페이지에서 조회
                    if not schedules:
                        schedules = await self._fetch_schedule(client, doc_id)

                    ext_id = f"INHA-{doc_id}"
                    all_doctors[doc_id] = {
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": doc["name"],
                        "department": doc["department"],
                        "position": doc["position"],
                        "specialty": doc["specialty"],
                        "profile_url": f"{BASE_URL}/page/department/medicine/doctor/{doc_id}",
                        "notes": "",
                        "schedules": schedules,
                    }

        result = list(all_doctors.values())
        logger.info(f"[INHA] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환"""
        depts = await self._fetch_departments()
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """교수 목록 (스케줄 제외)"""
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        # 캐시가 이미 있으면 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}
            return empty

        # 개별 조회: doc_id 추출 후 스케줄 가져오기
        prefix = "INHA-"
        doc_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            schedules = await self._fetch_schedule(client, doc_id)

            # 의사 정보: 진료과 순회하며 찾기
            name, department, position, specialty = "", "", "", ""
            depts = await self._fetch_departments()
            for dept in depts:
                docs = await self._fetch_dept_doctors(client, dept["code"], dept["name"])
                for doc in docs:
                    if doc["doc_id"] == doc_id:
                        name = doc["name"]
                        department = doc["department"]
                        position = doc["position"]
                        specialty = doc["specialty"]
                        break
                if name:
                    break

            ext_id = f"INHA-{doc_id}"
            return {
                "staff_id": ext_id,
                "name": name,
                "department": department,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/page/department/medicine/doctor/{doc_id}",
                "notes": "",
                "schedules": schedules,
            }

    async def crawl_doctors(self, department: str = None):
        """전체 크롤링 (CrawlResult 반환)"""
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d["position"],
                specialty=d["specialty"],
                profile_url=d["profile_url"],
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

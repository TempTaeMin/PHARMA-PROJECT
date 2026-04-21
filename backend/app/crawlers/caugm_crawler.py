"""중앙대학교광명병원(CAUGM) 크롤러

중앙대의료원 계열 사이트로 cau_crawler.py 와 동일한 템플릿 구조를 사용한다.
광명병원은 `www.cauhs.or.kr` 도메인을 루트로 사용하며 본원(ch.cauhs.or.kr) 과
마크업/엔드포인트가 동일하다.

페이지:
  진료과 목록(링크): GET /home/medical/deptAllIntro.do → deptProf{deptNo}.do
  의료진 목록:       POST /home/medical/profList.do (deptNo 파라미터)
  의료진 상세:       GET /home/medical/profView.do?deptNo=X&profNo=Y&empNo=Z

스케줄 테이블 구조 (profList 카드 + profView 페이지 공통):
  행: 오전 / 오후
  열: 월 화 수 목 금 토
  진료 표시: <img ...ico_outpatient.png> / ico_cir_col05.png 아이콘 또는 "외래" 텍스트

external_id 포맷:
  CAUGM-{deptNo}-{profNo}-{empNo}
  단독 profView 조회에 3개 파라미터가 필요하므로 모두 포함 (슬래시 금지 규칙 준수).
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cauhs.or.kr"
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_CHAR_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

# deptAllIntro.do 에서 WebFetch 로 확인한 진료과 매핑 (광명병원 기준, 36개)
KNOWN_DEPTS: list[tuple[str, str]] = [
    ("79", "가정의학과"), ("80", "감염내과"), ("433", "내과"), ("82", "내분비내과"),
    ("84", "류마티스내과"), ("108", "소화기내과"), ("109", "순환기내과"),
    ("112", "신장내과"), ("104", "호흡기알레르기내과"), ("103", "혈액종양내과"),
    ("85", "마취통증의학과"), ("107", "심장혈관흉부외과"), ("115", "외과"),
    ("111", "신경외과"), ("92", "정형외과"), ("105", "성형외과"),
    ("89", "방사선종양학과"), ("96", "병리과"), ("114", "영상의학과"),
    ("94", "진단검사의학과"), ("101", "핵의학과"),
    ("99", "비뇨의학과"), ("102", "산부인과"), ("106", "소아청소년과"),
    ("110", "신경과"), ("113", "안과"), ("87", "이비인후과"),
    ("88", "입원내과"), ("182", "입원외과"), ("90", "재활의학과"),
    ("91", "정신건강의학과"), ("86", "응급의학과"), ("412", "치과"),
    ("100", "피부과"),
]

# ─── 스케줄 셀 판정 키워드 (SKILL.md 핵심 원칙 #8) ───
CLINIC_MARKS = {"●", "○", "◎", "◯", "★", "ㅇ", "O", "V", "v", "◆", "■", "✓"}
CLINIC_KEYWORDS = ("진료", "외래", "예약", "격주", "순환", "왕진", "클리닉", "상담", "투석", "검진")
EXCLUDE_KEYWORDS = ("수술", "내시경", "시술", "초음파", "조영", "CT", "MRI", "PET", "회진", "실험", "연구", "검사")
INACTIVE_KEYWORDS = ("휴진", "휴무", "공휴일", "부재", "출장", "학회")


def _is_clinic_cell(cell) -> bool:
    """셀(<td>) 하나를 보고 외래 진료인지 판정.

    - img 태그(ico_outpatient.png, ico_cir_col05.png 등) 존재 → 진료
    - 텍스트 키워드: EXCLUDE 가 CLINIC 보다 우선
    """
    text = cell.get_text(" ", strip=True) if hasattr(cell, "get_text") else str(cell)
    text = (text or "").strip()

    # 1) 비활성
    for kw in INACTIVE_KEYWORDS:
        if kw in text:
            return False
    # 2) 제외 (수술/내시경/CT/MRI 등)
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            return False

    # 3) 이미지 아이콘 존재 → 진료 (광명병원은 오전 칸에서 주로 사용)
    if hasattr(cell, "select"):
        imgs = cell.select("img")
        for img in imgs:
            src = img.get("src", "") or ""
            alt = img.get("alt", "") or ""
            # ico_outpatient / ico_cir_col05 / 기타 진료 아이콘
            if "outpatient" in src or "ico_cir" in src:
                return True
            # alt 에 "외래" 등 들어있는 경우
            for kw in CLINIC_KEYWORDS:
                if kw in alt:
                    return True
            # alt/텍스트 EXCLUDE 재체크
            for kw in EXCLUDE_KEYWORDS:
                if kw in alt:
                    return False
        # img 가 있지만 위 조건에 안 걸리면 일반 아이콘으로 간주 (광명병원 이모지 fallback)
        if imgs and not text:
            return True

    # 4) 진료 키워드 / 마크
    for kw in CLINIC_KEYWORDS:
        if kw in text:
            return True
    for mark in CLINIC_MARKS:
        if mark in text:
            return True

    # 5) 시간 패턴 (09:00~12:00, 오전/오후)
    if re.search(r"\d{1,2}[:시]\d{0,2}", text):
        return True

    return False


class CaugmCrawler:
    """중앙대학교광명병원 크롤러"""

    def __init__(self):
        self.hospital_code = "CAUGM"
        self.hospital_name = "중앙대학교광명병원"
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
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(f"{BASE_URL}/home/medical/deptAllIntro.do")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts: list[dict] = []
                seen: set[str] = set()

                for a_tag in soup.select("a[href]"):
                    href = a_tag.get("href", "") or ""
                    name = a_tag.get_text(strip=True)
                    if not name:
                        continue

                    # deptProf{N}.do / deptIntro{N}.do
                    m = re.search(r"deptProf(\d+)\.do|deptIntro(\d+)\.do", href)
                    if m:
                        dept_no = m.group(1) or m.group(2)
                        if dept_no not in seen:
                            clean_name = re.sub(r"\s+", " ", name).strip()
                            if clean_name and len(clean_name) <= 20:
                                seen.add(dept_no)
                                depts.append({"code": dept_no, "name": clean_name})
                        continue

                    # deptNo=N 쿼리
                    m2 = re.search(r"deptNo=(\d+)", href)
                    if m2:
                        dept_no = m2.group(1)
                        if dept_no not in seen:
                            clean_name = re.sub(r"\s+", " ", name).strip()
                            if clean_name and len(clean_name) <= 20:
                                seen.add(dept_no)
                                depts.append({"code": dept_no, "name": clean_name})

                # 동적 파싱 결과가 부족하면 하드코딩 매핑 사용
                if len(depts) < 10:
                    depts = [{"code": c, "name": n} for c, n in KNOWN_DEPTS]

                logger.info(f"[CAUGM] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[CAUGM] 진료과 실패: {e}")
                fallback = [{"code": c, "name": n} for c, n in KNOWN_DEPTS]
                self._cached_depts = fallback
                return fallback

    # ─── 의료진 목록 페이지 파싱 ───
    async def _fetch_prof_list_page(
        self, client: httpx.AsyncClient, dept_code: str | None = None, page: int = 1
    ) -> tuple[list[dict], int]:
        """profList.do POST 호출. (doctors, total_pages) 반환."""
        try:
            form_data = {
                "sitePath": "home",
                "page": str(page),
                "list_show_cnt": "10",
                "sortOrder": "HAN",
                "searchYn": "Y",
                "cate1": "",
                "deptNo": dept_code or "",
                "deptNm": "",
                "tabCd": "",
                "publicYear": "",
                "prevYearYn": "",
                "workType": "",
                "initialText": "",
                "profInitKorNm": "",
                "searchfield": "",
                "searchword": "",
            }
            resp = await client.post(f"{BASE_URL}/home/medical/profList.do", data=form_data)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[CAUGM] profList 페이지 {page} 실패: {e}")
            return [], 0

        html_text = str(soup)

        detail_pattern = re.compile(
            r"fn_DeatilPop\s*\(\s*'([^']*)'\s*,\s*'?(\d+)'?\s*,\s*'?(\d+)'?\s*,\s*'?(\w+)'?\s*\)"
        )
        detail_calls = detail_pattern.findall(html_text)

        doctors: list[dict] = []
        for site_path, dept_no, prof_no, emp_no in detail_calls:
            doctor = self._parse_doctor_from_page(soup, dept_no, prof_no, emp_no)
            if doctor:
                doctors.append(doctor)

        # 총 페이지 수 추출
        total_pages = 1
        for el in soup.select("a[href*='G_MovePage'], a[onclick*='G_MovePage']"):
            raw = (el.get("href", "") or "") + (el.get("onclick", "") or "")
            m = re.search(r"G_MovePage\s*\(\s*(\d+)\s*\)", raw)
            if m:
                p = int(m.group(1))
                if p > total_pages:
                    total_pages = p
        for el in soup.select(".paging, .pagination, nav"):
            text = el.get_text(" ", strip=True)
            for n in re.findall(r"\d+", text):
                p = int(n)
                if 1 < p < 100 and p > total_pages:
                    total_pages = p

        return doctors, total_pages

    def _parse_doctor_from_page(self, soup: BeautifulSoup, dept_no: str, prof_no: str, emp_no: str) -> dict | None:
        """fn_DeatilPop(...) 링크의 부모 카드에서 의사 정보를 추출."""
        for a_tag in soup.select("a"):
            attr_blob = (a_tag.get("href", "") or "") + (a_tag.get("onclick", "") or "")
            if prof_no not in attr_blob or emp_no not in attr_blob:
                continue
            if "fn_DeatilPop" not in attr_blob:
                continue

            # 가장 적절한 카드 컨테이너 찾기
            card = a_tag.find_parent("li", class_=re.compile(r"doc_sche|doctor|prof|card"))
            if not card:
                inner_li = a_tag.find_parent("li")
                if inner_li:
                    card = inner_li.find_parent("li") or inner_li.find_parent(
                        "div", class_=re.compile(r"doc_|doctor|prof")
                    )
            if not card:
                card = a_tag.find_parent("div", class_=re.compile(r"doc_|doctor|prof")) or a_tag.find_parent("tr")
            if not card:
                card = a_tag.parent

            name = ""
            dept_name = ""
            specialty = ""

            if card:
                h4 = card.select_one("div.doc_name h4, h4")
                if h4:
                    name = h4.get_text(strip=True)

                if not name:
                    img = card.select_one("img[alt]")
                    if img:
                        alt = (img.get("alt") or "").strip()
                        alt_clean = re.sub(r"\s*(이미지|교수|전문의|과장|원장)$", "", alt).strip()
                        if alt_clean and 2 <= len(alt_clean) <= 10 and re.search(r"[가-힣]", alt_clean):
                            name = alt_clean

                dept_el = card.select_one("h5.doc_part")
                if dept_el:
                    dept_name = dept_el.get_text(strip=True).strip("[]")

                spec_el = card.select_one("h5.doc_explain")
                if spec_el:
                    specialty = spec_el.get_text(strip=True)

            schedules = self._parse_schedule_table(card) if card else []

            ext_id = f"CAUGM-{dept_no}-{prof_no}-{emp_no}"
            return {
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": "",
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/home/medical/profView.do?deptNo={dept_no}&profNo={prof_no}&empNo={emp_no}",
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
                "dept_no": dept_no,
                "prof_no": prof_no,
                "emp_no": emp_no,
            }

        # 부모 카드 탐색 실패 시 최소 정보만 반환
        ext_id = f"CAUGM-{dept_no}-{prof_no}-{emp_no}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": "",
            "department": "",
            "position": "",
            "specialty": "",
            "profile_url": f"{BASE_URL}/home/medical/profView.do?deptNo={dept_no}&profNo={prof_no}&empNo={emp_no}",
            "notes": "",
            "schedules": [],
            "date_schedules": [],
            "dept_no": dept_no,
            "prof_no": prof_no,
            "emp_no": emp_no,
        }

    @staticmethod
    def _parse_schedule_table(container) -> list[dict]:
        """컨테이너 내부 스케줄 테이블을 파싱해 schedules 리스트 반환.

        구조:
          <tr><th>구분</th><th>월</th>...<th>토</th></tr>
          <tr><td>오전</td><td><img .../></td>...</tr>
          <tr><td>오후</td><td>외래</td>...</tr>
        """
        if container is None or not hasattr(container, "select"):
            return []

        schedules: list[dict] = []
        seen: set[tuple[int, str]] = set()

        for table in container.select("table"):
            col_to_dow: dict[int, int] = {}
            header_row = table.select_one("thead tr") or table.select_one("tr")
            if not header_row:
                continue
            for ci, cell in enumerate(header_row.select("th, td")):
                txt = cell.get_text(strip=True)
                for char, dow in DAY_CHAR_MAP.items():
                    if char in txt:
                        col_to_dow[ci] = dow
                        break
            if not col_to_dow:
                continue

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
                    if not _is_clinic_cell(cell):
                        continue
                    key = (dow, slot)
                    if key in seen:
                        continue
                    seen.add(key)
                    start, end = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": dow,
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })

        return schedules

    # ─── 전체 크롤링 ───
    async def _fetch_all(self) -> list[dict]:
        """전체 의료진 크롤링. profList 는 deptNo 파라미터가 무시되어 전체 목록이 반환되므로
        deptNo 없이 페이지 순회만 수행한다 (본원 CAU 와 동일 동작)."""
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}

        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            page = 1
            while True:
                try:
                    doctors, total_pages = await self._fetch_prof_list_page(client, dept_code=None, page=page)
                except Exception as e:
                    logger.error(f"[CAUGM] 페이지 {page} 실패: {e}")
                    break

                for doc in doctors:
                    ext_id = doc["external_id"]
                    # 이름이 비어있거나 스케줄이 없으면 profView 로 보충
                    if (not doc["name"] or not doc["schedules"]) and doc.get("prof_no"):
                        try:
                            info, view_schedules = await self._fetch_prof_schedule(
                                client, doc["dept_no"], doc["prof_no"], doc["emp_no"]
                            )
                            if info.get("name") and not doc["name"]:
                                doc["name"] = info["name"]
                            if info.get("specialty") and not doc["specialty"]:
                                doc["specialty"] = info["specialty"]
                            if info.get("position") and not doc["position"]:
                                doc["position"] = info["position"]
                            if view_schedules and not doc["schedules"]:
                                doc["schedules"] = view_schedules
                        except Exception:
                            pass
                    if ext_id not in all_doctors:
                        all_doctors[ext_id] = doc

                logger.info(f"[CAUGM] 페이지 {page}/{total_pages}: {len(doctors)}명")

                if page >= total_pages or not doctors:
                    break
                page += 1

        result = list(all_doctors.values())
        logger.info(f"[CAUGM] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 개별 프로필 페이지 파싱 ───
    async def _fetch_prof_schedule(
        self, client: httpx.AsyncClient, dept_no: str, prof_no: str, emp_no: str
    ) -> tuple[dict, list[dict]]:
        """profView.do 에서 의사 상세 + 스케줄 파싱."""
        try:
            resp = await client.get(
                f"{BASE_URL}/home/medical/profView.do",
                params={"deptNo": dept_no, "profNo": prof_no, "empNo": emp_no},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[CAUGM] profView 실패 (profNo={prof_no}): {e}")
            return {}, []

        info = {"name": "", "department": "", "position": "", "specialty": ""}

        # 이름: h1 / h2 / h3 중 짧고 한글인 것
        for h_tag in soup.select("h1, h2, h3, h4, div.doc_name h4"):
            text = h_tag.get_text(strip=True)
            if text and 2 <= len(text) <= 10 and re.search(r"[가-힣]", text) and not info["name"]:
                # 네비게이션 메뉴 텍스트 배제
                if any(bad in text for bad in ("진료과", "의료진", "병원", "홈", "메뉴")):
                    continue
                info["name"] = text
                break

        # 진료과
        dept_el = soup.select_one("h5.doc_part, span.department")
        if dept_el:
            info["department"] = dept_el.get_text(strip=True).strip("[]")

        # 전문분야 (dt/th 라벨 뒤의 dd/td)
        for lbl in soup.select("dt, th, strong"):
            t = lbl.get_text(strip=True)
            if "전문분야" in t or "진료분야" in t:
                nxt = lbl.find_next_sibling("dd") or lbl.find_next_sibling("td")
                if nxt:
                    info["specialty"] = nxt.get_text(" ", strip=True)
                    break

        # 직위 (약력 섹션 내 "임상교수" 등)
        for el in soup.select("dd, p, li, span"):
            t = el.get_text(strip=True)
            if t in ("임상교수", "교수", "부교수", "조교수", "임상부교수", "임상조교수", "과장", "진료교수"):
                info["position"] = t
                break

        schedules = self._parse_schedule_table(soup)
        return info, schedules

    # ─── 공개 인터페이스 ───
    async def get_departments(self) -> list[dict]:
        return await self._fetch_departments()

    async def crawl_doctor_list(self, department: str | None = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "position": d["position"],
                "specialty": d["specialty"],
                "profile_url": d["profile_url"],
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 1명만 조회 (핵심 원칙 #7: _fetch_all 호출 금지).

        external_id 포맷: CAUGM-{deptNo}-{profNo}-{empNo}
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시가 있을 때만 사용 (crawl_doctors 흐름에서 의미)
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            return empty

        # staff_id 파싱
        prefix = f"{self.hospital_code}-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw_id.split("-")

        dept_no = prof_no = emp_no = ""
        if len(parts) >= 3:
            dept_no, prof_no, emp_no = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            # 잘못된 포맷 대비: {profNo}-{empNo}
            prof_no, emp_no = parts[0], parts[1]
        else:
            # 레거시 포맷 (CAUGM-{empNo}) 대비: 단독 조회 불가 → 빈 반환
            logger.warning(f"[CAUGM] staff_id 파싱 불가 (deptNo/profNo 누락): {staff_id}")
            return empty

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                info, schedules = await self._fetch_prof_schedule(client, dept_no, prof_no, emp_no)
            except Exception as e:
                logger.error(f"[CAUGM] 개별 조회 실패 {staff_id}: {e}")
                return empty

        return {
            "staff_id": staff_id,
            "name": info.get("name", ""),
            "department": info.get("department", ""),
            "position": info.get("position", ""),
            "specialty": info.get("specialty", ""),
            "profile_url": f"{BASE_URL}/home/medical/profView.do?deptNo={dept_no}&profNo={prof_no}&empNo={emp_no}",
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d.get("name", ""),
            "department": d.get("department", ""),
            "position": d.get("position", ""),
            "specialty": d.get("specialty", ""),
            "profile_url": d.get("profile_url", ""),
            "notes": d.get("notes", ""),
            "schedules": d.get("schedules", []),
            "date_schedules": d.get("date_schedules", []),
        }

    async def crawl_doctors(self, department: str | None = None):
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

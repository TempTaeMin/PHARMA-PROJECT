"""한림성심병원 크롤러

HTML 파싱 기반 크롤러.
페이지:
  진료과 목록: GET /hallymuniv_sub.asp?left_menu=left_ireserve&screen=ptm211
    → 진료과 타일에서 scode, stype 파싱
  의사 목록: GET /hallymuniv_sub.asp?left_menu=left_ireserve&screen=ptm212&scode={code}&stype=OS
    → 의사 링크에서 Doctor_Id 파싱
  의사 프로필+스케줄: GET /ptm207.asp?Doctor_Id={id}
    → 스케줄 테이블 (오전/오후 × 월~토) 파싱

스케줄 테이블 구조:
  행: 오전/오후
  열: 월~토 (또는 일~토)
  진료 표시: "진료" 텍스트 존재 시
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://hallym.hallym.or.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_CHAR_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class HallymCrawler:
    """한림성심병원 크롤러"""

    def __init__(self):
        self.hospital_code = "HALLYM"
        self.hospital_name = "한림성심병원"
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
        """진료과 목록 (ptm211 페이지에서 파싱)"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(
                    f"{BASE_URL}/hallymuniv_sub.asp",
                    params={"left_menu": "left_ireserve", "screen": "ptm211"},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts = []
                seen = set()

                # ptm212 링크에서 scode 파싱
                for a_tag in soup.select("a[href*='ptm212']"):
                    href = a_tag.get("href", "")
                    name = a_tag.get_text(strip=True)

                    # scode= 파라미터 추출
                    m_code = re.search(r'scode=([^&\s"\']+)', href)
                    m_type = re.search(r'stype=([^&\s"\']+)', href)

                    if m_code and name:
                        code = m_code.group(1).strip()
                        stype = m_type.group(1).strip() if m_type else "OS"
                        if code not in seen:
                            seen.add(code)
                            clean_name = re.sub(r'\s+', ' ', name).strip()
                            if clean_name:
                                depts.append({
                                    "code": code,
                                    "name": clean_name,
                                    "stype": stype,
                                })

                # 폴백: 알려진 진료과 목록
                if not depts:
                    known_depts = [
                        ("12105107", "내과", "OS"),
                        ("12105102", "호흡기-알레르기내과", "OS"),
                        ("12105113", "소화기내과", "OS"),
                        ("12105105", "신경과", "OS"),
                        ("12105108", "정신건강의학과", "OS"),
                        ("12105101", "일반외과", "OS"),
                        ("12105103", "흉부외과", "OS"),
                        ("12105109", "신경외과", "OS"),
                        ("12105106", "정형외과", "OS"),
                        ("12105114", "성형외과", "OS"),
                        ("12105117", "소아청소년과", "OS"),
                        ("12105118", "산부인과", "OS"),
                        ("12105119", "안과", "OS"),
                        ("12105120", "이비인후과", "OS"),
                        ("12105121", "비뇨기과", "OS"),
                        ("12105122", "재활의학과", "OS"),
                        ("12105124", "가정의학과", "OS"),
                        ("12105135", "피부과", "OS"),
                        ("12105127", "마취통증의학과", "OS"),
                        ("12105123", "방사선종양학과", "OS"),
                        ("12105130", "응급의학과", "OS"),
                        ("12105110", "소아외과", "OS"),
                        ("12105115", "치과", "OS"),
                        ("12105128", "진단방사선과", "OS"),
                        ("12105132", "영상의학과", "OS"),
                    ]
                    depts = [{"code": c, "name": n, "stype": s} for c, n, s in known_depts]

                logger.info(f"[HALLYM] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[HALLYM] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 진료과별 의사 목록 ───

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str, stype: str = "OS"
    ) -> list[dict]:
        """진료과별 의사 목록 (ptm212 페이지에서 파싱)"""
        try:
            resp = await client.get(
                f"{BASE_URL}/hallymuniv_sub.asp",
                params={
                    "left_menu": "left_ireserve",
                    "screen": "ptm212",
                    "scode": dept_code,
                    "stype": stype,
                },
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[HALLYM] {dept_name} 의사 목록 실패: {e}")
            return []

        doctors = []
        seen = set()

        # ptm207.asp?Doctor_Id=XXX 링크에서 의사 ID 추출
        for a_tag in soup.select("a[href*='ptm207']"):
            href = a_tag.get("href", "")
            m = re.search(r'Doctor_Id=(\d+)', href)
            if not m:
                continue

            dr_id = m.group(1)
            if dr_id in seen:
                continue

            # 링크 텍스트 또는 주변에서 이름 추출
            name = a_tag.get_text(strip=True)
            # "상세보기" 같은 텍스트인 경우 이름이 아님
            if not name or name in ("상세보기", "자세히보기", "상세정보") or len(name) > 15:
                # 부모 또는 형제 요소에서 이름 찾기
                parent = a_tag.parent
                if parent:
                    for el in parent.select("strong, span, b, em"):
                        t = el.get_text(strip=True)
                        if t and len(t) <= 10 and t not in ("상세보기", "자세히보기"):
                            name = t
                            break
                if not name or name in ("상세보기", "자세히보기", "상세정보") or len(name) > 15:
                    name = ""

            seen.add(dr_id)

            # 전문분야: 같은 컨테이너 내에서 찾기
            specialty = ""
            parent = a_tag.parent
            if parent:
                # 텍스트에서 전문분야 추출
                full_text = parent.get_text(separator="|", strip=True)
                parts = [p.strip() for p in full_text.split("|") if p.strip()]
                # 이름이 아닌 길이가 긴 텍스트가 전문분야일 가능성이 높음
                for p in parts:
                    if p != name and p not in ("상세보기", "예약하기") and len(p) > 3:
                        specialty = p
                        break

            doctors.append({
                "dr_id": dr_id,
                "name": name,
                "department": dept_name,
                "position": "",
                "specialty": specialty,
            })

        # 폴백: onclick 패턴
        if not doctors:
            html = str(soup)
            for m in re.finditer(r"Doctor_Id=(\d+)", html):
                dr_id = m.group(1)
                if dr_id not in seen:
                    seen.add(dr_id)
                    doctors.append({
                        "dr_id": dr_id,
                        "name": "",
                        "department": dept_name,
                        "position": "",
                        "specialty": "",
                    })

        logger.info(f"[HALLYM] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 의사 프로필 + 스케줄 파싱 ───

    async def _fetch_doctor_profile(self, client: httpx.AsyncClient, dr_id: str) -> tuple[dict, list[dict]]:
        """ptm207.asp 페이지에서 의사 정보 + 스케줄 파싱"""
        info = {"name": "", "department": "", "position": "", "specialty": ""}
        schedules = []

        try:
            resp = await client.get(
                f"{BASE_URL}/ptm207.asp",
                params={"Doctor_Id": dr_id},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[HALLYM] 프로필 조회 실패 (Doctor_Id={dr_id}): {e}")
            return info, schedules

        # 에러 페이지 체크
        page_text = soup.get_text()
        if "잘못된 접근" in page_text:
            return info, schedules

        # 이름 추출
        for sel in ("h2", "h3", "h4", "strong.name", "span.name", ".doctor-name"):
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                if name and len(name) <= 10:
                    info["name"] = name
                    break

        # 진료과, 직위, 전문분야 추출
        for dt in soup.select("dt, th"):
            text = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd") or dt.find_next_sibling("td")
            if not dd:
                continue
            val = dd.get_text(strip=True)

            if "진료과" in text or "과명" in text:
                info["department"] = val
            elif "직위" in text or "직급" in text:
                info["position"] = val
            elif "전문" in text or "진료분야" in text:
                info["specialty"] = val

        # 스케줄 테이블 파싱
        schedules = self._parse_schedule_table(soup)

        return info, schedules

    @staticmethod
    def _parse_schedule_table(soup) -> list[dict]:
        """스케줄 테이블 파싱 (오전/오후 × 월~토)"""
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

                    # 진료 여부 확인
                    cell_text = cell.get_text(strip=True)
                    has_schedule = bool(
                        cell_text and cell_text not in ("-", "X", "x", "휴진", "")
                    )
                    # "진료" 텍스트 명시적 확인
                    if "진료" in cell_text:
                        has_schedule = True
                    # 아이콘/이미지
                    if not has_schedule:
                        has_schedule = bool(cell.select("img, i, span.on, span.active"))
                    # CSS 클래스
                    if not has_schedule:
                        cell_classes = " ".join(cell.get("class", []))
                        has_schedule = "on" in cell_classes or "active" in cell_classes

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
                                "location": "",
                            })

        return schedules

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 의료진 크롤링 후 캐시"""
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}  # dr_id → doctor dict

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept in depts:
                stype = dept.get("stype", "OS")
                docs = await self._fetch_dept_doctors(client, dept["code"], dept["name"], stype)
                for doc in docs:
                    dr_id = doc["dr_id"]
                    if dr_id in all_doctors:
                        # 이미 있는 교수 → 전문분야 병합
                        existing = all_doctors[dr_id]
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing["specialty"] else doc["specialty"]
                            )
                        continue

                    # 프로필 페이지에서 상세 정보 + 스케줄 가져오기
                    profile_info, schedules = await self._fetch_doctor_profile(client, dr_id)

                    # 이름이 없으면 프로필에서 가져온 이름 사용
                    name = doc["name"] or profile_info.get("name", "")
                    department = doc["department"] or profile_info.get("department", "")
                    position = doc["position"] or profile_info.get("position", "")
                    specialty = doc["specialty"] or profile_info.get("specialty", "")

                    ext_id = f"HALLYM-{dr_id}"
                    all_doctors[dr_id] = {
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": name,
                        "department": department,
                        "position": position,
                        "specialty": specialty,
                        "profile_url": f"{BASE_URL}/ptm207.asp?Doctor_Id={dr_id}",
                        "notes": "",
                        "schedules": schedules,
                    }

        result = list(all_doctors.values())
        logger.info(f"[HALLYM] 총 {len(result)}명")
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

        # 개별 조회: dr_id 추출 후 프로필 페이지에서 스케줄 가져오기
        prefix = "HALLYM-"
        dr_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            profile_info, schedules = await self._fetch_doctor_profile(client, dr_id)

            ext_id = f"HALLYM-{dr_id}"
            return {
                "staff_id": ext_id,
                "name": profile_info.get("name", ""),
                "department": profile_info.get("department", ""),
                "position": profile_info.get("position", ""),
                "specialty": profile_info.get("specialty", ""),
                "profile_url": f"{BASE_URL}/ptm207.asp?Doctor_Id={dr_id}",
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

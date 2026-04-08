"""길병원 크롤러

Liferay 포틀릿 기반 HTML 크롤러.
POST 요청으로 진료과별 의사 목록 + 주간 스케줄을 파싱합니다.
"""
import logging
import re
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.gilhospital.com"
SEARCH_URL = (
    f"{BASE_URL}/web/www/doctor"
    "?p_p_id=searchDoctor_WAR_bookingHomepageportlet"
    "&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
    "&p_p_col_id=column-1&p_p_col_count=1"
    "&_searchDoctor_WAR_bookingHomepageportlet_action=view"
)

PARAM_PREFIX = "_searchDoctor_WAR_bookingHomepageportlet_"

DEPARTMENTS = [
    (46533, "가정의학과"), (50233, "감염내과"), (50243, "내분비대사내과"),
    (50253, "류마티스내과"), (50263, "마취통증의학과"), (50269, "방사선종양학과"),
    (50549, "병리과"), (50279, "비뇨의학과"), (50289, "산부인과"),
    (50299, "성형외과"), (50309, "소아심장과"), (50319, "소아청소년과"),
    (50329, "소화기내과"), (50339, "신경과"), (50349, "신경외과"),
    (50359, "신장내과"), (50369, "심장내과"), (50539, "심장혈관흉부외과"),
    (50379, "안과"), (50389, "영상의학과"), (50399, "외과"),
    (50409, "외상외과"), (50419, "응급의학과"), (50429, "이비인후과"),
    (50439, "재활의학과"), (50449, "정신건강의학과"), (50459, "정형외과"),
    (50469, "종양내과"), (3283958, "중환자의학과"), (50479, "직업환경의학과"),
    (50559, "진단검사의학과"), (50489, "치과"), (50569, "통합내과"),
    (50499, "피부과"), (50579, "핵의학과"), (50519, "혈관외과"),
    (50529, "혈액내과"), (50213, "호흡기알레르기내과"),
]

# 요일 인덱스: 월=0 ... 토=5
DAY_COLS = 6
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class GilCrawler:
    """길병원 크롤러"""

    def __init__(self):
        self.hospital_code = "GIL"
        self.hospital_name = "길병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html, */*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/web/www/doctor",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        self._cached_data = None

    # ─── HTML 파싱 헬퍼 ───

    @staticmethod
    def _parse_schedule_table(table_tag) -> list[dict]:
        """<table> 안의 오전/오후 × 월~토 스케줄 파싱"""
        schedules = []
        rows = table_tag.select("tbody tr")
        for row in rows:
            th = row.find("th")
            if not th:
                continue
            label = th.get_text(strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue

            cells = row.find_all("td")
            for dow, cell in enumerate(cells[:DAY_COLS]):
                text = cell.get_text(strip=True)
                if text and text != "\xa0" and "진료" in text:
                    start, end = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": dow,
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })
        return schedules

    @staticmethod
    def _extract_doctor_id(a_tag) -> str:
        """링크에서 doctorId 파라미터 추출"""
        href = a_tag.get("href", "")
        m = re.search(r"doctorId=(\d+)", href)
        return m.group(1) if m else ""

    # ─── 진료과별 크롤링 ───

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_id: int, dept_name: str
    ) -> list[dict]:
        """진료과별 POST 요청 → 의사 목록 HTML 파싱"""
        form_data = {f"{PARAM_PREFIX}sOrganizationId": str(dept_id)}
        try:
            resp = await client.post(SEARCH_URL, data=form_data)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[GIL] {dept_name} 요청 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("ul.doctor-list > li")
        doctors = []

        for li in items:
            # 이름
            name_tag = li.select_one("span.name")
            if not name_tag:
                continue
            name = name_tag.get_text(strip=True)

            # doctorId
            link = li.select_one("div.thumb a") or li.select_one("div.infomation a")
            doctor_id = self._extract_doctor_id(link) if link else ""
            if not doctor_id:
                continue

            # 전문분야
            specialty = ""
            text_p = li.select_one("p.text")
            if text_p:
                raw = text_p.get_text(strip=True)
                specialty = re.sub(r"^진료분야\s*:\s*", "", raw).strip()

            # 사진 URL
            photo = ""
            img = li.select_one("div.thumb img")
            if img and img.get("src"):
                photo = img["src"]
                if photo.startswith("/"):
                    photo = BASE_URL + photo

            # 주간 스케줄
            sched_table = li.select_one("div.schedule table")
            schedules = self._parse_schedule_table(sched_table) if sched_table else []

            ext_id = f"GIL-{doctor_id}"
            doctors.append({
                "doctor_id": doctor_id,
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": "",
                "specialty": specialty,
                "photo_url": photo,
                "profile_url": f"{BASE_URL}/web/www/doctor?p_p_id=searchDoctor_WAR_bookingHomepageportlet&p_p_lifecycle=0&p_p_col_id=column-1&p_p_col_count=1&{PARAM_PREFIX}action=view_message&{PARAM_PREFIX}doctorId={doctor_id}",
                "notes": "",
                "schedules": schedules,
            })

        logger.info(f"[GIL] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 의료진 크롤링 후 캐시"""
        if self._cached_data is not None:
            return self._cached_data

        all_doctors = {}  # doctor_id → doctor dict

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept_id, dept_name in DEPARTMENTS:
                docs = await self._fetch_dept_doctors(client, dept_id, dept_name)
                for doc in docs:
                    did = doc["doctor_id"]
                    if did in all_doctors:
                        existing = all_doctors[did]
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing["specialty"] else doc["specialty"]
                            )
                        continue
                    all_doctors[did] = doc

        result = list(all_doctors.values())
        logger.info(f"[GIL] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        return [{"code": str(did), "name": name} for did, name in DEPARTMENTS]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "photo_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        # 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}
            return empty

        # 캐시 없으면 전체 크롤링 후 검색
        await self._fetch_all()
        for d in (self._cached_data or []):
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}
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
                position=d["position"],
                specialty=d["specialty"],
                profile_url=d["profile_url"],
                photo_url=d.get("photo_url", ""),
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

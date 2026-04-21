"""국립암센터 크롤러

진료시간표: /main.ncc?uri=ncc_reservation02&centercd={centerCd}
13개 암센터별 HTML 페이지에 의사 스케줄 포함.
의사 상세: /mdlDoctorPopup.ncc?in_wkpers_id={id}
"""
import re
import asyncio
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.ncc.re.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

# 암센터 코드 목록
CENTER_CODES = [
    ("SP", "뇌척추종양센터"), ("SC", "위암센터"), ("PO", "전립선암센터"),
    ("LU", "폐암센터"), ("LV", "간암센터"), ("CO", "대장암센터"),
    ("GS", "부인암센터"), ("BR", "유방암센터"), ("CV", "심장혈관센터"),
    ("TH", "갑상선암센터"), ("PC", "췌장암센터"), ("HM", "혈액암센터"),
    ("ATC", "첨단기술융합센터"),
]


class NccCrawler:
    """국립암센터 크롤러"""

    def __init__(self):
        self.hospital_code = "NCC"
        self.hospital_name = "국립암센터"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data = None
        self._cached_depts = None

    async def _fetch_center_schedule(self, client: httpx.AsyncClient, center_cd: str, center_nm: str) -> list[dict]:
        """암센터별 진료시간표 HTML 파싱"""
        try:
            resp = await client.get(
                f"{BASE_URL}/main.ncc",
                params={"uri": "ncc_reservation02", "centercd": center_cd},
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error(f"[NCC] {center_nm} 스케줄 실패: {e}")
            return []

        return self._parse_schedule_html(html, center_nm)

    def _parse_schedule_html(self, html: str, center_nm: str) -> list[dict]:
        """HTML 테이블에서 의사 정보와 스케줄 추출

        테이블 4열 구조:
        <td><a ...in_wkpers_id={id}...><font>{name}</font></a></td>
        <td class="left">{specialty}</td>
        <td>{am_days}</td>
        <td>{pm_days}</td>
        """
        doctors = []

        row_pattern = re.compile(
            r'<td[^>]*>\s*<a[^>]*in_wkpers_id=(\d+)[^>]*'     # wkpers_id
            r'[^>]*>\s*(?:<font[^>]*>)?\s*([^<]+?)\s*'         # name
            r'(?:</font>)?\s*</a>\s*</td>\s*'
            r'<td[^>]*>([^<]*)</td>\s*'                        # specialty
            r'<td[^>]*>([^<]*)</td>\s*'                        # AM days
            r'<td[^>]*>([^<]*)</td>',                          # PM days
            re.DOTALL,
        )

        for m in row_pattern.finditer(html):
            wkpers_id = m.group(1)
            name = m.group(2).strip()
            specialty = m.group(3).strip()
            am_days_str = m.group(4).strip()
            pm_days_str = m.group(5).strip()

            if not name:
                continue

            schedules = []

            if am_days_str:
                for day_char in re.findall(r'[월화수목금토]', am_days_str):
                    if day_char in DAY_MAP:
                        dow = DAY_MAP[day_char]
                        start, end = TIME_RANGES["morning"]
                        schedules.append({
                            "day_of_week": dow, "time_slot": "morning",
                            "start_time": start, "end_time": end, "location": "외래",
                        })

            if pm_days_str:
                for day_char in re.findall(r'[월화수목금토]', pm_days_str):
                    if day_char in DAY_MAP:
                        dow = DAY_MAP[day_char]
                        start, end = TIME_RANGES["afternoon"]
                        schedules.append({
                            "day_of_week": dow, "time_slot": "afternoon",
                            "start_time": start, "end_time": end, "location": "외래",
                        })

            ext_id = f"NCC-{wkpers_id}"
            doctors.append({
                "staff_id": ext_id, "external_id": ext_id,
                "name": name, "department": center_nm,
                "position": "", "specialty": specialty,
                "profile_url": f"{BASE_URL}/mdlDoctorPopup.ncc?in_wkpers_id={wkpers_id}",
                "notes": "",
                "schedules": schedules,
                "_wkpers_id": wkpers_id, "_center": center_nm,
            })

        logger.info(f"[NCC] {center_nm}: {len(doctors)}명")
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors = {}

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            for center_cd, center_nm in CENTER_CODES:
                docs = await self._fetch_center_schedule(client, center_cd, center_nm)
                for doc in docs:
                    ext_id = doc["external_id"]
                    if ext_id in all_doctors:
                        existing = all_doctors[ext_id]
                        existing_keys = {(s["day_of_week"], s["time_slot"]) for s in existing["schedules"]}
                        for s in doc["schedules"]:
                            if (s["day_of_week"], s["time_slot"]) not in existing_keys:
                                existing["schedules"].append(s)
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = f"{existing['specialty']}, {doc['specialty']}" if existing["specialty"] else doc["specialty"]
                    else:
                        all_doctors[ext_id] = doc

        result = list(all_doctors.values())
        logger.info(f"[NCC] 총 {len(result)}명 (병합 후)")
        self._cached_data = result
        return result

    async def get_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        data = await self._fetch_all()
        dept_set = {}
        for d in data:
            dept = d["department"]
            if dept and dept not in dept_set:
                dept_set[dept] = {"code": dept, "name": dept}
        self._cached_depts = list(dept_set.values())
        return self._cached_depts

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회

        NCC는 의사 개별 상세 URL이 없다(`/mdlDoctorPopup.ncc` 는 404).
        어느 센터에 속하는지 external_id로는 알 수 없고, 한 의사가 여러 센터에
        중복 등장할 수 있어 **13개 센터를 병렬 조회 후 스케줄/전문분야를 병합**한다.
        순차 루프 대비 응답 시간이 13배 가량 단축된다.
        """
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": []}

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}
            return empty

        prefix = "NCC-"
        wkpers_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        logger.warning(
            f"[NCC] 개별 상세 URL이 없어 13개 센터 병렬 조회 (staff_id={staff_id})"
        )

        matched: dict | None = None
        merged_specialty = ""
        merged_schedules: list[dict] = []
        merged_keys: set = set()

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            tasks = [
                asyncio.create_task(self._fetch_center_schedule(client, cd, nm))
                for cd, nm in CENTER_CODES
            ]
            try:
                for coro in asyncio.as_completed(tasks):
                    docs = await coro
                    for doc in docs:
                        if doc.get("_wkpers_id") != wkpers_id and doc.get("external_id") != staff_id:
                            continue
                        if matched is None:
                            matched = doc
                            for s in doc["schedules"]:
                                merged_keys.add((s["day_of_week"], s["time_slot"]))
                                merged_schedules.append(s)
                            merged_specialty = doc.get("specialty", "")
                        else:
                            # 여러 센터에서 발견되면 스케줄/전문분야 병합
                            for s in doc["schedules"]:
                                k = (s["day_of_week"], s["time_slot"])
                                if k not in merged_keys:
                                    merged_keys.add(k)
                                    merged_schedules.append(s)
                            sp = doc.get("specialty", "")
                            if sp and sp not in merged_specialty:
                                merged_specialty = f"{merged_specialty}, {sp}" if merged_specialty else sp
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()

        if matched is None:
            return empty

        return {
            "staff_id": matched["staff_id"],
            "name": matched["name"],
            "department": matched["department"],
            "position": matched.get("position", ""),
            "specialty": merged_specialty,
            "profile_url": matched.get("profile_url", ""),
            "notes": matched.get("notes", ""),
            "schedules": merged_schedules,
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        doctors = [
            CrawledDoctor(name=d["name"], department=d["department"], position=d["position"],
                          specialty=d["specialty"], profile_url=d["profile_url"],
                          external_id=d["external_id"], notes=d.get("notes", ""), schedules=d["schedules"])
            for d in data
        ]
        return CrawlResult(hospital_code=self.hospital_code, hospital_name=self.hospital_name,
                           status="success" if doctors else "partial", doctors=doctors, crawled_at=datetime.utcnow())

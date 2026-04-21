"""세브란스병원 크롤러

JSON API 기반 크롤러. Playwright 불필요.
API:
  진료과 목록: GET /api/department/list.do?insttCode=2&page=1&pagePerNum=100&sort=name
  진료시간표: GET /api/hospital/reservation/scheduleList.do?insttCode=2&tyCode=..&seCode=..&seq=..&deptCode=..

진료시간:
  monAm/monPm ~ satAm → 빈 문자열이면 진료 없음, 값이 있으면 진료 장소(본관/암 등)

주의:
  VIP건강증진센터 등 일부 예약 전용 부서는 전원 매일 진료로 표시됨 (부정확).
  → 자동 감지: 교수의 80% 이상이 8슬롯 이상 채워진 부서는 스케줄을 버리고 교수 정보만 등록.
"""
import logging
import httpx
from datetime import datetime
from urllib.parse import unquote

logger = logging.getLogger(__name__)

BASE_URL = "https://sev.severance.healthcare"
INSTT_CODE = "2"  # 세브란스병원 (신촌)

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 요일별 스케줄 필드 매핑 (day_index, am_field, pm_field)
SCHEDULE_FIELDS = [
    (0, "monAm", "monPm"),  # 월
    (1, "tueAm", "tuePm"),  # 화
    (2, "wedAm", "wedPm"),  # 수
    (3, "thuAm", "thuPm"),  # 목
    (4, "friAm", "friPm"),  # 금
    (5, "satAm", None),     # 토 (오후 없음)
]

# 전체 슬롯 필드 (풀스케줄 감지용)
ALL_SLOT_FIELDS = [
    "monAm", "monPm", "tueAm", "tuePm", "wedAm", "wedPm",
    "thuAm", "thuPm", "friAm", "friPm",
]


def _is_fake_schedule_dept(doc_list: list[dict], threshold: float = 0.8) -> bool:
    """교수의 80% 이상이 8/10 슬롯 이상 차있으면 예약 전용(가짜) 부서로 판단."""
    if len(doc_list) < 3:
        return False
    full_count = sum(
        1 for doc in doc_list
        if sum(1 for f in ALL_SLOT_FIELDS if (doc.get(f) or "").strip()) >= 8
    )
    return (full_count / len(doc_list)) >= threshold


class SeveranceCrawler:
    """세브란스병원 크롤러"""

    def __init__(self):
        self.hospital_code = "SEVERANCE"
        self.hospital_name = "세브란스병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"{BASE_URL}/sev/patient-carer/appointment/treatment/schedule.do",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data = None
        self._cached_depts = None

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 가져오기"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{BASE_URL}/api/department/list.do", params={
                    "insttCode": INSTT_CODE,
                    "page": "1",
                    "pagePerNum": "200",
                    "sort": "name",
                })
                resp.raise_for_status()
                data = resp.json()
                dept_list = data.get("data", {}).get("list", [])
                logger.info(f"[SEVERANCE] 진료과 {len(dept_list)}개")
                self._cached_depts = dept_list
                return dept_list
            except Exception as e:
                logger.error(f"[SEVERANCE] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 스케줄 크롤링 후 캐시.

        1단계: 정상 부서 크롤링 (스케줄 포함)
        2단계: 예약 전용 부서 감지 → 해당 부서 교수는 스케줄 없이 정보만 등록
        """
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}  # key -> doctor dict

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            for dept in depts:
                dept_seq = dept.get("seq")
                dept_nm = dept.get("deptNm", "")
                ty_code = dept.get("tyCode", "")
                se_code = dept.get("seCode", "")
                ocs_dept_code = dept.get("ocsDeptCode", "")

                if not dept_seq or not ocs_dept_code:
                    continue

                try:
                    resp = await client.get(
                        f"{BASE_URL}/api/hospital/reservation/scheduleList.do",
                        params={
                            "insttCode": INSTT_CODE,
                            "tyCode": ty_code,
                            "seCode": se_code,
                            "seq": str(dept_seq),
                            "deptCode": ocs_dept_code,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    doc_list = data.get("data", {}).get("list", [])
                except Exception as e:
                    logger.error(f"[SEVERANCE] {dept_nm} 스케줄 실패: {e}")
                    continue

                if not doc_list:
                    continue

                # 예약 전용(가짜 스케줄) 부서 감지 → 완전히 제외
                if _is_fake_schedule_dept(doc_list):
                    logger.info(f"[SEVERANCE] {dept_nm}: 예약 전용 부서 감지 ({len(doc_list)}명) → 제외")
                    continue

                count = 0
                for doc in doc_list:
                    emp_no = doc.get("empNo") or ""
                    name = doc.get("nm") or doc.get("phtchrgNm") or ""
                    if not name:
                        continue

                    key = emp_no if emp_no else f"{name}_{dept_nm}"

                    schedules = self._parse_schedules(doc)
                    specialty = doc.get("clnicRealm") or ""

                    if key in all_doctors:
                        existing = all_doctors[key]
                        # 스케줄 병합
                        existing_keys = {
                            (s["day_of_week"], s["time_slot"], s["location"])
                            for s in existing["schedules"]
                        }
                        for s in schedules:
                            skey = (s["day_of_week"], s["time_slot"], s["location"])
                            if skey not in existing_keys:
                                existing["schedules"].append(s)
                                existing_keys.add(skey)
                        if dept_nm and dept_nm not in existing["departments"]:
                            existing["departments"].append(dept_nm)
                        if specialty and specialty not in existing["specialty"]:
                            existing["specialty"] = (
                                f"{existing['specialty']}, {specialty}"
                                if existing["specialty"] else specialty
                            )
                    else:
                        if emp_no:
                            ext_id = f"SEV-{emp_no}"
                        else:
                            safe_dept = (dept_nm or "").replace("/", "_").replace(" ", "")
                            ext_id = f"SEV-{name}-{safe_dept}" if safe_dept else f"SEV-{name}"
                        all_doctors[key] = {
                            "staff_id": ext_id,
                            "external_id": ext_id,
                            "name": name,
                            "department": dept_nm,
                            "departments": [dept_nm] if dept_nm else [],
                            "position": "",
                            "specialty": specialty,
                            "profile_url": "",
                            "notes": "",
                            "schedules": schedules,
                        }
                    count += 1

                if count > 0:
                    logger.info(f"[SEVERANCE] {dept_nm}: {count}명")

        # dict -> list 변환, 특이사항 생성
        result = []
        for doc in all_doctors.values():
            locations = set(s["location"] for s in doc["schedules"] if s["location"])
            notes = ""
            if len(locations) > 1:
                lines = []
                day_names = ["월", "화", "수", "목", "금", "토"]
                for loc in sorted(locations):
                    loc_scheds = [s for s in doc["schedules"] if s["location"] == loc]
                    if loc_scheds:
                        day_slots = []
                        for s in loc_scheds:
                            day = day_names[s["day_of_week"]] if s["day_of_week"] < 6 else "?"
                            slot = "오전" if s["time_slot"] == "morning" else "오후"
                            day_slots.append(f"{day} {slot}")
                        lines.append(f"{loc}: {', '.join(day_slots)}")
                notes = "\n".join(lines)

            result.append({
                "staff_id": doc["staff_id"],
                "external_id": doc["external_id"],
                "name": doc["name"],
                "department": doc["department"],
                "position": doc["position"],
                "specialty": doc["specialty"],
                "profile_url": doc["profile_url"],
                "notes": notes or doc.get("notes", ""),
                "schedules": doc["schedules"],
            })

        logger.info(f"[SEVERANCE] 총 {len(result)}명 (병합 후)")
        self._cached_data = result
        return result

    @staticmethod
    def _parse_schedules(doc: dict) -> list[dict]:
        """API 응답에서 진료 스케줄 추출"""
        schedules = []
        for day_idx, am_field, pm_field in SCHEDULE_FIELDS:
            am_val = (doc.get(am_field) or "").strip()
            if am_val:
                start, end = TIME_RANGES["morning"]
                schedules.append({
                    "day_of_week": day_idx,
                    "time_slot": "morning",
                    "start_time": start,
                    "end_time": end,
                    "location": am_val,
                })
            if pm_field:
                pm_val = (doc.get(pm_field) or "").strip()
                if pm_val:
                    start, end = TIME_RANGES["afternoon"]
                    schedules.append({
                        "day_of_week": day_idx,
                        "time_slot": "afternoon",
                        "start_time": start,
                        "end_time": end,
                        "location": pm_val,
                    })
        return schedules

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환"""
        depts = await self._fetch_departments()
        return [
            {"code": str(d.get("seq", "")), "name": d.get("deptNm", "")}
            for d in depts
            if d.get("deptNm")
        ]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """교수 목록 (스케줄 제외)"""
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
        """개별 교수 진료시간 조회 (개별 검색, 전체 크롤링 안 함)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        decoded_id = unquote(staff_id)

        # 캐시가 이미 있으면 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                d_id = d["staff_id"]
                d_ext = d["external_id"]
                if (d_id == staff_id or d_ext == staff_id
                        or d_id == decoded_id or d_ext == decoded_id
                        or unquote(d_id) == decoded_id or unquote(d_ext) == decoded_id):
                    return self._to_schedule_dict(d)
            return empty

        # 개별 조회: 진료과 순회하며 해당 교수 찾으면 즉시 반환
        emp_no = staff_id.replace("SEV-", "") if staff_id.startswith("SEV-") else decoded_id.replace("SEV-", "") if decoded_id.startswith("SEV-") else ""
        depts = await self._fetch_departments()

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            for dept in depts:
                dept_seq = dept.get("seq")
                dept_nm = dept.get("deptNm", "")
                ty_code = dept.get("tyCode", "")
                se_code = dept.get("seCode", "")
                ocs_dept_code = dept.get("ocsDeptCode", "")
                if not dept_seq or not ocs_dept_code:
                    continue

                try:
                    resp = await client.get(
                        f"{BASE_URL}/api/hospital/reservation/scheduleList.do",
                        params={
                            "insttCode": INSTT_CODE,
                            "tyCode": ty_code,
                            "seCode": se_code,
                            "seq": str(dept_seq),
                            "deptCode": ocs_dept_code,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    doc_list = data.get("data", {}).get("list", [])
                except Exception:
                    continue

                for doc in doc_list:
                    doc_emp = doc.get("empNo") or ""
                    doc_name = doc.get("nm") or doc.get("phtchrgNm") or ""
                    # empNo 또는 이름으로 매칭
                    if not (doc_emp == emp_no or doc_name == emp_no):
                        continue

                    # 찾음! 스케줄 파싱 후 즉시 반환
                    schedules = self._parse_schedules(doc)
                    specialty = doc.get("clnicRealm") or ""
                    ext_id = f"SEV-{doc_emp}" if doc_emp else f"SEV-{doc_name}"

                    return {
                        "staff_id": ext_id,
                        "name": doc_name,
                        "department": dept_nm,
                        "position": "",
                        "specialty": specialty,
                        "profile_url": "",
                        "notes": "",
                        "schedules": schedules,
                    }

        return empty

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d["name"],
            "department": d["department"],
            "position": d["position"],
            "specialty": d["specialty"],
            "profile_url": d["profile_url"],
            "notes": d.get("notes", ""),
            "schedules": d["schedules"],
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

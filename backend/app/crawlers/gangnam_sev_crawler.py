"""강남세브란스병원 크롤러

세브란스병원과 동일한 JSON API 구조. insttCode=4, upperCode=OG010000.
"""
import logging
import httpx
from urllib.parse import unquote
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://gs.severance.healthcare"
INSTT_CODE = "4"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_FIELDS = [
    (0, "monAm", "monPm"),
    (1, "tueAm", "tuePm"),
    (2, "wedAm", "wedPm"),
    (3, "thuAm", "thuPm"),
    (4, "friAm", "friPm"),
    (5, "satAm", None),
]


class GangnamSevCrawler:
    """강남세브란스병원 크롤러"""

    def __init__(self):
        self.hospital_code = "GANSEV"
        self.hospital_name = "강남세브란스병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"{BASE_URL}/gs/patient-carer/appointment/treatment/schedule.do",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data = None
        self._cached_depts = None

    async def _fetch_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(f"{BASE_URL}/api/department/list.do", params={
                    "insttCode": INSTT_CODE, "page": "1", "pagePerNum": "200",
                    "sort": "name", "resveAt": "Y", "upperCode": "OG010000",
                })
                resp.raise_for_status()
                data = resp.json()
                dept_list = data.get("data", {}).get("list", [])
                logger.info(f"[GANSEV] 진료과 {len(dept_list)}개")
                self._cached_depts = dept_list
                return dept_list
            except Exception as e:
                logger.error(f"[GANSEV] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
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
                            "insttCode": INSTT_CODE, "tyCode": ty_code,
                            "seCode": se_code, "seq": str(dept_seq),
                            "deptCode": ocs_dept_code,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    doc_list = data.get("data", {}).get("list", [])
                except Exception as e:
                    logger.error(f"[GANSEV] {dept_nm} 스케줄 실패: {e}")
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
                        existing_keys = {(s["day_of_week"], s["time_slot"], s["location"]) for s in existing["schedules"]}
                        for s in schedules:
                            if (s["day_of_week"], s["time_slot"], s["location"]) not in existing_keys:
                                existing["schedules"].append(s)
                        if dept_nm and dept_nm not in existing.get("departments", []):
                            existing.setdefault("departments", []).append(dept_nm)
                        if specialty and specialty not in existing["specialty"]:
                            existing["specialty"] = f"{existing['specialty']}, {specialty}" if existing["specialty"] else specialty
                    else:
                        ext_id = f"GANSEV-{emp_no}" if emp_no else f"GANSEV-{name}"
                        all_doctors[key] = {
                            "staff_id": ext_id, "external_id": ext_id,
                            "name": name, "department": dept_nm,
                            "departments": [dept_nm] if dept_nm else [],
                            "position": "", "specialty": specialty,
                            "profile_url": "", "notes": "",
                            "schedules": schedules, "_emp_no": emp_no,
                        }
                    count += 1
                if count > 0:
                    logger.info(f"[GANSEV] {dept_nm}: {count}명")

        result = []
        for doc in all_doctors.values():
            locations = set(s["location"] for s in doc["schedules"] if s["location"])
            notes = ""
            if len(locations) > 1:
                day_names = ["월", "화", "수", "목", "금", "토"]
                lines = []
                for loc in sorted(locations):
                    loc_scheds = [s for s in doc["schedules"] if s["location"] == loc]
                    if loc_scheds:
                        day_slots = [f"{day_names[s['day_of_week']]} {'오전' if s['time_slot'] == 'morning' else '오후'}" for s in loc_scheds]
                        lines.append(f"{loc}: {', '.join(day_slots)}")
                notes = "\n".join(lines)
            result.append({
                "staff_id": doc["staff_id"], "external_id": doc["external_id"],
                "name": doc["name"], "department": doc["department"],
                "position": doc["position"], "specialty": doc["specialty"],
                "profile_url": doc["profile_url"], "notes": notes or doc.get("notes", ""),
                "schedules": doc["schedules"],
            })

        logger.info(f"[GANSEV] 총 {len(result)}명 (병합 후)")
        self._cached_data = result
        return result

    @staticmethod
    def _parse_schedules(doc: dict) -> list[dict]:
        schedules = []
        for day_idx, am_field, pm_field in DAY_FIELDS:
            am_val = (doc.get(am_field) or "").strip()
            if am_val:
                start, end = TIME_RANGES["morning"]
                schedules.append({"day_of_week": day_idx, "time_slot": "morning",
                                  "start_time": start, "end_time": end, "location": am_val})
            if pm_field:
                pm_val = (doc.get(pm_field) or "").strip()
                if pm_val:
                    start, end = TIME_RANGES["afternoon"]
                    schedules.append({"day_of_week": day_idx, "time_slot": "afternoon",
                                      "start_time": start, "end_time": end, "location": pm_val})
        return schedules

    async def get_departments(self) -> list[dict]:
        depts = await self._fetch_departments()
        return [{"code": str(d.get("seq", "")), "name": d.get("deptNm", "")} for d in depts if d.get("deptNm")]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회 (개별 검색, 전체 크롤링 안 함)"""
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": []}

        decoded_id = unquote(staff_id)
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id or d["staff_id"] == decoded_id or d["external_id"] == decoded_id:
                    return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}
            return empty

        emp_no = staff_id.replace("GANSEV-", "") if staff_id.startswith("GANSEV-") else decoded_id.replace("GANSEV-", "") if decoded_id.startswith("GANSEV-") else ""
        depts = await self._fetch_departments()

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
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
                        params={"insttCode": INSTT_CODE, "tyCode": ty_code,
                                "seCode": se_code, "seq": str(dept_seq), "deptCode": ocs_dept_code},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    doc_list = data.get("data", {}).get("list", [])
                except Exception:
                    continue

                for doc in doc_list:
                    doc_emp = doc.get("empNo") or ""
                    doc_name = doc.get("nm") or doc.get("phtchrgNm") or ""
                    if not (doc_emp == emp_no or doc_name == emp_no):
                        continue
                    schedules = self._parse_schedules(doc)
                    ext_id = f"GANSEV-{doc_emp}" if doc_emp else f"GANSEV-{doc_name}"
                    return {
                        "staff_id": ext_id, "name": doc_name, "department": dept_nm,
                        "position": "", "specialty": doc.get("clnicRealm") or "",
                        "profile_url": "", "notes": "", "schedules": schedules,
                    }
        return empty

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}

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

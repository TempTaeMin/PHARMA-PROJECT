"""가톨릭중앙의료원 공통 크롤러 베이스

서울성모, 은평성모, 여의도성모 등 CMC 계열 병원은 동일한 JSON API를 사용.
API:
  진료과 목록: GET /api/department?deptClsf=A
  의료진 목록: GET /api/doctor?deptClsf=A&deptCd={code}&orderType=dept&fsexamflag=A

진료시간:
  doctorTreatment.hoursAm[0~5] → 월~토 오전 (null=없음, object=있음)
  doctorTreatment.hoursPm[0~5] → 월~토 오후
"""
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class CmcBaseCrawler:
    """CMC 계열 병원 공통 크롤러"""

    def __init__(self, base_url: str, inst_no: str, hospital_code: str, hospital_name: str):
        self.base_url = base_url
        self.inst_no = inst_no
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"{base_url}/common.examination.doc_list.sp",
            "X-Requested-With": "XMLHttpRequest",
        }
        self.cookies = {"instNo": inst_no}
        self._cached_data = None

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}  # drNo → doctor dict (중복 제거)
        async with httpx.AsyncClient(
            headers=self.headers, cookies=self.cookies,
            timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{self.base_url}/api/department", params={"deptClsf": "A"})
                resp.raise_for_status()
                depts = resp.json()
                logger.info(f"[{self.hospital_code}] 진료과 {len(depts)}개")
            except Exception as e:
                logger.error(f"[{self.hospital_code}] 진료과 목록 실패: {e}")
                self._cached_data = []
                return []

            for dept in depts:
                dept_cd = dept.get("deptCd", "")
                dept_nm = dept.get("deptNm", "")
                if not dept_cd:
                    continue
                try:
                    resp = await client.get(f"{self.base_url}/api/doctor", params={
                        "deptClsf": "A", "deptCd": dept_cd,
                        "orderType": "dept", "fsexamflag": "A",
                    })
                    resp.raise_for_status()
                    docs = resp.json()
                except Exception as e:
                    logger.error(f"[{self.hospital_code}] {dept_nm} 의료진 실패: {e}")
                    continue

                for doc in docs:
                    dr_no = doc.get("drNo", "")
                    dr_name = doc.get("drName", "")
                    if not dr_no or not dr_name:
                        continue

                    if dr_no in all_doctors:
                        existing = all_doctors[dr_no]
                        if dept_nm and dept_nm != existing["department"] and dept_nm not in existing["_extra_depts"]:
                            existing["_extra_depts"].append(dept_nm)
                        continue

                    schedules = self._parse_schedules(doc)
                    doc_dept = doc.get("doctorDept") or {}
                    treatment = doc.get("doctorTreatment") or {}
                    specialty = doc_dept.get("nuSpecial") or treatment.get("special") or ""
                    position = doc.get("nuHptlJobTitle") or doc.get("hptlJobTitle", "")
                    ext_id = f"{self.hospital_code}-{dr_no}"

                    all_doctors[dr_no] = {
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": dr_name,
                        "department": dept_nm,
                        "position": position,
                        "specialty": specialty,
                        "profile_url": "",
                        "notes": "",
                        "schedules": schedules,
                        "_extra_depts": [],
                    }

                logger.info(f"[{self.hospital_code}] {dept_nm}: {len(docs)}명")

        # 복수 진료과 표시를 notes 로 정리
        result: list[dict] = []
        for d in all_doctors.values():
            extras = d.pop("_extra_depts")
            if extras:
                tag = f"복수 진료과: {', '.join(extras)}"
                d["notes"] = (d["notes"] + "\n" + tag) if d["notes"] else tag
            result.append(d)

        logger.info(f"[{self.hospital_code}] 총 {len(result)}명 (dedup)")
        self._cached_data = result
        return result

    @staticmethod
    def _parse_schedules(doc: dict) -> list[dict]:
        treatment = doc.get("doctorTreatment") or {}
        hours_am = treatment.get("hoursAm") or [None] * 6
        hours_pm = treatment.get("hoursPm") or [None] * 6
        schedules = []
        for day_idx in range(6):
            if day_idx < len(hours_am) and hours_am[day_idx] is not None:
                h = hours_am[day_idx]
                type_c = h.get("nuDeptCdTypeC", "-") if isinstance(h, dict) else "-"
                loc = "센터" if (type_c and type_c != "-") else "과진료"
                start, end = TIME_RANGES["morning"]
                schedules.append({
                    "day_of_week": day_idx, "time_slot": "morning",
                    "start_time": start, "end_time": end, "location": loc,
                })
            if day_idx < len(hours_pm) and hours_pm[day_idx] is not None:
                h = hours_pm[day_idx]
                type_c = h.get("nuDeptCdTypeC", "-") if isinstance(h, dict) else "-"
                loc = "센터" if (type_c and type_c != "-") else "과진료"
                start, end = TIME_RANGES["afternoon"]
                schedules.append({
                    "day_of_week": day_idx, "time_slot": "afternoon",
                    "start_time": start, "end_time": end, "location": loc,
                })
        return schedules

    async def get_departments(self) -> list[dict]:
        async with httpx.AsyncClient(
            headers=self.headers, cookies=self.cookies,
            timeout=30, follow_redirects=True,
        ) as client:
            resp = await client.get(f"{self.base_url}/api/department", params={"deptClsf": "A"})
            resp.raise_for_status()
            depts = resp.json()
            return [{"code": d["deptCd"], "name": d["deptNm"]} for d in depts if d.get("deptCd")]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회 (개별 API 호출, 전체 크롤링 안 함)"""
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": []}

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            return empty

        prefix = f"{self.hospital_code}-"
        dr_no = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        async with httpx.AsyncClient(
            headers=self.headers, cookies=self.cookies,
            timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{self.base_url}/api/doctor", params={"drNo": dr_no})
                resp.raise_for_status()
                docs = resp.json()
            except Exception as e:
                logger.error(f"[{self.hospital_code}] 개별 조회 실패 ({staff_id}): {e}")
                return empty

            if not docs:
                return empty

            doc = docs[0]
            dr_name = doc.get("drName", "")
            treatment = doc.get("doctorTreatment") or {}
            doc_dept = doc.get("doctorDept") or {}
            schedules = self._parse_schedules(doc)
            specialty = doc_dept.get("nuSpecial") or treatment.get("special") or ""
            position = doc.get("nuHptlJobTitle") or doc.get("hptlJobTitle", "")
            dept_nm = doc_dept.get("deptNm", "")

            return {
                "staff_id": f"{prefix}{dr_no}" if dr_no else staff_id,
                "name": dr_name,
                "department": dept_nm,
                "position": position,
                "specialty": specialty,
                "profile_url": "",
                "notes": "",
                "schedules": schedules,
            }

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        doctors = [
            CrawledDoctor(
                name=d["name"], department=d["department"], position=d["position"],
                specialty=d["specialty"], profile_url=d["profile_url"],
                external_id=d["external_id"], notes=d.get("notes", ""),
                schedules=d["schedules"],
            )
            for d in data
        ]
        return CrawlResult(
            hospital_code=self.hospital_code, hospital_name=self.hospital_name,
            status="success" if doctors else "partial",
            doctors=doctors, crawled_at=datetime.utcnow(),
        )

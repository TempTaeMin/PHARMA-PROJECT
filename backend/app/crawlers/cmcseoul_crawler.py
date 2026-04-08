"""서울성모병원 크롤러

JSON API 기반 크롤러. Playwright 불필요.
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

BASE_URL = "https://www.cmcseoul.or.kr"
INST_NO = "2"  # 서울성모병원

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class CmcseoulCrawler:
    """서울성모병원 크롤러"""

    def __init__(self):
        self.hospital_code = "CMCSEOUL"
        self.hospital_name = "서울성모병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"{BASE_URL}/common.examination.doc_list.sp",
            "X-Requested-With": "XMLHttpRequest",
        }
        self.cookies = {"instNo": INST_NO}
        self._cached_data = None

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과+의료진 크롤링 후 캐시"""
        if self._cached_data is not None:
            return self._cached_data

        all_doctors = []

        async with httpx.AsyncClient(
            headers=self.headers, cookies=self.cookies,
            timeout=30, follow_redirects=True,
        ) as client:
            # 1. 진료과 목록
            try:
                resp = await client.get(f"{BASE_URL}/api/department", params={"deptClsf": "A"})
                resp.raise_for_status()
                depts = resp.json()
                logger.info(f"[CMCSEOUL] 진료과 {len(depts)}개")
            except Exception as e:
                logger.error(f"[CMCSEOUL] 진료과 목록 실패: {e}")
                self._cached_data = []
                return []

            # 2. 진료과별 의료진 목록
            for dept in depts:
                dept_cd = dept.get("deptCd", "")
                dept_nm = dept.get("deptNm", "")
                if not dept_cd:
                    continue

                try:
                    resp = await client.get(f"{BASE_URL}/api/doctor", params={
                        "deptClsf": "A",
                        "deptCd": dept_cd,
                        "orderType": "dept",
                        "fsexamflag": "A",
                    })
                    resp.raise_for_status()
                    docs = resp.json()
                except Exception as e:
                    logger.error(f"[CMCSEOUL] {dept_nm} 의료진 실패: {e}")
                    continue

                for doc in docs:
                    dr_no = doc.get("drNo", "")
                    dr_name = doc.get("drName", "")
                    if not dr_no or not dr_name:
                        continue

                    # 진료시간 파싱
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
                                "day_of_week": day_idx,
                                "time_slot": "morning",
                                "start_time": start,
                                "end_time": end,
                                "location": loc,
                            })
                        if day_idx < len(hours_pm) and hours_pm[day_idx] is not None:
                            h = hours_pm[day_idx]
                            type_c = h.get("nuDeptCdTypeC", "-") if isinstance(h, dict) else "-"
                            loc = "센터" if (type_c and type_c != "-") else "과진료"
                            start, end = TIME_RANGES["afternoon"]
                            schedules.append({
                                "day_of_week": day_idx,
                                "time_slot": "afternoon",
                                "start_time": start,
                                "end_time": end,
                                "location": loc,
                            })

                    # 전문분야
                    doc_dept = doc.get("doctorDept") or {}
                    specialty = doc_dept.get("nuSpecial") or treatment.get("special") or ""

                    # 직위
                    position = doc.get("nuHptlJobTitle", "")

                    # 특이사항
                    remark = doc_dept.get("remark", "")

                    ext_id = f"CMC-{dr_no}"

                    all_doctors.append({
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": dr_name,
                        "department": dept_nm,
                        "position": position,
                        "specialty": specialty,
                        "profile_url": "",
                        "notes": "",
                        "schedules": schedules,
                    })

                logger.info(f"[CMCSEOUL] {dept_nm}: {len(docs)}명")

        # 동명이인 처리: 같은 이름+진료과가 다른 경우 병합하지 않음 (ext_id로 구분)
        logger.info(f"[CMCSEOUL] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환"""
        async with httpx.AsyncClient(
            headers=self.headers, cookies=self.cookies,
            timeout=30, follow_redirects=True,
        ) as client:
            resp = await client.get(f"{BASE_URL}/api/department", params={"deptClsf": "A"})
            resp.raise_for_status()
            depts = resp.json()
            return [{"code": d["deptCd"], "name": d["deptNm"]} for d in depts if d.get("deptCd")]

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
        """개별 교수 진료시간 조회 (개별 API 호출, 전체 크롤링 안 함)"""
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": []}

        # 캐시가 이미 있으면 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            return empty

        # 개별 API 호출
        dr_no = staff_id.replace("CMC-", "") if staff_id.startswith("CMC-") else staff_id
        async with httpx.AsyncClient(
            headers=self.headers, cookies=self.cookies,
            timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{BASE_URL}/api/doctor", params={"drNo": dr_no})
                resp.raise_for_status()
                docs = resp.json()
            except Exception as e:
                logger.error(f"[CMCSEOUL] 개별 조회 실패 ({staff_id}): {e}")
                return empty

            if not docs:
                return empty

            doc = docs[0]
            return self._parse_single_doctor(doc, staff_id)

    def _parse_single_doctor(self, doc: dict, staff_id: str) -> dict:
        """API 응답 단일 의사 데이터를 스케줄 dict로 변환"""
        dr_no = doc.get("drNo", "")
        dr_name = doc.get("drName", "")
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

        doc_dept = doc.get("doctorDept") or {}
        specialty = doc_dept.get("nuSpecial") or treatment.get("special") or ""
        position = doc.get("nuHptlJobTitle", "")
        dept_nm = doc_dept.get("deptNm", "")

        return {
            "staff_id": f"CMC-{dr_no}" if dr_no else staff_id,
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

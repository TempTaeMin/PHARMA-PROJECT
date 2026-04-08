"""분당서울대병원 크롤러

JSON API 기반 크롤러.
API:
  진료과 목록: GET /medical/deptList.do → HTML 파싱 (bh_dept_box_li 에서 DP_CD 추출)
  스케줄 페이지: GET /medical/deptListTime.do?dp_cd={code}
    → 이 페이지에서 getDoctorList(this, ctr_dept_cd, med_dept_cd) 호출 패턴 추출
  의료진+스케줄: POST /medical/getDoctorList.do
    → params: ctr_dept_cd, med_dept_cd
    → JSON 응답: {dp_cd, dp_nm, rsvt_disp_yn, data: [{DR_NM, DR_STF_NO, DR_SID,
        SPLT_MTFL_CNTE, MON_AM_SIGN~SAT_AM_SIGN, MON_PM_SIGN~FRI_PM_SIGN, ...}]}
  SIGN 필드: HTML 포함 가능 (예: "월 <img src='...' alt='외래진료' />"), 비어있지 않으면 진료 있음
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.snubh.org"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# getDoctorList.do 응답의 스케줄 필드 매핑 (day_index, am_field, pm_field)
SCHEDULE_FIELDS = [
    (0, "MON_AM_SIGN", "MON_PM_SIGN"),  # 월
    (1, "TUE_AM_SIGN", "TUE_PM_SIGN"),  # 화
    (2, "WED_AM_SIGN", "WED_PM_SIGN"),  # 수
    (3, "THU_AM_SIGN", "THU_PM_SIGN"),  # 목
    (4, "FRI_AM_SIGN", "FRI_PM_SIGN"),  # 금
    (5, "SAT_AM_SIGN", None),           # 토 (오후 없음)
]


class SnubhCrawler:
    """분당서울대병원 크롤러"""

    def __init__(self):
        self.hospital_code = "SNUBH"
        self.hospital_name = "분당서울대병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 (deptList.do HTML 파싱 - 이름 + DP_CD 추출)"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{BASE_URL}/medical/deptList.do")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts = []
                seen = set()
                for box in soup.select("li.bh_dept_box_li"):
                    inner = box.select_one("div.bh_inner")
                    if not inner:
                        continue

                    code = ""
                    for a in inner.select("a[href*='DP_CD=']"):
                        href = a.get("href", "")
                        m = re.search(r"DP_CD=([A-Za-z0-9]+)", href)
                        if m:
                            code = m.group(1)
                            break
                    if not code:
                        continue
                    if code in seen:
                        continue
                    seen.add(code)

                    name = ""
                    for a in inner.select("a"):
                        text = a.get_text(strip=True)
                        if text and text not in ("일정표", "의료진", "홈페이지") and len(text) < 30:
                            name = text
                            break
                    if not name:
                        name = code

                    depts.append({"code": code, "name": name})

                logger.info(f"[SNUBH] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[SNUBH] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    async def _fetch_all_api_pairs(self, client: httpx.AsyncClient) -> dict:
        """deptListTime.do 페이지에서 전체 getDoctorList(this, ctr_dept_cd, med_dept_cd) 쌍 추출.

        Returns: {med_dept_cd: [(ctr_dept_cd, med_dept_cd), ...]}
        """
        if hasattr(self, "_api_pairs_cache") and self._api_pairs_cache:
            return self._api_pairs_cache

        try:
            # 아무 dp_cd 로 호출해도 전체 페이지가 나옴
            resp = await client.get(
                f"{BASE_URL}/medical/deptListTime.do",
                params={"dp_cd": "FM"},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SNUBH] deptListTime 실패: {e}")
            return {}

        result = {}
        seen = set()
        for m in re.finditer(r"getDoctorList\(\s*this\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", resp.text):
            ctr = m.group(1)
            med = m.group(2)
            key = (ctr, med)
            if key not in seen:
                seen.add(key)
                result.setdefault(med, []).append(key)

        self._api_pairs_cache = result
        logger.info(f"[SNUBH] API 쌍 {len(seen)}개 (진료과 {len(result)}개)")
        return result

    # ─── 진료과별 스케줄 크롤링 (JSON API) ───

    async def _fetch_dept_schedule(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """진료과의 모든 (ctr_dept_cd, med_dept_cd) 쌍으로 getDoctorList.do 호출"""
        all_pairs = await self._fetch_all_api_pairs(client)
        # dept_code와 일치하는 쌍만 필터링
        pairs = all_pairs.get(dept_code, [])
        if not pairs:
            # 폴백: dept_code 자체를 med_dept_cd로 사용
            pairs = [("NONC", dept_code)]

        all_docs = []
        for ctr_cd, med_cd in pairs:
            docs = await self._fetch_doctors_by_pair(client, ctr_cd, med_cd, dept_name)
            all_docs.extend(docs)

        return all_docs

    async def _fetch_doctors_by_pair(
        self, client: httpx.AsyncClient, ctr_dept_cd: str, med_dept_cd: str, dept_name: str
    ) -> list[dict]:
        """단일 (ctr_dept_cd, med_dept_cd) 쌍으로 의사+스케줄 가져오기"""
        try:
            resp = await client.post(
                f"{BASE_URL}/medical/getDoctorList.do",
                data={"ctr_dept_cd": ctr_dept_cd, "med_dept_cd": med_dept_cd},
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.error(f"[SNUBH] getDoctorList ({ctr_dept_cd}/{med_dept_cd}) 실패: {e}")
            return []

        doc_list = payload if isinstance(payload, list) else payload.get("data", [])
        if isinstance(doc_list, dict):
            doc_list = doc_list.get("data", [])

        doctors = []
        for doc in doc_list:
            name = str(doc.get("DR_NM", "")).strip()
            if not name:
                continue

            stf_no = str(doc.get("DR_STF_NO", doc.get("DR_SID", ""))).strip()
            specialty = str(doc.get("SPLT_MTFL_CNTE", "")).strip()
            notes_parts = []
            spcl_clnc = str(doc.get("SPCL_CLNC_MEMO_CNTE", "")).strip()
            spcl_schd = str(doc.get("SPCL_SCHD_MEMO_CNTE", "")).strip()
            if spcl_clnc:
                notes_parts.append(spcl_clnc)
            if spcl_schd:
                notes_parts.append(spcl_schd)

            # 스케줄 파싱
            schedules = []
            for day_idx, am_field, pm_field in SCHEDULE_FIELDS:
                am_val = str(doc.get(am_field, "")).strip()
                if am_val and am_val not in ("", "None", "null"):
                    start, end = TIME_RANGES["morning"]
                    schedules.append({
                        "day_of_week": day_idx,
                        "time_slot": "morning",
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })
                if pm_field:
                    pm_val = str(doc.get(pm_field, "")).strip()
                    if pm_val and pm_val not in ("", "None", "null"):
                        start, end = TIME_RANGES["afternoon"]
                        schedules.append({
                            "day_of_week": day_idx,
                            "time_slot": "afternoon",
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })

            ext_id = f"SNUBH-{stf_no}" if stf_no else f"SNUBH-{name}"

            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": "",
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/medical/drMedicalTeam.do?DP_TP=O&DP_CD={med_dept_cd}" if stf_no else "",
                "notes": "; ".join(notes_parts),
                "schedules": schedules,
            })

        logger.info(f"[SNUBH] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 의료진 크롤링 후 캐시"""
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}  # ext_id → doctor dict

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept in depts:
                docs = await self._fetch_dept_schedule(
                    client, dept["code"], dept["name"]
                )
                for doc in docs:
                    ext_id = doc["external_id"]
                    if ext_id in all_doctors:
                        # 이미 있는 교수 → 스케줄 병합
                        existing = all_doctors[ext_id]
                        existing_keys = {
                            (s["day_of_week"], s["time_slot"], s["location"])
                            for s in existing["schedules"]
                        }
                        for s in doc["schedules"]:
                            skey = (s["day_of_week"], s["time_slot"], s["location"])
                            if skey not in existing_keys:
                                existing["schedules"].append(s)
                                existing_keys.add(skey)
                        # 전문분야 병합
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing["specialty"] else doc["specialty"]
                            )
                    else:
                        all_doctors[ext_id] = doc

        result = list(all_doctors.values())
        logger.info(f"[SNUBH] 총 {len(result)}명 (병합 후)")
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
        """개별 교수 진료시간 조회"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        # 캐시가 이미 있으면 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            # 이름으로 재검색
            if staff_id.startswith("SNUBH-"):
                search_key = staff_id.split("-", 1)[-1]
                for d in self._cached_data:
                    if d["name"] == search_key:
                        return self._to_schedule_dict(d)
            return empty

        # 개별 조회: dr_cd로 스케줄 가져오기
        prefix = "SNUBH-"
        dr_cd = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            # 전체 진료과 순회하며 해당 의사 찾기
            depts = await self._fetch_departments()
            for dept in depts:
                docs = await self._fetch_dept_schedule(
                    client, dept["code"], dept["name"]
                )
                for doc in docs:
                    if doc["staff_id"] == staff_id or doc["external_id"] == staff_id:
                        return self._to_schedule_dict(doc)
                    if doc["name"] == dr_cd:
                        return self._to_schedule_dict(doc)

        return empty

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d["name"],
            "department": d["department"],
            "position": d.get("position", ""),
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
                position=d.get("position", ""),
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

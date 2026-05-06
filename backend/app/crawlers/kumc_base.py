"""고려대학교 의료원 공통 크롤러 (안암, 구로, 안산)

API:
  의사 목록: GET /api/doctorApi.do?startIndex=1&pageRow=500&instNo={1,2,3}
  진료과 목록: GET /api/getDepartmentList.do?hpCd={AA,GR,AS}
  개별 스케줄: GET /api/getDoctorSchedule.do?hpCd=&empId=&inqrStrtYmd=&inqrFnshYmd=&mcdpCd=
"""
import logging
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://anam.kumc.or.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class KumcBaseCrawler:
    """고려대학교 의료원 공통 크롤러"""

    def __init__(self, hp_cd: str, inst_no: int, hospital_code: str, hospital_name: str):
        self.hp_cd = hp_cd
        self.inst_no = inst_no
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        }
        self._cached_data = None
        self._cached_depts = None

    async def _fetch_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    f"{BASE_URL}/api/getDepartmentList.do",
                    params={"hpCd": self.hp_cd},
                )
                resp.raise_for_status()
                dept_list = resp.json()
                if isinstance(dept_list, dict):
                    dept_list = dept_list.get("list", dept_list.get("data", []))
                logger.info(f"[{self.hospital_code}] 진료과 {len(dept_list)}개")
                self._cached_depts = dept_list
                return dept_list
            except Exception as e:
                logger.error(f"[{self.hospital_code}] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    async def _fetch_doctor_list(self, client: httpx.AsyncClient) -> list[dict]:
        """전체 의사 목록 조회"""
        try:
            resp = await client.get(
                f"{BASE_URL}/api/doctorApi.do",
                params={
                    "instNo": str(self.inst_no),
                    "hpCd": self.hp_cd,
                    "langType": "kr",
                    "startIndex": "1",
                    "pageRow": "1000",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            doc_list = data.get("doctorList", [])
            logger.info(f"[{self.hospital_code}] 의사 {len(doc_list)}명 (원본)")
            return doc_list
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 의사 목록 실패: {e}")
            return []

    async def _fetch_doctor_schedule(self, client: httpx.AsyncClient, emp_id: str, mcdp_cd: str) -> dict:
        """개별 의사 3개월 스케줄 조회 → 주간 패턴 + 날짜별 스케줄 반환

        KUMC API 는 휴진일을 응답에서 누락하는 방식으로 표현한다 (5/21 같이 그 날만
        휴진이면 응답에 5/21 자체가 없음). frontend ScheduleCalendar /
        useMonthCalendar 가 '그 날 date_schedule 없으면 주간 schedules 폴백' 으로
        동작하기 때문에, 휴진일이 평소 정기 진료일로 잘못 표시된다.

        해결 — raw 응답을 받은 뒤, 그 의사의 정기 진료 (dow, slot) 패턴 중 응답에
        누락된 날짜를 모두 status='휴진' 의 date_schedule 행으로 명시. 비-정기 슬롯은
        채우지 않음 (데이터 폭증 방지).
        """
        today = datetime.now()
        days_ahead = 90
        start = today.strftime("%Y%m%d")
        end = (today + timedelta(days=days_ahead)).strftime("%Y%m%d")

        try:
            resp = await client.get(
                f"{BASE_URL}/api/getDoctorSchedule.do",
                params={
                    "hpCd": self.hp_cd,
                    "empId": emp_id,
                    "inqrStrtYmd": start,
                    "inqrFnshYmd": end,
                    "mcdpCd": mcdp_cd,
                },
            )
            resp.raise_for_status()
            entries = resp.json()
            if isinstance(entries, dict):
                entries = entries.get("list", entries.get("data", []))
        except Exception:
            return {"schedules": [], "date_schedules": []}

        # 날짜별 스케줄 수집 + 요일 기반 집계
        date_schedules = []
        day_slots = {}  # (day_of_week, time_slot) → location
        present_pairs = set()  # (formatted_date, slot) — 진료로 응답된 (날짜, 슬롯)
        for entry in entries:
            date_str = entry.get("mdcrYmd", "")
            if not date_str:
                continue
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                dow = dt.weekday()
                formatted_date = dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

            dept_nm = entry.get("mcdpNm", "")
            am = entry.get("amSttsDvsnCd")
            pm = entry.get("pmSttsDvsnCd")

            if am == "1":
                day_slots[(dow, "morning")] = dept_nm or "외래"
                present_pairs.add((formatted_date, "morning"))
                date_schedules.append({
                    "schedule_date": formatted_date, "time_slot": "morning",
                    "start_time": "09:00", "end_time": "12:00",
                    "location": dept_nm or "외래", "status": "진료",
                })
            if pm == "1":
                day_slots[(dow, "afternoon")] = dept_nm or "외래"
                present_pairs.add((formatted_date, "afternoon"))
                date_schedules.append({
                    "schedule_date": formatted_date, "time_slot": "afternoon",
                    "start_time": "13:00", "end_time": "17:00",
                    "location": dept_nm or "외래", "status": "진료",
                })

        # 휴진일 명시 채움 — 정기 (dow, slot) 패턴에 매칭되지만 raw 응답에 누락된 날짜
        for offset in range(days_ahead + 1):
            day = today + timedelta(days=offset)
            formatted = day.strftime("%Y-%m-%d")
            dow = day.weekday()
            for slot in ("morning", "afternoon"):
                key = (dow, slot)
                if key not in day_slots:
                    continue
                if (formatted, slot) in present_pairs:
                    continue
                start_t, end_t = TIME_RANGES[slot]
                date_schedules.append({
                    "schedule_date": formatted, "time_slot": slot,
                    "start_time": start_t, "end_time": end_t,
                    "location": day_slots[key],
                    "status": "휴진",
                })

        schedules = []
        for (dow, slot), loc in sorted(day_slots.items()):
            start_t, end_t = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow, "time_slot": slot,
                "start_time": start_t, "end_time": end_t, "location": loc,
            })
        return {"schedules": schedules, "date_schedules": date_schedules}

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            # 1. doctorApi에서 의사 상세 정보 — 보강용 (specialty, position, profile_url)
            #    매칭 안 되어도 의사 등록은 막지 않는다.
            #    KUMC 는 doctorApi (교수 인증용 풀) 와 getDoctorList (외래 진료 의사 풀) 가
            #    분리돼서, doctorApi 매칭을 의무화하면 외래 진료 의사가 누락된다 (유양재 같이).
            #    cf. 사용자 보고 2026-05: 고대구로 간센터(내과) 유양재 — 외래 schedule 있는데
            #    doctorApi 응답에 없어서 누락됐던 케이스.
            raw_docs = await self._fetch_doctor_list(client)
            doc_info_by_name: dict[str, dict] = {}  # name → 보강 정보
            for doc in raw_docs:
                name = (doc.get("drName") or "").strip()
                if not name or name in doc_info_by_name:
                    continue
                doc_info_by_name[name] = {
                    "department": doc.get("deptNm", ""),
                    "specialty": doc.get("special", ""),
                    "position": (doc.get("hptlJobTitle") or "").strip(),
                    "_dr_no": str(doc.get("drNo") or ""),
                }
            logger.info(f"[{self.hospital_code}] doctorApi 보강 후보 {len(doc_info_by_name)}명")

            # 2. getDepartmentList + getDoctorList로 mddrId(스케줄 API용 empId) 수집
            depts = await self._fetch_departments()
            all_doctors = {}  # mddrId → doctor dict

            for dept in depts:
                mcdp_cd = dept.get("mcdpCd", "")
                dept_nm = dept.get("mcdpNm", "")
                if not mcdp_cd:
                    continue

                try:
                    resp = await client.get(
                        f"{BASE_URL}/api/getDoctorList.do",
                        params={"hpCd": self.hp_cd, "mcdpCd": mcdp_cd, "instNo": str(self.inst_no)},
                    )
                    resp.raise_for_status()
                    doc_list = resp.json()
                    if isinstance(doc_list, dict):
                        doc_list = doc_list.get("list", doc_list.get("data", []))
                except Exception:
                    continue

                for d in doc_list:
                    mddr_id = d.get("mddrId", "")
                    name = d.get("mddrNm", "").strip()
                    if not mddr_id or not name:
                        continue
                    if mddr_id in all_doctors:
                        continue

                    # doctorApi 보강 정보 (있으면 사용, 없어도 등록 진행)
                    info = doc_info_by_name.get(name, {})
                    dr_no = info.get("_dr_no", "")
                    profile_url = (
                        f"https://{self.hp_cd.lower()}.kumc.or.kr/kr/doctor-department/doctor/view.do?drNo={dr_no}"
                        if dr_no else ""
                    )

                    ext_id = f"{self.hospital_code}-{mddr_id}"
                    all_doctors[mddr_id] = {
                        "staff_id": ext_id, "external_id": ext_id,
                        "name": name, "department": dept_nm,
                        "position": info.get("position", ""),
                        "specialty": info.get("specialty", ""),
                        "profile_url": profile_url,
                        "notes": "", "schedules": [],
                        "_mddr_id": mddr_id, "_mcdp_cd": mcdp_cd,
                        "_dr_no": dr_no,
                    }

            # 3. 스케줄 조회
            for doc in all_doctors.values():
                mddr_id = doc.get("_mddr_id", "")
                mcdp_cd = doc.get("_mcdp_cd", "")
                if mddr_id and mcdp_cd:
                    sched_result = await self._fetch_doctor_schedule(client, mddr_id, mcdp_cd)
                    doc["schedules"] = sched_result.get("schedules", [])
                    doc["date_schedules"] = sched_result.get("date_schedules", [])

        result = list(all_doctors.values())
        logger.info(f"[{self.hospital_code}] 총 {len(result)}명")
        self._cached_data = result
        return result

    async def get_departments(self) -> list[dict]:
        depts = await self._fetch_departments()
        return [{"code": d.get("mcdpCd", ""), "name": d.get("mcdpNm", "")} for d in depts if d.get("mcdpNm")]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department or department in d.get("_depts", [])]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회 (개별 API 호출)"""
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": [], "date_schedules": []}

        # 캐시 검색
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    result = {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}
                    result["date_schedules"] = d.get("date_schedules", [])
                    return result
            return empty

        # 개별 조회: staff_id = "KUANAM-{mddrId}" 형태
        prefix = f"{self.hospital_code}-"
        mddr_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            # 진료과 순회하며 해당 mddrId 찾기
            depts = await self._fetch_departments()
            for dept in depts:
                mcdp_cd = dept.get("mcdpCd", "")
                dept_nm = dept.get("mcdpNm", "")
                if not mcdp_cd:
                    continue
                try:
                    resp = await client.get(
                        f"{BASE_URL}/api/getDoctorList.do",
                        params={"hpCd": self.hp_cd, "mcdpCd": mcdp_cd, "instNo": str(self.inst_no)},
                    )
                    resp.raise_for_status()
                    doc_list = resp.json()
                    if isinstance(doc_list, dict):
                        doc_list = doc_list.get("list", doc_list.get("data", []))
                except Exception:
                    continue

                for d in doc_list:
                    if d.get("mddrId") == mddr_id:
                        name = d.get("mddrNm", "").strip()
                        sched_result = await self._fetch_doctor_schedule(client, mddr_id, mcdp_cd)
                        ext_id = f"{self.hospital_code}-{mddr_id}"
                        return {
                            "staff_id": ext_id, "name": name, "department": dept_nm,
                            "position": "", "specialty": "",
                            "profile_url": f"https://{self.hp_cd.lower()}.kumc.or.kr/kr/doctor-department/doctor/view.do?drNo=",
                            "notes": "",
                            "schedules": sched_result.get("schedules", []),
                            "date_schedules": sched_result.get("date_schedules", []),
                        }

        return empty

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department or department in d.get("_depts", [])]
        doctors = [
            CrawledDoctor(name=d["name"], department=d["department"], position=d["position"],
                          specialty=d["specialty"], profile_url=d["profile_url"],
                          external_id=d["external_id"], notes=d.get("notes", ""),
                          schedules=d["schedules"], date_schedules=d.get("date_schedules", []))
            for d in data
        ]
        return CrawlResult(hospital_code=self.hospital_code, hospital_name=self.hospital_name,
                           status="success" if doctors else "partial", doctors=doctors, crawled_at=datetime.utcnow())

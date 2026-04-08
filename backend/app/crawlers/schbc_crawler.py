"""부천순천향병원 크롤러

JSON API 기반 크롤러. Playwright 불필요.
API:
  진료과 목록: POST /common/getCommDeptList.json (hsptlCode=bucheon)
  의료진 목록: POST /bucheon/doctr/list/selectIemList.json (deptNo)
  진료일정:   POST /bucheon/doctr/home/selectEmrScheduleList.json (instcd, orddeptcd, orddrid, basedd)
"""
import logging
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://www.schmc.ac.kr"
INSTCD = "053"  # 부천=053 (서울=052, 천안=054, 구미=055)
HSPTL_CODE = "bucheon"
DOCTR_KEY = "2947"  # 의료진 프로필 페이지 key

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class SchbcCrawler:
    """부천순천향병원 크롤러"""

    def __init__(self):
        self.hospital_code = "SCHBC"
        self.hospital_name = "부천순천향병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.post(
                    f"{BASE_URL}/common/getCommDeptList.json",
                    data={"hsptlCode": HSPTL_CODE, "lang": "kor", "isAll": "false"},
                )
                resp.raise_for_status()
                items = resp.json().get("data", [])
                depts = [
                    {
                        "code": str(d["deptNo"]),
                        "name": d["deptNm"],
                        "deptCode": d.get("deptCode", ""),
                    }
                    for d in items
                    if d.get("deptNm") and d["deptNm"] not in ("기타", "검진센터")
                ]
                logger.info(f"[SCHBC] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[SCHBC] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 진료과별 의사 목록 ───

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_no: str, dept_name: str, dept_code: str
    ) -> list[dict]:
        try:
            resp = await client.post(
                f"{BASE_URL}/{HSPTL_CODE}/doctr/list/selectIemList.json",
                data={"lang": "kor", "hsptlCode": HSPTL_CODE, "deptNo": dept_no},
            )
            resp.raise_for_status()
            items = resp.json().get("data", [])
        except Exception as e:
            logger.error(f"[SCHBC] {dept_name} 의사 목록 실패: {e}")
            return []

        doctors = []
        for d in items:
            doctr_no = str(d.get("doctrNo", ""))
            if not doctr_no:
                continue
            ext_id = f"SCHBC-{doctr_no}"
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": d.get("doctrNm", ""),
                "department": d.get("deptNm", dept_name),
                "position": d.get("ofcpsHsptl", "") or "",
                "specialty": d.get("spcltyRealm", "") or "",
                "profile_url": f"{BASE_URL}/{HSPTL_CODE}/doctr/home.do?key={DOCTR_KEY}&doctrNo={doctr_no}",
                "notes": "",
                "schedules": [],
                "date_schedules": [],
                "_doctr_no": doctr_no,
                "_dept_code": d.get("deptCode", dept_code),
                "_lcns_no": str(d.get("doctrLcnsNo", "")),
            })

        logger.info(f"[SCHBC] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 일정 조회 ───

    async def _fetch_schedule(
        self, client: httpx.AsyncClient, dept_code: str, lcns_no: str, months: int = 3
    ) -> tuple[list[dict], list[dict]]:
        """EMR 스케줄 API → (weekly_schedules, date_schedules)"""
        if not lcns_no or not dept_code:
            return [], []

        day_slots = {}  # (dow, slot) → count
        date_schedules = []
        now = datetime.now()

        for i in range(months):
            target = now + timedelta(days=i * 30)
            basedd = target.strftime("%Y%m")
            try:
                resp = await client.post(
                    f"{BASE_URL}/{HSPTL_CODE}/doctr/home/selectEmrScheduleList.json",
                    data={
                        "instcd": INSTCD,
                        "orddeptcd": dept_code,
                        "orddrid": lcns_no,
                        "basedd": basedd,
                    },
                )
                resp.raise_for_status()
                output = resp.json().get("data", {}).get("root", {}).get("output", [])
            except Exception:
                continue

            for entry in output:
                date_str_raw = str(entry.get("basedd", ""))
                if len(date_str_raw) != 8:
                    continue

                try:
                    dt = datetime.strptime(date_str_raw, "%Y%m%d")
                except ValueError:
                    continue

                date_str = dt.strftime("%Y-%m-%d")
                dow = dt.weekday()  # 0=Mon

                for slot, flag_key in [("morning", "amordyn"), ("afternoon", "pmordyn")]:
                    if entry.get(flag_key) == "Y":
                        start, end = TIME_RANGES[slot]
                        date_schedules.append({
                            "schedule_date": date_str,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                            "status": "진료",
                        })
                        key = (dow, slot)
                        day_slots[key] = day_slots.get(key, 0) + 1

        # 주간 패턴: 3회 이상 나온 (dow, slot) → 정기 스케줄
        schedules = []
        for (dow, slot), count in sorted(day_slots.items()):
            if dow > 5:
                continue
            if count >= 2:
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        return schedules, date_schedules

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept in depts:
                docs = await self._fetch_dept_doctors(
                    client, dept["code"], dept["name"], dept.get("deptCode", "")
                )
                for doc in docs:
                    ext_id = doc["external_id"]
                    if ext_id in all_doctors:
                        continue

                    schedules, date_schedules = await self._fetch_schedule(
                        client, doc["_dept_code"], doc["_lcns_no"]
                    )
                    doc["schedules"] = schedules
                    doc["date_schedules"] = date_schedules
                    all_doctors[ext_id] = doc

        result = list(all_doctors.values())
        logger.info(f"[SCHBC] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        depts = await self._fetch_departments()
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")
        return [{k: d[k] for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        _keys = ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules", "date_schedules")
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "" if k not in ("schedules", "date_schedules") else []) for k in _keys}
            return empty

        prefix = "SCHBC-"
        doctr_no = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            depts = await self._fetch_departments()
            for dept in depts:
                docs = await self._fetch_dept_doctors(
                    client, dept["code"], dept["name"], dept.get("deptCode", "")
                )
                for doc in docs:
                    if doc["_doctr_no"] == doctr_no or doc["staff_id"] == staff_id:
                        schedules, date_schedules = await self._fetch_schedule(
                            client, doc["_dept_code"], doc["_lcns_no"]
                        )
                        doc["schedules"] = schedules
                        doc["date_schedules"] = date_schedules
                        return {k: doc.get(k, "" if k not in ("schedules", "date_schedules") else []) for k in _keys}

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
                position=d.get("position", ""),
                specialty=d["specialty"],
                profile_url=d["profile_url"],
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
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

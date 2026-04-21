"""용인세브란스병원(YONGIN) 크롤러

병원 공식명: 연세대학교 의과대학 용인세브란스병원 (경기 용인시 기흥구)
홈페이지: yi.severance.healthcare (Spring + JSON AJAX)

구조:
- 진료과: POST `/api/department/list.do`  form=insttCode=16&tyCode={type}&seCode={sub}&sort=name
  tyCode 조합: DP010100 (진료과 46개), DP010200/DP020401 (7개), DP010200/DP020402 (18개) ≒ 71개
- 의료진: GET `/api/doctor/list.do?insttCode=16&tyCode={t}&seCode={s}&seq={deptSeq}&sort=name&pagePerNum=200`
    doctor 필드: nm, deptNm, deptSeq, empNo (URL-encoded 토큰), ofcps, clnicRealm, thumbnail
- 개인 + 스케줄: GET `/yi/doctor/doctor-view.do?empNo={empNo}&deptSeq={deptSeq}`
    `<table>` thead 요일(월~토), tbody 2행(오전/오후), td 텍스트 "진료" 있으면 진료
    `.name`, `h2` 파싱으로 이름/진료과 확인 가능

external_id 포맷: `YONGIN-{deptSeq}-{empNoHash8}` — empNo 전체가 너무 길고 URL-encoded `%` 포함 → md5 앞 12자로 축약
개별 조회를 위해 `_empNo` 원문을 dict 에 보관. 개별 호출 시 deptSeq 가 있으면 해당 과 doctor-list 한 번 + view 한 번으로 찾는다.
"""
from __future__ import annotations

import hashlib
import urllib.parse
import asyncio
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://yi.severance.healthcare"
DEPT_LIST_URL = f"{BASE_URL}/api/department/list.do"
DOCTOR_LIST_URL = f"{BASE_URL}/api/doctor/list.do"
DOCTOR_VIEW_URL = f"{BASE_URL}/yi/doctor/doctor-view.do"

INSTT_CODE = "16"
TY_CODES = [
    ("DP010100", ""),
    ("DP010200", "DP020401"),
    ("DP010200", "DP020402"),
]

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}


def _short_id(empNo: str) -> str:
    return hashlib.md5(empNo.encode()).hexdigest()[:12]


class YonginCrawler:
    def __init__(self):
        self.hospital_code = "YONGIN"
        self.hospital_name = "용인세브란스병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/yi/doctor/doctor.do",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data: list[dict] | None = None

    # ─── 파싱 ───

    @staticmethod
    def _parse_schedule(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        tbl = soup.select_one(".time-table table")
        if not tbl:
            return []
        out: list[dict] = []
        # thead: ['진료시간', '월','화','수','목','금','토']
        # tbody rows: ['오전', ...], ['오후', ...]
        tbody = tbl.find("tbody") or tbl
        for tr in tbody.find_all("tr"):
            th = tr.find("th")
            if not th:
                continue
            label = th.get_text(" ", strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            tds = tr.find_all("td")
            for dow, td in enumerate(tds[:6]):
                text = td.get_text(" ", strip=True)
                if "진료" not in text:
                    continue
                s, e = TIME_RANGES[slot]
                out.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": s, "end_time": e, "location": "",
                })
        return out

    @staticmethod
    def _parse_view_info(html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        name = ""
        department = ""
        name_el = soup.select_one(".name")
        if name_el:
            name = name_el.get_text(" ", strip=True)
        h2 = soup.find("h2")
        if h2:
            txt = h2.get_text(" ", strip=True)
            if name and txt.startswith(name):
                department = txt[len(name):].strip()
            else:
                department = txt
        return {"name": name, "department": department}

    # ─── 네트워크 ───

    async def _fetch_depts(self, client: httpx.AsyncClient) -> list[dict]:
        all_depts: list[dict] = []
        for ty, se in TY_CODES:
            try:
                r = await client.post(
                    DEPT_LIST_URL,
                    data={"insttCode": INSTT_CODE, "tyCode": ty, "seCode": se, "sort": "name"},
                )
                r.raise_for_status()
                j = r.json()
            except Exception as e:
                logger.warning(f"[YONGIN] deptList ty={ty}/{se} 실패: {e}")
                continue
            for d in j.get("data", {}).get("list", []):
                all_depts.append({
                    "seq": d["seq"], "name": d["deptNm"],
                    "tyCode": ty, "seCode": se,
                })
        return all_depts

    async def _fetch_doctors_of_dept(
        self, client: httpx.AsyncClient, dept: dict
    ) -> list[dict]:
        try:
            r = await client.get(
                DOCTOR_LIST_URL,
                params={
                    "insttCode": INSTT_CODE, "tyCode": dept["tyCode"],
                    "seCode": dept["seCode"], "seq": dept["seq"],
                    "sort": "name", "pagePerNum": "200",
                },
            )
            r.raise_for_status()
            j = r.json()
        except Exception as e:
            logger.warning(f"[YONGIN] doctorList seq={dept['seq']} 실패: {e}")
            return []
        out: list[dict] = []
        for doc in j.get("data", {}).get("list", []):
            empNo = doc.get("empNo", "")
            if not empNo:
                continue
            out.append({
                "_empNo": empNo,
                "_deptSeq": dept["seq"],
                "name": doc.get("nm", "") or "",
                "department": doc.get("deptNm", "") or dept["name"],
                "position": doc.get("ofcps", "") or "",
                "specialty": doc.get("clnicRealm", "") or "",
            })
        return out

    async def _fetch_doctor_view(
        self, client: httpx.AsyncClient, empNo: str, deptSeq: int
    ) -> dict:
        try:
            r = await client.get(
                DOCTOR_VIEW_URL,
                params={"empNo": empNo, "deptSeq": deptSeq},
            )
            r.raise_for_status()
        except Exception as e:
            logger.warning(f"[YONGIN] doctor-view 실패: {e}")
            return {"schedules": [], "name": "", "department": ""}
        html = r.content.decode("utf-8", errors="replace")
        info = self._parse_view_info(html)
        info["schedules"] = self._parse_schedule(html)
        return info

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            depts = await self._fetch_depts(client)
            logger.info(f"[YONGIN] 진료과 {len(depts)}개")

            # 모든 과의 의사를 병렬로 수집
            sem = asyncio.Semaphore(6)

            async def bounded_doctors(dept):
                async with sem:
                    return await self._fetch_doctors_of_dept(client, dept)

            all_docs_nested = await asyncio.gather(
                *[bounded_doctors(d) for d in depts]
            )

            # empNo 단위로 중복 제거 (동일 의사가 여러 과에 속할 수 있음)
            seen: set[str] = set()
            doctors: list[dict] = []
            for docs in all_docs_nested:
                for d in docs:
                    if d["_empNo"] in seen:
                        continue
                    seen.add(d["_empNo"])
                    doctors.append(d)

            logger.info(f"[YONGIN] 의료진 {len(doctors)}명 (view 조회 중...)")

            # 각 의사 view 페이지 병렬 조회
            async def bounded_view(d):
                async with sem:
                    return d, await self._fetch_doctor_view(client, d["_empNo"], d["_deptSeq"])

            view_results = await asyncio.gather(*[bounded_view(d) for d in doctors])

        final: list[dict] = []
        for d, view in view_results:
            empNo = d["_empNo"]
            schedules = view.get("schedules", [])
            short = _short_id(empNo)
            external_id = f"{self.hospital_code}-{d['_deptSeq']}-{short}"
            notes = "" if schedules else "※ 홈페이지에 진료시간표가 게시되어 있지 않습니다. 외래 가능 시간은 병원에 직접 문의해 주세요."
            final.append({
                "staff_id": external_id,
                "external_id": external_id,
                "_empNo": empNo,
                "_deptSeq": d["_deptSeq"],
                "name": view.get("name") or d["name"],
                "department": view.get("department") or d["department"],
                "position": d["position"],
                "specialty": d["specialty"],
                "profile_url": f"{DOCTOR_VIEW_URL}?empNo={empNo}&deptSeq={d['_deptSeq']}",
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
            })

        self._cached_data = final
        return final

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        depts = sorted({d["department"] for d in data if d["department"]})
        return [{"code": dn, "name": dn} for dn in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if department in d["department"]]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — 해당 과 doctor-list 한 번 + view 한 번.

        external_id 에서 deptSeq 를 복원 → 그 과의 의사 목록만 조회 → empNo 매칭.
        view 는 1명분만 호출한다.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {
                        "staff_id": staff_id, "name": d["name"], "department": d["department"],
                        "position": d["position"], "specialty": d["specialty"],
                        "profile_url": d["profile_url"], "notes": d["notes"],
                        "schedules": d["schedules"], "date_schedules": d["date_schedules"],
                    }

        prefix = f"{self.hospital_code}-"
        if not staff_id.startswith(prefix):
            return empty
        rest = staff_id[len(prefix):]
        parts = rest.split("-", 1)
        if len(parts) != 2:
            return empty
        dept_seq_str, short = parts
        if not dept_seq_str.isdigit():
            return empty
        dept_seq = int(dept_seq_str)

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            # 그 과가 어떤 tyCode/seCode 인지 몰라도 doctor-list 는 seq 만으로 동작한다.
            # tyCode 는 필수지만 어느 값이든 seq 에 해당하는 결과를 반환한다 (내부적으로 seq 가 unique key).
            # 3 가지 tyCode 조합을 순차 시도.
            found = None
            for ty, se in TY_CODES:
                dept = {"seq": dept_seq, "name": "", "tyCode": ty, "seCode": se}
                docs = await self._fetch_doctors_of_dept(client, dept)
                for d in docs:
                    if _short_id(d["_empNo"]) == short:
                        found = d
                        break
                if found:
                    break
            if not found:
                return empty

            view = await self._fetch_doctor_view(client, found["_empNo"], dept_seq)

        schedules = view.get("schedules", [])
        notes = "" if schedules else "※ 홈페이지에 진료시간표가 게시되어 있지 않습니다. 외래 가능 시간은 병원에 직접 문의해 주세요."
        return {
            "staff_id": staff_id,
            "name": view.get("name") or found["name"],
            "department": view.get("department") or found["department"],
            "position": found["position"],
            "specialty": found["specialty"],
            "profile_url": f"{DOCTOR_VIEW_URL}?empNo={found['_empNo']}&deptSeq={dept_seq}",
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if department in d["department"]]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
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
